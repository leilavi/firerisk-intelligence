"""Phase 2 live check: the production SAM client (firerisk/sam.py) on one real frame. ORIGIN: NEW (2026-10-28).

Same frame source as scripts/check_sam.py. Verifies with a real call that the client's request (including
`store: false`) is accepted, and that its parser gives the same objects as the Phase 1 check.
Writes a sanitized report to evidence/sam_client_check_<timestamp>.json (no key, no image, no mask data).

Usage:  python scripts/check_sam_client.py [--video PATH] [--time SECONDS] [--phrase "push button"]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from check_sam import FRAME_DIR, extract, find_video, jpeg_size  # noqa: E402
from firerisk.sam import SamClient, SamError  # noqa: E402
from firerisk.video import mp4_info  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video")
    ap.add_argument("--time", type=float)
    ap.add_argument("--phrase", default="push button")
    a = ap.parse_args()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print("FireRisk Intelligence - SAM client check (Phase 2)")
    client = SamClient()
    if not client.configured:
        print("[FAIL] MODEL_API_KEY not found. Run setup_api_key.bat first.")
        return 2
    video, _ = find_video(a.video)
    if not video:
        print("[FAIL] Video 'Electrical Panel - B1' not found.")
        return 2
    dur = mp4_info(video).get("duration_s")
    at = a.time if a.time is not None else (dur / 2 if dur else 1.0)
    frame = FRAME_DIR / f"sam_client_check_{stamp}.jpg"
    extract(video, at, frame)
    jpeg = frame.read_bytes()
    ev = {"check": "sam_client_live", "run_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
          "client": "firerisk/sam.py SamClient", "phrase": a.phrase, "video": video.name, "frame_time_s": round(at, 2),
          "frame_size": list(jpeg_size(jpeg) or [])}
    try:
        r = client.locate(jpeg, a.phrase)
        ev.update({"result": r.status.upper(), "model_returned": r.model, "request_seconds": r.seconds,
                   "images_billed": r.images_billed, "store_false_sent": client.store_param_ok is not False,
                   "store_false_accepted": r.store_disabled, "parse_complete": r.parse.complete,
                   "diagnostics": r.parse.diagnostics, "frame_size_in_answer": {str(k): list(v) for k, v in
                                                                                r.parse.frame_sizes.items()},
                   "max_confidence": r.max_confidence,
                   "objects": [{"object_id": o.object_id, "box": o.box, "confidence": o.confidence,
                                "mask_decoded": o.mask_svg_path is not None} for o in r.parse.objects]})
        print(f"[OK]   {ev['result']}: {len(r.parse.objects)} object(s), max confidence {r.max_confidence}, "
              f"{r.seconds}s, store:false accepted = {r.store_disabled}")
        rc = 0
    except SamError as err:
        ev.update({"result": "ERROR", "error_kind": err.kind, "error": str(err)[:300]})
        print(f"[FAIL] {err.kind}: {err}")
        rc = 1
    text = json.dumps(ev, indent=2, ensure_ascii=False)
    if client.config.api_key and client.config.api_key in text:
        text = text.replace(client.config.api_key, "<REDACTED_KEY>")
    out = ROOT / "evidence" / f"sam_client_check_{stamp}.json"
    out.write_text(text, encoding="utf-8")
    print(f"RESULT: {ev['result']}\nSanitized report: {out}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
