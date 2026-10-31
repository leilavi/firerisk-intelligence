"""Find drawn symbols (no text) on the scanned drawings, using the drawing's own legend. ORIGIN: NEW (2026-10-31).

Runs ON THE AUTHOR'S COMPUTER only (data owner's condition 2): OpenCV template matching, no AI, no network.

Why: on these drawings an emergency light and a main panel are drawn as symbols WITHOUT a text label, so OCR cannot
count them. Every drawing carries a legend ("GHI CHU") that shows each symbol next to its name. This script
  1. finds the legend line by its OCR text (e.g. "DEN CHIEU SANG SU CO") and cuts the symbol drawn to its left,
  2. checks that the cut-out looks like a symbol (size, amount of ink) - otherwise the symbol is reported as not found,
  3. searches every page of the same drawing for that symbol (4 rotations, small scale range), keeps matches above a
     threshold, removes overlaps and anything inside the legend,
  4. writes the matches to ocr/symbols.json and a review page ocr/symbols_review.html with a box on every match,
     so the author can see what was counted before confirming anything.
The console prints counts only.

Limits stated openly: a symbol drawn much smaller/larger than in the legend, overlapped by lines or text, or very
faint in the scan can be missed; a similar-looking shape can be counted. The review page is the check.
"""

from __future__ import annotations

import html
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data" / "private" / "drawings"

# legend wording (diacritics removed, lower case) -> equipment type used in power_links
LEGEND = {"emergency_light": ["chieu sang su co", "den su co", "emergency light"],
          "exit_sign": ["den thoat hiem", "exit sign"],
          "main_panel": ["tu dien chinh", "main switchboard", "main panel"]}
THRESHOLD = 0.72          # normalised correlation needed for a match
SCALES = (0.85, 0.92, 1.0, 1.08, 1.17)
MIN_INK, MAX_INK = 0.02, 0.6   # share of dark pixels a symbol cut-out must have
MAX_SIDE = 5000           # pages are searched at most this many pixels wide/high (speed); boxes scaled back


def _probe():
    spec = importlib.util.spec_from_file_location("probe", Path(__file__).with_name("probe_drawings.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


fold = _probe().fold


def _collapse(s: str) -> str:
    return "".join(ch for ch in fold(s) if ch.isalnum())


def text_lines(texts: list[dict]) -> list[dict]:
    """OCR words on the same line merged left to right (a legend name is often read as 2-3 pieces)."""
    items = sorted((t for t in texts if not t.get("rotated")), key=lambda t: (t["box"][1], t["box"][0]))
    lines: list[dict] = []
    for t in items:
        x1, y1, x2, y2 = t["box"]
        h = max(1, y2 - y1)
        for ln in lines:
            lx1, ly1, lx2, ly2 = ln["box"]
            if abs((y1 + y2) / 2 - (ly1 + ly2) / 2) < 0.6 * h and 0 <= x1 - lx2 < 2.5 * h:
                ln["text"] += " " + t["text"]
                ln["box"] = [lx1, min(ly1, y1), x2, max(ly2, y2)]
                break
        else:
            lines.append({"text": t["text"], "box": list(t["box"])})
    return lines


def legend_lines(texts: list[dict]) -> dict[str, dict]:
    """The legend line of each symbol: matched on letters only (no spaces or accents), on single OCR words and on
    words merged into lines, tolerant to one or two misread letters."""
    from difflib import SequenceMatcher
    out = {}
    cands = list(texts) + text_lines(texts)
    for kind, words in LEGEND.items():
        best, best_r = None, 0.0
        for t in cands:
            c = _collapse(t["text"])
            if not c or len(c) > 45:
                continue
            for w in words:
                wc = _collapse(w)
                if wc in c:
                    r = 1.0
                else:
                    r = max((SequenceMatcher(None, wc, c[i:i + len(wc)]).ratio()
                             for i in range(0, max(1, len(c) - len(wc) + 1))), default=0.0)
                # the name should be most of the text (a legend line, not a sentence that mentions it)
                if r >= 0.85 and len(wc) / len(c) >= 0.5 and (r, -len(c)) > (best_r, -len(_collapse(best["text"])) if best else 0):
                    best, best_r = t, r
        if best:
            out[kind] = best
    return out


def cut_symbol(gray, text_box: list[int]):
    """The symbol to the LEFT of the legend text, tightened to its ink. Returns (template, box) or (None, reason)."""
    import numpy as np
    x1, y1, x2, y2 = text_box
    h = max(8, y2 - y1)
    rx1, rx2 = max(0, int(x1 - 8 * h)), max(0, int(x1 - 0.4 * h))
    ry1, ry2 = max(0, int(y1 - 0.8 * h)), min(gray.shape[0], int(y2 + 0.8 * h))
    if rx2 - rx1 < 5:
        return None, "no room left of the legend text"
    region = gray[ry1:ry2, rx1:rx2]
    import cv2
    level, _ = cv2.threshold(region, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    level = min(max(level, 60), 200)
    ink = region < level
    cols = np.where(ink.any(axis=0))[0]
    rows = np.where(ink.any(axis=1))[0]
    if len(cols) == 0:
        return None, "no ink left of the legend text"
    # the symbol is the right-most group of ink columns (gaps wider than 0.6 h separate groups, e.g. a frame line)
    gap = max(3, int(0.6 * h))
    groups, start = [], cols[0]
    for a, b in zip(cols, cols[1:]):
        if b - a > gap:
            groups.append((start, a))
            start = b
    groups.append((start, cols[-1]))
    c1, c2 = groups[-1]
    sub = ink[:, c1:c2 + 1]
    rows = np.where(sub.any(axis=1))[0]
    r1, r2 = rows[0], rows[-1]
    tpl = region[r1:r2 + 1, c1:c2 + 1]
    th, tw = tpl.shape
    share = float((tpl < level).mean())
    if th < 8 or tw < 8:
        return None, "cut-out too small"
    if not (MIN_INK <= share <= MAX_INK):
        return None, f"cut-out does not look like a symbol (ink {share:.2f})"
    return tpl, [int(rx1 + c1), int(ry1 + r1), int(rx1 + c2 + 1), int(ry1 + r2 + 1)]


def _nms(boxes: list[tuple], iou: float = 0.3) -> list[tuple]:
    keep = []
    for b in sorted(boxes, key=lambda x: -x[4]):
        if all(_iou(b, k) < iou for k in keep):
            keep.append(b)
    return keep


def _iou(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u else 0.0


def find(gray, tpl, exclude: list[list[int]]) -> list[dict]:
    import cv2
    import numpy as np
    hits = []
    for rot in range(4):
        t = np.rot90(tpl, rot) if rot else tpl
        for s in SCALES:
            ts = cv2.resize(t, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s != 1.0 else t
            th, tw = ts.shape
            if th >= gray.shape[0] or tw >= gray.shape[1]:
                continue
            res = cv2.matchTemplate(gray, ts, cv2.TM_CCOEFF_NORMED)
            # local maxima only (one candidate per symbol, not every pixel around it)
            k = np.ones((max(3, th // 2), max(3, tw // 2)), np.uint8)
            peaks = (res >= THRESHOLD) & (res >= cv2.dilate(res, k))
            ys, xs = np.where(peaks)
            for y, x in zip(ys, xs):
                hits.append((int(x), int(y), int(x + tw), int(y + th), float(res[y, x])))
    hits = _nms(hits)
    out = []
    for b in hits:
        if any(_iou(b, e) > 0 or (e[0] <= (b[0] + b[2]) / 2 <= e[2] and e[1] <= (b[1] + b[3]) / 2 <= e[3]) for e in exclude):
            continue
        out.append({"box": list(b[:4]), "score": round(b[4], 3)})
    return out


def legend_area(lines: dict[str, dict], sym_boxes: list[list[int]]) -> list[int] | None:
    """One rectangle around the legend (texts and their cut symbols), padded, so legend symbols are not counted."""
    boxes = [t["box"] for t in lines.values()] + sym_boxes
    if not boxes:
        return None
    x1, y1 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x2, y2 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    pad = max(20, int(0.15 * (y2 - y1)))
    return [x1 - pad, y1 - pad, x2 + pad, y2 + pad]


def _load(path: Path):
    """Grayscale page, shrunk to MAX_SIDE; returns (image, factor). Read via numpy so any Windows path works."""
    import cv2
    import numpy as np
    try:
        img = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    except (OSError, ValueError):
        img = None
    if img is None:
        return None, 1.0
    f = min(1.0, MAX_SIDE / max(img.shape))
    if f < 1.0:
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    return cv2.medianBlur(img, 3), f          # scan speckle removed before cutting and matching


def process(folder: Path) -> tuple[dict, dict]:
    import cv2
    ocr = folder / "ocr"
    results, stats = {}, {}
    for jf in sorted(ocr.glob("*.json")):
        if jf.name == "symbols.json":
            continue
        data = json.loads(jf.read_text(encoding="utf-8"))
        pages = data["pages"]
        # templates: from the first page whose legend shows the symbol
        templates, notes = {}, {}
        legend_by_page = {}
        diag = {"pages": len(pages), "pages_read": 0, "legend_lines_matched": 0,
                "texts_mentioning_su_co": 0, "texts_mentioning_thoat_hiem": 0}
        for p in pages:
            for t in p["texts"]:
                c = _collapse(t["text"])
                diag["texts_mentioning_su_co"] += "suco" in c
                diag["texts_mentioning_thoat_hiem"] += "thoathiem" in c
            img, f = _load(ocr / p["image"])
            if img is None:
                continue
            diag["pages_read"] += 1
            lines = {k: {**t, "box": [int(v * f) for v in t["box"]]} for k, t in legend_lines(p["texts"]).items()}
            diag["legend_lines_matched"] += len(lines)
            cut_boxes = []
            for kind, t in lines.items():
                tpl, box = cut_symbol(img, t["box"])
                if tpl is None:
                    notes.setdefault(kind, box)
                    continue
                cut_boxes.append(box)
                templates.setdefault(kind, (tpl, f))      # with the scale of the page it was cut from
            legend_by_page[p["page"]] = legend_area(lines, cut_boxes)
        file_res = {"file": data.get("file"), "templates": {k: list(v[0].shape) for k, v in templates.items()},
                    "not_found": {k: notes[k] for k in notes if k not in templates}, "pages": []}
        for p in pages:
            img, f = _load(ocr / p["image"])
            if img is None:
                continue
            excl = [legend_by_page[p["page"]]] if legend_by_page.get(p["page"]) else []
            found = {}
            for kind, (tpl, f0) in templates.items():
                t2 = tpl if abs(f - f0) < 1e-6 else cv2.resize(tpl, None, fx=f / f0, fy=f / f0, interpolation=cv2.INTER_AREA)
                found[kind] = [{**s, "box": [int(v / f) for v in s["box"]]} for s in find(img, t2, excl)]
            file_res["pages"].append({"page": p["page"], "image": p["image"], "size": p["size"], "symbols": found})
        results[jf.stem] = file_res
        kind = _probe().classify_name(data.get("file", jf.name))
        stats[kind] = {"templates_found": sorted(templates), "templates_missing": sorted(file_res["not_found"]), **diag,
                       **{f"count_{k}": sum(len(pg["symbols"].get(k, [])) for pg in file_res["pages"]) for k in templates}}
    (ocr / "symbols.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    review(ocr, results)
    return results, stats


COLORS = {"emergency_light": "#f59e0b", "exit_sign": "#22c55e", "main_panel": "#ef4444"}


def review(ocr: Path, results: dict) -> None:
    parts = []
    for r in results.values():
        for p in r["pages"]:
            rects = "".join(f'<rect x="{s["box"][0]}" y="{s["box"][1]}" width="{s["box"][2] - s["box"][0]}" '
                            f'height="{s["box"][3] - s["box"][1]}" stroke="{COLORS.get(k, "#0ea5e9")}"><title>{k} '
                            f'{s["score"]}</title></rect>' for k, lst in p["symbols"].items() for s in lst)
            counts = ", ".join(f"{k}: {len(v)}" for k, v in p["symbols"].items())
            parts.append(f'<h2>{html.escape(r["file"] or "")} - page {p["page"]} ({html.escape(counts)})</h2><div class="w">'
                         f'<img src="{html.escape(p["image"])}"><svg viewBox="0 0 {p["size"][0]} {p["size"][1]}" '
                         f'preserveAspectRatio="none">{rects}</svg></div>')
    (ocr / "symbols_review.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Symbol review - PRIVATE</title><style>body{font:13px sans-serif;'
        'margin:16px;background:#111;color:#eee}.w{position:relative;margin-bottom:24px}img{width:100%;display:block;'
        'background:#fff}svg{position:absolute;inset:0;width:100%;height:100%}rect{fill:none;stroke-width:3;'
        'vector-effect:non-scaling-stroke}</style><h1>Symbols found from the legend - PRIVATE, stays on this computer</h1>'
        '<p>Orange = emergency light, green = exit sign, red = main panel. Check that every symbol on the drawing has a box '
        'and that no box is on something else.</p>' + "".join(parts), encoding="utf-8")


def main(argv: list[str]) -> int:
    folder = Path(argv[1]) if len(argv) > 1 else DEFAULT_DIR
    if not list((folder / "ocr").glob("*.json")):
        print("No OCR results. Run run_drawing_ocr.bat first.")
        return 1
    _, stats = process(folder)
    print("--- Symbols (numbers only) ---")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
