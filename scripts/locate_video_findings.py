"""Historical backfill: SAM 3.1 localization of existing Muse Spark video items. ORIGIN: NEW (2026-10-28).

Uses the same Localizer as the dashboard's continuous processing (firerisk/localize.py): same SAM client, parser,
tables and duplicate rules. Videos are NOT re-analysed by Muse Spark; Muse is only asked (text only) for a
segment phrase when an item was analysed before the segment_phrase field existed.

  python scripts/locate_video_findings.py --dry-run        plan + cost estimate; no API call, no change to the database
  python scripts/locate_video_findings.py                  run (asks for confirmation; --yes to skip)
  python scripts/locate_video_findings.py --max-requests 30
Safe to stop and run again: finished frames are skipped, interrupted ones are retried.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from firerisk.ai.muse import MuseClient, MuseConfig  # noqa: E402
from firerisk.localize import Localizer, items_of  # noqa: E402
from firerisk.sam import SamClient  # noqa: E402
from firerisk.video import VideoStore  # noqa: E402

DB = ROOT / "data" / "private" / "firerisk.db"


def report(loc: Localizer) -> dict:
    c = Counter()
    for v, ana in loc.targets():
        phr = loc.phrases(ana["id"])
        for it in items_of(ana):
            st = loc.item_result(ana["id"], it["kind"], it["index"])["status"]
            if st == "not_checked" and (it["kind"], it["index"]) not in phr:
                st = "phrase_pending"
            c[st] += 1
            c["total"] += 1
    return dict(c)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--max-requests", type=int)
    ap.add_argument("--db", default=str(DB))
    a = ap.parse_args()
    db = Path(a.db)
    if not db.exists():
        print(f"[FAIL] database not found: {db}")
        return 2
    tmp = None
    if a.dry_run:                       # work on a copy: the real database is not touched at all
        tmp = Path(tempfile.mkdtemp(prefix="firerisk_dry_"))
        shutil.copy2(db, tmp / "dry.db")
        db = tmp / "dry.db"
    try:
        videos = VideoStore(db)
        loc = Localizer(db, videos)
        plan = loc.plan(muse_client=None, dry_run=True)
        s = plan["summary"]
        print("SAM 3.1 localization - " + ("DRY RUN (no API call, database unchanged)" if a.dry_run else "plan"))
        print(f"  videos with a Muse Spark analysis : {s['videos']}")
        print(f"  items (findings + observations)   : {s['items']}")
        print(f"  eligible (visible object phrase)  : {s['eligible']}")
        print(f"  not applicable                     : {s['not_applicable']}")
        print(f"  phrase still to derive (Muse text): {s['phrase_pending']}  (up to {s['frames_if_pending_phrases_apply']} more frames)")
        print(f"  frames planned / already done      : {s['frames']} / {s['frames_done']}")
        print(f"  SAM requests needed now            : {s['frames_to_request']} (+{s['frames_reusable']} reused, no call)")
        print(f"  estimated cost                     : ${s['estimated_cost_usd']:.4f} now, at most "
              f"${s['estimated_cost_upper_bound_usd']:.4f}  (${s['price_per_image_usd'] * 1000:.2f} per 1,000 images)")
        print(f"  daily limit / used today / allowed : {s['daily_limit']} / {s['requests_today']} / "
              f"{s['requests_allowed_today']}")
        if a.dry_run:
            print(json.dumps({"summary": s}, indent=1))
            return 0
        if not a.yes and input("Run now? Type yes: ").strip().lower() != "yes":
            print("Not run.")
            return 0
        muse = MuseClient(MuseConfig.load())
        out = loc.run(SamClient(), muse_client=muse if muse.config.configured else None, max_requests=a.max_requests)
        print({k: v for k, v in out.items() if k != "summary"})
        print("Item status:", report(loc))
        return 0
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
