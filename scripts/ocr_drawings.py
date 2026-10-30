"""Read text from SCANNED technical drawings ON THIS COMPUTER (local OCR). ORIGIN: NEW (2026-10-30).

Data owner's condition 2: original drawings stay on the author's computer and are processed there only. This script
renders each page with pypdfium2 and reads the text with RapidOCR (PP-OCR models shipped inside the pip package,
run by onnxruntime on the CPU). Nothing is uploaded, no AI service is called, no network is needed.

Scanned drawings are large (A1/A3) and the labels are small, so each page is rendered at high resolution and read in
overlapping tiles, also turned 90 degrees for vertical labels. Results stay PRIVATE in data/private/drawings/ocr/:
  * <file>.json      every text found: page, text, confidence, box (page pixels)
  * <file>_pN.png    the rendered page, and review.html showing the boxes over it - open it in a browser to check
The console prints NUMBERS ONLY (pages, texts, confidence, generic category counts) - safe to paste in the chat.
OCR makes mistakes; the next step (panel -> circuit -> equipment links) is checked by the author before the app uses it.

Usage:
  put the scanned PDFs (or PNG/JPG/TIF) into data/private/drawings/
  run_drawing_ocr.bat            (or: python scripts/ocr_drawings.py [folder] [--dpi 300] [--no-rotate])
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data" / "private" / "drawings"
TILE, OVERLAP = 1600, 200
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def _probe():
    spec = importlib.util.spec_from_file_location("probe", Path(__file__).with_name("probe_drawings.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def render_pages(path: Path, dpi: int):
    """PIL images of every page (PDF via pypdfium2, images as they are)."""
    from PIL import Image
    if path.suffix.lower() in IMAGE_SUFFIXES:
        Image.MAX_IMAGE_PIXELS = None
        img = Image.open(path)
        frames = getattr(img, "n_frames", 1)
        for i in range(frames):
            img.seek(i)
            yield i + 1, img.convert("RGB")
        return
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(path))
    try:
        for i in range(len(pdf)):
            yield i + 1, pdf[i].render(scale=dpi / 72).to_pil().convert("RGB")
    finally:
        pdf.close()


def tiles(w: int, h: int, size: int = TILE, overlap: int = OVERLAP):
    step = size - overlap
    xs = list(range(0, max(1, w - overlap), step)) or [0]
    ys = list(range(0, max(1, h - overlap), step)) or [0]
    for y in ys:
        for x in xs:
            yield x, y, min(x + size, w), min(y + size, h)


def _iou(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def dedupe(items: list[dict]) -> list[dict]:
    """Same text found twice in overlapping tiles (or both rotations): keep the more confident one."""
    keep: list[dict] = []
    for it in sorted(items, key=lambda d: -d["score"]):
        if not any(_iou(it["box"], k["box"]) > 0.5 for k in keep):
            keep.append(it)
    return keep


def ocr_page(engine, img, rotate: bool) -> list[dict]:
    """Text boxes in page pixel coordinates [x1, y1, x2, y2]."""
    import numpy as np
    w, h = img.size
    found = []
    for x1, y1, x2, y2 in tiles(w, h):
        tile = img.crop((x1, y1, x2, y2))
        tw, th = tile.size
        for angle in ((0, 90) if rotate else (0,)):
            arr = np.asarray(tile if angle == 0 else tile.rotate(90, expand=True))
            r = engine(arr)
            if r is None or r.txts is None:
                continue
            for poly, txt, score in zip(r.boxes, r.txts, r.scores):
                xs, ys = [p[0] for p in poly], [p[1] for p in poly]
                if angle == 90:          # rotated 90 deg counter-clockwise: (u, v) -> (tw - 1 - v, u)
                    xs, ys = [tw - 1 - v for v in ys], list(xs)
                box = [int(min(xs)) + x1, int(min(ys)) + y1, int(max(xs)) + x1, int(max(ys)) + y1]
                if txt.strip():
                    found.append({"text": txt.strip(), "score": round(float(score), 3), "box": box,
                                  "rotated": angle == 90})
    return dedupe(found)


def review_html(out_dir: Path, name: str, pages: list[dict]) -> str:
    parts = []
    for p in pages:
        boxes = "".join(f'<rect x="{t["box"][0]}" y="{t["box"][1]}" width="{t["box"][2] - t["box"][0]}" '
                        f'height="{t["box"][3] - t["box"][1]}"><title>{html.escape(t["text"])} ({t["score"]})</title></rect>'
                        for t in p["texts"])
        parts.append(f'<h2>{html.escape(name)} - page {p["page"]} ({len(p["texts"])} texts)</h2>'
                     f'<div class="w"><img src="{html.escape(p["image"])}"><svg viewBox="0 0 {p["size"][0]} {p["size"][1]}" '
                     f'preserveAspectRatio="none">{boxes}</svg></div>')
    return "".join(parts)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", default=str(DEFAULT_DIR))
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--no-rotate", action="store_true")
    a = ap.parse_args(argv[1:])
    folder = Path(a.folder)
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES | {".pdf"}) if folder.is_dir() else []
    if not files:
        print(f"No PDF or image in {folder}. Copy the drawings there (the folder is private and git-ignored).")
        return 1
    from rapidocr import RapidOCR
    engine = RapidOCR()
    probe = _probe()
    out_dir = folder / "ocr"
    out_dir.mkdir(exist_ok=True)
    review, summary = [], []
    for i, f in enumerate(files):
        tag = chr(65 + i)
        t0 = time.monotonic()
        print(f"Reading {f.name} ...", flush=True)
        pages = []
        try:
            for n, img in render_pages(f, a.dpi):
                texts = ocr_page(engine, img, not a.no_rotate)
                png = f"{f.stem}_p{n}.png"
                img.save(out_dir / png)
                pages.append({"page": n, "size": list(img.size), "image": png, "texts": texts})
                print(f"  page {n}: {len(texts)} texts", flush=True)
        except Exception as exc:
            summary.append(f"{tag} ({probe.classify_name(f.name)}): ERROR {type(exc).__name__}")
            continue
        (out_dir / f"{f.stem}.json").write_text(json.dumps({"file": f.name, "dpi": a.dpi, "pages": pages},
                                                           ensure_ascii=False, indent=1), encoding="utf-8")
        review.append(review_html(out_dir, f.name, pages))
        words = [t["text"] for p in pages for t in p["texts"]]
        scores = [t["score"] for p in pages for t in p["texts"]]
        low = sum(1 for s in scores if s < 0.8)
        summary.append(f"{tag} ({probe.classify_name(f.name)}): {len(pages)} pages · {len(words)} texts · "
                       f"mean confidence {sum(scores) / len(scores) if scores else 0:.2f} · {low} below 0.80 · "
                       f"{time.monotonic() - t0:.0f} s")
        summary.append(f"   categories {probe.count_matches(words, probe.CATEGORIES)}")
        summary.append(f"   floors {probe.count_matches(words, probe.FLOORS)}")
    (out_dir / "review.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Drawing OCR review - PRIVATE</title><style>'
        "body{font:13px sans-serif;margin:16px;background:#111;color:#eee} .w{position:relative;margin-bottom:24px}"
        "img{width:100%;display:block;background:#fff} svg{position:absolute;inset:0;width:100%;height:100%}"
        "rect{fill:rgba(34,211,238,.12);stroke:#0891b2;stroke-width:2;vector-effect:non-scaling-stroke}"
        "</style><h1>Drawing OCR review - PRIVATE, stays on this computer</h1>"
        "<p>Hover a box to see the text read there. Check that panel, circuit and equipment labels were read correctly.</p>"
        + "".join(review), encoding="utf-8")
    print("\n--- Summary (numbers only, safe to paste in the chat) ---")
    print("\n".join(summary))
    print(f"\nPrivate results and review page: {out_dir / 'review.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
