"""Visual localization of Muse Spark video items with SAM 3.1. ORIGIN: NEW (2026-10-28, Hackathon).

Flow:  Muse Spark observation / finding -> segment_phrase -> 1-3 still frames from the original video
       -> SAM 3.1 boxes + masks -> stored in `video_finding_locations` -> dashboard overlay.

Rules this module keeps (and tests check):
  * Localization is supporting visual evidence. It never creates, removes or changes an alert, a severity, a rule
    result or the Muse Spark record. Original analysis records are never modified; phrases and locations live in
    their own tables.
  * Items = the findings AND observations of the LATEST successful Muse Spark analysis of each video (what the
    dashboard shows). Superseded analyses are not localized.
  * An item that describes an absence, or has no specific visible object, gets no phrase and is `not_applicable`.
  * Frame-level results are kept. Item status: located (any frame located) / not_located (every frame answered,
    none located) / error (no frame located and at least one request failed) / not_applicable / not_checked.
  * Idempotent: one row per fingerprint sha256(video sha256 | analysis id | item kind | item index | phrase | frame
    time). A SAM answer for the same video bytes + phrase + frame time is reused instead of calling the API again.
  * Daily request limit (FIRERISK_SAM_DAILY_LIMIT, default 300). Over the limit, work stays pending - never dropped.
  * Frames are private files under data/private/media/frames/ (git-ignored).

Pricing (official page dev.meta.ai/docs/pricing-rate-limits, read 2026-10-28): image segmentation $2.50 per 1,000
images; sam-3.1 rate limit 3,000 requests per minute per team.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from .config import LOCAL_TZ
from .sam import (SamAuthError, SamBadRequest, SamRateLimited, SamClient, SamError, SamModelNotFound, SamNotConfigured,
                  phrase_problem)

ROOT = Path(__file__).resolve().parent.parent
FRAMES_DIR = Path(os.environ.get("FIRERISK_FRAMES_DIR", ROOT / "data" / "private" / "media" / "frames"))
PRICE_PER_IMAGE_USD = 2.50 / 1000          # docs/pricing-rate-limits, read 2026-10-28
DEFAULT_DAILY_LIMIT = 300
FRAMES_PER_ITEM = 3
FRAME_MAX_SIDE = 1280
MAX_ATTEMPTS = 3                            # per frame fingerprint, retryable errors only
PHRASE_PROMPT_VERSION = "segment-phrase-v1"
STOP_BATCH = (SamNotConfigured, SamAuthError, SamModelNotFound, SamRateLimited)   # no point continuing with other frames

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS finding_phrases (
  analysis_id INTEGER NOT NULL, item_kind TEXT NOT NULL, item_index INTEGER NOT NULL,
  segment_phrase TEXT NOT NULL, phrase_source TEXT NOT NULL, applicable INTEGER NOT NULL, reason TEXT,
  created_at TEXT NOT NULL, PRIMARY KEY (analysis_id, item_kind, item_index));
CREATE TABLE IF NOT EXISTS video_finding_locations (
  id INTEGER PRIMARY KEY AUTOINCREMENT, fingerprint TEXT NOT NULL UNIQUE,
  analysis_id INTEGER NOT NULL, video_id TEXT NOT NULL, video_sha256 TEXT NOT NULL,
  item_kind TEXT NOT NULL, finding_index INTEGER NOT NULL, segment_phrase TEXT NOT NULL, phrase_source TEXT NOT NULL,
  frame_time_s REAL NOT NULL, frame_file TEXT, frame_w INTEGER, frame_h INTEGER,
  status TEXT NOT NULL, objects_json TEXT, max_confidence REAL, model TEXT, request_seconds REAL,
  frames_billed INTEGER, reused_from INTEGER, error_kind TEXT, error TEXT, attempts INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS vfl_item ON video_finding_locations (analysis_id, item_kind, finding_index);
CREATE INDEX IF NOT EXISTS vfl_reuse ON video_finding_locations (video_sha256, segment_phrase, frame_time_s);
CREATE TABLE IF NOT EXISTS localizer_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

# --- fallback phrases: fixed, documented, conservative ------------------------------------------------------
# Used only when the Muse Spark derivation fails. A phrase is chosen only when the item's own text names the
# object (keyword) AND the category fits; otherwise no phrase (never a guess from the category alone).
CATEGORY_MAP: list[tuple[set[str], tuple[str, ...], str]] = [
    ({"extinguishers_first_aid", "fire_equipment"}, ("extinguisher",), "fire extinguisher"),
    ({"extinguishers_first_aid", "fire_equipment", "suppression_smoke_control"}, ("hose reel",), "hose reel"),
    ({"detection_alarm", "fire_detection_or_alarm", "fire_equipment"}, ("smoke detector",), "smoke detector"),
    ({"detection_alarm", "fire_detection_or_alarm", "fire_equipment"}, ("alarm panel", "fire alarm panel"),
     "fire alarm panel"),
    ({"suppression_smoke_control", "fire_equipment"}, ("fire pump",), "pump"),
    ({"suppression_smoke_control", "fire_equipment"}, ("sprinkler",), "sprinkler"),
    ({"ignition_source", "electrical_equipment", "water_moisture_electrical"},
     ("switchboard", "electrical panel", "distribution board", "control panel", "cabinet"), "electrical panel"),
    ({"ignition_source", "electrical_equipment", "water_moisture_electrical"}, ("cable tray",), "cable tray"),
    ({"ignition_source", "electrical_equipment"}, ("transformer",), "transformer"),
    ({"ignition_source", "electrical_equipment"}, ("generator",), "generator"),
    ({"egress_access", "exit_or_escape_route", "signage_or_emergency_lighting"}, ("exit sign",), "exit sign"),
    ({"combustibles_housekeeping", "storage_or_combustibles", "obstruction"}, ("cardboard box", "carton"),
     "cardboard box"),
]
_ABSENCE = re.compile(r"\b(no|not visible|missing|absent|without|none|lack(?:ing)?|not present|could not see)\b", re.I)


def category_phrase(item: dict) -> str | None:
    text = " ".join(str(item.get(k) or "") for k in ("title", "what_is_visible", "observation")).lower()
    for cats, keys, phrase in CATEGORY_MAP:
        if item.get("category") in cats and any(k in text for k in keys):
            return phrase
    return None


def items_of(analysis: dict) -> list[dict]:
    """The localizable items of one analysis record: v2 findings, then observations, with their original index."""
    out = []
    for kind, key in (("finding", "findings"), ("observation", "observations")):
        for i, it in enumerate(analysis.get(key) or []):
            if not isinstance(it, dict):
                continue
            out.append({"kind": kind, "index": i, "category": it.get("category"),
                        "title": it.get("title") or "",
                        "what_is_visible": it.get("what_is_visible") or it.get("observation") or "",
                        "time_start_s": it.get("time_start_s"), "time_end_s": it.get("time_end_s"),
                        "segment_phrase": it.get("segment_phrase"), "has_phrase_field": "segment_phrase" in it})
    return out


# --- Muse Spark phrase derivation for items analysed before segment_phrase existed -----------------------------
PHRASE_SCHEMA = {
    "name": "SegmentPhrases", "strict": True,
    "schema": {"type": "object", "additionalProperties": False, "required": ["items"], "properties": {
        "items": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["ref", "applicable", "segment_phrase", "reason"],
            "properties": {"ref": {"type": "string"}, "applicable": {"type": "boolean"},
                           "segment_phrase": {"type": "string"}, "reason": {"type": "string"}}}}}}}

PHRASE_SYSTEM = """You prepare text prompts for an image segmentation model (SAM 3.1).
For each building-survey item, give ONE short English noun phrase (1-3 words, lower case) naming the single visible
physical object the item is about, e.g. "fire extinguisher", "electrical panel", "smoke detector", "cable tray",
"cardboard box". No sentences, no adjectives about condition, no locations, no lists, no people.
Set applicable=false and segment_phrase="" when the item describes something ABSENT or not visible (e.g. "no
extinguisher seen"), a general area or room, a condition without one specific object, or people.
Use only the text given. Do not invent objects. reason: a few words."""


def derive_phrases_muse(client, items: list[dict]) -> dict[tuple[str, int], dict]:
    """One structured Muse Spark text request per batch; returns {(kind, index): {phrase, applicable, reason}}."""
    out: dict[tuple[str, int], dict] = {}
    for start in range(0, len(items), 30):
        batch = items[start:start + 30]
        lines = [{"ref": f"{it['kind'][0]}{it['index']}", "category": it.get("category"),
                  "title": (it.get("title") or "")[:200], "what_is_visible": (it.get("what_is_visible") or "")[:400]}
                 for it in batch]
        res = client.chat_json(PHRASE_SYSTEM, json.dumps({"items": lines}, ensure_ascii=False), PHRASE_SCHEMA,
                               reasoning_effort="low", max_completion_tokens=4000)
        by_ref = {f"{it['kind'][0]}{it['index']}": it for it in batch}
        for r in (res.data or {}).get("items") or []:
            it = by_ref.get(r.get("ref"))
            if it:
                out[(it["kind"], it["index"])] = {"phrase": (r.get("segment_phrase") or "").strip().lower(),
                                                  "applicable": bool(r.get("applicable")),
                                                  "reason": (r.get("reason") or "")[:200]}
    return out


# --- frames ----------------------------------------------------------------------------------------------------
def sample_times(start, end, duration: float | None, n: int = FRAMES_PER_ITEM) -> list[float]:
    """Up to n frame times near the beginning, middle and end of [start, end], clamped to the video length."""
    def clamp(t: float) -> float:
        t = max(0.0, t)
        if duration:
            t = min(t, max(duration - 0.1, 0.0))
        return round(t, 1)
    try:
        a, b = float(start), float(end)
    except (TypeError, ValueError):
        a = b = None
    if a is None or a < 0 or (duration and a > duration):
        if not duration:
            return []
        a, b = 0.0, duration                              # no usable interval: middle of the video
        return [clamp((a + b) / 2)]
    if b is None or b < a:
        b = a
    if duration:
        b = min(b, duration)
    if b - a < 1.0:
        return [clamp((a + b) / 2)]
    ts = [clamp(a + (b - a) * f) for f in ((0.15, 0.5, 0.85) if n >= 3 else (0.5,))]
    return sorted(set(ts))


def frame_path(video_sha: str, t: float) -> Path:
    return FRAMES_DIR / video_sha[:16] / f"t{int(round(t * 10)):06d}.jpg"


def extract_still(video: Path, t: float, out: Path, ffmpeg: str | None = None) -> Path:
    """One upright JPEG frame (ffmpeg autorotate on), long side <= 1280 px. Reuses an existing file."""
    if out.exists() and out.stat().st_size > 0:
        return out
    from .video import ffmpeg_path
    ff = ffmpeg or ffmpeg_path()
    if not ff:
        raise FrameError("ffmpeg is not available (run install.bat)")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part.jpg")
    scale = (f"scale=w='if(gte(iw,ih),min({FRAME_MAX_SIDE},iw),-2)':"
             f"h='if(gte(iw,ih),-2,min({FRAME_MAX_SIDE},ih))'")
    try:
        subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(t, 0):.2f}", "-i", str(video),
                        "-frames:v", "1", "-vf", scale, "-q:v", "3", str(tmp)], check=True, timeout=120,
                       capture_output=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as err:
        tmp.unlink(missing_ok=True)
        raise FrameError(f"frame extraction failed at {t:.1f}s: {type(err).__name__}") from None
    if not tmp.exists() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        raise FrameError(f"no frame at {t:.1f}s")
    tmp.replace(out)
    return out


class FrameError(Exception):
    kind = "frame_extraction"


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        if data[i + 1] in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
        i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
    return None


def fingerprint(video_sha: str, analysis_id: int, kind: str, index: int, phrase: str, t: float) -> str:
    return hashlib.sha256(f"{video_sha}|{analysis_id}|{kind}|{index}|{phrase}|{t:.1f}".encode()).hexdigest()


# --- settings --------------------------------------------------------------------------------------------------
def sam_settings() -> dict:
    from .env import load_env
    env = load_env()
    try:
        limit = int(env.get("FIRERISK_SAM_DAILY_LIMIT", DEFAULT_DAILY_LIMIT))
    except ValueError:
        limit = DEFAULT_DAILY_LIMIT
    return {"auto": env.get("FIRERISK_AUTO_SAM", "1") != "0", "daily_limit": max(0, limit)}


def now_iso() -> str:
    return datetime.now(LOCAL_TZ).isoformat(timespec="seconds")


# --- store + worker --------------------------------------------------------------------------------------------
class Localizer:
    """Historical backfill (scripts/locate_video_findings.py) and continuous processing (dashboard, after each new
    Muse Spark analysis) both use this one class, the same client, parser, tables and duplicate rules."""

    def __init__(self, db_path: Path, videos, frames_dir: Path | None = None):
        self.db_path, self.videos = db_path, videos
        self.frames_dir = frames_dir
        with self._conn() as c:
            c.executescript(SCHEMA_SQL)
            # Continuous processing covers analyses made after SAM was installed; older ones are the historical
            # backlog, processed only by scripts/locate_video_findings.py (dry run + cost estimate first).
            if not c.execute("SELECT 1 FROM localizer_meta WHERE key='auto_from_analysis_id'").fetchone():
                has = c.execute("SELECT name FROM sqlite_master WHERE name='video_analyses'").fetchone()
                last = c.execute("SELECT COALESCE(MAX(id),0) FROM video_analyses").fetchone()[0] if has else 0
                c.execute("INSERT INTO localizer_meta VALUES ('auto_from_analysis_id', ?)", (str(last),))
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.status: dict = {"state": "idle"}
        self._again = False

    def _conn(self):
        c = sqlite3.connect(self.db_path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def _frame_path(self, sha: str, t: float) -> Path:
        if self.frames_dir:
            return self.frames_dir / sha[:16] / f"t{int(round(t * 10)):06d}.jpg"
        return frame_path(sha, t)

    # targets ---------------------------------------------------------------------------------------------------
    def auto_boundary(self) -> int:
        with self._conn() as c:
            r = c.execute("SELECT value FROM localizer_meta WHERE key='auto_from_analysis_id'").fetchone()
        return int(r[0]) if r else 0

    def targets(self, scope: str = "all") -> list[tuple[dict, dict]]:
        """(video, latest ok analysis) for every registered video with a successful analysis.
        scope="new": only analyses newer than the backlog boundary (continuous processing)."""
        lo = self.auto_boundary() if scope == "new" else 0
        out = []
        for v in self.videos.list():
            ana = self.videos.latest_analysis(v["video_id"], only_ok=True)
            if ana and ana["id"] > lo:
                out.append((v, ana))
        return out

    # phrases ---------------------------------------------------------------------------------------------------
    def phrases(self, analysis_id: int) -> dict[tuple[str, int], dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM finding_phrases WHERE analysis_id=?", (analysis_id,)).fetchall()
        return {(r["item_kind"], r["item_index"]): dict(r) for r in rows}

    def _save_phrase(self, analysis_id, kind, index, phrase, source, applicable, reason) -> None:
        with self._conn() as c:
            c.execute("INSERT OR IGNORE INTO finding_phrases VALUES (?,?,?,?,?,?,?,?)",
                      (analysis_id, kind, index, phrase or "", source, 1 if applicable else 0, reason, now_iso()))

    def ensure_phrases(self, analysis: dict, muse_client=None, dry_run: bool = False) -> dict[tuple[str, int], dict]:
        """Phrase for every item of one analysis: from the record (spark_v2), else Muse Spark (spark_derived), else
        the fixed map (category_map). Items with no phrase source left get none (not guessed). Existing phrase rows
        are never changed. In dry_run nothing is written and Muse is not called."""
        aid = analysis["id"]
        have = self.phrases(aid)
        items = [it for it in items_of(analysis) if (it["kind"], it["index"]) not in have]
        planned: dict[tuple[str, int], dict] = {}
        need_muse = []
        for it in items:
            key = (it["kind"], it["index"])
            if it["has_phrase_field"]:                      # analysed with the segment_phrase schema
                p = (it["segment_phrase"] or "").strip().lower()
                prob = phrase_problem(p) if p else "no visible object"
                planned[key] = {"segment_phrase": p if not prob else "", "phrase_source": "spark_v2",
                                "applicable": not prob, "reason": prob or ""}
            else:
                need_muse.append(it)
        derived = {}
        if need_muse and muse_client is not None and not dry_run:
            try:
                derived = derive_phrases_muse(muse_client, need_muse)
            except Exception as err:                        # Muse failure -> fixed map below
                derived = {}
                self.status["phrase_error"] = f"{getattr(err, 'kind', type(err).__name__)}"
        for it in need_muse:
            key = (it["kind"], it["index"])
            d = derived.get(key)
            rejected = None
            if d is not None:
                if not d["applicable"]:
                    planned[key] = {"segment_phrase": "", "phrase_source": "spark_derived", "applicable": False,
                                    "reason": d["reason"] or "no visible object"}
                    continue
                rejected = phrase_problem(d["phrase"])
                if not rejected:
                    planned[key] = {"segment_phrase": d["phrase"], "phrase_source": "spark_derived",
                                    "applicable": True, "reason": d["reason"]}
                    continue
            # Derivation failed, was not possible, or its phrase broke the rules: fixed documented map.
            if dry_run:     # a real run asks Muse Spark first; the fixed map is only its fallback
                planned[key] = {"segment_phrase": "", "phrase_source": "pending_derivation", "applicable": None,
                                "reason": "Muse Spark (text only) would be asked for a phrase"}
                continue
            m = category_phrase(it)
            if m and not _ABSENCE.search(it.get("title") or ""):
                planned[key] = {"segment_phrase": m, "phrase_source": "category_map", "applicable": True,
                                "reason": "fixed map: object named in the item text"}
            elif rejected:
                planned[key] = {"segment_phrase": "", "phrase_source": "spark_derived", "applicable": False,
                                "reason": f"phrase not usable for SAM ({rejected})"}
            # else: Muse Spark unavailable and no safe fixed phrase -> no row; retried on a later run.
        if not dry_run:
            for (kind, idx), p in planned.items():
                self._save_phrase(aid, kind, idx, p["segment_phrase"], p["phrase_source"], p["applicable"],
                                  p["reason"])
            return self.phrases(aid)
        merged = {k: {**v, "item_kind": k[0], "item_index": k[1]} for k, v in planned.items()}
        merged.update(have)
        return merged

    # planning --------------------------------------------------------------------------------------------------
    def plan(self, muse_client=None, dry_run: bool = False, scope: str = "all") -> dict:
        """Every frame job for the current targets, marking which are already done."""
        jobs, summary = [], {"videos": 0, "items": 0, "eligible": 0, "not_applicable": 0, "phrase_pending": 0,
                             "frames": 0, "frames_done": 0, "frames_to_request": 0, "frames_reusable": 0,
                             "frames_if_pending_phrases_apply": 0}
        for v, ana in self.targets(scope):
            summary["videos"] += 1
            phr = self.ensure_phrases(ana, muse_client, dry_run=dry_run)
            for it in items_of(ana):
                summary["items"] += 1
                p = phr.get((it["kind"], it["index"]))
                if not p or p.get("applicable") is None:
                    summary["phrase_pending"] += 1
                    summary["frames_if_pending_phrases_apply"] += len(
                        sample_times(it["time_start_s"], it["time_end_s"], v.get("duration_s")))
                    continue
                if not p["applicable"]:
                    summary["not_applicable"] += 1
                    continue
                summary["eligible"] += 1
                for t in sample_times(it["time_start_s"], it["time_end_s"], v.get("duration_s")):
                    fp = fingerprint(v["sha256"], ana["id"], it["kind"], it["index"], p["segment_phrase"], t)
                    job = {"fingerprint": fp, "video": v, "analysis_id": ana["id"], "item": it,
                           "phrase": p["segment_phrase"], "phrase_source": p["phrase_source"], "t": t}
                    summary["frames"] += 1
                    state = self._job_state(job)
                    if state == "done":
                        summary["frames_done"] += 1
                        continue
                    if state == "reusable":
                        summary["frames_reusable"] += 1
                    else:
                        summary["frames_to_request"] += 1
                    jobs.append(job)
        summary["estimated_cost_usd"] = round(summary["frames_to_request"] * PRICE_PER_IMAGE_USD, 4)
        summary["estimated_cost_upper_bound_usd"] = round(
            (summary["frames_to_request"] + summary["frames_if_pending_phrases_apply"]) * PRICE_PER_IMAGE_USD, 4)
        cfg = sam_settings()
        used = self.requests_today()
        summary.update({"daily_limit": cfg["daily_limit"], "requests_today": used,
                        "requests_allowed_today": max(0, cfg["daily_limit"] - used),
                        "price_per_image_usd": PRICE_PER_IMAGE_USD})
        return {"jobs": jobs, "summary": summary}

    def _job_state(self, job) -> str:
        with self._conn() as c:
            r = c.execute("SELECT status, error_kind, attempts FROM video_finding_locations WHERE fingerprint=?",
                          (job["fingerprint"],)).fetchone()
            if r and (r["status"] in ("located", "not_located") or r["attempts"] >= MAX_ATTEMPTS
                      or r["error_kind"] in ("bad_request", "frame_extraction")):
                return "done"
            if self._reusable(c, job):
                return "reusable"
        return "todo"

    def _reusable(self, c, job):
        return c.execute("SELECT * FROM video_finding_locations WHERE video_sha256=? AND segment_phrase=? AND "
                         "frame_time_s=? AND status IN ('located','not_located') AND reused_from IS NULL "
                         "ORDER BY id LIMIT 1", (job["video"]["sha256"], job["phrase"], job["t"])).fetchone()

    def requests_today(self) -> int:
        day = datetime.now(LOCAL_TZ).date().isoformat()
        with self._conn() as c:
            return c.execute("SELECT COALESCE(SUM(attempts),0) FROM video_finding_locations WHERE updated_at >= ?",
                             (day,)).fetchone()[0]

    # execution -------------------------------------------------------------------------------------------------
    def _write(self, job, **f) -> None:
        now = now_iso()
        v, it = job["video"], job["item"]
        with self._conn() as c:
            old = c.execute("SELECT id, attempts FROM video_finding_locations WHERE fingerprint=?",
                            (job["fingerprint"],)).fetchone()
            attempts = (old["attempts"] if old else 0) + f.pop("attempt", 0)
            cols = {"analysis_id": job["analysis_id"], "video_id": v["video_id"], "video_sha256": v["sha256"],
                    "item_kind": it["kind"], "finding_index": it["index"], "segment_phrase": job["phrase"],
                    "phrase_source": job["phrase_source"], "frame_time_s": job["t"], "attempts": attempts,
                    "updated_at": now, "objects_json": None, "max_confidence": None, "model": None,
                    "request_seconds": None, "frames_billed": None, "reused_from": None, "error_kind": None,
                    "error": None, "frame_file": None, "frame_w": None, "frame_h": None, **f}
            if old:
                c.execute("UPDATE video_finding_locations SET " + ",".join(f"{k}=?" for k in cols) +
                          " WHERE id=?", (*cols.values(), old["id"]))
            else:
                cols.update({"fingerprint": job["fingerprint"], "created_at": now})
                c.execute(f"INSERT INTO video_finding_locations ({','.join(cols)}) VALUES "
                          f"({','.join('?' * len(cols))})", tuple(cols.values()))

    def run(self, sam: SamClient | None = None, muse_client=None, max_requests: int | None = None,
            stop=None, scope: str = "all") -> dict:
        """Process pending frame jobs (one at a time). Returns counts. Never raises for API problems."""
        sam = sam or SamClient()
        plan = self.plan(muse_client, scope=scope)
        cfg = sam_settings()
        budget = max(0, cfg["daily_limit"] - self.requests_today())
        if max_requests is not None:
            budget = min(budget, max_requests)
        out = {"requested": 0, "reused": 0, "located": 0, "not_located": 0, "errors": 0, "deferred": 0,
               "stopped": None, "summary": plan["summary"]}
        if not sam.configured:
            out["stopped"] = "not_configured"
            out["deferred"] = len(plan["jobs"])
            return out
        for n, job in enumerate(plan["jobs"]):
            if stop and stop():
                out["stopped"] = "cancelled"
                out["deferred"] += len(plan["jobs"]) - n
                break
            with self._conn() as c:
                reuse = self._reusable(c, job)
            if reuse:
                self._write(job, status=reuse["status"], objects_json=reuse["objects_json"],
                            max_confidence=reuse["max_confidence"], model=reuse["model"], frame_file=reuse["frame_file"],
                            frame_w=reuse["frame_w"], frame_h=reuse["frame_h"], reused_from=reuse["id"])
                out["reused"] += 1
                out[reuse["status"]] += 1
                continue
            if out["requested"] >= budget:
                out["deferred"] += 1
                out["stopped"] = out["stopped"] or "daily_limit"
                continue
            self.status.update({"state": "running", "current": f"{job['video']['video_id']} {job['item']['kind']} "
                                f"#{job['item']['index']} @ {job['t']:.1f}s"})
            path = self._frame_path(job["video"]["sha256"], job["t"])
            try:
                src = self.videos.path(job["video"]["video_id"])
                if not src or not Path(src).exists():
                    raise FrameError("source video file is not on this computer")
                extract_still(Path(src), job["t"], path)
                data = path.read_bytes()
                size = jpeg_size(data) or (None, None)
            except FrameError as err:
                self._write(job, status="error", error_kind="frame_extraction", error=str(err)[:300])
                out["errors"] += 1
                continue
            rel = str(path.relative_to(path.parents[1])).replace("\\", "/")
            try:
                res = sam.locate(data, job["phrase"])
            except SamError as err:
                out["requested"] += 1
                self._write(job, status="error", error_kind=err.kind, error=str(err)[:300], attempt=1,
                            frame_file=rel, frame_w=size[0], frame_h=size[1])
                out["errors"] += 1
                if isinstance(err, STOP_BATCH):
                    out["stopped"] = err.kind
                    out["deferred"] += len(plan["jobs"]) - n - 1
                    break
                continue
            out["requested"] += 1
            objs = [o.as_dict() for o in res.parse.objects]
            for o in objs:
                o.pop("rle", None)
            fs = res.parse.frame_sizes.get(0)
            self._write(job, status=res.status, objects_json=json.dumps({
                "objects": objs, "frame_size": list(fs) if fs else list(size), "complete": res.parse.complete,
                "diagnostics": res.parse.diagnostics}), max_confidence=res.max_confidence, model=res.model,
                request_seconds=res.seconds, frames_billed=res.images_billed, attempt=1, frame_file=rel,
                frame_w=size[0], frame_h=size[1])
            out[res.status] += 1
        self.status = {"state": "idle", "last_run": now_iso(), "last_result": {k: v for k, v in out.items()
                                                                                 if k != "summary"}}
        return out

    # background (continuous processing) ------------------------------------------------------------------------
    def start(self, sam_factory=SamClient, muse_factory=None, scope: str = "new") -> bool:
        """Run pending localization in a background thread (one at a time). Returns False if already running."""
        if not sam_settings()["auto"]:
            return False
        with self.lock:
            if self.thread and self.thread.is_alive():
                self._again = True                    # another pass after this one (new work arrived)
                return False

            def loop():
                while True:
                    self._again = False
                    try:
                        self.run(sam_factory(), muse_factory() if muse_factory else None, scope=scope)
                    except Exception as err:     # never let localization stop the dashboard
                        self.status = {"state": "failed", "error": f"{type(err).__name__}", "last_run": now_iso()}
                    with self.lock:
                        if not self._again:
                            self.thread = None
                            break
            self.thread = threading.Thread(target=loop, name="sam-localize", daemon=True)
            self.status = {"state": "running"}
            self.thread.start()
            return True

    def counts(self) -> dict:
        """Item status counts over all current targets (dashboard / status endpoint)."""
        out: dict[str, int] = {}
        for _v, ana in self.targets():
            phr = self.phrases(ana["id"])
            for it in items_of(ana):
                st = self.item_result(ana["id"], it["kind"], it["index"])["status"]
                if st == "not_checked" and (it["kind"], it["index"]) not in phr:
                    st = "phrase_pending"
                out[st] = out.get(st, 0) + 1
        return out

    # reading (dashboard) ---------------------------------------------------------------------------------------
    def item_result(self, analysis_id: int, kind: str, index: int) -> dict:
        """Item-level status + frame-level rows for one Muse Spark item."""
        p = self.phrases(analysis_id).get((kind, index))
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM video_finding_locations WHERE analysis_id=? AND item_kind=? AND finding_index=? "
                "ORDER BY frame_time_s", (analysis_id, kind, index))]
        frames = []
        for r in rows:
            o = json.loads(r["objects_json"]) if r["objects_json"] else {}
            frames.append({"frame_time_s": r["frame_time_s"], "frame_file": r["frame_file"], "status": r["status"],
                           "frame_w": r["frame_w"], "frame_h": r["frame_h"], "objects": o.get("objects", []),
                           "frame_size": o.get("frame_size"), "max_confidence": r["max_confidence"],
                           "model": r["model"], "error_kind": r["error_kind"], "created_at": r["created_at"]})
        return {"segment_phrase": (p or {}).get("segment_phrase") or None,
                "phrase_source": (p or {}).get("phrase_source"),
                "status": item_status(p, frames), "frames": frames}


def item_status(phrase_row: dict | None, frames: list[dict]) -> str:
    if phrase_row is not None and not phrase_row.get("applicable"):
        return "not_applicable"
    if not frames:
        return "not_checked"
    if any(f["status"] == "located" for f in frames):
        return "located"
    if any(f["status"] == "error" for f in frames):
        return "error"
    return "not_located"
