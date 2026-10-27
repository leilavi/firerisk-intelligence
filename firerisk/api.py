"""HTTP backend for the dashboard (FastAPI). ORIGIN: NEW.

Run:  python -m firerisk.serve      (see README)
"""

from __future__ import annotations

import os
import threading
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .ai.investigation import investigate
from .ai.muse import MuseClient, MuseConfig
from .config import ASSETS, BUILDING_NAME, LOCAL_TZ, METERS, METER_FEEDS, SEVERITY_LABEL
from .engine import AnalysisResult, run_analysis
from .hazards.pathways import PATHWAYS
from .media import media_inventory
from .store import VERIFICATION_STATES, Store

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = Path(os.environ.get("FIRERISK_SNAPSHOT_DIR", ROOT / "data" / "private" / "snapshot"))
DB_PATH = Path(os.environ.get("FIRERISK_DB", ROOT / "data" / "private" / "firerisk.db"))
WEB_DIR = ROOT / "web"


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.result: AnalysisResult | None = None
        self.run_id: int | None = None
        self.store = Store(DB_PATH)

    def analyse(self) -> AnalysisResult:
        with self.lock:
            self.result = run_analysis(SNAPSHOT_DIR, now=datetime.now(LOCAL_TZ))
            self.run_id = self.store.record_run(self.result)
            return self.result

    def get(self) -> AnalysisResult:
        return self.result or self.analyse()


state = State()
app = FastAPI(title="FireRisk Intelligence", version=__version__)


def _alert(alert_id: str):
    res = state.get()
    for a in res.alerts:
        if a.alert_id == alert_id:
            return res, a
    raise HTTPException(404, f"alert {alert_id} not found")


def _ev(e) -> dict:
    d = e.to_dict()
    d["asset_name"] = (ASSETS.get(e.asset_id or "") or METERS.get(e.asset_id or "") or {}).get("name")
    return d


@app.get("/api/status")
def status():
    res = state.get()
    cfg = MuseConfig.load()
    counts: dict[str, int] = {}
    for a in res.alerts:
        counts[a.severity] = counts.get(a.severity, 0) + 1
    return {"building": BUILDING_NAME, "version": __version__, "generated_at": res.generated_at.isoformat(),
            "run_id": state.run_id, "sources": res.source_status, "alert_counts": counts,
            "severity_labels": SEVERITY_LABEL, "evidence_count": len(res.evidence),
            "signal_count": len(res.signals), "data_quality_issues": len(res.data_quality),
            "ai": {"configured": cfg.configured, "model": cfg.model, "base_url": cfg.base_url},
            "media": media_inventory(res)["summary"]}


@app.post("/api/refresh")
def refresh():
    res = state.analyse()
    return {"generated_at": res.generated_at.isoformat(), "alerts": len(res.alerts), "run_id": state.run_id}


@app.get("/api/alerts")
def alerts():
    res = state.get()
    out = []
    for a in res.alerts:
        d = a.to_dict()
        d.pop("links")
        d["link_count"] = len(a.links)
        d["verification"] = state.store.current_status(a.alert_id)
        inv = state.store.latest_investigation(a.alert_id, only_ok=True)
        d["ai"] = ({"created_at": inv["created_at"], "ai_priority": inv["result"]["risk_assessment"]["ai_priority"],
                    "summary": inv["result"]["summary"]} if inv else None)
        out.append(d)
    return out


@app.get("/api/alerts/{alert_id}")
def alert_detail(alert_id: str):
    res, a = _alert(alert_id)
    sigs = [s.to_dict() | {"mechanism": PATHWAYS[s.pathway]["mechanism"]} for s in res.signals if s.signal_id in a.signal_ids]
    ev_ids = list(dict.fromkeys(a.evidence_ids + a.context_ids))
    evidence = [_ev(res.evidence[i]) | {"role": "context" if i in a.context_ids else "finding"}
                for i in ev_ids if i in res.evidence]
    timeline = sorted((e for e in evidence if e["timestamp"]), key=lambda e: e["timestamp"])
    meters = sorted({e["asset_id"] for e in evidence if e["kind"] == "meter_episode"} |
                    {m for m, feeds in METER_FEEDS.items() if any(e["asset_id"] in feeds for e in evidence)})
    return {"alert": a.to_dict(), "signals": sigs, "evidence": evidence, "timeline": timeline,
            "meters": {m: {"meta": METERS.get(m), "calendar": res.meter_calendars.get(m, [])[-90:],
                           "episodes": res.meter_episodes.get(m, [])} for m in meters},
            "verification": state.store.current_status(alert_id), "status_log": state.store.status_log(alert_id),
            "history": state.store.alert_history(alert_id),
            "investigation": state.store.latest_investigation(alert_id),
            "investigations": state.store.investigations(alert_id),
            "media": [m for m in media_inventory(res)["items"] if m["evidence_id"] in ev_ids]}


@app.post("/api/alerts/{alert_id}/investigate")
def run_investigation(alert_id: str):
    res, a = _alert(alert_id)
    rec = investigate(a, res.signals, res.evidence, datetime.now(LOCAL_TZ), MuseClient())
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
    d["in_alerts"] = [a.alert_id for a in res.alerts if evidence_id in a.evidence_ids or evidence_id in a.context_ids]
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
        if kind and e.kind != kind or zone and e.zone != zone:
            continue
        if q and q.lower() not in f"{e.title} {e.text}".lower():
            continue
        out.append(_ev(e))
    out.sort(key=lambda e: e["timestamp"] or "", reverse=True)
    return out


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


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(WEB_DIR / "index.html")
