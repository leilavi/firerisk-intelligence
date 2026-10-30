"""Probe the building's technical drawings ON THIS COMPUTER and print counts only. ORIGIN: NEW (2026-10-30).

Data owner's condition 2: original technical drawings stay on the author's computer and are processed there only.
This script reads the PDFs with pdfplumber (plain code, no AI, no network) and prints how the files are built, so the
real extractor can be designed without the drawings ever leaving the computer:
  * pages, and per page whether it has a text layer (exported from CAD) or is only an image (scan);
  * how many line / rectangle / curve objects it has (drawing-like page vs text page);
  * how many words match generic categories (emergency light, exit sign, panel, fire equipment, circuit label, floor).
It prints and saves NUMBERS ONLY - no words, labels, coordinates or dimensions from the drawings - so the summary can
be shared in the chat. The full per-page counts are saved next to the drawings in data/private/drawings/probe.json.

Usage:
  put the PDFs into data/private/drawings/   (git-ignored; copy them from Drive by hand)
  run_drawing_probe.bat                       (or: python scripts/probe_drawings.py [folder])
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data" / "private" / "drawings"

# Generic categories (English and Vietnamese, matched after removing diacritics). Counts only are reported.
CATEGORIES = {
    "emergency_light": r"\bem\b|emergency|den\s*su\s*co|chieu\s*sang\s*su\s*co",
    "exit_sign": r"\bexit\b|loi\s*thoat|den\s*thoat\s*hiem|thoat\s*hiem",
    "panel": r"\bmsb\b|\bmdb\b|\bsdb\b|\bdb[-_ ]?\w*|\bats\b|tu\s*dien|tu\s*phan\s*phoi",
    "fire_equipment": r"\bfhc\b|hose|extinguisher|sprinkler|\bfa\b|alarm|binh\s*chua\s*chay|hong\s*nuoc|bao\s*chay|chua\s*chay",
    "circuit_label": r"^[a-z]{1,3}\d{0,2}[-_.]?\d{1,3}$",
    "cable_spec": r"\d+\s*(x|\*)\s*\d+(\.\d+)?\s*mm|\bcu/|\bxlpe\b|\bpvc\b|\bcxv\b|\bcvv\b",
    "dimension": r"^\d{3,6}$|\d+\s*(mm|m)\b",
}
FLOORS = {"B1": r"\bb1\b|ham|basement", "F1": r"\bf1\b|\bl1\b|tang\s*1\b|1st|ground",
          "F2": r"\bf2\b|\bl2\b|tang\s*2\b|2nd", "F3": r"\bf3\b|\bl3\b|tang\s*3\b|3rd",
          "F4": r"\bf4\b|\bl4\b|tang\s*4\b|4th", "Roof": r"\broof\b|\bmai\b|\btum\b"}


def fold(s: str) -> str:
    s = unicodedata.normalize("NFD", s.replace("Đ", "D").replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def count_matches(words: list[str], patterns: dict[str, str]) -> dict[str, int]:
    folded = [fold(w) for w in words]
    joined = " ".join(folded)
    out = {}
    for k, p in patterns.items():
        rx = re.compile(p)
        out[k] = sum(1 for w in folded if rx.search(w)) if p.startswith("^") else len(rx.findall(joined))
    return out


def probe_pdf(path: Path) -> dict:
    import pdfplumber
    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = [w["text"] for w in page.extract_words(keep_blank_chars=False)]
            n_lines, n_rects, n_curves, n_images = len(page.lines), len(page.rects), len(page.curves), len(page.images)
            kind = ("scan_image" if not words and n_images else
                    "drawing" if (n_lines + n_rects + n_curves) > 200 and len(words) < 1500 else
                    "text" if words else "empty")
            pages.append({"page": page.page_number, "kind": kind, "words": len(words), "lines": n_lines,
                          "rects": n_rects, "curves": n_curves, "images": n_images,
                          "size_pt": [round(float(page.width)), round(float(page.height))],
                          "categories": count_matches(words, CATEGORIES), "floors": count_matches(words, FLOORS)})
    total = lambda key: {k: sum(p[key][k] for p in pages) for k in (CATEGORIES if key == "categories" else FLOORS)}
    kinds = {}
    for p in pages:
        kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
    return {"file_kind": classify_name(path.name), "pages": len(pages), "page_kinds": kinds,
            "words": sum(p["words"] for p in pages), "categories": total("categories"), "floors": total("floors"),
            "per_page": pages}


def classify_name(name: str) -> str:
    n = fold(name)
    if "lighting" in n or "exit" in n:
        return "exit_emergency_lighting"
    if "cable" in n or "msb" in n:
        return "cable_routing_msb"
    if "manual" in n or "o&m" in n:
        return "om_manual"
    return "other"


def summary_lines(results: dict[str, dict]) -> list[str]:
    """Numbers only, no file content. File names are replaced by their kind (A, B, C ...)."""
    lines = []
    for i, (_, r) in enumerate(sorted(results.items())):
        tag = chr(65 + i)
        if "error" in r:
            lines.append(f"{tag} ({r.get('file_kind', 'other')}): ERROR {r['error']}")
            continue
        lines.append(f"{tag} ({r['file_kind']}): {r['pages']} pages {r['page_kinds']} · words {r['words']}")
        lines.append(f"   categories {r['categories']}")
        lines.append(f"   floors {r['floors']}")
    return lines


def main(argv: list[str]) -> int:
    folder = Path(argv[1]) if len(argv) > 1 else DEFAULT_DIR
    pdfs = sorted(folder.glob("*.pdf"))
    if not pdfs:
        print(f"No PDF in {folder}. Copy the drawings there (the folder is private and git-ignored).")
        return 1
    results = {}
    for p in pdfs:
        print(f"Reading {p.name} ...", flush=True)
        try:
            results[p.name] = probe_pdf(p)
        except Exception as exc:                    # one bad file must not stop the probe
            results[p.name] = {"file_kind": classify_name(p.name), "error": type(exc).__name__}
    out = folder / "probe.json"
    out.write_text(json.dumps({"at": datetime.now().isoformat(timespec="seconds"), "files": results}, indent=1),
                   encoding="utf-8")
    print("\n--- Summary (numbers only, safe to paste in the chat) ---")
    print("\n".join(summary_lines(results)))
    print(f"\nDetails saved privately: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
