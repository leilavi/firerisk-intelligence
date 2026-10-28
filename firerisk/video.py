"""Building survey videos: storage, metadata, Muse Spark video analysis, links to fire-risk alerts. ORIGIN: NEW.

Status (2026-10-27): the architecture is built and tested with TEST files only. **No real survey video has been
provided yet, and no video has been sent to Meta.** Nothing in this module runs until the author uploads a video.

Why this design (checked against the official docs on 2026-10-27):
  * https://dev.meta.ai/docs/video-understanding - Muse Spark (`muse-spark-1.3`) accepts video directly on the
    Responses API, as an `input_video` part with a `file_id` (Files API upload) or a `video_url`. Supported
    format: `video/mp4`. The page does not state a maximum duration, the frame-sampling behaviour, or whether
    timestamps in the answer are reliable.
  * https://dev.meta.ai/docs/file-handling - `POST /v1/files` (multipart, `purpose=user_data`, optional
    `expires_after[anchor]=created_at` + `expires_after[seconds]` 3600..2592000), 1 GiB limit for uploads,
    `DELETE /v1/files/{id}`.
  * https://dev.meta.ai/docs/api-reference/responses/schemas - `input_video` has `video_url`, `file_id`, `fps`;
    structured output is `text.format`; the answer text is in `output[].content[]` items of type `output_text`.
  NOT YET VERIFIED with a real call: the exact `text.format` json_schema shape on /v1/responses (written in the
  OpenAI-compatible form `{"type":"json_schema","name","schema","strict"}`), and how accurate the model's
  timestamps are. The first real run must be checked before relying on it.

Privacy: the uploaded copy expires after 1 hour and is deleted right after the analysis; `store: false` asks the
API not to keep the response. The model is told not to identify people or transcribe speech.

Meaning of a video observation: it shows what was VISIBLE WHEN THE VIDEO WAS RECORDED. It is context for a
fire-risk alert. It never sets or changes a rule level, it does not prove that equipment works today, and it
does not confirm that a fire risk has materialised.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from .config import LOCAL_TZ, ZONE_LABELS

ROOT = Path(__file__).resolve().parent.parent
VIDEO_DIR = Path(os.environ.get("FIRERISK_VIDEO_DIR", ROOT / "data" / "private" / "media" / "videos"))
MAX_UPLOAD_BYTES = 1_073_741_824            # Files API limit (docs/file-handling)
ANALYSABLE_MIME = {"video/mp4"}            # docs/video-understanding: supported video format
ACCEPTED_EXT = {".mp4": "video/mp4", ".mov": "video/quicktime", ".m4v": "video/mp4"}
FILE_EXPIRY_SECONDS = 3600                 # uploaded copy at Meta expires after 1 h (minimum allowed)
VIDEO_PROMPT_VERSION = "survey-video-v1"
OLD_VIDEO_DAYS = 30                        # display hint only: "recorded more than 30 days ago"
VIDEO_TIMEOUT_S = 900                      # per network wait during video upload / analysis
INBOX_DIR = Path(os.environ.get("FIRERISK_VIDEO_INBOX", ROOT / "data" / "private" / "media" / "survey_inbox"))

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS survey_videos (
  video_id TEXT PRIMARY KEY, filename TEXT NOT NULL, stored_name TEXT NOT NULL, sha256 TEXT NOT NULL,
  size INTEGER NOT NULL, mime TEXT NOT NULL, duration_s REAL, zone TEXT, floor TEXT, area TEXT, room TEXT,
  recorded_at TEXT, recorded_at_source TEXT NOT NULL, uploaded_at TEXT NOT NULL, note TEXT);
CREATE TABLE IF NOT EXISTS video_analyses (
  id INTEGER PRIMARY KEY AUTOINCREMENT, video_id TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL,
  model TEXT, record TEXT NOT NULL);
"""

CATEGORIES = ["exit_or_escape_route", "corridor_or_walkway", "fire_equipment", "fire_detection_or_alarm",
              "electrical_equipment", "obstruction", "storage_or_combustibles", "water_or_moisture",
              "heat_or_burn_marks", "signage_or_emergency_lighting", "housekeeping", "other"]

VIDEO_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["summary", "observations", "not_determinable", "limitations"],
    "properties": {
        "summary": {"type": "string"},
        "observations": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["time_start_s", "time_end_s", "location_in_video", "category", "observation",
                         "visible_certainty", "fire_safety_relevance"],
            "properties": {
                "time_start_s": {"type": "number"}, "time_end_s": {"type": "number"},
                "location_in_video": {"type": "string"},
                "category": {"type": "string", "enum": CATEGORIES},
                "observation": {"type": "string"},
                "visible_certainty": {"type": "string", "enum": ["clearly_visible", "possibly_visible"]},
                "fire_safety_relevance": {"type": "string"}}}},
        "not_determinable": {"type": "array", "items": {"type": "string"}},
        "limitations": {"type": "string"},
    },
}

VIDEO_INSTRUCTIONS = """You review a building survey video for fire-safety inspection support.
Report only what is VISIBLE in the video: exits and escape routes, corridors, fire equipment (extinguishers, hose
reels, alarm panels, detectors, signage, emergency lighting), electrical rooms and panels, obstructions, stored
combustible material, water or moisture, heat or burn marks, housekeeping.
Rules: (1) Do not guess what is outside the frame or what happened before or after the recording.
(2) Do not say equipment works or does not work unless it is visibly obvious; a visible extinguisher does not
prove it is charged. (3) Do not identify people, do not describe faces, and do not transcribe speech.
(4) Give the approximate time in the video (seconds from the start) for every observation.
(5) No probabilities and no fire predictions. (6) Put things that cannot be judged from the video in
not_determinable. Write in clear English."""


class VideoStore:
    def __init__(self, db_path: Path, video_dir: Path = VIDEO_DIR):
        self.db_path, self.video_dir = db_path, video_dir
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA_SQL)
            cols = {r["name"] for r in c.execute("PRAGMA table_info(survey_videos)")}
            for col in ("drive_file_id", "equipment", "imported_from"):     # added 2026-10-28
                if col not in cols:
                    c.execute(f"ALTER TABLE survey_videos ADD COLUMN {col} TEXT")
        self.running: set[str] = set()
        self.lock = threading.Lock()

    def _conn(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    # --- upload -----------------------------------------------------------------------------------
    @staticmethod
    def check_name(filename: str) -> str:
        ext = Path(filename).suffix.lower()
        if ext not in ACCEPTED_EXT:
            raise ValueError(f"unsupported file type {ext or '(none)'}; use .mp4 (or .mov, which must be converted)")
        return ext

    def incoming_path(self, filename: str) -> Path:
        self.video_dir.mkdir(parents=True, exist_ok=True)
        return self.video_dir / f"upload-{uuid.uuid4().hex}{self.check_name(filename)}.incoming"

    def add(self, chunks, filename: str, meta: dict) -> dict:
        """Store an uploaded video from an iterable of bytes (used by tests and scripts)."""
        tmp = self.incoming_path(filename)
        size = 0
        try:
            with open(tmp, "wb") as f:
                for chunk in chunks:
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise ValueError("file larger than 1 GiB (Meta Files API limit)")
                    f.write(chunk)
            return self.add_file(tmp, filename, meta)
        finally:
            if tmp.exists():
                tmp.unlink()

    def add_file(self, src: Path, filename: str, meta: dict) -> dict:
        """Register a fully received upload (`src` is moved into the video folder)."""
        ext = self.check_name(filename)
        clean = clean_meta(meta)              # validate before keeping anything
        size = src.stat().st_size
        if size == 0:
            raise ValueError("empty file")
        if size > MAX_UPLOAD_BYTES:
            raise ValueError("file larger than 1 GiB (Meta Files API limit)")
        h = hashlib.sha256()
        with open(src, "rb") as f:
            while chunk := f.read(1 << 20):
                h.update(chunk)
        now = datetime.now(LOCAL_TZ)
        vid = f"VID-{now:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"
        self.video_dir.mkdir(parents=True, exist_ok=True)
        target = self.video_dir / f"{vid}{ext}"
        try:
            os.replace(src, target)
        except OSError:                       # different drive: copy, then remove the original
            shutil.copy2(src, target)
            src.unlink()
        info = mp4_info(target) if ext in (".mp4", ".m4v", ".mov") else {}
        if not clean["recorded_at"] and info.get("creation_time"):
            clean["recorded_at"] = info["creation_time"]
            clean["recorded_at_source"] = "mp4_metadata"
        rec = {"video_id": vid, "filename": Path(filename).name[:200], "stored_name": target.name,
               "sha256": h.hexdigest(), "size": size, "mime": ACCEPTED_EXT[ext],
               "duration_s": _num(meta.get("duration_s")) or info.get("duration_s"),
               "uploaded_at": now.isoformat(timespec="seconds"), **clean,
               "drive_file_id": meta.get("drive_file_id"), "equipment": json.dumps(meta.get("equipment") or [], ensure_ascii=False),
               "imported_from": meta.get("imported_from")}
        with self._conn() as c:
            c.execute("INSERT INTO survey_videos (video_id, filename, stored_name, sha256, size, mime, duration_s, zone, "
                      "floor, area, room, recorded_at, recorded_at_source, uploaded_at, note, drive_file_id, equipment, "
                      "imported_from) VALUES "
                      "(:video_id,:filename,:stored_name,:sha256,:size,:mime,:duration_s,:zone,:floor,:area,:room,"
                      ":recorded_at,:recorded_at_source,:uploaded_at,:note,:drive_file_id,:equipment,:imported_from)", rec)
        return self.get(vid)

    def update_meta(self, video_id: str, meta: dict) -> dict:
        if not self.get(video_id):
            raise KeyError(video_id)
        m = clean_meta(meta)
        with self._conn() as c:
            c.execute("UPDATE survey_videos SET zone=:zone, floor=:floor, area=:area, room=:room, recorded_at=:recorded_at, "
                      "recorded_at_source=:recorded_at_source, note=:note WHERE video_id=:video_id", {**m, "video_id": video_id})
        return self.get(video_id)

    # --- read ----------------------------------------------------------------------------------------
    def get(self, video_id: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM survey_videos WHERE video_id=?", (video_id,)).fetchone()
        return self._view(dict(r)) if r else None

    def list(self) -> list[dict]:
        with self._conn() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM survey_videos ORDER BY COALESCE(recorded_at, uploaded_at) DESC")]
        return [self._view(r) for r in rows]

    def path(self, video_id: str) -> Path | None:
        v = self.get(video_id)
        p = self.video_dir / v["stored_name"] if v else None
        return p if p and p.exists() else None

    def _view(self, r: dict) -> dict:
        try:
            r["equipment"] = json.loads(r.get("equipment") or "[]")
        except (TypeError, ValueError):
            r["equipment"] = []
        r["zone_label"] = ZONE_LABELS.get(r.get("zone") or "", r.get("zone") or "Not assigned")
        r["analysable"] = r["mime"] in ANALYSABLE_MIME
        if not r["analysable"]:
            r["analysable_reason"] = "Muse Spark accepts video/mp4 only (official docs); convert this file to .mp4"
        r["age_days"] = _age_days(r.get("recorded_at"))
        r["recording_note"] = recording_note(r)
        latest = self.latest_analysis(r["video_id"])
        r["analysis_status"] = ("running" if r["video_id"] in getattr(self, "running", set()) else
                                latest["status"] if latest else "not_analysed")
        r["analysis_id"] = latest["id"] if latest else None
        return r

    def latest_analysis(self, video_id: str, only_ok: bool = False) -> dict | None:
        q = "SELECT * FROM video_analyses WHERE video_id=?" + (" AND status='ok'" if only_ok else "") + " ORDER BY id DESC LIMIT 1"
        with self._conn() as c:
            r = c.execute(q, (video_id,)).fetchone()
        if not r:
            return None
        rec = json.loads(r["record"])
        rec.update({"id": r["id"], "status": r["status"]})
        return rec

    def save_analysis(self, rec: dict) -> int:
        with self._conn() as c:
            return c.execute("INSERT INTO video_analyses (video_id, created_at, status, model, record) VALUES (?,?,?,?,?)",
                             (rec["video_id"], rec["created_at"], rec["status"], rec.get("model"),
                              json.dumps(rec, ensure_ascii=False))).lastrowid

    def for_zone(self, zone: str | None) -> list[dict]:
        """Survey videos of a zone, newest recording first, each with its latest valid observations."""
        out = []
        for v in self.list():
            if zone and v.get("zone") == zone:
                ana = self.latest_analysis(v["video_id"], only_ok=True)
                out.append({**v, "observations": (ana or {}).get("observations", []),
                            "analysis_created_at": (ana or {}).get("created_at"), "analysis_model": (ana or {}).get("model"),
                            "origin": "ai_vision" if ana else None})
        return out

    def context_for(self, zone: str | None) -> list[dict]:
        """Compact, validated video observations for a fire-risk alert's AI package (context, never a finding)."""
        out = []
        for v in self.for_zone(zone):
            if v["observations"]:
                out.append({"video_id": v["video_id"], "analysis_created_at": v["analysis_created_at"],
                            "recorded_at": v.get("recorded_at"), "age_days": v.get("age_days"),
                            "place": " / ".join(x for x in (v.get("floor"), v.get("area"), v.get("room")) if x) or None,
                            "observations": [{k: o[k] for k in ("time_start_s", "category", "observation", "visible_certainty")}
                                             for o in v["observations"]][:30]})
        return out

    # --- analysis ----------------------------------------------------------------------------------------
    def analyse(self, video_id: str, client, context: str = "", on_done=None, trigger: str = "button") -> dict:
        """Run one analysis. `on_done(record)` runs after the record is stored and BEFORE the video stops being
        'running', so whoever waits for 'not running' sees the alert context already updated."""
        v = self.get(video_id)
        if not v:
            raise KeyError(video_id)
        now = datetime.now(LOCAL_TZ)
        rec = {"video_id": video_id, "created_at": now.isoformat(timespec="seconds"), "prompt_version": VIDEO_PROMPT_VERSION,
               "model_requested": client.config.model, "recorded_at": v.get("recorded_at"), "zone": v.get("zone"),
               "trigger": trigger}
        with self.lock:
            if video_id in self.running:
                return {"status": "running"}
            self.running.add(video_id)
        try:
            try:
                if not v["analysable"]:
                    raise VideoNotAnalysable(v["analysable_reason"])
                rec.update(analyse_video(client, self.path(video_id), context, v.get("duration_s")))
                rec["status"] = "ok"
            except Exception as exc:
                rec.update({"status": "failed", "error_kind": getattr(exc, "kind", type(exc).__name__),
                            "error": str(exc)[:500]})
            rec["id"] = self.save_analysis(rec)
            if on_done:
                try:
                    on_done(rec)
                except Exception:
                    pass
            return rec
        finally:
            with self.lock:
                self.running.discard(video_id)

    def analyse_in_background(self, video_id: str, client_factory, context: str = "", on_done=None) -> bool:
        if video_id in self.running:
            return False
        threading.Thread(target=self.analyse, args=(video_id, client_factory(), context, on_done), daemon=True,
                         name=f"video-{video_id}").start()
        return True


    # --- import from a local folder (videos referenced in the asset register) ------------------------------
    def import_folder(self, inbox: Path, refs: list[dict]) -> dict:
        """Register every .mp4/.mov in `inbox`. A file is matched to an asset-register reference by its Drive
        title (file name) or, failing that, by exact size; the match gives zone and linked equipment.
        Already imported files (same SHA-256) are left in place and reported."""
        inbox.mkdir(parents=True, exist_ok=True)
        by_title = {((r.get("drive") or {}).get("title") or "").lower(): r for r in refs if (r.get("drive") or {}).get("title")}
        by_size = {(r.get("drive") or {}).get("size"): r for r in refs if (r.get("drive") or {}).get("size")}
        known = {v["sha256"] for v in self.list()}
        out = {"inbox": str(inbox), "imported": [], "skipped": []}
        for f in sorted(inbox.iterdir()):
            if not f.is_file() or f.suffix.lower() not in ACCEPTED_EXT:
                continue
            h = hashlib.sha256()
            with open(f, "rb") as fh:
                while chunk := fh.read(1 << 20):
                    h.update(chunk)
            if h.hexdigest() in known:
                out["skipped"].append({"file": f.name, "reason": "already imported"})
                continue
            ref = by_title.get(f.name.lower()) or by_size.get(f.stat().st_size)
            meta = meta_from_ref(ref)
            meta.update({"drive_file_id": (ref or {}).get("drive_file_id"), "imported_from": "folder"})
            try:
                v = self.add_file(f, f.name, meta)
            except ValueError as exc:
                out["skipped"].append({"file": f.name, "reason": str(exc)})
                continue
            out["imported"].append({"video_id": v["video_id"], "file": f.name, "matched": bool(ref),
                                    "zone": v.get("zone"), "recorded_at": v.get("recorded_at"),
                                    "recorded_at_source": v.get("recorded_at_source")})
        return out

    def reference_status(self, refs: list[dict]) -> list[dict]:
        """Asset-register video references with whether the file is on this computer."""
        have = {v.get("drive_file_id"): v for v in self.list() if v.get("drive_file_id")}
        out = []
        for r in refs:
            v = have.get(r["drive_file_id"])
            out.append({**r, "zone_label": ZONE_LABELS.get(r.get("zone") or "", "Not assigned"),
                        "video_id": v["video_id"] if v else None, "on_this_computer": bool(v),
                        "analysis_status": v["analysis_status"] if v else None})
        return out


    def auto_analyses_today(self) -> int:
        day = datetime.now(LOCAL_TZ).date().isoformat()
        with self._conn() as c:
            rows = c.execute("SELECT record FROM video_analyses WHERE created_at >= ?", (day,)).fetchall()
        return sum(1 for r in rows if json.loads(r["record"]).get("trigger") == "auto")

    def pending_auto(self) -> list[dict]:
        """Analysable videos with no analysis attempt yet (one automatic attempt per video), smallest first."""
        out = [v for v in self.list() if v["analysable"] and v["analysis_status"] == "not_analysed"]
        return sorted(out, key=lambda v: v["size"])


def meta_from_ref(ref: dict | None, folder: str | None = None) -> dict:
    """Video metadata from an asset-register reference (zone from the register Floor; never guessed)."""
    eq = (ref or {}).get("equipment") or []
    names = [e.get("name") or e["equipment_id"] for e in eq]
    if eq:
        note = "Linked in the asset register to: " + "; ".join(f"{e['equipment_id']} {e.get('name') or ''}".strip() for e in eq)
    else:
        note = (f"In the Google Drive folder '{folder}'; " if folder else "") + "not linked to equipment in the asset register"
    return {"zone": (ref or {}).get("zone"), "floor": next((e.get("floor") for e in eq if e.get("floor")), None),
            "room": names[0] if names else None, "note": note, "equipment": eq}


class VideoNotAnalysable(Exception):
    kind = "not_analysable"


# --- Meta API calls (Files API + Responses API) ---------------------------------------------------------------
def upload_file(client, path: Path, mime: str = "video/mp4") -> str:
    """POST /v1/files (multipart). Field order per docs: purpose and expires_after first, file last."""
    import urllib.request
    boundary = "----firerisk" + uuid.uuid4().hex
    def part(name, value):
        return (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n").encode()
    head = (part("purpose", "user_data") + part("expires_after[anchor]", "created_at")
            + part("expires_after[seconds]", str(FILE_EXPIRY_SECONDS))
            + (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"survey{path.suffix}\"\r\n"
               f"Content-Type: {mime}\r\n\r\n").encode())
    tail = f"\r\n--{boundary}--\r\n".encode()
    size = len(head) + path.stat().st_size + len(tail)

    def body():
        yield head
        with open(path, "rb") as f:
            while chunk := f.read(1 << 20):
                yield chunk
        yield tail
    req = urllib.request.Request(f"{client.config.base_url}/files", data=body(), method="POST", headers={
        "Authorization": f"Bearer {client.config.api_key}", "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(size)})
    resp = client._send(req)
    fid = resp.get("id")
    if not fid:
        from .ai.muse import MuseBadResponse
        raise MuseBadResponse(f"file upload returned no id: {str(resp)[:200]}")
    return fid


def delete_file(client, file_id: str) -> bool:
    import urllib.request
    req = urllib.request.Request(f"{client.config.base_url}/files/{file_id}", method="DELETE",
                                 headers={"Authorization": f"Bearer {client.config.api_key}"})
    try:
        client._send(req)
        return True
    except Exception:
        return False


def responses_text(body: dict) -> str:
    """Concatenate the output_text parts of a /v1/responses answer (docs: Response.output -> OutputMessage)."""
    texts = []
    for item in body.get("output") or []:
        if item.get("type") == "message":
            for c in item.get("content") or []:
                if c.get("type") == "output_text" and isinstance(c.get("text"), str):
                    texts.append(c["text"])
    return "".join(texts)


def analyse_video(client, path: Path, context: str, duration_s: float | None) -> dict:
    from .ai.muse import MuseBadResponse, MuseNotConfigured
    if not client.config.configured:
        raise MuseNotConfigured("MODEL_API_KEY is not set (run setup_api_key.bat)")
    from dataclasses import replace
    from .ai.muse import MuseClient
    # Large uploads and video processing take minutes; the timeout applies to each network wait.
    client = MuseClient(replace(client.config, timeout_s=max(client.config.timeout_s, VIDEO_TIMEOUT_S)), opener=client._open)
    t0 = time.monotonic()
    file_id = upload_file(client, path)
    deleted = False
    try:
        payload = {
            "model": client.config.model,
            "instructions": VIDEO_INSTRUCTIONS,
            "input": [{"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": "Building log context (for orientation only; report only what the video "
                                               f"shows): {context or 'none'}"},
                {"type": "input_video", "file_id": file_id}]}],
            "text": {"format": {"type": "json_schema", "name": "SurveyVideoObservations", "schema": VIDEO_SCHEMA,
                                "strict": True}},
            "reasoning": {"effort": "low"},
            "max_output_tokens": 8000,
            "store": False,
        }
        body = client._post("/responses", payload)
    finally:
        deleted = delete_file(client, file_id)
    if body.get("status") not in (None, "completed"):
        raise MuseBadResponse(f"response status {body.get('status')}: {str(body.get('incomplete_details') or body.get('error'))[:200]}")
    text = responses_text(body)
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        raise MuseBadResponse(f"model output is not valid JSON: {text[:200]}") from None
    obs, rejected = validate_observations(data.get("observations") or [], duration_s)
    return {"model": body.get("model"), "usage": body.get("usage"), "seconds": round(time.monotonic() - t0, 1),
            "summary": data.get("summary"), "observations": obs, "rejected_observations": rejected,
            "not_determinable": data.get("not_determinable") or [], "limitations": data.get("limitations"),
            "remote_file_deleted": deleted, "timestamps_verified": False}


def validate_observations(items: list[dict], duration_s: float | None) -> tuple[list[dict], list[dict]]:
    """Keep observations with a usable time range inside the video; others are kept aside with the reason."""
    ok, bad = [], []
    for o in items:
        try:
            a, b = float(o.get("time_start_s")), float(o.get("time_end_s"))
        except (TypeError, ValueError):
            bad.append({**o, "reason": "no usable time"}); continue
        if a < 0 or b < a:
            bad.append({**o, "reason": "time range invalid"}); continue
        if duration_s and a > duration_s + 1:
            bad.append({**o, "reason": f"time {a:g}s is after the end of the video ({duration_s:g}s)"}); continue
        if o.get("category") not in CATEGORIES:
            bad.append({**o, "reason": "unknown category"}); continue
        ok.append({**o, "time_start_s": a, "time_end_s": b, "origin": "ai_vision",
                   "time_note": "approximate time given by the model; check the clip"})
    return ok, bad


def extract_frame(video: Path, at_s: float, out: Path) -> Path | None:
    """One still frame for display (needs ffmpeg). Returns None when ffmpeg is not installed."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(at_s, 0):.2f}", "-i", str(video),
                    "-frames:v", "1", "-vf", "scale=640:-2", str(out)], check=True, timeout=60)
    return out if out.exists() else None


# --- helpers -------------------------------------------------------------------------------------------------
def _num(v):
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def clean_meta(meta: dict) -> dict:
    def s(k, n=120):
        v = (meta.get(k) or "").strip() if isinstance(meta.get(k), str) else meta.get(k)
        return str(v)[:n] if v not in (None, "") else None
    zone = s("zone", 20)
    if zone and zone not in ZONE_LABELS:
        raise ValueError(f"unknown zone {zone}; use one of {', '.join(ZONE_LABELS)}")
    rec_at = s("recorded_at", 40)
    if rec_at:
        try:
            d = datetime.fromisoformat(rec_at)
            rec_at = (d if d.tzinfo else d.replace(tzinfo=LOCAL_TZ)).isoformat(timespec="minutes")
        except ValueError:
            raise ValueError("recorded_at must be a date/time like 2026-10-20T09:30") from None
    return {"zone": zone, "floor": s("floor", 40), "area": s("area"), "room": s("room"), "recorded_at": rec_at,
            "recorded_at_source": "entered_by_user" if rec_at else "unknown", "note": s("note", 500)}


def _age_days(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return round((datetime.now(LOCAL_TZ) - datetime.fromisoformat(iso)).total_seconds() / 86400, 1)
    except ValueError:
        return None


def recording_note(v: dict) -> str:
    if not v.get("recorded_at"):
        return "Recording date unknown: treat what the video shows as of an unknown date."
    age = v.get("age_days")
    base = f"Shows the situation on {v['recorded_at'][:10]} only, not the current state."
    if v.get("recorded_at_source") == "mp4_metadata":
        base += " Date read from the video file's own metadata (camera clock, not verified)."
    return base + (f" Recorded {age:g} days ago." if age is not None and age > OLD_VIDEO_DAYS else "")


# --- MP4 header reading (no ffmpeg needed) ------------------------------------------------------------------------
_MP4_EPOCH = datetime(1904, 1, 1, tzinfo=__import__("datetime").timezone.utc)


def mp4_info(path: Path) -> dict:
    """Creation time and duration from the MP4 'mvhd' box. Creation time is what the camera wrote (usually UTC);
    0 means not set. Returns {} when the file cannot be parsed."""
    import struct
    try:
        with open(path, "rb") as f:
            end = path.stat().st_size

            def boxes(start, stop):
                pos = start
                while pos + 8 <= stop:
                    f.seek(pos)
                    size, typ = struct.unpack(">I4s", f.read(8))
                    head = 8
                    if size == 1:
                        size, head = struct.unpack(">Q", f.read(8))[0], 16
                    elif size == 0:
                        size = stop - pos
                    if size < head:
                        return
                    yield typ, pos + head, pos + size
                    pos += size
            for typ, a, b in boxes(0, end):
                if typ != b"moov":
                    continue
                for t2, a2, b2 in boxes(a, b):
                    if t2 != b"mvhd":
                        continue
                    f.seek(a2)
                    version = f.read(1)[0]
                    f.read(3)
                    if version == 1:
                        ctime, _m, scale, dur = struct.unpack(">QQIQ", f.read(28))
                    else:
                        ctime, _m, scale, dur = struct.unpack(">IIII", f.read(16))
                    out = {"duration_s": round(dur / scale, 1) if scale else None}
                    if ctime:
                        from datetime import timedelta as _td
                        out["creation_time"] = (_MP4_EPOCH + _td(seconds=ctime)).astimezone(LOCAL_TZ).isoformat(timespec="minutes")
                    return out
    except (OSError, ValueError, IndexError, Exception):
        return {}
    return {}
