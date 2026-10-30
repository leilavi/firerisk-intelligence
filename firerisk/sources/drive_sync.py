"""Automatic update of the data snapshot from Google Drive. ORIGIN: NEW.

How it works
------------
The author deploys a small Google Apps Script web app in their OWN Google account
(`apps_script/FireRiskExport.gs`). It can read only the files whose IDs are written into it, and it
answers only requests that carry the shared token. It runs as the author, so no Google Cloud project,
OAuth client or service account is needed.

This module POSTs `{"token": ...}` to that web app, receives each file as base64 `.xlsx`, checks it, and
replaces the file in the snapshot folder. Rules:

* A file is replaced only after it opens as a workbook. A failed or invalid download keeps the previous
  file, and the manifest says so (`sync_error`), so the dashboard shows the older date honestly.
* The previous version of every replaced file is kept in `snapshot/previous/`.
* The token and the web-app URL are never logged, stored in the database or returned by the API.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..config import LOCAL_TZ
from ..env import load_env

LOCAL_NAMES = {"ops_data": "ops_data.xlsx", "vehicles": "vehicles.xlsx"}
MAX_FILE_BYTES = 50 * 1024 * 1024
WEBAPP_PREFIX = "https://script.google.com/macros/s/"


class SyncError(Exception):
    """The whole sync failed; nothing was changed."""


@dataclass
class SyncConfig:
    url: str | None
    token: str | None
    interval_minutes: int = 30
    timeout_s: int = 120

    @classmethod
    def load(cls) -> "SyncConfig":
        env = load_env()
        try:
            minutes = int(env.get("FIRERISK_SYNC_MINUTES", "30"))
        except ValueError:
            minutes = 30
        return cls(url=env.get("FIRERISK_DRIVE_EXPORT_URL") or None,
                   token=env.get("FIRERISK_DRIVE_TOKEN") or None,
                   interval_minutes=max(0, minutes))

    @property
    def configured(self) -> bool:
        return bool(self.url and self.token)


def valid_webapp_url(url: str) -> bool:
    url = (url or "").strip()
    return url.startswith(WEBAPP_PREFIX) and url.endswith("/exec")


def _fetch(cfg: SyncConfig) -> dict:
    body = json.dumps({"token": cfg.token}).encode("utf-8")
    req = urllib.request.Request(cfg.url, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        # Apps Script answers with a 302 redirect; urllib follows it with a GET, as Google expects.
        with urllib.request.urlopen(req, timeout=cfg.timeout_s) as resp:
            raw = resp.read()
            ctype = resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        raise SyncError(f"Google returned HTTP {exc.code}. Check that the web app is deployed and the URL is the "
                        f"'/exec' URL of the latest deployment.") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise SyncError(f"Could not reach Google Drive ({type(reason).__name__}). Check the internet connection.") from None
    text = raw.decode("utf-8", errors="replace")
    if "json" not in ctype and text.lstrip().startswith("<"):
        raise SyncError("The web app returned a web page instead of data. In the deployment settings, "
                        "'Execute as' must be 'Me' and 'Who has access' must be 'Anyone'.")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise SyncError("The web app answer is not valid JSON.") from None
    if not isinstance(data, dict) or not data.get("ok"):
        err = data.get("error") if isinstance(data, dict) else None
        if err == "unauthorized":
            raise SyncError("The web app refused the token. Run setup_drive_sync.bat again and paste the new script.")
        raise SyncError(f"The web app reported an error: {str(err)[:200]}")
    return data


def _check_workbook(content: bytes) -> list[str]:
    if len(content) > MAX_FILE_BYTES:
        raise ValueError(f"file larger than {MAX_FILE_BYTES // (1024 * 1024)} MB")
    if not content.startswith(b"PK\x03\x04"):
        raise ValueError("not an .xlsx file")
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
    try:
        names = list(wb.sheetnames)
    finally:
        wb.close()
    if not names:
        raise ValueError("workbook has no tabs")
    return names


def _local_only(f: dict) -> bool:
    from ..data_policy import is_local_only_document
    return is_local_only_document(str(f.get("title") or ""), f.get("mime_type"), f.get("folder"))


def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def sync_from_drive(snapshot_dir: Path, cfg: SyncConfig | None = None, now: datetime | None = None) -> dict:
    """Download the configured files and update the snapshot. Returns a report (never contains secrets).

    Raises SyncError when the web app cannot be used at all; the snapshot is then unchanged.
    """
    cfg = cfg or SyncConfig.load()
    if not cfg.configured:
        raise SyncError("Google Drive sync is not set up. Run setup_drive_sync.bat.")
    t0 = time.monotonic()
    started = (now or datetime.now(LOCAL_TZ)).isoformat(timespec="seconds")
    data = _fetch(cfg)

    snapshot_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = snapshot_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"files": {}}
    files_meta = manifest.setdefault("files", {})
    report_files: dict[str, dict] = {}

    for key, item in (data.get("files") or {}).items():
        if key not in LOCAL_NAMES:
            report_files[key] = {"status": "ignored", "error": "unknown source key"}
            continue
        meta = files_meta.get(key, {})
        target = snapshot_dir / meta.get("local_file", LOCAL_NAMES[key])
        try:
            if item.get("error"):
                raise ValueError(f"Google: {str(item['error'])[:200]}")
            content = base64.b64decode(item.get("data_b64") or "", validate=True)
            tabs = _check_workbook(content)
        except Exception as exc:
            msg = str(exc) if isinstance(exc, ValueError) else f"{type(exc).__name__}"
            meta["sync_error"] = msg
            meta["sync_error_at"] = started
            files_meta[key] = meta
            report_files[key] = {"status": "failed", "error": msg,
                                 "kept_previous": target.exists(), "previous_downloaded_at": meta.get("downloaded_at")}
            continue

        new_hash = hashlib.sha256(content).hexdigest()
        old_hash = _sha256(target)
        if new_hash != old_hash:
            if target.exists():
                prev_dir = snapshot_dir / "previous"
                prev_dir.mkdir(exist_ok=True)
                os.replace(target, prev_dir / target.name)
            tmp = target.with_name(target.name + ".incoming")
            tmp.write_bytes(content)
            os.replace(tmp, target)
        meta.update({"title": item.get("title") or meta.get("title"),
                     "drive_file_id": item.get("drive_file_id") or meta.get("drive_file_id"),
                     "drive_modified_time": item.get("drive_modified_time"),
                     "mime_type": item.get("mime_type"),
                     "export": "xlsx via Apps Script web app",
                     "downloaded_at": started, "local_file": target.name,
                     "sha256": new_hash, "size": len(content), "tabs": len(tabs)})
        meta.pop("sync_error", None)
        meta.pop("sync_error_at", None)
        files_meta[key] = meta
        report_files[key] = {"status": "updated" if new_hash != old_hash else "unchanged",
                             "size": len(content), "tabs": len(tabs),
                             "drive_modified_time": item.get("drive_modified_time")}

    for key in LOCAL_NAMES:
        if key not in report_files:
            report_files[key] = {"status": "failed", "error": "not returned by the web app",
                                 "kept_previous": (snapshot_dir / files_meta.get(key, {}).get("local_file", LOCAL_NAMES[key])).exists()}

    if isinstance(data.get("listing"), list):        # every file in the data folder (incl. "Video Uploaded")
        manifest["drive_listing"] = {"at": started, "files": data["listing"]}
        # Technical drawings and manuals: recorded by name only, never downloaded or sent anywhere (condition 2).
        from ..data_policy import local_only_documents
        manifest["local_only_documents"] = {"at": started, "files": local_only_documents(data["listing"])}
        catalog = manifest.setdefault("video_catalog", {})
        for f in data["listing"]:
            if str(f.get("mime_type", "")).startswith("video/") and not _local_only(f):
                catalog[f["id"]] = {"title": f.get("title"), "size": f.get("size"), "mime_type": f.get("mime_type"),
                                    "drive_created_time": f.get("created_time"),
                                    "drive_modified_time": f.get("modified_time"), "folder": f.get("folder"),
                                    "note": "Drive upload/modified time, not the recording time",
                                    "checked_at": started, "checked_by": "FireRisk Drive sync"}
    manifest["created_by"] = "FireRisk Google Drive sync (Apps Script web app)"
    manifest["last_sync"] = {"at": started, "script_time": data.get("generated_at"),
                             "files": {k: v["status"] for k, v in report_files.items()}}
    tmp = manifest_path.with_name("manifest.json.incoming")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, manifest_path)

    statuses = [v["status"] for k, v in report_files.items() if k in LOCAL_NAMES]
    listing = data.get("listing") if isinstance(data.get("listing"), list) else []
    return {"ok": all(s in ("updated", "unchanged") for s in statuses),
            "changed": any(s == "updated" for s in statuses),
            "listing": {"files": len(listing), "videos": sum(1 for f in listing if str(f.get("mime_type", "")).startswith("video/")),
                        "error": data.get("listing_error")},
            "started_at": started, "seconds": round(time.monotonic() - t0, 1), "files": report_files}
