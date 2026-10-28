"""English display text for Vietnamese source records. ORIGIN: NEW.

The source data stays unchanged; only what the dashboard SHOWS is English.
  1. Fixed vocabularies (record status values, tab names, generator-run reasons) use the deterministic glossary
     below - no AI involved.
  2. Free text (record titles and descriptions, equipment names from the asset register) is translated by
     Muse Spark in small batches, in the background, and cached in SQLite (`translations`). Personal names and
     e-mails are pseudonymised before sending and put back afterwards. Each translation is labelled in the API
     (`*_en_origin = "ai_translation"`), and the original Vietnamese stays available next to it.
  3. Until a translation exists, the API returns no English text for that string and the dashboard shows the
     original with "translation pending" - it never invents a translation.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from ..config import LOCAL_TZ
from .redact import Redactor

VI = re.compile(r"[À-ÖØ-öø-ỹĐđ]")   # Vietnamese letters (excludes × and ÷)
TRANSLATION_VERSION = "translate-v1"
BATCH = 40

STATUS_EN = {   # record status values observed in the data (2026-10-28)
    "6. Hoàn tất": "6. Completed", "Hoàn tất": "Completed", "Hoàn tất thi công": "Works completed",
    "Đạt": "Passed", "Không đạt": "Failed", "Đang thi công": "Works in progress", "3. Đang tìm PA": "3. Seeking a solution",
    "3. Tạm dừng": "3. On hold", "Mới": "New", "Đang xử lý": "In progress", "Chưa xử lý": "Not handled",
}
SHEET_EN = {
    "chỉ số điện nước": "Daily meter readings & checklists",
    "BC hư hỏng TS": "Asset repairs & maintenance",
    "NK thi công - sự cố": "Incident & works log",
    "Dầu M Phát điện": "Generator log",
    "Asset": "Asset register",
}
GENERATOR_REASON_EN = {
    "VH định kỳ": "Scheduled test run", "Mất điện lưới": "Grid power outage", "Nhập dầu": "Fuel delivery",
    "Điện lực cắt điện": "Planned power cut by the utility",
}

SCHEMA = {
    "name": "Translations", "strict": True,
    "schema": {"type": "object", "additionalProperties": False, "required": ["items"],
               "properties": {"items": {"type": "array", "items": {
                   "type": "object", "additionalProperties": False, "required": ["id", "en"],
                   "properties": {"id": {"type": "string"}, "en": {"type": "string"}}}}}},
}
SYSTEM = """Translate building-operations log entries from Vietnamese to clear, plain English.
Rules: translate faithfully and briefly; keep equipment codes, numbers, units and placeholders like <person-1>
exactly as written; keep the meaning cautious (do not add causes, severity or certainty that the original does not
state); common abbreviations: PCCC = fire protection, MBA = transformer, MSB = main switchboard, XLNT = wastewater
treatment, TS = asset, KT = technician, VH = operation, PA = solution plan. Return one item per input id."""


def needs(s: str | None) -> bool:
    return bool(s) and bool(VI.search(s))


def _h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:24]


def glossary(s: str | None) -> str | None:
    """Deterministic English for fixed vocabularies, or None."""
    if not s:
        return None
    if s in STATUS_EN:
        return STATUS_EN[s]
    if s in SHEET_EN:
        return SHEET_EN[s]
    for vi, en in GENERATOR_REASON_EN.items():
        if s.startswith(vi):
            return en + s[len(vi):] if not needs(s[len(vi):]) else en
    m = re.match(r"^(Generator run - )(.+?)( \(\d+ min\))?$", s)
    if m and glossary(m.group(2)):
        return m.group(1) + glossary(m.group(2)) + (m.group(3) or "")
    m = re.match(r"^(Daily checklist - .+?: )(.+)$", s)
    if m and m.group(2) in STATUS_EN and not needs(m.group(1)):
        return m.group(1) + STATUS_EN[m.group(2)]
    return None


class Translator:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS translations (src_hash TEXT PRIMARY KEY, src TEXT NOT NULL, "
                      "en TEXT NOT NULL, model TEXT, created_at TEXT NOT NULL, version TEXT)")
            self.cache = {r["src"]: r["en"] for r in c.execute("SELECT src, en FROM translations")}
        self.lock = threading.Lock()
        self.running = False
        self.last: dict = {}

    def _conn(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    # --- lookup -------------------------------------------------------------------------------------------------
    def en(self, s: str | None) -> tuple[str | None, str | None]:
        """(english, origin) - origin is "source" (already English), "glossary", "ai_translation" or None (pending)."""
        if not s:
            return s, "source"
        if not needs(s):
            return s, "source"
        g = glossary(s)
        if g is not None:
            return g, "glossary"
        t = self.cache.get(s)
        return (t, "ai_translation") if t else (None, None)

    def pending(self, strings) -> list[str]:
        return sorted({s for s in strings if needs(s) and glossary(s) is None and s not in self.cache})

    # --- translation (background) ------------------------------------------------------------------------------
    def translate(self, client, strings: list[str]) -> dict:
        todo = self.pending(strings)
        done = failed = 0
        errors = []
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            red = Redactor()
            items = [{"id": f"T{n:02d}", "vi": red.text(s[:600])} for n, s in enumerate(chunk, 1)]
            joined = "\n".join(chunk)
            back = {}
            for low, token in red.mapping.items():           # restore the original spelling (mapping keys are lower-case)
                m = re.search(re.escape(low), joined, re.IGNORECASE)
                back[token] = m.group(0) if m else low
            try:
                r = client.chat_json(SYSTEM, json.dumps({"items": items}, ensure_ascii=False), SCHEMA,
                                     reasoning_effort="low", max_completion_tokens=8000)
            except Exception as exc:
                failed += len(chunk)
                errors.append(f"{type(exc).__name__}: {str(exc)[:160]}")
                break
            got = {x.get("id"): x.get("en") for x in r.data.get("items", []) if isinstance(x, dict)}
            now = datetime.now(LOCAL_TZ).isoformat(timespec="seconds")
            rows = []
            for n, s in enumerate(chunk, 1):
                en = got.get(f"T{n:02d}")
                if not en or not isinstance(en, str):
                    failed += 1
                    continue
                for token, original in back.items():     # put pseudonymised names back
                    en = en.replace(token, original)
                rows.append((_h(s), s, en.strip(), r.model, now, TRANSLATION_VERSION))
            with self._conn() as c:
                c.executemany("INSERT OR REPLACE INTO translations VALUES (?,?,?,?,?,?)", rows)
            for row in rows:
                self.cache[row[1]] = row[2]
            done += len(rows)
        self.last = {"translated": done, "failed": failed, "errors": errors, "remaining": len(self.pending(strings)),
                     "at": datetime.now(LOCAL_TZ).isoformat(timespec="seconds")}
        return self.last

    def start(self, client_factory, strings: list[str]) -> bool:
        if not self.pending(strings) or not self.lock.acquire(blocking=False):
            return False

        def run():
            self.running = True
            try:
                self.translate(client_factory(), strings)
            finally:
                self.running = False
                self.lock.release()
        threading.Thread(target=run, daemon=True, name="translate").start()
        return True


def display_strings(res) -> list[str]:
    """Every Vietnamese string the dashboard can show for this analysis (records, names, alert titles)."""
    out = set()
    for e in res.evidence.values():
        if e.kind in ("meter_reading", "vehicle_day"):
            continue
        for s in (e.title, (e.text or "")[:600], e.status):
            if needs(s):
                out.add(s)
    for a in res.equipment_alerts:
        for s in (a.title, a.asset_name):
            if needs(s):
                out.add(s)
    for r in getattr(res, "asset_register", {}).values():
        if needs(r.get("name")):
            out.add(r["name"])
    return sorted(out)
