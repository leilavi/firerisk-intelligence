"""Blurred demo copies of the evidence frames: SAM 3.1 finds signs and labels, ffmpeg blurs them. ORIGIN: NEW (2026-10-29).

Originals in data/private/media/frames/ are never modified. Copies go to data/private/media/frames_demo/ (git-ignored)
with manifest.json. The dashboard uses the copies only in demo mode (run_dashboard_demo.bat).

  python scripts/mask_labels_for_demo.py --dry-run          count frames and SAM requests, estimate cost; no API call
  python scripts/mask_labels_for_demo.py                    make the copies (asks first; --yes to skip)
  python scripts/mask_labels_for_demo.py --review           write review.html (every copy with its blurred boxes)
  python scripts/mask_labels_for_demo.py --add-box a20eeae9372bb0ef/t000330.jpg 100,40,260,90
                                                            blur one more region that SAM missed (after review)
  python scripts/mask_labels_for_demo.py --mark-reviewed    record that review.html was inspected

A frame where SAM found no sign or label is copied unblurred and flagged; SAM can miss things, so the review sheet
must be looked at before the demo. Nothing is called anonymized until --mark-reviewed.
"""

from __future__ import annotations

import argparse
import base64
import html
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from firerisk.config import LOCAL_TZ  # noqa: E402
from firerisk.demo import (DEFAULT_PHRASES, FACE_DETECTOR, FRAMES_DEMO_DIR, blur_regions, local_face_boxes, load_manifest, padded,  # noqa: E402
                           save_manifest)
from firerisk.localize import FRAMES_DIR, PRICE_PER_IMAGE_USD, jpeg_size  # noqa: E402
from firerisk.sam import SamClient, SamError, SamModelNotFound, SamAuthError, SamNotConfigured, SamRateLimited  # noqa: E402

DB = ROOT / "data" / "private" / "firerisk.db"
STOP = (SamModelNotFound, SamAuthError, SamNotConfigured, SamRateLimited)


def frame_files(db: Path) -> list[str]:
    with sqlite3.connect(db) as c:
        has = c.execute("SELECT 1 FROM sqlite_master WHERE name='video_finding_locations'").fetchone()
        if not has:
            return []
        return sorted({r[0] for r in c.execute("SELECT frame_file FROM video_finding_locations WHERE frame_file IS NOT NULL")})


def now() -> str:
    return datetime.now(LOCAL_TZ).isoformat(timespec="seconds")


def process(files, phrases, sam, frames_dir: Path, out_dir: Path, max_requests=None) -> dict:
    m = load_manifest(out_dir)
    stats = {"requests": 0, "blurred": 0, "no_label_found": 0, "errors": 0, "skipped": 0, "stopped": None}
    for ff in files:
        e = m["frames"].get(ff)
        if e and e.get("status") in ("blurred", "no_label_found") and e.get("phrases") == list(phrases):
            if e.get("face_detector") == FACE_DETECTOR or not (frames_dir / ff).exists():
                stats["skipped"] += 1
                continue
            # SAM part already done: add the local face check only (no API call)
            src = frames_dir / ff
            w, h = e.get("frame_size") or (jpeg_size(src.read_bytes()) or (0, 0))
            faces, det = local_face_boxes(src)
            regions = [tuple(r) for r in e.get("regions", [])] + faces
            try:
                blur_regions(src, out_dir / ff, regions)
            except Exception as exc:
                m["frames"][ff] = {**e, "status": "error", "error": f"blur failed: {type(exc).__name__}", "updated_at": now()}
                stats["errors"] += 1
                continue
            m["frames"][ff] = {**e, "status": "blurred" if regions else "no_label_found", "face_boxes": [list(f) for f in faces],
                               "face_detector": det, "regions": [list(r) for r in regions], "updated_at": now()}
            if faces:
                m["reviewed"] = False
            stats["faces"] = stats.get("faces", 0) + len(faces)
            save_manifest(m, out_dir)
            continue
        src = frames_dir / ff
        if not src.exists():
            m["frames"][ff] = {"status": "error", "error": "original frame missing", "updated_at": now()}
            stats["errors"] += 1
            continue
        data = src.read_bytes()
        w, h = jpeg_size(data) or (0, 0)
        boxes, err = [], None
        for ph in phrases:
            if max_requests is not None and stats["requests"] >= max_requests:
                stats["stopped"] = "max_requests"
                break
            try:
                res = sam.locate(data, ph)
                stats["requests"] += 1
            except SamError as exc:
                err = exc
                if exc.kind not in ("bad_request",):
                    stats["requests"] += 1
                break
            boxes += [{"phrase": ph, "confidence": o.confidence, **o.box} for o in res.parse.objects]
        if stats["stopped"] or err:
            if err:
                m["frames"][ff] = {"status": "error", "error": f"{err.kind}", "updated_at": now()}
                stats["errors"] += 1
                if isinstance(err, STOP):
                    stats["stopped"] = err.kind
            if stats["stopped"]:
                break
            continue
        extra = (e or {}).get("manual_boxes", [])
        faces, det = local_face_boxes(src)                 # local OpenCV, never SAM (project rule) - condition 3
        regions = [padded(b, w, h) for b in boxes] + [tuple(x) for x in extra] + faces
        try:
            blur_regions(src, out_dir / ff, regions)
        except Exception as exc:          # ffmpeg problem: no copy, original untouched
            m["frames"][ff] = {"status": "error", "error": f"blur failed: {type(exc).__name__}", "updated_at": now()}
            stats["errors"] += 1
            continue
        status = "blurred" if regions else "no_label_found"
        m["frames"][ff] = {"status": status, "phrases": list(phrases), "frame_size": [w, h], "sam_boxes": boxes,
                           "manual_boxes": extra, "face_boxes": [list(f) for f in faces], "face_detector": det, "regions": [list(r) for r in regions], "updated_at": now()}
        m["reviewed"] = False                 # any new copy needs a new look
        stats[status] += 1
        save_manifest(m, out_dir)
    save_manifest(m, out_dir)
    return stats


def review_sheet(out_dir: Path) -> Path:
    m = load_manifest(out_dir)
    cards = []
    for ff, e in sorted(m["frames"].items(), key=lambda kv: (kv[1].get("status") != "no_label_found", kv[0])):
        p = out_dir / ff
        img = f'<img src="data:image/jpeg;base64,{base64.b64encode(p.read_bytes()).decode()}">' if p.exists() else "<p>missing</p>"
        w, h = e.get("frame_size") or (1, 1)
        rects = "".join(f'<rect x="{r[0]}" y="{r[1]}" width="{r[2] - r[0]}" height="{r[3] - r[1]}"/>' for r in e.get("regions", []))
        tag = {"blurred": f"{len(e.get('regions', []))} region(s) blurred", "no_label_found": "NO sign/label found - check",
               "error": "ERROR - no copy"}.get(e.get("status"), e.get("status"))
        cards.append(f'<figure class="{e.get("status")}"><div class="w">{img}<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
                     f'{rects}</svg></div><figcaption>{html.escape(ff)} · {html.escape(tag)}</figcaption></figure>')
    out = out_dir / "review.html"
    out.write_text(f"""<!doctype html><meta charset="utf-8"><title>Demo frames review</title><style>
body{{background:#111;color:#eee;font:13px sans-serif;margin:16px}} .g{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:10px}}
figure{{margin:0}} .w{{position:relative}} img{{width:100%;display:block}} svg{{position:absolute;inset:0;width:100%;height:100%}}
rect{{fill:none;stroke:#22d3ee;stroke-width:3;vector-effect:non-scaling-stroke}} .no_label_found figcaption{{color:#facc15}} .error figcaption{{color:#ef4444}}
</style><h1>Blurred demo frames - PRIVATE</h1><p>Look for any building name, readable label, staff name or face left visible. Cyan outlines = blurred
regions. Missed text: run <code>--add-box FRAME x1,y1,x2,y2</code>. When everything is checked: <code>--mark-reviewed</code>.
Reviewed: <b>{m.get('reviewed')}</b></p><div class="g">{''.join(cards)}</div>""", encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--review", action="store_true")
    ap.add_argument("--mark-reviewed", action="store_true")
    ap.add_argument("--add-box", nargs=2, metavar=("FRAME", "X1,Y1,X2,Y2"))
    ap.add_argument("--phrases", default=",".join(DEFAULT_PHRASES))
    ap.add_argument("--max-requests", type=int)
    ap.add_argument("--db", default=str(DB))
    a = ap.parse_args()
    phrases = [p.strip() for p in a.phrases.split(",") if p.strip()]
    if a.mark_reviewed:
        m = load_manifest()
        m.update({"reviewed": True, "reviewed_at": now()})
        save_manifest(m)
        print("Recorded: review sheet inspected.")
        return 0
    if a.add_box:
        ff, coords = a.add_box
        x1, y1, x2, y2 = (int(v) for v in coords.split(","))
        m = load_manifest()
        e = m["frames"].setdefault(ff, {})
        e.setdefault("manual_boxes", []).append([x1, y1, x2, y2])
        e["status"] = "pending"
        save_manifest(m)
        print(f"Added a region to {ff}. Run the script again to rebuild that copy.")
        return 0
    if a.review:
        print(f"Review sheet: {review_sheet(FRAMES_DEMO_DIR)}")
        return 0
    files = frame_files(Path(a.db))
    m = load_manifest()
    sam_done = lambda f: (m["frames"].get(f, {}).get("status") in ("blurred", "no_label_found")
                          and m["frames"][f].get("phrases") == phrases)
    sam_todo = [f for f in files if not sam_done(f)]
    face_todo = [f for f in files if sam_done(f) and m["frames"][f].get("face_detector") != FACE_DETECTOR]
    todo = sam_todo + face_todo
    n = len(sam_todo) * len(phrases)
    print(f"Evidence frames: {len(files)} · to process: {len(todo)} ({len(face_todo)} need only the local face check) · "
          f"SAM requests: up to {n} (phrases: {', '.join(phrases)}) · estimated cost: up to ${n * PRICE_PER_IMAGE_USD:.4f}")
    if local_face_boxes(Path("__none__.jpg"))[1] == "unavailable":
        print("WARNING: OpenCV is not installed, faces will NOT be blurred. Run: pip install opencv-python-headless")
    if a.dry_run:
        return 0
    if not todo:
        print("Nothing to do.")
    elif sam_todo and not a.yes and input("Run now? Type yes: ").strip().lower() != "yes":
        print("Not run.")
        return 0
    else:
        stats = process(todo, phrases, SamClient(), FRAMES_DIR, FRAMES_DEMO_DIR, a.max_requests)
        print(stats)
    print(f"Review sheet: {review_sheet(FRAMES_DEMO_DIR)}  (open it and check every frame before the demo)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
