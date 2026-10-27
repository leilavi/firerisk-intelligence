"""HTTP backend for the dashboard (FastAPI). ORIGIN: NEW.

Run:  python -m firerisk.serve      (see README)

Every payload states where its content comes from, so the dashboard can label it:
  "source"  - value read from a real source record (file / tab / row)
  "derived" - computed by a documented rule from source values (e.g. meter episodes)
  "rule"    - produced by the deterministic rule engine (severity, basis, 14 alert fields)
  "ai"      - produced by Muse Spark (hypotheses, explanations); never used as a measurement
  "test"    - produced against a mock/test endpoint (only in test setups)
"""

from __future__ import annotations

import os
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .ai.investigation import investigate
from .ai.muse import MuseClient, MuseConfig
from .config import ASSETS, BUILDING_NAME, LOCAL_TZ, METERS, METER_FEEDS, SEVERITY_LABEL, SEVERITY_ORDER, ZONE_LABELS
from .engine import AnalysisResult, run_analysis
from .hazards.pathways import PATHWAYS
from .media import media_inventory
from .sources.drive_sync import SyncConfig, SyncError, sync_from_drive
from .store import VERIFICATION_STATES, Store

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = Path(os.environ.get("FIRERISK_SNAPSHOT_DIR", ROOT / "data" / "private" / "snapshot"))
DB_PATH = Path(os.environ.get("FIRERISK_DB", ROOT / "data" / "private" / "firerisk.db"))
WEB_DIR = ROOT / "web"
LIVE_API_HOST = "api.meta.ai"


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.result: AnalysisResult | None = None
        self.run_id: int | None = None
        self.store = Store(DB_PATH)
        self.sync_lock = threading.Lock()
        self.auto_sync_minutes: int = 0
        self.next_sync_at: str | None = None

    def analyse(self) -> AnalysisResult:
        with self.lock:
            res = run_analysis(SNAPSHOT_DIR, now=datetime.now(LOCAL_TZ))
            self.run_id = self.store.record_run(res)
            late = self.store.mark_seen(res)
            for item in late:
                e = res.evidence.get(item["evidence_id"])
                if e and "late_arrival" not in e.flags:
                    e.flags.append("late_arrival")
            res.data_quality.extend(late)
            self.result = res
            return res

    def get(self) -> AnalysisResult:
        return self.result or self.analyse()

    def sync(self, trigger: str) -> dict:
        """Update the snapshot from Google Drive, then re-run the analysis if anything changed or failed."""
        if not self.sync_lock.acquire(blocking=False):
            return {"ok": False, "busy": True, "error": "An update is already running."}
        try:
            started = datetime.now(LOCAL_TZ).isoformat(timespec="seconds")
            try:
                with self.lock:
                    report = sync_from_drive(SNAPSHOT_DIR, SyncConfig.load())
            except SyncError as exc:
                report = {"ok": False, "changed": False, "started_at": started, "error": str(exc), "files": {}}
            except Exception as exc:   # never let a sync problem stop the dashboard
                report = {"ok": False, "changed": False, "started_at": started,
                          "error": f"Unexpected error: {type(exc).__name__}", "files": {}}
            self.store.save_sync(report, trigger)
            if report.get("files") and (report.get("changed") or not report.get("ok")) or self.result is None:
                res = self.analyse()
                report["analysis"] = {"generated_at": res.generated_at.isoformat(), "alerts": len(res.alerts),
                                      "run_id": self.run_id}
            return report
        finally:
            self.sync_lock.release()


state = State()
app = FastAPI(title="FireRisk Intelligence", version=__version__)


def start_auto_sync() -> threading.Thread | None:
    """Background updates from Google Drive while the dashboard runs (started by firerisk.serve only)."""
    cfg = SyncConfig.load()
    if not cfg.configured or cfg.interval_minutes <= 0:
        return None
    state.auto_sync_minutes = cfg.interval_minutes

    def loop() -> None:
        while True:
            state.sync("auto")
            state.next_sync_at = (datetime.now(LOCAL_TZ) + timedelta(minutes=cfg.interval_minutes)).isoformat(
                timespec="seconds")
            time.sleep(cfg.interval_minutes * 60)

    t = threading.Thread(target=loop, name="drive-sync", daemon=True)
    t.start()
    return t


def _sync_view() -> dict:
    cfg = SyncConfig.load()
    runs = state.store.sync_runs(limit=1)
    ok_runs = [r for r in state.store.sync_runs(limit=50) if r.get("ok")]
    return {"configured": cfg.configured, "auto_minutes": state.auto_sync_minutes or 0,
            "next_at": state.next_sync_at, "running": state.sync_lock.locked(),
            "last": runs[0] if runs else None, "last_ok_at": ok_runs[0]["started_at"] if ok_runs else None}


def _rank(sev: str) -> int:
    return SEVERITY_ORDER.index(sev)


def _alert(alert_id: str):
    res = state.get()
    for a in res.alerts:
        if a.alert_id == alert_id:
            return res, a
    raise HTTPException(404, f"alert {alert_id} not found")


def _asset_name(a: str | None) -> str | None:
    return (ASSETS.get(a or "") or METERS.get(a or "") or {}).get("name") if a else None


def _ev(e) -> dict:
    d = e.to_dict()
    d["asset_name"] = _asset_name(e.asset_id)
    d["origin"] = "derived" if "derived" in e.flags else "source"
    return d


def _ai_mode(base_url: str) -> str:
    return "live" if urlparse(base_url).hostname == LIVE_API_HOST else "test"


def _investigation_view(rec: dict | None) -> dict | None:
    if not rec:
        return None
    rec = dict(rec)
    rec.setdefault("api_mode", "live" if rec.get("model") and not rec.get("base_url") else
                   _ai_mode(rec.get("base_url", f"https://{LIVE_API_HOST}/v1")))
    if rec.get("result") and "MOCK RESPONSE" in str(rec["result"].get("summary", "")):
        rec["api_mode"] = "test"
    return rec


@app.get("/api/status")
def status():
    res = state.get()
    cfg = MuseConfig.load()
    counts = Counter(a.severity for a in res.alerts)
    states = {a.alert_id: (state.store.current_status(a.alert_id) or {}).get("status", "new") for a in res.alerts}
    active = [a for a in res.alerts if states[a.alert_id] not in ("resolved", "false_alarm")]
    serious = [a for a in active if _rank(a.severity) >= _rank("high")]
    abnormal_assets = _abnormal_assets(res)
    return {"building": BUILDING_NAME, "version": __version__, "generated_at": res.generated_at.isoformat(),
            "run_id": state.run_id, "sources": res.source_status, "alert_counts": dict(counts),
            "active_alerts": len(active), "serious_alerts": len(serious),
            "abnormal_equipment": len(abnormal_assets),
            "zones_attention": sorted({a.zone_label for a in active if _rank(a.severity) >= _rank("warning")}),
            "severity_labels": SEVERITY_LABEL, "evidence_count": len(res.evidence),
            "signal_count": len(res.signals), "data_quality_issues": len(res.data_quality),
            "sources_down": [s for s in res.source_status if s.get("error")],
            "sources_stale": [s for s in res.source_status if s.get("stale")],
            "zone_records": dict(Counter(e.zone or "Building" for e in res.evidence.values()
                                         if e.kind in ("incident", "construction", "asset_service", "inspection_check",
                                                       "generator_run", "meter_episode"))),
            "zones": ZONE_LABELS,
            "ai": {"configured": cfg.configured, "model": cfg.model, "mode": _ai_mode(cfg.base_url)},
            "media": media_inventory(res)["summary"], "sync": _sync_view()}


@app.post("/api/refresh")
def refresh():
    res = state.analyse()
    return {"generated_at": res.generated_at.isoformat(), "alerts": len(res.alerts), "run_id": state.run_id}


def _alert_summary(a) -> dict:
    inv = state.store.latest_investigation(a.alert_id, only_ok=True)
    f = a.fields
    return {"alert_id": a.alert_id, "zone": a.zone, "zone_label": a.zone_label, "severity": a.severity,
            "severity_label": SEVERITY_LABEL[a.severity], "headline": f.get("headline"),
            "why": (f.get("why_short") or [""])[0], "why_all": f.get("why_short", []),
            "detected_at": state.store.first_detected(a.alert_id), "assessment_class": f.get("assessment_class"),
            "assessment_text": f.get("assessment_text"), "first_seen": a.first_seen.isoformat() if a.first_seen else None,
            "last_seen": a.last_seen.isoformat() if a.last_seen else None, "open_items": a.open_items,
            "evidence_count": len(a.evidence_ids), "pathways": a.pathways,
            "urgency": f.get("urgency"), "deadline": f.get("deadline"),
            "assets": [x[0] for x in f.get("affected_assets", [])][:4],
            "verification": state.store.current_status(a.alert_id),
            "ai": ({"created_at": inv["created_at"], "ai_priority": inv["result"]["risk_assessment"]["ai_priority"],
                    "mode": _investigation_view(inv)["api_mode"]} if inv else None)}


@app.post("/api/sync")
def sync_now():
    if not SyncConfig.load().configured:
        raise HTTPException(400, "Google Drive sync is not set up. Run setup_drive_sync.bat.")
    return state.sync("button")


@app.get("/api/sync")
def sync_history():
    return {**_sync_view(), "history": state.store.sync_runs(limit=20)}


@app.get("/api/alerts")
def alerts():
    return [_alert_summary(a) for a in state.get().alerts]


def _window(cal: list[dict], start: str, end: str, pad: int = 7) -> list[dict]:
    days = [c["day"] for c in cal]
    if start not in days:
        return []
    i0 = days.index(start)
    i1 = days.index(end) if end in days else i0
    return cal[max(0, i0 - pad): i1 + pad + 1]


@app.get("/api/alerts/{alert_id}")
def alert_detail(alert_id: str):
    res, a = _alert(alert_id)
    sigs = []
    for s in res.signals:
        if s.signal_id in a.signal_ids:
            d = s.to_dict()
            d["mechanism"] = PATHWAYS[s.pathway]["mechanism"]
            d["severity_label"] = SEVERITY_LABEL[s.severity]
            sigs.append(d)
    sigs.sort(key=lambda d: -_rank(d["severity"]))
    ev_ids = list(dict.fromkeys(a.evidence_ids + a.context_ids))
    evidence = [_ev(res.evidence[i]) | {"role": "context" if i in a.context_ids else "finding"}
                for i in ev_ids if i in res.evidence]
    timeline = sorted((e for e in evidence if e["timestamp"]), key=lambda e: e["timestamp"])
    # trend windows: each meter episode with 7 days before/after (real readings, derived daily values)
    trends = []
    for e in evidence:
        if e["kind"] == "meter_episode":
            m = e["asset_id"]
            v = e["values"]
            start = (e["timestamp"] or "")[:10]
            trends.append({"evidence_id": e["evidence_id"], "meter": m, "meter_name": _asset_name(m),
                           "unit": v.get("unit"), "unit_verified": v.get("unit_verified"), "label": v.get("label"),
                           "start": start, "end": v.get("end"), "median": v.get("median"),
                           "points": _window(res.meter_calendars.get(m, []), start, v.get("end") or start)})
    # most relevant windows first: episodes linked to an equipment record, then recurring, then most recent
    trends.sort(key=lambda t: ("record on measured equipment" not in (res.evidence[t["evidence_id"]].values.get("note") or ""),
                               t["label"] != "Evidence-based risk", -(int(t["start"].replace("-", "") or 0))))
    meters = sorted({t["meter"] for t in trends} |
                    {m for m, feeds in METER_FEEDS.items() if any(e["asset_id"] in feeds for e in evidence)})
    # maintenance / incident history of the affected assets (all dates)
    assets = {e["asset_id"] for e in evidence if e["asset_id"]}
    history = sorted((_ev(e) for e in res.evidence.values()
                      if e.kind in ("asset_service", "incident", "construction", "inspection_check")
                      and e.asset_id in assets), key=lambda d: d["timestamp"] or "", reverse=True)
    return {"alert": a.to_dict(), "summary": _alert_summary(a), "fields": a.fields, "signals": sigs,
            "evidence": evidence, "timeline": timeline, "trends": trends,
            "meters": {m: {"meta": METERS.get(m), "calendar": res.meter_calendars.get(m, [])[-90:]} for m in meters},
            "maintenance_history": history,
            "verification": state.store.current_status(alert_id), "status_log": state.store.status_log(alert_id),
            "history": state.store.alert_history(alert_id),
            "investigation": _investigation_view(state.store.latest_investigation(alert_id)),
            "investigations": state.store.investigations(alert_id),
            "media": [m for m in media_inventory(res)["items"] if m["evidence_id"] in ev_ids],
            "data_quality": [q for q in res.data_quality if q.get("evidence_id") in ev_ids]}


@app.post("/api/alerts/{alert_id}/investigate")
def run_investigation(alert_id: str):
    res, a = _alert(alert_id)
    client = MuseClient()
    rec = investigate(a, res.signals, res.evidence, datetime.now(LOCAL_TZ), client)
    rec["base_url"] = client.config.base_url
    rec["api_mode"] = _ai_mode(client.config.base_url)
    rec["id"] = state.store.save_investigation(rec)
    return rec


class StatusIn(BaseModel):
    status: str
    note: str | None = None
    by: str | None = None


@app.post("/api/alerts/{alert_id}/status")
def set_status(alert_id: str, body: StatusIn):
    _alert(alert_id)
    if body.status not in VERIFICATION_STATES:
        raise HTTPException(400, f"status must be one of {VERIFICATION_STATES}")
    return state.store.set_status(alert_id, body.status, body.note, body.by)


@app.get("/api/evidence/{evidence_id:path}")
def evidence(evidence_id: str):
    res = state.get()
    e = res.evidence.get(evidence_id)
    if not e:
        raise HTTPException(404, "evidence not found")
    d = _ev(e)
    if e.kind == "meter_episode":
        d["derived_records"] = [_ev(res.evidence[i]) for i in e.values.get("derived_from", []) if i in res.evidence]
        d["window"] = _window(res.meter_calendars.get(e.asset_id, []), e.timestamp.date().isoformat(),
                              e.values.get("end") or e.timestamp.date().isoformat())
    d["in_alerts"] = [a.alert_id for a in res.alerts if evidence_id in a.evidence_ids or evidence_id in a.context_ids]
    d["data_quality"] = [q for q in res.data_quality if q.get("evidence_id") == evidence_id]
    return d


@app.get("/api/events")
def events(kind: str | None = None, zone: str | None = None, q: str | None = None, hazard_only: bool = True):
    res = state.get()
    out = []
    for e in res.evidence.values():
        if e.kind in ("meter_reading", "vehicle_day"):
            continue
        hazard = [t["tag"] for t in e.tags if t["tag"] not in ("checklist_pass",)]
        if hazard_only and not hazard and e.kind not in ("meter_episode",):
            continue
        if (kind and e.kind != kind) or (zone and e.zone != zone):
            continue
        if q and q.lower() not in f"{e.title} {e.text}".lower():
            continue
        out.append(_ev(e))
    out.sort(key=lambda e: e["timestamp"] or "", reverse=True)
    return out


def _abnormal_assets(res) -> list[dict]:
    """Equipment with an unresolved record or an active rule signal (rule output, not AI)."""
    by_asset: dict[str, dict] = {}
    for s in res.signals:
        for i in s.evidence_ids:
            e = res.evidence.get(i)
            if not e or not e.asset_id:
                continue
            row = by_asset.setdefault(e.asset_id, {"asset_id": e.asset_id, "name": _asset_name(e.asset_id),
                                                   "zone": e.zone, "severity": "normal", "signals": set(),
                                                   "open_records": 0, "last_event": None})
            row["signals"].add(s.title)
            if _rank(s.severity) > _rank(row["severity"]):
                row["severity"] = s.severity
            if e.is_open:
                row["open_records"] += 1
            t = e.timestamp.isoformat() if e.timestamp else None
            if t and (not row["last_event"] or t > row["last_event"]):
                row["last_event"] = t
    rows = [r | {"signals": sorted(r["signals"]), "severity_label": SEVERITY_LABEL[r["severity"]]}
            for r in by_asset.values() if _rank(r["severity"]) >= _rank("watch")]
    rows.sort(key=lambda r: (-_rank(r["severity"]), -r["open_records"]))
    return rows


@app.get("/api/assets")
def assets():
    return _abnormal_assets(state.get())


@app.get("/api/assets/{asset_id:path}")
def asset_detail(asset_id: str):
    res = state.get()
    recs = sorted((_ev(e) for e in res.evidence.values() if e.asset_id == asset_id and e.kind != "meter_reading"),
                  key=lambda d: d["timestamp"] or "", reverse=True)
    sigs = [s.to_dict() for s in res.signals if any((res.evidence.get(i) and res.evidence[i].asset_id == asset_id)
                                                    for i in s.evidence_ids)]
    return {"asset_id": asset_id, "name": _asset_name(asset_id), "meta": ASSETS.get(asset_id) or METERS.get(asset_id),
            "records": recs, "signals": sigs, "calendar": res.meter_calendars.get(asset_id, [])[-60:]}


@app.get("/api/trends")
def trends(weeks: int = 12):
    """Weekly counts from real records: fire-relevant records by hazard tag, and meter episodes by label."""
    res = state.get()
    end = res.generated_at
    start = end - timedelta(weeks=weeks)
    buckets = [(start + timedelta(weeks=i)).date().isoformat() for i in range(weeks)]

    def bucket(ts):
        i = int((ts - start).total_seconds() // (7 * 86400))
        return buckets[i] if 0 <= i < weeks else None

    hazards: dict[str, Counter] = defaultdict(Counter)
    episodes: dict[str, Counter] = defaultdict(Counter)
    for e in res.evidence.values():
        if not e.timestamp:
            continue
        b = bucket(e.timestamp)
        if not b:
            continue
        if e.kind == "meter_episode":
            episodes[e.values.get("label", "")][b] += 1
        elif e.kind in ("incident", "asset_service"):
            tags = {t["tag"] for t in e.tags} - {"fault", "motor_equipment", "checklist_pass"}
            if "fault" in {t["tag"] for t in e.tags} and tags:
                for t in tags:
                    hazards[t][b] += 1
    return {"weeks": buckets, "origin": "source records (counts) and derived meter episodes",
            "hazard_records": {k: [v.get(b, 0) for b in buckets] for k, v in hazards.items()},
            "meter_episodes": {k: [v.get(b, 0) for b in buckets] for k, v in episodes.items()}}


@app.get("/api/meters/{meter_id}")
def meter(meter_id: str):
    res = state.get()
    if meter_id not in res.meter_calendars:
        raise HTTPException(404, "meter not found")
    return {"meta": METERS.get(meter_id), "calendar": res.meter_calendars[meter_id],
            "episodes": res.meter_episodes.get(meter_id, []), "issues": res.meter_issues.get(meter_id, [])}


@app.get("/api/quality")
def quality():
    res = state.get()
    return {"sources": res.source_status, "issues": res.data_quality}


@app.get("/api/media")
def media():
    return media_inventory(state.get())


@app.get("/api/zones")
def zones():
    return ZONE_LABELS


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(WEB_DIR / "index.html")
