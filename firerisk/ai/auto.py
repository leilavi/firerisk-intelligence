"""Automatic Muse Spark analysis of fire-risk alerts, in the background. ORIGIN: NEW.

Flow (the alert never waits for the AI):
  rules create / update the fire-risk alert -> alert shown immediately -> eligible alerts are queued ->
  one background worker calls Muse Spark -> result validated (cited evidence IDs must exist) -> stored.

When is an alert analysed automatically?
  * its evidence fingerprint (ai/investigation.fingerprint) has no successful analysis yet - i.e. a new alert or
    evidence that changed (records added/removed, status/resolution changed, level changed);
  * its rule level is at least FIRERISK_AI_MIN_LEVEL (default: watch = every fire-risk alert);
  * fewer than FIRERISK_AI_DAILY_LIMIT automatic calls today (default 20) - protects the API credit;
  * a failed attempt is retried automatically once, after 15 minutes; then only on request.
Reloading the dashboard never queues anything: queuing happens only after an analysis run (start-up, the
"Update" button, a Drive update) or when the user asks for a re-analysis.
"""

from __future__ import annotations

import threading
import traceback
from collections import deque
from datetime import datetime, timedelta
from urllib.parse import urlparse

from ..config import LOCAL_TZ, SEVERITY_ORDER
from ..env import load_env
from .investigation import fingerprint, investigate
from .muse import MuseClient, MuseConfig

STATE_LABELS = {   # (label, longer description) - English UI since 2026-10-28 (author request)
    "not_analysed": ("Not Analysed by AI", "Muse Captain has not analysed the current evidence yet"),
    "running": ("AI Analysis Running", "Muse Captain is analysing the evidence"),
    "done": ("AI Analysis Complete", "Muse Captain analysed the current evidence"),
    "failed": ("AI Analysis Failed", "The last Muse Captain analysis failed; the rule-based explanation is shown"),
    "fallback": ("Rule-Based Explanation", "The explanation comes from the rule set, not from AI"),
}
RETRY_AFTER = timedelta(minutes=15)
MAX_AUTO_RETRIES = 1


def _rank(s: str) -> int:
    return SEVERITY_ORDER.index(s)


class AutoAnalyst:
    def __init__(self, store, get_result, client_factory=MuseClient):
        self.store = store
        self.get_result = get_result            # () -> AnalysisResult (latest)
        self.client_factory = client_factory
        self.cv = threading.Condition()
        self.queue: deque[tuple[str, str]] = deque()   # (alert_id, trigger)
        self.pending: dict[str, dict] = {}              # alert_id -> {"trigger", "queued_at", "running"}
        self.skipped: dict[str, str] = {}               # alert_id -> reason it was not queued (for the UI)
        self.thread: threading.Thread | None = None

    # --- settings ---------------------------------------------------------------------------
    @staticmethod
    def settings() -> dict:
        env = load_env()
        try:
            limit = int(env.get("FIRERISK_AI_DAILY_LIMIT", "20"))
        except ValueError:
            limit = 20
        lvl = env.get("FIRERISK_AI_MIN_LEVEL", "watch")
        return {"enabled": env.get("FIRERISK_AUTO_AI", "1") != "0", "daily_limit": max(0, limit),
                "min_level": lvl if lvl in SEVERITY_ORDER else "watch"}

    # --- decisions ----------------------------------------------------------------------------
    def _decide(self, alert, fp: str, now: datetime, cfg: dict) -> str | None:
        """Returns None when the alert should be queued, otherwise the reason it is not."""
        if not cfg["enabled"]:
            return "automatic AI analysis is switched off (FIRERISK_AUTO_AI=0)"
        if not MuseConfig.load().configured:
            return "Muse Captain is not configured (no MODEL_API_KEY)"
        if _rank(alert.severity) < _rank(cfg["min_level"]):
            return f"level below FIRERISK_AI_MIN_LEVEL ({cfg['min_level']})"
        attempts = self.store.ai_attempts(alert.alert_id, fp)
        if any(a["status"] == "ok" for a in attempts):
            return "already analysed for this evidence"
        failed = [a for a in attempts if a["status"] != "ok"]
        if len(failed) > MAX_AUTO_RETRIES:
            return "automatic attempts used up for this evidence; use Re-analyse"
        if failed and now - datetime.fromisoformat(failed[-1]["created_at"]) < RETRY_AFTER:
            return "last attempt failed less than 15 minutes ago"
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        if self.store.auto_runs_since(day_start) + self._queued_auto() >= cfg["daily_limit"]:
            return f"daily limit of automatic analyses reached ({cfg['daily_limit']})"
        return None

    def _queued_auto(self) -> int:
        return sum(1 for p in self.pending.values() if p["trigger"] == "auto")

    def schedule(self, res, now: datetime | None = None) -> list[str]:
        """Called after each analysis run. Queues eligible fire-risk alerts; returns the queued alert IDs."""
        now = now or datetime.now(LOCAL_TZ)
        cfg = self.settings()
        queued = []
        with self.cv:
            for a in res.alerts:
                if a.alert_id in self.pending:
                    continue
                fp = fingerprint(a, res.evidence, res.equipment_alerts)
                reason = self._decide(a, fp, now, cfg)
                if reason:
                    self.skipped[a.alert_id] = reason
                    continue
                self.skipped.pop(a.alert_id, None)
                self._enqueue(a.alert_id, "auto", now)
                queued.append(a.alert_id)
        return queued

    def request(self, alert_id: str, trigger: str = "button") -> dict:
        """User asked for (re-)analysis: queued even if this evidence was analysed before."""
        if not MuseConfig.load().configured:
            return {"queued": False, "reason": "Muse Captain is not configured (no MODEL_API_KEY)"}
        with self.cv:
            if alert_id not in self.pending:
                self._enqueue(alert_id, trigger, datetime.now(LOCAL_TZ))
        return {"queued": True}

    def _enqueue(self, alert_id: str, trigger: str, now: datetime) -> None:
        self.pending[alert_id] = {"trigger": trigger, "queued_at": now.isoformat(), "running": False}
        self.queue.append((alert_id, trigger))
        self._ensure_thread()
        self.cv.notify()

    def _ensure_thread(self) -> None:
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._loop, name="muse-auto", daemon=True)
            self.thread.start()

    # --- worker ----------------------------------------------------------------------------------
    def _loop(self) -> None:
        while True:
            with self.cv:
                while not self.queue:
                    self.cv.wait()
                alert_id, trigger = self.queue.popleft()
                if alert_id in self.pending:
                    self.pending[alert_id]["running"] = True
            try:
                self.run_one(alert_id, trigger)
            except Exception:   # never let the worker die; the failure is stored by run_one when possible
                traceback.print_exc()
            finally:
                with self.cv:
                    self.pending.pop(alert_id, None)
                    self.cv.notify_all()

    def run_one(self, alert_id: str, trigger: str) -> dict | None:
        res = self.get_result()
        alert = next((a for a in res.alerts if a.alert_id == alert_id), None)
        if alert is None:
            return None
        client = self.client_factory()
        rec = investigate(alert, res.signals, res.evidence, datetime.now(LOCAL_TZ), client, res.equipment_alerts)
        rec["trigger"] = trigger
        rec["base_url"] = client.config.base_url
        rec["api_mode"] = "live" if urlparse(client.config.base_url).hostname == "api.meta.ai" else "test"
        rec["id"] = self.store.save_investigation(rec)
        return rec

    def wait_idle(self, timeout: float = 30) -> bool:
        """For tests: wait until the queue is empty and nothing is running."""
        end = datetime.now().timestamp() + timeout
        with self.cv:
            while self.pending:
                left = end - datetime.now().timestamp()
                if left <= 0:
                    return False
                self.cv.wait(left)
        return True

    # --- status shown in the UI -------------------------------------------------------------------
    def status(self, alert, res) -> dict:
        fp = fingerprint(alert, res.evidence, res.equipment_alerts)
        configured = MuseConfig.load().configured
        latest_ok = self.store.latest_investigation(alert.alert_id, only_ok=True)
        latest_any = self.store.latest_investigation(alert.alert_id)
        current_ok = latest_ok if latest_ok and latest_ok.get("fingerprint") == fp else None
        if alert.alert_id in self.pending:
            code = "running"
        elif current_ok:
            code = "done"
        elif latest_any and latest_any.get("fingerprint") == fp and latest_any.get("status") != "ok":
            code = "failed"
        else:
            code = "not_analysed"
        fallback = current_ok is None
        vi, en = STATE_LABELS[code]
        out = {"code": code, "label": vi, "label_en": en, "fallback": fallback,
               "fallback_label": STATE_LABELS["fallback"][0] if fallback else None,
               "fallback_label_en": STATE_LABELS["fallback"][1] if fallback else None,
               "configured": configured, "fingerprint": fp,
               "result_is_current": current_ok is not None,
               "shown_result_created_at": latest_ok["created_at"] if latest_ok else None,
               "api_mode": (latest_ok or {}).get("api_mode") or (
                   "test" if latest_ok and urlparse(latest_ok.get("base_url") or "https://api.meta.ai").hostname != "api.meta.ai"
                   else "live" if latest_ok else None),
               "shown_result_outdated": bool(latest_ok and not current_ok),
               "not_queued_reason": None if code in ("running", "done") else self.skipped.get(alert.alert_id)}
        if code == "failed":
            out["error"] = {"kind": latest_any.get("error_kind"), "message": (latest_any.get("error") or "")[:300]}
        if code == "running":
            out["queued_at"] = self.pending.get(alert.alert_id, {}).get("queued_at")
        return out
