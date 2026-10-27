"""One-time setup of automatic Google Drive updates. ORIGIN: NEW.

Run with setup_drive_sync.bat (Windows) or:  python scripts/setup_drive_sync.py

1. Creates a random token and stores it in .env (FIRERISK_DRIVE_TOKEN).
2. Writes a ready-to-paste Apps Script (with your file IDs and the token) to data/private/drive_sync/.
3. Asks for the web-app URL you get after deploying it, stores it in .env (FIRERISK_DRIVE_EXPORT_URL).
4. Runs one update and prints what was downloaded (names, sizes, dates - never the token or file content).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from firerisk.env import ENV_FILE, read_env_file, update_env_file  # noqa: E402
from firerisk.sources.drive_sync import SyncConfig, SyncError, sync_from_drive, valid_webapp_url  # noqa: E402

TEMPLATE_DIR = ROOT / "apps_script"
OUT_DIR = ROOT / "data" / "private" / "drive_sync"
SNAPSHOT_DIR = Path(os.environ.get("FIRERISK_SNAPSHOT_DIR", ROOT / "data" / "private" / "snapshot"))
SOURCES = {"ops_data": "Operations Data (meters, checklists, repairs, incidents, generator)",
           "vehicles": "Vehicle / visitor count workbook"}

_ID_RE = re.compile(r"(?:/d/|id=)([A-Za-z0-9_-]{20,})")


def extract_drive_id(text: str) -> str | None:
    text = (text or "").strip()
    m = _ID_RE.search(text)
    if m:
        return m.group(1)
    return text if re.fullmatch(r"[A-Za-z0-9_-]{20,}", text) else None


def render_script(token: str, files: dict[str, str]) -> str:
    src = (TEMPLATE_DIR / "FireRiskExport.gs").read_text(encoding="utf-8")
    return (src.replace("__FIRERISK_TOKEN__", token)
               .replace("__FIRERISK_FILES__", json.dumps(files)))


def known_file_ids() -> dict[str, str]:
    ids: dict[str, str] = {}
    saved = OUT_DIR / "files.json"
    if saved.exists():
        ids.update(json.loads(saved.read_text(encoding="utf-8")))
    manifest = SNAPSHOT_DIR / "manifest.json"
    if manifest.exists():
        for k, m in json.loads(manifest.read_text(encoding="utf-8")).get("files", {}).items():
            if k in SOURCES and m.get("drive_file_id"):
                ids.setdefault(k, m["drive_file_id"])
    return ids


def main() -> int:
    print("\n FireRisk Intelligence - automatic Google Drive updates (one-time setup)")
    print(" -----------------------------------------------------------------------")
    ids = known_file_ids()
    for key, label in SOURCES.items():
        if key in ids:
            print(f"  {label}: file found ({ids[key][:6]}...)")
            continue
        while True:
            got = extract_drive_id(input(f"  Paste the Google Drive link of: {label}\n  > "))
            if got:
                ids[key] = got
                break
            print("  That does not look like a Google Drive link. Try again.")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "files.json").write_text(json.dumps(ids, indent=1), encoding="utf-8")

    env = read_env_file()
    token = env.get("FIRERISK_DRIVE_TOKEN")
    if not token or "--new-token" in sys.argv:
        token = secrets.token_urlsafe(32)
        update_env_file({"FIRERISK_DRIVE_TOKEN": token})
    script_path = OUT_DIR / "FireRiskExport.gs"
    script_path.write_text(render_script(token, ids), encoding="utf-8")
    (OUT_DIR / "appsscript.json").write_text((TEMPLATE_DIR / "appsscript.json").read_text(encoding="utf-8"),
                                             encoding="utf-8")
    print(f"\n  The script is ready: {script_path}")
    print("  It contains your private token. Do not share it or put it on GitHub.\n")
    print("  Follow the steps Claude gave you in the chat:")
    print("    script.google.com > New project > paste FireRiskExport.gs > (optional) appsscript.json")
    print("    > Run testExport > allow access > Deploy > New deployment > Web app")
    print("    > Execute as: Me, Who has access: Anyone > Deploy > copy the Web app URL\n")
    if os.name == "nt":
        try:
            os.startfile(str(OUT_DIR))   # opens the folder in File Explorer
        except OSError:
            pass

    while True:
        url = input("  Paste the Web app URL here (ends with /exec), or press Enter to stop for now:\n  > ").strip()
        if not url:
            print("\n  Stopped. Run setup_drive_sync.bat again when you have the URL.")
            return 1
        if valid_webapp_url(url):
            break
        print("  The URL must start with https://script.google.com/macros/s/ and end with /exec.")
    update_env_file({"FIRERISK_DRIVE_EXPORT_URL": url})

    print("\n  Testing: downloading the files from Google Drive...")
    try:
        report = sync_from_drive(SNAPSHOT_DIR, SyncConfig.load())
    except SyncError as exc:
        print(f"\n  RESULT: FAIL - {exc}")
        return 2
    for key, r in report["files"].items():
        if r["status"] in ("updated", "unchanged"):
            print(f"  {key}: {r['status']}, {r['size']:,} bytes, {r['tabs']} tabs, Drive modified {r.get('drive_modified_time')}")
        else:
            print(f"  {key}: FAILED - {r.get('error')} (previous file kept: {r.get('kept_previous')})")
    print(f"\n  RESULT: {'PASS' if report['ok'] else 'PARTIAL'} in {report['seconds']} s.")
    print("  The dashboard now updates from Google Drive automatically while run_dashboard is open.")
    print(f"  Settings are in {ENV_FILE.name}: FIRERISK_SYNC_MINUTES (default 30, 0 = only the button).")
    return 0 if report["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
