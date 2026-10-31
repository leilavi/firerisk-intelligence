"""Draft of 'which panel supplies which life-safety equipment', from the local OCR of the drawings. ORIGIN: NEW (2026-10-31).

Runs ON THE AUTHOR'S COMPUTER only (data owner's condition 2). Input: data/private/drawings/ocr/*.json written by
scripts/ocr_drawings.py. Output: data/private/drawings/power_links_draft.xlsx with three sheets:
  * Links   one row per (floor, panel, equipment type) the OCR suggests. Every row starts NOT confirmed.
  * Panels  every panel label read on the drawings, its floor guess, OCR confidence and a suggested asset_id.
  * Assets  the asset register codes and names (to fill asset_id).
The author checks each row against the drawing (the page is given), corrects it, writes Y in "confirmed" and saves
the file as data/private/drawings/power_links.xlsx. The app uses ONLY confirmed rows of that file.

How the draft is made (all guesses are labelled in the "basis" column; nothing is used before a person confirms):
  * floor of a page: the floor named most often on that page; when two floors are named about equally often
    (a riser diagram or a legend page) the floor is left empty ("?") instead of guessed;
  * emergency lights / exit signs: SHORT labels next to a symbol (e.g. "EXIT", "EM"); long phrases are taken as legend
    or notes and NOT counted. A symbol drawn without a text label is not seen by OCR, so counts can be too low;
  * panel of a symbol: the nearest panel label within a small distance on the same page; if none, and the page
    names exactly one panel, that panel with a weaker basis; otherwise empty (to fill in);
  * fire pump / smoke control / fire alarm on the electrical drawing: the nearest panel label, same rule.
The console prints numbers only. The xlsx stays in the private, git-ignored folder.

Usage: run_draft_power_links.bat   (or: python scripts/draft_power_links.py [drawings folder])
"""

from __future__ import annotations

import importlib.util
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DEFAULT_DIR = ROOT / "data" / "private" / "drawings"
NEAR = 0.06              # "near" = within 6 % of the page diagonal
SHORT = 10               # a symbol label has at most this many characters; longer text = legend / note
FLOOR_SHARE = 0.6        # a page gets a floor only if that floor has >= 60 % of the floor mentions on the page


def _probe():
    spec = importlib.util.spec_from_file_location("probe", Path(__file__).with_name("probe_drawings.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


P = _probe()
fold = P.fold
PANEL_RX = re.compile(r"\b(MSB|MDB|SMDB|SDB|EMDB|EDB|DB|ELP|LP|EP|PP|ATS|MCC|CP)(?:[-_.]?[A-Z0-9]{1,6}){0,3}\b")
DEVICE_RX = {"exit_sign": re.compile(P.CATEGORIES["exit_sign"]), "emergency_light": re.compile(P.CATEGORIES["emergency_light"])}
FIRE_RX = {"fire_pump": re.compile(r"bom\s*chua\s*chay|fire\s*pump|\bfp\b|\bjockey"),
           "smoke_control": re.compile(r"hut\s*khoi|tang\s*ap|smoke|\beaf\d*\b|\bsef\d*\b|\bpaf\d*\b|\bspf\d*\b"),
           "fire_alarm": re.compile(r"bao\s*chay|fire\s*alarm|\bfacp\b|\bfac\b")}
FLOOR_TOKEN = [("B1", re.compile(r"(?:^|[-_.\s])(B1|H1|HAM)(?:$|[-_.\s])")),
               ("Roof", re.compile(r"(?:^|[-_.\s])(R|RF|MAI|TUM|ROOF)(?:$|[-_.\s])"))] + [
              (f"F{n}", re.compile(rf"(?:^|[-_.\s])(?:F|T|L|TANG){n}(?:$|[-_.\s])")) for n in range(1, 5)]
FLOORS = ["B1", "F1", "F2", "F3", "F4", "Roof"]
# Floor NAMES as written in drawing titles (not short codes: "L1" is usually a lighting circuit, not floor 1).
PAGE_FLOOR_RX = {"B1": re.compile(r"tang\s*ham|\bham\b|basement"),
                 "F1": re.compile(r"tang\s*1\b|tang\s*tret|\btret\b|ground\s*floor|1st\s*floor|floor\s*1\b|level\s*1\b"),
                 "F2": re.compile(r"tang\s*2\b|2nd\s*floor|floor\s*2\b|level\s*2\b"),
                 "F3": re.compile(r"tang\s*3\b|3rd\s*floor|floor\s*3\b|level\s*3\b"),
                 "F4": re.compile(r"tang\s*4\b|4th\s*floor|floor\s*4\b|level\s*4\b"),
                 "Roof": re.compile(r"tang\s*mai|\bmai\b|roof|tang\s*tum|\btum\b")}
CIRCUIT_RX = re.compile(P.CATEGORIES["circuit_label"])


def panel_label(text: str) -> str | None:
    m = PANEL_RX.search(fold(text).upper())
    return m.group(0) if m else None


def device_type(text: str) -> str | None:
    t = fold(text).strip()
    if len(t) > SHORT:
        return None
    for k, rx in DEVICE_RX.items():
        if rx.search(t):
            return k
    return None


def fire_type(text: str) -> str | None:
    t = fold(text)
    return next((k for k, rx in FIRE_RX.items() if rx.search(t)), None)


def floor_of_label(label: str) -> str | None:
    hits = [f for f, rx in FLOOR_TOKEN if rx.search(label.upper().replace(" ", "-"))]
    return hits[0] if len(hits) == 1 else None


def page_floor(texts: list[dict]) -> str | None:
    """Floor named most often on the page in words (titles, notes). Panel and circuit labels do not vote."""
    votes = Counter()
    for t in texts:
        if panel_label(t["text"]) or CIRCUIT_RX.search(fold(t["text"]).strip()):
            continue
        ft = fold(t["text"])
        for f, rx in PAGE_FLOOR_RX.items():
            if rx.search(ft):
                votes[f] += 1
    if not votes:
        return None
    (top, n), total = votes.most_common(1)[0], sum(votes.values())
    return top if n / total >= FLOOR_SHARE else None


def centre(t: dict) -> tuple[float, float]:
    b = t["box"]
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def nearest(t: dict, cands: list[dict], limit: float) -> dict | None:
    x, y = centre(t)
    best, bd = None, limit
    for c in cands:
        cx, cy = centre(c)
        d = math.hypot(cx - x, cy - y)
        if d <= bd:
            best, bd = c, d
    return best


def draft(ocr_files: list[Path], assets: dict[str, str], symbols: dict | None = None) -> tuple[list[dict], list[dict], dict]:
    """`symbols`: ocr/symbols.json (scripts/detect_symbols.py). Where the legend symbol of a device type was found,
    that type is counted from the symbols on the drawing instead of from text labels."""
    symbols = symbols or {}
    rows: dict[tuple, dict] = {}
    panels: dict[str, dict] = {}
    stats = Counter()
    for f in ocr_files:
        data = json.loads(f.read_text(encoding="utf-8"))
        kind = P.classify_name(data.get("file", f.name))
        for page in data["pages"]:
            texts = page["texts"]
            w, h = page["size"]
            limit = NEAR * math.hypot(w, h)
            floor = page_floor(texts)
            stats["pages"] += 1
            stats["pages_without_floor"] += floor is None
            plabels = []
            for t in texts:
                lab = panel_label(t["text"])
                if lab:
                    t = {**t, "panel": lab}
                    plabels.append(t)
                    p = panels.setdefault(lab, {"label": lab, "floors": Counter(), "pages": set(), "mentions": 0,
                                                "best_score": 0.0, "kinds": set()})
                    p["mentions"] += 1
                    p["best_score"] = max(p["best_score"], t["score"])
                    p["pages"].add(f"{kind} p{page['page']}")
                    p["kinds"].add(kind)
                    fl = floor_of_label(lab) or floor
                    if fl:
                        p["floors"][fl] += 1
            only_panel = plabels[0]["panel"] if len({p["panel"] for p in plabels}) == 1 else None
            circuits = [t for t in texts if CIRCUIT_RX.search(fold(t["text"]).strip()) and not panel_label(t["text"])]
            sym_file = symbols.get(f.stem) or {}
            sym_page = next((pg["symbols"] for pg in sym_file.get("pages", []) if pg["page"] == page["page"]), {})
            from_symbols = {k for k in ("emergency_light",) if k in (sym_file.get("templates") or {})}
            devices = []
            for t in texts:
                typ = device_type(t["text"]) if kind != "cable_routing_msb" else None
                typ = typ or fire_type(t["text"])
                if not typ:
                    if fold(t["text"]) and any(rx.search(fold(t["text"])) for rx in DEVICE_RX.values()):
                        stats["legend_or_note_skipped"] += 1
                    continue
                if typ in from_symbols:
                    continue                       # counted from the drawn symbols below, not twice
                devices.append((t, typ, "label"))
            for typ in from_symbols:
                devices += [({"text": "", "score": s["score"], "box": s["box"]}, typ, "symbol") for s in sym_page.get(typ, [])]
            if "exit_sign" in sym_page:            # cross-check: EXIT text labels vs EXIT symbols on this page
                n_txt = sum(1 for _, ty, _ in devices if ty == "exit_sign")
                if abs(n_txt - len(sym_page["exit_sign"])) > max(1, 0.2 * max(n_txt, 1)):
                    stats["pages_exit_text_vs_symbol_differ"] += 1
            for t, typ, how in devices:
                stats[f"{'symbols' if how == 'symbol' else 'labels'}_{typ}"] += 1
                near = nearest(t, plabels, limit)
                if near:
                    panel, basis = near["panel"], "panel label next to the symbol"
                elif only_panel:
                    panel, basis = only_panel, "only panel label on this page (weaker)"
                else:
                    panel, basis = "", "no panel label near the symbol - fill in from the drawing"
                stats["linked_near" if near else "linked_page_only" if only_panel else "not_linked"] += 1
                key = (floor or "?", panel, typ)
                r = rows.setdefault(key, {"floor": floor or "", "panel_label": panel, "feeds": typ, "count": 0,
                                          "pages": set(), "bases": Counter(), "scores": [], "circuits": set(),
                                          "how": set()})
                r["how"].add(how)
                r["count"] += 1
                r["pages"].add(f"{kind} p{page['page']}")
                r["bases"][basis] += 1
                r["scores"].append(t["score"])
                c = nearest(t, circuits, limit)
                if c:
                    r["circuits"].add(c["text"].strip())
    links = []
    for (_, panel, typ), r in sorted(rows.items(), key=lambda kv: (FLOORS.index(kv[0][0]) if kv[0][0] in FLOORS else 9, kv[0][1], kv[0][2])):
        asset, _ = suggest_asset(panel, assets) if panel else ("", "")
        links.append({"confirmed": "", "floor": r["floor"], "panel_label": panel, "asset_id": asset, "feeds": typ,
                      "count": "", "auto_count_hint": r["count"], "fed_panel_label": "", "circuits": ", ".join(sorted(r["circuits"]))[:200], "source": ", ".join(sorted(r["pages"])),
                      "basis": "; ".join(f"{b} ({n})" for b, n in r["bases"].most_common())
                               + ("" if r["floor"] else "; floor not clear on this page - fill in")
                               + ("; count = legend symbols found on the drawing (check symbols_review.html)"
                                  if r["how"] == {"symbol"} else
                                  "; count = text labels read by OCR, symbols without a label are missed"),
                      "ocr_confidence": round(min(r["scores"]), 2), "note": ""})
    panel_rows = []
    for lab, p in sorted(panels.items()):
        asset, why = suggest_asset(lab, assets)
        fl = p["floors"].most_common(1)[0][0] if p["floors"] else ""
        panel_rows.append({"panel_label": lab, "floor_guess": fl, "mentions": p["mentions"],
                           "ocr_confidence": round(p["best_score"], 2), "pages": ", ".join(sorted(p["pages"])),
                           "suggested_asset_id": asset, "suggestion_basis": why})
    stats["link_rows"] = len(links)
    stats["panels"] = len(panel_rows)
    stats["panels_with_asset_suggestion"] = sum(1 for p in panel_rows if p["suggested_asset_id"])
    return links, panel_rows, dict(stats)


def suggest_asset(label: str, assets: dict[str, str]) -> tuple[str, str]:
    """An asset whose name or code contains the panel label (spaces and separators ignored). Only an unambiguous
    match is suggested."""
    key = re.sub(r"[^A-Z0-9]", "", label.upper())
    if len(key) < 3:
        return "", ""
    hits = [a for a, name in assets.items() if key in re.sub(r"[^A-Z0-9]", "", fold(f"{a} {name}").upper())]
    if len(hits) == 1:
        return hits[0], "panel label appears in the asset name or code"
    return "", (f"{len(hits)} assets match - choose one" if hits else "")


def load_assets() -> dict[str, str]:
    from firerisk.config import ASSETS
    out = {k: v.get("name") or "" for k, v in ASSETS.items()}
    try:
        from firerisk.engine import load_manifest
        from firerisk.sources.register import load_asset_register
        snap = ROOT / "data" / "private" / "snapshot"
        meta = load_manifest(snap).get("files", {}).get("ops_data", {})
        reg, _, _ = load_asset_register(snap / meta.get("local_file", "ops_data.xlsx"), "ops")
        for k, v in reg.items():
            out.setdefault(k, " ".join(filter(None, [v.get("name"), v.get("notes"), v.get("area"), v.get("floor")])))
    except Exception:
        pass
    return out


def write_xlsx(path: Path, links: list[dict], panels: list[dict], assets: dict[str, str]) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    from firerisk.power_links import COLUMNS, FEEDS
    wb = Workbook()
    ws = wb.active
    ws.title = "Links"
    ws.append(COLUMNS)
    low = PatternFill("solid", fgColor="FFF2CC")
    for r in links:
        ws.append([r.get(c, "") for c in COLUMNS])
        if not r["panel_label"] or not r["floor"] or r["ocr_confidence"] < 0.8 or "weaker" in r["basis"]:
            for cell in ws[ws.max_row]:
                cell.fill = low
    for c in ws[1]:
        c.font = Font(bold=True)
    n = max(ws.max_row + 50, 200)
    for col, values in (("A", "Y,N"), ("B", "B1,F1,F2,F3,F4,Roof,Building"), ("E", ",".join(FEEDS))):   # by COLUMNS order
        dv = DataValidation(type="list", formula1=f'"{values}"', allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"{col}2:{col}{n}")
    for col, wdt in zip("ABCDEFGHIJKLM", (10, 8, 16, 16, 16, 7, 12, 16, 12, 30, 60, 10, 30)):
        ws.column_dimensions[col].width = wdt
    ws.freeze_panes = "A2"
    wp = wb.create_sheet("Panels")
    cols = ["panel_label", "floor_guess", "mentions", "ocr_confidence", "pages", "suggested_asset_id", "suggestion_basis"]
    wp.append(cols)
    for p in panels:
        wp.append([p[c] for c in cols])
    wa = wb.create_sheet("Assets")
    wa.append(["asset_id", "name"])
    for k, v in sorted(assets.items()):
        wa.append([k, v])
    wh = wb.create_sheet("How to check")
    for line in [
        "1. For each row in Links, open the page named in 'source' (review.html shows what OCR read).",
        "2. Correct floor, panel_label and feeds. Fill asset_id from the Assets sheet (once per panel is enough).",
        "   'count' starts EMPTY on purpose: the automatic count ('auto_count_hint') misses symbols on scanned drawings.",
        "   Write the count from the drawing, or leave it empty - the app then says 'number not recorded'.",
        "3. Downstream panels: add a row feeds = sub_panel with fed_panel_label = the panel it supplies.",
        "4. Write Y in 'confirmed' only when the row matches the drawing. Rows without Y are ignored by the app.",
        "5. Yellow rows need most attention: no panel or floor found, low OCR confidence, or a weak guess.",
        "6. Save as data/private/drawings/power_links.xlsx (keep the sheet name 'Links').",
        "Only floor, equipment type and count ever leave this computer (to Meta Muse Spark); labels and circuits never do.",
    ]:
        wh.append([line])
    wh.column_dimensions["A"].width = 120
    wb.save(path)


def main(argv: list[str]) -> int:
    folder = Path(argv[1]) if len(argv) > 1 else DEFAULT_DIR
    files = sorted(f for f in (folder / "ocr").glob("*.json") if f.name != "symbols.json")
    if not files:
        print(f"No OCR results in {folder / 'ocr'}. Run run_drawing_ocr.bat first.")
        return 1
    assets = load_assets()
    sym_path = folder / "ocr" / "symbols.json"
    newest_input = max([f.stat().st_mtime for f in files] + [Path(__file__).with_name("detect_symbols.py").stat().st_mtime])
    if not sym_path.exists() or sym_path.stat().st_mtime < newest_input:     # new OCR or a newer symbol search
        print("Finding the legend symbols on the drawings (local, a few minutes) ...", flush=True)
        try:
            spec = importlib.util.spec_from_file_location("sym", Path(__file__).with_name("detect_symbols.py"))
            sym = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(sym)
            _, sstats = sym.process(folder)
            for k, v in sstats.items():
                print(f"  symbols {k}: {v}")
        except Exception as exc:              # OpenCV missing or a page unreadable: draft from text only
            print(f"  symbol search not done ({type(exc).__name__}); counts come from text labels only")
    symbols = json.loads(sym_path.read_text(encoding="utf-8")) if sym_path.exists() else {}
    links, panels, stats = draft(files, assets, symbols)
    out = folder / "power_links_draft.xlsx"
    write_xlsx(out, links, panels, assets)
    print("--- Summary (numbers only, safe to paste in the chat) ---")
    for k in sorted(stats):
        print(f"  {k}: {stats[k]}")
    print(f"  assets_in_register: {len(assets)}")
    print(f"\nDraft (private): {out}")
    print("Check it, write Y in 'confirmed', save as power_links.xlsx in the same folder.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
