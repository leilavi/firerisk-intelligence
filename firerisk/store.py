"""Local SQLite store: analysis runs, alert history, verification status, AI investigations.

ORIGIN: NEW (the skill used a Google Sheet "OPERATOR_Alert_Log" maintained by Claude; this app keeps
its own local log so it works without Claude). The database lives in data/private/ (never published).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

VERIFICATION_STATES = ["new", "acknowledged", "investigating", "confirmed", "resolved", "false_alarm"]
# "confirmed" = a person verified the hazard on site. Rules and AI never set it.

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS analysis_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, generated_at TEXT NOT NULL, source_status TEXT NOT NULL,
  alert_count INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS alert_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL, alert_id TEXT NOT NULL, severity TEXT NOT NULL,
  title TEXT NOT NULL, evidence_count INTEGER NOT NULL, open_items INTEGER NOT NULL, recorded_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alert_state (
  id INTEGER PRIMARY KEY AUTOINCREMENT, alert_id TEXT NOT NULL, status TEXT NOT NULL, note TEXT,
  changed_at TEXT NOT NULL, changed_by TEXT);
CREATE TABLE IF NOT EXISTS evidence_seen (
  evidence_id TEXT PRIMARY KEY, first_seen_at TEXT NOT NULL, record_time TEXT);
CREATE TABLE IF NOT EXISTS ai_investigations (
  id INTEGER PRIMARY KEY AUTOINCREMENT, alert_id TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL,
  model TEXT, record TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sync_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, ok INTEGER NOT NULL, changed INTEGER NOT NULL,
  trigger TEXT NOT NULL, report TEXT NOT NULL);
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._conn() as c:
            c.executescript(SCHEMA_SQL)

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    # --- analysis runs --------------------------------------------------------------
    def record_run(self, result) -> int:
        with self._conn() as c:
            cur = c.execute("INSERT INTO analysis_runs (generated_at, source_status, alert_count) VALUES (?,?,?)",
                            (result.generated_at.isoformat(), json.dumps(result.source_status, ensure_ascii=False),
                             len(result.alerts)))
            run_id = cur.lastrowid
            for a in result.alerts:
                c.execute("INSERT INTO alert_history (run_id, alert_id, severity, title, evidence_count, open_items, "
                          "recorded_at) VALUES (?,?,?,?,?,?,?)",
                          (run_id, a.alert_id, a.severity, a.title, len(a.evidence_ids), a.open_items,
                           result.generated_at.isoformat()))
                if not c.execute("SELECT 1 FROM alert_state WHERE alert_id=?", (a.alert_id,)).fetchone():
                    c.execute("INSERT INTO alert_state (alert_id, status, note, changed_at, changed_by) VALUES (?,?,?,?,?)",
                              (a.alert_id, "new", "first detected", result.generated_at.isoformat(), "system"))
            return run_id

    def mark_seen(self, result) -> list[dict]:
        """Record evidence IDs seen in this run. Returns records that arrived late: new in this run although their
        own timestamp is more than 1 day older than the previous run (data entered after the fact)."""
        from datetime import datetime as _dt, timedelta as _td
        late: list[dict] = []
        with self._conn() as c:
            prev = c.execute("SELECT generated_at FROM analysis_runs ORDER BY id DESC LIMIT 1 OFFSET 1").fetchone()
            prev_at = _dt.fromisoformat(prev["generated_at"]) if prev else None
            known = {r["evidence_id"] for r in c.execute("SELECT evidence_id FROM evidence_seen")}
            now = result.generated_at.isoformat()
            rows = []
            for e in result.evidence.values():
                if e.kind in ("meter_episode",) or e.evidence_id in known:
                    continue
                ts = e.timestamp.isoformat() if e.timestamp else None
                rows.append((e.evidence_id, now, ts))
                if prev_at and known and e.timestamp and e.timestamp < prev_at - _td(days=1):
                    late.append({"type": "late_arrival", "evidence_id": e.evidence_id, "record_time": ts,
                                 "first_seen_at": now, "previous_run_at": prev_at.isoformat()})
            c.executemany("INSERT OR IGNORE INTO evidence_seen VALUES (?,?,?)", rows)
        return late

    def alert_history(self, alert_id: str, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM alert_history WHERE alert_id=? ORDER BY id DESC LIMIT ?", (alert_id, limit))
            return [dict(r) for r in rows]

    # --- verification status -----------------------------------------------------------
    def set_status(self, alert_id: str, status: str, note: str | None, by: str | None) -> dict:
        if status not in VERIFICATION_STATES:
            raise ValueError(f"status must be one of {VERIFICATION_STATES}")
        now = datetime.now().astimezone().isoformat()
        with self._conn() as c:
            c.execute("INSERT INTO alert_state (alert_id, status, note, changed_at, changed_by) VALUES (?,?,?,?,?)",
                      (alert_id, status, note, now, by))
        return self.current_status(alert_id)

    def current_status(self, alert_id: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM alert_state WHERE alert_id=? ORDER BY id DESC LIMIT 1", (alert_id,)).fetchone()
            return dict(r) if r else None

    def first_detected(self, alert_id: str) -> str | None:
        with self._conn() as c:
            r = c.execute("SELECT changed_at FROM alert_state WHERE alert_id=? ORDER BY id LIMIT 1", (alert_id,)).fetchone()
            return r["changed_at"] if r else None

    def status_log(self, alert_id: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM alert_state WHERE alert_id=? ORDER BY id DESC", (alert_id,))]

    # --- AI investigations ----------------------------------------------------------------
    def save_investigation(self, record: dict) -> int:
        with self._conn() as c:
            cur = c.execute("INSERT INTO ai_investigations (alert_id, created_at, status, model, record) VALUES (?,?,?,?,?)",
                            (record["alert_id"], record["created_at"], record["status"], record.get("model"),
                             json.dumps(record, ensure_ascii=False)))
            return cur.lastrowid

    def latest_investigation(self, alert_id: str, only_ok: bool = False) -> dict | None:
        q = "SELECT * FROM ai_investigations WHERE alert_id=?" + (" AND status='ok'" if only_ok else "") + \
            " ORDER BY id DESC LIMIT 1"
        with self._conn() as c:
            r = c.execute(q, (alert_id,)).fetchone()
            if not r:
                return None
            rec = json.loads(r["record"])
            rec["id"] = r["id"]
            return rec

    def investigations(self, alert_id: str) -> list[dict]:
        with self._conn() as c:
            return [{"id": r["id"], "created_at": r["created_at"], "status": r["status"], "model": r["model"]}
                    for r in c.execute("SELECT id, created_at, status, model FROM ai_investigations WHERE alert_id=? "
                                       "ORDER BY id DESC", (alert_id,))]

    # --- Google Drive sync runs (reports never contain the token or the URL) -------------------
    def save_sync(self, report: dict, trigger: str) -> int:
        with self._conn() as c:
            cur = c.execute("INSERT INTO sync_runs (started_at, ok, changed, trigger, report) VALUES (?,?,?,?,?)",
                            (report["started_at"], int(bool(report.get("ok"))), int(bool(report.get("changed"))),
                             trigger, json.dumps(report, ensure_ascii=False)))
            return cur.lastrowid

    def sync_runs(self, limit: int = 20) -> list[dict]:
        with self._conn() as c:
            out = []
            for r in c.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT ?", (limit,)):
                rec = json.loads(r["report"])
                rec.update({"id": r["id"], "trigger": r["trigger"]})
                out.append(rec)
            return out
