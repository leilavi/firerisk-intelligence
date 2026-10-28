"""Survey videos straight from Google Drive: download, register, analyse automatically. ORIGIN: NEW.

Flow (runs in the background on the author's computer):
  1. The Drive sync (sources/drive_sync.py) stores a listing of every file in the folder of the operations sheet,
     e.g. the sub-folder "Video Uploaded", and the asset register (Asset tab) links videos to equipment.
  2. A short-lived read-only access token is obtained from the author's own Apps Script web app (action "token").
     Its scope is checked with Google's tokeninfo endpoint: a token that can WRITE to Drive is refused.
  3. Each video not yet on this computer is downloaded with the Drive API (files.get alt=media), smallest first,
     checked against the size Drive reports, and registered with zone and equipment from the asset register.
     A video in the folder that no register row links keeps zone "not assigned" (nothing is guessed).
  4. When automatic video analysis is on (FIRERISK_AUTO_VIDEO_AI, default on), each new video is reviewed by
     Muse Spark (video.analyse_video: Files API + Responses API), one at a time, at most
     FIRERISK_VIDEO_AI_DAILY_LIMIT (default 8) automatic analyses per day, one automatic attempt per video.
The token is kept in memory for the run only; it is never written to disk, the database, logs or API output.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from .config import LOCAL_TZ
from .env import load_env
from .sources.drive_sync import SyncConfig, SyncError
from .video import MAX_UPLOAD_BYTES, meta_from_ref

DRIVE_FILES = "https://www.googleapis.com/drive/v3/files"
TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
WRITE_SCOPES = {"https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/drive.file"}
READ_SCOPE = "https://www.googleapis.com/auth/drive.readonly"


def video_settings() -> dict:
    env = load_env()
    try:
        limit = max(0, int(env.get("FIRERISK_VIDEO_AI_DAILY_LIMIT", "8")))
    except ValueError:
        limit = 8
    return {"auto_analyse": env.get("FIRERISK_AUTO_VIDEO_AI", "1") != "0", "daily_limit": limit,
            "download": env.get("FIRERISK_DRIVE_VIDEOS", "1") != "0"}


def get_token(cfg: SyncConfig, opener=urllib.request.urlopen) -> str:
    body = json.dumps({"token": cfg.token, "action": "token"}).encode()
    req = urllib.request.Request(cfg.url, data=body, method="POST", headers={"Content-Type": "application/json"})
    try:
        with opener(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise SyncError(f"Could not get a Drive access token from the web app ({type(exc).__name__}).") from None
    if not data.get("ok") or not data.get("access_token"):
        if data.get("error") == "unauthorized":
            raise SyncError("The web app refused the token. Run setup_drive_sync.bat again.")
        raise SyncError("The web app did not return an access token. Paste the latest FireRiskExport.gs and deploy a "
                        "new version.")
    return data["access_token"]


def check_scope(access_token: str, opener=urllib.request.urlopen) -> list[str]:
    """Refuse tokens that can write to Drive (the appsscript.json read-only step was skipped)."""
    req = urllib.request.Request(TOKENINFO, data=urllib.parse.urlencode({"access_token": access_token}).encode(),
                                 method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with opener(req, timeout=30) as r:
            info = json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise SyncError(f"Could not check the Drive token ({type(exc).__name__}).") from None
    scopes = str(info.get("scope", "")).split()
    if WRITE_SCOPES & set(scopes):
        raise SyncError("The Drive token can modify your Drive, so it was not used. In the Apps Script project, replace "
                        "appsscript.json with the read-only version from data/private/drive_sync and deploy again.")
    if READ_SCOPE not in scopes:
        raise SyncError("The Drive token has no read access to Drive files.")
    return scopes


class DriveVideoSync:
    def __init__(self, videos, inbox: Path, opener=urllib.request.urlopen):
        self.videos, self.inbox, self.opener = videos, inbox, opener
        self.lock = threading.Lock()
        self.progress: dict = {"running": False}

    # --- public ---------------------------------------------------------------------------------------------
    def start(self, items: list[dict], analyse_hook=None) -> bool:
        """items: [{"drive_file_id", "title", "size", "ref"}]. Runs in a background thread; False if already running."""
        if not self.lock.acquire(blocking=False):
            return False
        threading.Thread(target=self._run_locked, args=(items, analyse_hook), daemon=True, name="drive-videos").start()
        return True

    def run(self, items: list[dict], analyse_hook=None) -> dict:
        with self.lock:
            return self._run(items, analyse_hook)

    # --- internals ------------------------------------------------------------------------------------------
    def _run_locked(self, items, analyse_hook):
        try:
            self._run(items, analyse_hook)
        finally:
            self.lock.release()

    def _run(self, items: list[dict], analyse_hook) -> dict:
        now = datetime.now(LOCAL_TZ).isoformat(timespec="seconds")
        p = self.progress = {"running": True, "started_at": now, "downloaded": [], "skipped": [], "errors": [],
                             "current": None, "analysed": [], "finished_at": None}
        try:
            cfg = SyncConfig.load()
            if not cfg.configured:
                raise SyncError("Google Drive sync is not set up. Run setup_drive_sync.bat.")
            have = {v.get("drive_file_id"): v for v in self.videos.list() if v.get("drive_file_id")}
            todo = []
            for it in sorted(items, key=lambda x: x.get("size") or 0):
                v = have.get(it["drive_file_id"])
                if v and (not it.get("size") or v["size"] == it["size"]):
                    p["skipped"].append({"title": it["title"], "reason": "already on this computer"})
                elif (it.get("size") or 0) > MAX_UPLOAD_BYTES:
                    p["skipped"].append({"title": it["title"], "reason": "larger than 1 GiB (Meta Files API limit)"})
                else:
                    todo.append(it)
            if todo:
                token = get_token(cfg, self.opener)
                check_scope(token, self.opener)
                for it in todo:
                    try:
                        v = self._download(it, token)
                        p["downloaded"].append({"title": it["title"], "video_id": v["video_id"], "zone": v.get("zone")})
                    except Exception as exc:
                        p["errors"].append({"title": it["title"], "error": _safe(exc)})
                    finally:
                        p["current"] = None
                del token
            if analyse_hook:
                p["analysed"] = analyse_hook() or []
        except Exception as exc:
            p["errors"].append({"title": None, "error": _safe(exc)})
        finally:
            p["running"] = False
            p["current"] = None
            p["finished_at"] = datetime.now(LOCAL_TZ).isoformat(timespec="seconds")
        return p

    def _download(self, it: dict, token: str) -> dict:
        self.inbox.mkdir(parents=True, exist_ok=True)
        url = f"{DRIVE_FILES}/{urllib.parse.quote(it['drive_file_id'])}?alt=media&supportsAllDrives=true"
        tmp = self.inbox / f"drive-{it['drive_file_id']}.part"
        cur = self.progress["current"] = {"title": it["title"], "size": it.get("size"), "bytes_done": 0,
                                          "started_at": datetime.now(LOCAL_TZ).isoformat(timespec="seconds")}
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        try:
            with self.opener(req, timeout=120) as r, open(tmp, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
                    cur["bytes_done"] += len(chunk)
                    if cur["bytes_done"] > MAX_UPLOAD_BYTES:
                        raise ValueError("larger than 1 GiB")
            if it.get("size") and tmp.stat().st_size != it["size"]:
                raise ValueError(f"download incomplete ({tmp.stat().st_size} of {it['size']} bytes)")
            meta = meta_from_ref(it.get("ref"), it.get("folder"))
            meta["drive_file_id"], meta["imported_from"] = it["drive_file_id"], "google_drive"
            return self.videos.add_file(tmp, it["title"], meta)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Google Drive returned HTTP {exc.code}") from None
        finally:
            if tmp.exists():
                tmp.unlink()


def _safe(exc: Exception) -> str:
    """Error text without tokens or URLs."""
    msg = f"{type(exc).__name__}: {exc}" if not isinstance(exc, (SyncError, RuntimeError, ValueError)) else str(exc)
    return msg.split("access_token")[0][:300]


def drive_video_items(catalog: dict, refs: list[dict]) -> list[dict]:
    """All videos known from Drive: the folder listing plus links in the asset register."""
    by_id = {r["drive_file_id"]: r for r in refs}
    items = []
    for fid, c in (catalog or {}).items():
        if str(c.get("mime_type", "video/")).startswith("video/"):
            items.append({"drive_file_id": fid, "title": c.get("title") or fid, "size": c.get("size"),
                          "folder": c.get("folder"), "drive": c, "ref": by_id.get(fid)})
    for fid, r in by_id.items():
        if fid not in (catalog or {}):
            items.append({"drive_file_id": fid, "title": fid, "size": None, "folder": None, "drive": None, "ref": r})
    return items


def wait(sync: DriveVideoSync, timeout: float = 30) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not sync.lock.locked():
            return True
        time.sleep(0.05)
    return False
