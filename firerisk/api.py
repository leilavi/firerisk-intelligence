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
import re
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .ai.auto import STATE_LABELS, AutoAnalyst
from .ai.investigation import investigate
from .ai.muse import MuseClient, MuseConfig
from .ai.translate import SHEET_EN, Translator, display_strings
from .ai.translate import needs as translate_needs
from .config import ASSETS, BUILDING_NAME, LOCAL_TZ, METERS, METER_FEEDS, SEVERITY_LABEL, SEVERITY_ORDER, ZONE_LABELS
from .engine import AnalysisResult, run_analysis
from .hazards.pathways import PATHWAYS
from .media import media_inventory
from .drive_videos import DriveVideoSync, drive_video_items, video_settings
from .demo import DEMO_BUILDING, demo_frame_path, demo_mode, name_patterns
from .localize import FRAMES_DIR, Localizer, sam_settings
from .sam import SamClient
from .video import VIDEO_PROMPT_VERSION, INBOX_DIR, OLD_VIDEO_DAYS, VideoStore, extract_frame
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
        self.ai = AutoAnalyst(self.store, self.get)
        self.videos = VideoStore(DB_PATH)
        self.drive_videos = DriveVideoSync(self.videos, INBOX_DIR)
        self.translator = Translator(DB_PATH)
        self.localizer = Localizer(DB_PATH, self.videos)

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
            self.attach_video_context(res)
            self.result = res
        # Alerts are available now; Muse Spark runs afterwards in the background (never blocks the alert).
        self.ai.schedule(res)
        self.start_translation(res)
        return res

    def start_translation(self, res) -> bool:
        """English display text for Vietnamese records (Muse Spark, background, cached). Source data unchanged."""
        from .env import load_env
        if load_env().get("FIRERISK_AUTO_TRANSLATE", "1") == "0" or not MuseConfig.load().configured:
            return False
        vids = [v.get(k) for v in self.videos.list() for k in ("room", "area", "floor", "note")]
        vids += [e.get("name") for v in self.videos.list() for e in v.get("equipment") or []]
        strings = display_strings(res) + [x for x in vids if isinstance(x, str) and translate_needs(x)]
        return self.translator.start(self.ai.client_factory, strings)

    def get(self) -> AnalysisResult:
        return self.result or self.analyse()

    def video_context_text(self, v: dict, res: AnalysisResult) -> str:
        from .ai.redact import Redactor
        red = Redactor()
        ctx = "; ".join(red.text(a.fields.get("headline") or a.title) for a in res.alerts if v.get("zone") and a.zone == v["zone"])
        eq = "; ".join(red.text(e.get("name") or e["equipment_id"]) for e in v.get("equipment") or [])
        return (f"Zone {v['zone_label']}. Linked equipment: {eq or 'not linked'}. "
                f"Open fire-risk findings in this zone: {ctx or 'none'}")

    def on_video_analysed(self, _rec=None) -> None:
        """New video observations become context of the zone's fire-risk alerts, which are then re-analysed
        automatically when eligible (their evidence fingerprint changed)."""
        r = self.get()
        self.attach_video_context(r)
        self.ai.schedule(r)
        self.start_localization()

    def start_localization(self) -> bool:
        """SAM 3.1 visual localization of the items of new Muse Spark video analyses (background, daily limit).
        Never touches alerts or levels; a failure only leaves items 'not checked'."""
        if not MuseConfig.load().configured:
            return False
        try:
            return self.localizer.start(SamClient, self.ai.client_factory, scope="new")
        except Exception:
            return False

    def auto_analyse_videos(self) -> list[dict]:
        """Automatic Muse Spark review of new survey videos: one at a time, one attempt per video, daily limit."""
        cfg = video_settings()
        if not cfg["auto_analyse"] or not MuseConfig.load().configured:
            return []
        done = []
        for v in self.videos.pending_auto():
            if self.videos.auto_analyses_today() >= cfg["daily_limit"]:
                break
            rec = self.videos.analyse(v["video_id"], self.ai.client_factory(), self.video_context_text(v, self.get()),
                                      on_done=self.on_video_analysed, trigger="auto")
            done.append({"video_id": v["video_id"], "status": rec.get("status")})
        return done

    def start_drive_videos(self) -> bool:
        """Download every Drive video not yet on this computer, then analyse new ones (background)."""
        if not video_settings()["download"] or not SyncConfig.load().configured:
            return False
        res = self.get()
        return self.drive_videos.start(drive_video_items(res.video_catalog, res.video_refs), self.auto_analyse_videos)

    def attach_video_context(self, res: AnalysisResult) -> None:
        """Survey-video observations of the same zone become CONTEXT of a fire-risk alert (never a finding)."""
        for a in res.alerts:
            a.video_context = self.videos.context_for(a.zone)

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
            if report.get("files"):
                report["videos_started"] = self.start_drive_videos()
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
    if not a:
        return None
    name = (ASSETS.get(a) or METERS.get(a) or {}).get("name")
    if not name and state.result is not None:        # fall back to the asset register (Asset tab)
        name = (state.result.asset_register.get(a) or {}).get("name")
        if name:
            name = _en(name)[0] or name
    return name


def _en(text):
    """(english or None, origin) for display; never changes the source value."""
    return state.translator.en(text)


def _tx(d: dict, keys=("title", "text", "status")) -> dict:
    """Add <key>_en and <key>_en_origin next to each Vietnamese source field (originals kept)."""
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v:
            en, origin = _en(v)
            d[f"{k}_en"], d[f"{k}_en_origin"] = en, origin
    return d


def _ev(e) -> dict:
    d = e.to_dict()
    d["asset_name"] = _asset_name(e.asset_id)
    d["origin"] = "derived" if "derived" in e.flags else "source"
    if e.source:
        d["source"]["sheet_en"] = SHEET_EN.get(e.source.sheet, e.source.sheet)
    return _tx(d)


def _tx_fields(fields: dict) -> dict:
    """Translate record titles inside rule fields (evidence lines) for display."""
    out = dict(fields)
    for key in ("evidence", "context_evidence"):
        if isinstance(out.get(key), list):
            out[key] = [_tx(dict(x), ("title", "status")) for x in out[key]]
    return out


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
    demo = demo_mode()
    return {"building": DEMO_BUILDING if demo else BUILDING_NAME, "version": __version__,
            "demo_mode": demo, "name_patterns": name_patterns() if demo else [], "generated_at": res.generated_at.isoformat(),
            "run_id": state.run_id, "sources": _sources_en(res.source_status), "alert_counts": dict(counts),
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
            "media": media_inventory(res)["summary"], "sync": _sync_view(),
            "equipment_alerts": len([a for a in res.equipment_alerts if _is_active(a.alert_id)]),
            "equipment_alert_counts": dict(Counter(a.severity for a in res.equipment_alerts))}


@app.post("/api/refresh")
def refresh():
    res = state.analyse()
    return {"generated_at": res.generated_at.isoformat(), "alerts": len(res.alerts), "run_id": state.run_id}


def _alert_summary(a, res=None) -> dict:
    res = res or state.get()
    inv = state.store.latest_investigation(a.alert_id, only_ok=True)
    f = a.fields
    st = (state.store.current_status(a.alert_id) or {}).get("status", "new")
    return {"alert_id": a.alert_id, "kind": "fire", "ai_status": state.ai.status(a, res),
            "status": st, "status_label": STATUS_LABEL.get(st, st), "risks": f.get("risks", []), "card": f.get("card"),
            "related_equipment": len(a.related_equipment), "zone": a.zone, "zone_label": a.zone_label, "severity": a.severity,
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


STATUS_LABEL = {"new": "Open", "acknowledged": "Acknowledged", "investigating": "Investigating",
                "confirmed": "Confirmed on Site", "resolved": "Resolved", "false_alarm": "False Alarm"}


def _eq_summary(ea) -> dict:
    f = ea.fields
    st = (state.store.current_status(ea.alert_id) or {}).get("status", "new")
    return {"status": st, "status_label": STATUS_LABEL.get(st, st),
            "headline_en": _en(ea.title)[0], "asset_name_en": _en(ea.asset_name)[0],"alert_id": ea.alert_id, "kind": "equipment", "asset_id": ea.asset_id, "asset_name": ea.asset_name,
            "zone": ea.zone, "zone_label": ea.zone_label, "critical": ea.critical, "severity": ea.severity,
            "severity_label": SEVERITY_LABEL[ea.severity], "headline": ea.title,
            "why": (f.get("why_short") or [""])[0], "why_all": f.get("why_short", []), "type": f.get("kind"),
            "rules": [r["rule"] for r in ea.rules], "open_items": ea.open_items, "evidence_count": len(ea.evidence_ids),
            "first_seen": ea.first_seen.isoformat() if ea.first_seen else None,
            "last_seen": ea.last_seen.isoformat() if ea.last_seen else None,
            "detected_at": state.store.first_detected(ea.alert_id), "deadline": f.get("deadline"),
            "urgency": f.get("urgency"), "confidence": f.get("confidence"),
            "verification": state.store.current_status(ea.alert_id),
            "fire_links": ea.fire_links}


def _eq_alert(alert_id: str):
    res = state.get()
    for a in res.equipment_alerts:
        if a.alert_id == alert_id:
            return res, a
    raise HTTPException(404, f"equipment alert {alert_id} not found")


def _is_active(alert_id: str) -> bool:
    return ((state.store.current_status(alert_id) or {}).get("status", "new")) not in ("resolved", "false_alarm")


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
    """Fire-risk alerts (kept at this path for compatibility; also served at /api/fire-alerts)."""
    res = state.get()
    return [_alert_summary(a, res) for a in res.alerts]


@app.get("/api/fire-alerts")
def fire_alerts():
    return alerts()


@app.get("/api/equipment-alerts")
def equipment_alerts():
    return [_eq_summary(a) for a in state.get().equipment_alerts]


@app.get("/api/equipment-alerts/{alert_id:path}")
def equipment_alert_detail(alert_id: str):
    res, ea = _eq_alert(alert_id)
    evidence = [_ev(res.evidence[i]) for i in ea.evidence_ids if i in res.evidence]
    trends = []
    meter = ea.asset_id if ea.asset_id in res.meter_calendars else None
    for e in evidence:
        if e["kind"] == "meter_episode":
            v = e["values"]
            start = (e["timestamp"] or "")[:10]
            trends.append({"evidence_id": e["evidence_id"], "meter": e["asset_id"], "meter_name": _asset_name(e["asset_id"]),
                           "unit": v.get("unit"), "unit_verified": v.get("unit_verified"), "label": v.get("label"),
                           "start": start, "end": v.get("end"), "median": v.get("median"),
                           "points": _window(res.meter_calendars.get(e["asset_id"], []), start, v.get("end") or start)})
    trends.sort(key=lambda t: t["start"], reverse=True)
    history = sorted((_ev(e) for e in res.evidence.values()
                      if ea.asset_id and e.asset_id == ea.asset_id and e.kind in ("asset_service", "incident", "inspection_check")),
                     key=lambda d: d["timestamp"] or "", reverse=True)
    fire = {a.alert_id: a for a in res.alerts}
    return {"alert": ea.to_dict(), "summary": _eq_summary(ea), "fields": _tx_fields(ea.fields), "evidence": evidence,
            "trends": trends, "meter": {"meta": METERS.get(meter), "calendar": res.meter_calendars.get(meter, [])[-90:]} if meter else None,
            "maintenance_history": history,
            "fire_alerts": [{"alert_id": l["fire_alert_id"], "reasons": l["reasons"],
                             "severity": fire[l["fire_alert_id"]].severity,
                             "headline": fire[l["fire_alert_id"]].fields.get("headline"),
                             "zone_label": fire[l["fire_alert_id"]].zone_label}
                            for l in ea.fire_links if l["fire_alert_id"] in fire],
            "verification": state.store.current_status(alert_id), "status_log": state.store.status_log(alert_id),
            "history": state.store.alert_history(alert_id),
            "data_quality": [_tx(dict(q), ("title",)) for q in res.data_quality if q.get("evidence_id") in set(ea.evidence_ids)]}


# Floors of the building, top to bottom. Verified against the real data on 2026-10-28: the asset register (Asset tab)
# uses the floors B1, F1, F2, F3, F4 and Rooftop (plus two lift entries), and the zone mapping of the records uses the
# same set. "Building" holds alerts that concern the whole building.
FLOORS = ["Roof", "F4", "F3", "F2", "F1", "B1"]
FLOOR_STATE_LABEL = {"emergency": "Emergency", "high": "High Risk", "warning": "Warning", "watch": "Watch",
                     "no_active_alert": "No Active Fire-Risk Alert", "not_assessed": "Not Assessed"}
ASSESSED_KINDS = ("incident", "construction", "asset_service", "inspection_check", "generator_run", "meter_episode")
COVERAGE_NOTE = ("Assessed from maintenance, incident and checklist records, meter readings and survey videos. The data "
                 "has no smoke, heat or gas sensor readings, so \"no active alert\" does not mean a floor is confirmed safe.")


def _floor_state(risks: list[dict], records: int) -> str:
    """Highest severity among the floor's active risks; without risks: assessed-without-alert, or not assessed.
    Never "normal"/green: the rules can raise risks but none of them confirms that a floor is safe."""
    if risks:
        return max((r["severity"] for r in risks), key=_rank)
    return "no_active_alert" if records else "not_assessed"


@app.get("/api/building")
def building():
    """Building Risk Map: one entry per floor plus whole-building risks, and the building summary.
    All values come from active fire-risk alerts (rule results) and record counts; nothing is estimated."""
    res = state.get()
    active = [a for a in res.alerts if _is_active(a.alert_id)]
    eq_active = [a for a in res.equipment_alerts if _is_active(a.alert_id)]
    records = Counter(e.zone for e in res.evidence.values() if e.kind in ASSESSED_KINDS and e.zone)
    reg = Counter((r.get("zone") or "") for r in res.asset_register.values())
    vids = state.videos.list()
    floors = []
    for z in FLOORS + ["Building"]:
        alerts = [a for a in active if a.zone == z]
        risks = [{**c, "alert_id": a.alert_id} for a in alerts for c in a.fields.get("risks", [])]
        risks.sort(key=lambda c: (-_rank(c["severity"]), not c["open"]))
        st = _floor_state(risks, records.get(z, 0))
        zv = [v for v in vids if v.get("zone") == z]
        floors.append({
            "zone": z, "label": ZONE_LABELS.get(z, z), "state": st, "state_label": FLOOR_STATE_LABEL[st],
            "risk_count": len(risks), "open_risks": sum(1 for r in risks if r["open"]),
            "by_level": dict(Counter(r["severity"] for r in risks)), "alert_ids": [a.alert_id for a in alerts],
            "top_risk": risks[0] if risks else None, "risks": risks,
            "needs_attention": any(_rank(r["severity"]) >= _rank("warning") or r["open"] for r in risks),
            "records_checked": records.get(z, 0), "register_items": reg.get(z, 0),
            "equipment_alerts": [_eq_summary(e) for e in eq_active if e.zone == z],
            "videos": len(zv), "videos_analysed": sum(1 for v in zv if v["analysis_status"] == "ok"),
        })
    issues = _issues(res)
    for f in floors:
        f.update(_map_floor(f, [i for i in issues if (i["zone"] or "") == f["zone"]]))
    known = set(FLOORS + ["Building"])
    unassigned = [i for i in issues if (i["zone"] or "") not in known]
    all_risks = [r for f in floors for r in f["risks"]]
    overall = max((r["severity"] for r in all_risks), key=_rank) if all_risks else (
        "no_active_alert" if sum(records.values()) else "not_assessed")
    urgent = [r for r in all_risks if _rank(r["severity"]) >= _rank("high") and r["open"]]
    syncs = [r for r in state.store.sync_runs(limit=50) if r.get("ok")]
    not_assessed = [f["zone"] for f in floors if f["zone"] in FLOORS and f["state"] == "not_assessed"]
    if issues:
        overall_all = max((i["severity"] for i in issues), key=_rank)
        overall_all_label = MAP_STATE_LABEL[overall_all]
    else:
        overall_all = "incomplete" if not_assessed else "no_active_alert"
        overall_all_label = "Assessment Incomplete" if not_assessed else "No Active Alert"
    return {
        "generated_at": res.generated_at.isoformat(), "floors": floors,
        "unassigned": {"label": "Location not recorded", "issues": unassigned},
        "summary": {
            "overall": overall, "overall_label": FLOOR_STATE_LABEL.get(overall, SEVERITY_LABEL.get(overall, overall)),
            "overall_rule": "Highest severity among the active fire-risk alerts' risks (rule results).",
            "risks_by_level": dict(Counter(r["severity"] for r in all_risks)), "risk_count": len(all_risks),
            "alerts_active": len(active),
            "floors_affected": sum(1 for f in floors if f["risk_count"] and f["zone"] != "Building"),
            "building_wide_risks": next((f["risk_count"] for f in floors if f["zone"] == "Building"), 0),
            "urgent_actions": len(urgent),
            "urgent_rule": "Open risks at High Risk or Emergency (rule deadline: within 24 hours or immediately).",
            "equipment_active": len(eq_active), "equipment_by_level": dict(Counter(a.severity for a in eq_active)),
            "last_analysis": res.generated_at.isoformat(),
            "last_drive_sync_ok": syncs[0]["started_at"] if syncs else None,
            "coverage_note": COVERAGE_NOTE,
            "building_state": overall_all, "building_state_label": overall_all_label,
            "building_state_rule": "Highest rule level among all active issues (fire-safety risks and equipment alerts). "
                                   "With no active issue it is never shown as safe.",
            "issues_active": len(issues), "issues_by_level": dict(Counter(i["severity"] for i in issues)),
            "issues_unresolved": sum(1 for i in issues if i["open"]),
            "high_priority": sum(1 for i in issues if _rank(i["severity"]) >= _rank("high") and i["open"]),
            "floors_with_issues": sum(1 for f in floors if f["issue_count"] and f["zone"] != "Building"),
            "floors_not_assessed": not_assessed,
            "sources_down": [x for x in res.source_status if x.get("error")],
        },
        "urgent": urgent,
        "recent": _recent(res),
    }


# ---------------------------------------------------------------------------------------------------------------
# Unified building view (0.8). Fire-safety risks and equipment alerts are shown together on the floor they belong to,
# each keeping its own classification and its own rule level. Nothing here changes how either is generated.
# ---------------------------------------------------------------------------------------------------------------
MAP_STATE_LABEL = {"emergency": "Emergency", "high": "High Risk", "warning": "Warning", "watch": "Watch",
                   "no_active_alert": "No Active Alert", "not_assessed": "Not Assessed"}
KIND_LABEL = {"fire_risk": "Fire-safety risk", "equipment": "Equipment fault", "meter": "Consumption anomaly"}


def _place(location: str | None) -> str:
    """'Basement B1 (technical rooms) · MSB room, Transformer room' -> 'MSB room, Transformer room'."""
    loc = location or ""
    return loc.split(" · ", 1)[1] if " · " in loc else loc


def _fire_issue(c: dict, a) -> dict:
    return {"issue_id": f"fire:{c['signal_id']}", "kind": "fire_risk", "kind_label": KIND_LABEL["fire_risk"],
            "severity": c["severity"], "severity_label": SEVERITY_LABEL[c["severity"]], "open": c["open"],
            "title": c["risk"], "place": _place(c.get("location")), "location": c.get("location"),
            "zone": a.zone, "zone_label": a.zone_label,
            "status_text": f"{c['unresolved']} unresolved" if c["open"] else "all records marked fixed",
            "count_text": c.get("evidence"), "alert_id": a.alert_id, "signal_id": c["signal_id"],
            "link": f"#/fire/{a.alert_id}?risk={c['signal_id']}", "last_seen": c.get("last_seen"),
            "origin": "rule"}


def _eq_issue(ea) -> dict:
    kind = "meter" if ea.fields.get("kind") == "meter" else "equipment"
    name_en = _en(ea.asset_name)[0] if ea.asset_name else ea.asset_id
    finding = ea.title.split(": ", 1)[1] if ": " in (ea.title or "") else None
    if finding and translate_needs(finding):
        finding = None
    n_ev = len(ea.evidence_ids)
    return {"issue_id": f"eq:{ea.alert_id}", "kind": "equipment", "subkind": kind, "kind_label": KIND_LABEL[kind],
            "severity": ea.severity, "severity_label": SEVERITY_LABEL[ea.severity], "open": bool(ea.open_items),
            "title": name_en, "title_pending": name_en is None, "place": name_en, "summary": finding,
            "zone": ea.zone, "zone_label": ZONE_LABELS.get(ea.zone or "", "Location not recorded"),
            "status_text": f"{ea.open_items} open" if ea.open_items else None,
            "count_text": f"{n_ev} event{'s' if n_ev != 1 else ''}" if kind == "meter" else
                          (f"{ea.open_items} open" if ea.open_items else f"{n_ev} record{'s' if n_ev != 1 else ''}"),
            "alert_id": ea.alert_id, "critical": ea.critical, "link": f"#/equipment/{ea.alert_id}",
            "fire_links": [l["fire_alert_id"] for l in ea.fire_links],
            "last_seen": ea.last_seen.isoformat() if ea.last_seen else None, "origin": "rule"}


def _issue_key(i: dict):
    return (-_rank(i["severity"]), not i["open"], i["kind"] != "fire_risk")


def _issues(res) -> list[dict]:
    """Every active issue of the building (fire-safety risks and equipment alerts), highest priority first."""
    out = [_fire_issue(c, a) for a in res.alerts if _is_active(a.alert_id) for c in a.fields.get("risks", [])]
    out += [_eq_issue(ea) for ea in res.equipment_alerts if _is_active(ea.alert_id)]
    out.sort(key=lambda i: i.get("last_seen") or "", reverse=True)    # most recent first within equal priority
    out.sort(key=_issue_key)
    return out


def _map_floor(f: dict, issues: list[dict]) -> dict:
    """Map state of one floor: highest level among ALL its active issues; without issues the fire-floor state
    (assessed without alert / not assessed). Never "normal": no rule confirms that a floor is safe."""
    st = max((i["severity"] for i in issues), key=_rank) if issues else f["state"]
    top = issues[0] if issues else None
    return {"map_state": st, "map_state_label": MAP_STATE_LABEL.get(st, st), "issues": issues,
            "issue_count": len(issues), "open_issues": sum(1 for i in issues if i["open"]),
            "marker": ({"severity": top["severity"], "count": len(issues),
                        "high_count": sum(1 for i in issues if _rank(i["severity"]) >= _rank("high"))} if top else None)}


def _ai_text(t):
    """AI text is shown only when it is English (older analyses can quote Vietnamese record wording)."""
    return t if isinstance(t, str) and t.strip() and not translate_needs(t) else None


AI_BRIEF_LABEL = {
    "complete": "Meta Muse Spark Analysis Complete", "complete_older": "Meta Muse Spark Analysis Complete · Update Pending",
    "pending": "Meta Muse Spark Analysis Pending", "failed": "Meta Muse Spark Analysis Failed", "insufficient_evidence": "Insufficient Evidence",
    "unavailable": "Meta Muse Spark Analysis Unavailable", "not_applicable": "Rule-Based Summary",
}


# Survey-video categories that matter for each fire-risk pathway (used only to pick which AI video observations to
# show first; they never change a level).
VIDEO_CATS = {
    "water_electrical": {"water_or_moisture", "electrical_equipment"},
    "motor_overheat": {"electrical_equipment", "storage_or_combustibles", "housekeeping", "obstruction"},
    "detection_impairment": {"fire_detection_or_alarm"},
    "backup_power": {"electrical_equipment", "storage_or_combustibles", "housekeeping"},
    "fire_water": {"fire_equipment", "water_or_moisture"},
    "pa_system": {"fire_detection_or_alarm", "signage_or_emergency_lighting"},
    "smoke_control": {"fire_equipment", "obstruction", "corridor_or_walkway"},
}


def _video_findings(zone, pathway=None, asset_ids=(), place: str = "", limit_videos=3, limit_obs=3) -> list[dict]:
    """Muse Spark survey-video observations of the zone (AI · video, recording-time only), most relevant first."""
    cats = VIDEO_CATS.get(pathway or "", set())
    out = []
    words = {w for w in re.findall(r"[a-z]{5,}", (place or "").lower()) if w not in ("panel", "room", "rooms", "basement")}
    for v in state.videos.list():
        linked = bool({e.get("equipment_id") for e in v.get("equipment") or []} & set(asset_ids))
        text = f"{v.get('filename', '')} {v.get('room') or ''} {v.get('area') or ''}".lower()
        named = bool(words and any(w in text for w in words))      # e.g. "Wastewater ..." risk -> "Wastewater Treatment Room.mp4"
        if not ((zone and v.get("zone") == zone) or linked or named):  # same floor, linked in the register, or same room name
            continue
        ana = state.videos.latest_analysis(v["video_id"], only_ok=True) or {}
        v = {**v, "observations": ana.get("observations", []), "analysis_created_at": ana.get("created_at"),
             "analysis_model": ana.get("model")}
        if not v["observations"]:
            continue
        obs = sorted(v["observations"], key=lambda o: (o["category"] not in cats, o["visible_certainty"] != "clearly_visible",
                                                       o["category"] in ("other", "signage_or_emergency_lighting")))
        hits = sum(1 for o in v["observations"] if o["category"] in cats)
        out.append({"video_id": v["video_id"], "filename": v["filename"], "recorded_at": v.get("recorded_at"),
                    "match": "equipment" if linked else "room_name" if named else "same_floor",
                    "analysed_at": v.get("analysis_created_at"), "model": v.get("analysis_model"),
                    "summary": _ai_text(ana.get("summary")), "observation_count": len(v["observations"]),
                    "linked_to_this_equipment": linked, "relevant_count": hits,
                    "observations": [{k: o.get(k) for k in ("time_start_s", "category", "observation", "visible_certainty",
                                                            "fire_safety_relevance")} for o in obs[:limit_obs]
                                     if _ai_text(o.get("observation"))],
                    "recording_note": v.get("recording_note")})
    out.sort(key=lambda x: (["equipment", "room_name", "same_floor"].index(x["match"]), -x["relevant_count"], x["recorded_at"] or ""))
    if any(x["match"] != "same_floor" for x in out):         # a video of this very equipment/room exists: show only those
        out = [x for x in out if x["match"] != "same_floor"]
    return out[:limit_videos]


def _brief_detail(rb: dict) -> dict:
    """Structured per-risk analysis (prompt v6) for the expandable part of the briefing; English text only."""
    lst = lambda k: [x for x in (rb.get(k) or []) if _ai_text(x)]
    return {"history_link": _ai_text(rb.get("history_link")), "consequence_chain": lst("consequence_chain"),
            "not_established": lst("not_established"), "actions_immediate": lst("actions_immediate"),
            "actions_follow_up": lst("actions_follow_up"), "closure_criteria": lst("closure_criteria"),
            "claims": [{"statement": c["statement"], "basis": c.get("basis"), "evidence_ids": c.get("evidence_ids", []),
                        "downgraded": bool(c.get("downgraded"))}
                       for c in rb.get("claims") or [] if _ai_text(c.get("statement"))]}


def _brief_fire(issue: dict, res, a, sig) -> dict:
    st = state.ai.status(a, res)
    inv = state.store.latest_investigation(a.alert_id, only_ok=True)
    r = (inv or {}).get("result") or {}
    rb = next((b for b in r.get("risk_briefings", []) if b.get("signal_id") == issue["signal_id"]), None)
    f = sig.fields if sig else {}
    card = next((c for c in a.fields.get("risks", []) if c["signal_id"] == issue["signal_id"]), {})
    ev = set(card.get("evidence_ids", []))
    # Older analyses (prompt v3/v4) have no per-risk briefing: use the parts of the real Muse Spark result that cite
    # this risk's own records (facts, actions, hypotheses). Nothing is written for the model.
    cites = lambda x, k="evidence_ids": bool(ev & set(x.get(k) or []))
    facts = [x["statement"] for x in r.get("observed_facts", []) if cites(x) and _ai_text(x.get("statement"))]
    acts = [x for x in r.get("recommended_actions", []) if cites(x) and _ai_text(x.get("action"))]
    hyps = [x for x in r.get("hypotheses", []) if cites(x, "supporting_evidence_ids") and _ai_text(x.get("cause"))]
    scen = [x for x in r.get("scenarios", []) if cites(x, "supporting_evidence_ids") and _ai_text(x.get("how_it_could_develop"))]
    if rb and rb.get("certainty") == "insufficient_evidence":
        code = "insufficient_evidence"
    elif inv:
        code = "complete" if st["result_is_current"] else "complete_older"
    elif st["code"] == "running":
        code = "pending"
    elif st["code"] == "failed":
        code = "failed"
    elif not st["configured"]:
        code = "unavailable"
    else:
        code = "pending" if st["code"] == "not_analysed" and not st.get("not_queued_reason") else "unavailable"

    def field(ai_key, ai_alt, rule_text):
        t = (_ai_text(rb.get(ai_key)) if rb else None) or _ai_text(ai_alt)
        if t:
            return {"text": t, "origin": "ai"}
        return {"text": rule_text, "origin": "rule"} if rule_text and not translate_needs(rule_text) else None
    actions = f.get("preventive_actions") or []
    sig_assets = {res.evidence[i].asset_id for i in (sig.evidence_ids if sig else []) if i in res.evidence and res.evidence[i].asset_id}
    return {**issue,
            "observed": field("observed", " ".join(facts[:2]) or None, None),
            "why_it_matters": field("why_it_matters", None, card.get("why_it_matters")),
            "potential_consequence": field("potential_consequence", scen[0]["how_it_could_develop"] if scen else None,
                                           f.get("consequence")),
            "uncertainty": field("uncertainty", (rb or {}).get("not_established", [None])[0] if rb and rb.get("not_established") else None, None),
            "first_action": field("first_action", acts[0]["action"] if acts else None,
                                  card.get("action") or (actions[0] if actions else None)),
            "certainty": rb.get("certainty") if rb else None,
            "detail": _brief_detail(rb) if rb else None,
            "evidence_text": card.get("evidence"), "evidence_ids": card.get("evidence_ids", []),
            "zone_ai": ({"situation": _ai_text(r.get("situation") or r.get("summary")),
                         "ai_priority": (r.get("risk_assessment") or {}).get("ai_priority"),
                         "agrees_with_rule": (r.get("risk_assessment") or {}).get("agrees_with_rule_severity"),
                         "rationale": _ai_text((r.get("risk_assessment") or {}).get("rationale")),
                         "differs": (r.get("risk_assessment") or {}).get("ai_priority") not in (None, a.severity),
                         "possible_causes": [{"cause": h["cause"], "plausibility": h.get("plausibility"),
                                              "how_to_verify": _ai_text(h.get("how_to_verify"))} for h in hyps[:3]],
                         "actions": [{"action": x["action"], "urgency": x.get("urgency"),
                                      "role": _ai_text(x.get("responsible_role"))} for x in acts[:3]],
                         "uncertainty": _ai_text(r.get("uncertainty")),
                         "prompt_version": inv.get("prompt_version")} if inv else None),
            "videos": _video_findings(a.zone, sig.pathway if sig else None, sig_assets, issue.get("place") or ""),
            "ai": {"code": code, "label": AI_BRIEF_LABEL[code], "running": st["code"] == "running",
                   "analysed_at": inv["created_at"] if inv else None,
                   "model": inv.get("model") if inv else None,
                   "api_mode": _investigation_view(inv)["api_mode"] if inv else None,
                   "is_current": bool(inv and st["result_is_current"]), "per_risk": bool(rb),
                   "error": st.get("error"), "has_full_analysis": bool(inv)}}


def _brief_eq(issue: dict, ea) -> dict:
    f = ea.fields
    ok = lambda t: t if isinstance(t, str) and t and not translate_needs(t) else None
    acts = f.get("preventive_actions") or []
    return {**issue,
            "observed": {"text": ok((f.get("why_short") or [None])[0]), "origin": "rule"} if ok((f.get("why_short") or [None])[0]) else None,
            "why_it_matters": None,
            "potential_consequence": {"text": ok(f.get("consequence")), "origin": "rule"} if ok(f.get("consequence")) else None,
            "uncertainty": {"text": ok(f.get("cause_status")), "origin": "rule"} if ok(f.get("cause_status")) else None,
            "first_action": {"text": ok(acts[0]), "origin": "rule"} if acts and ok(acts[0]) else None,
            "certainty": None, "evidence_text": issue["count_text"], "evidence_ids": list(ea.evidence_ids)[:20],
            "zone_ai": None, "videos": _video_findings(ea.zone, None, {ea.asset_id} if ea.asset_id else set(), issue.get("place") or ""),
            "ai": {"code": "not_applicable", "label": AI_BRIEF_LABEL["not_applicable"], "running": False,
                   "analysed_at": None, "model": None, "api_mode": None, "is_current": False, "error": None,
                   "has_full_analysis": False,
                   "note": "Meta Muse Spark analyses fire-safety risks; equipment alerts are explained by the rule set."}}


@app.get("/api/briefing")
def briefing(limit: int = 12):
    """AI Risk Briefing: the highest-priority issue first, then the next ones (to switch to on demand).
    Priority = rule level, then unresolved first, then fire-safety risks before equipment alerts, then most recent.
    AI text comes only from a stored Muse Spark analysis; otherwise the rule explanation is shown and labelled."""
    res = state.get()
    issues = _issues(res)
    alerts = {a.alert_id: a for a in res.alerts}
    sigs = {s.signal_id: s for s in res.signals}
    eqs = {e.alert_id: e for e in res.equipment_alerts}
    items = []
    for i in issues[:limit]:
        if i["kind"] == "fire_risk":
            items.append(_brief_fire(i, res, alerts[i["alert_id"]], sigs.get(i["signal_id"])))
        else:
            items.append(_brief_eq(i, eqs[i["alert_id"]]))
    high = [i for i in issues if _rank(i["severity"]) >= _rank("high") and i["open"]]
    return {"generated_at": res.generated_at.isoformat(), "items": items, "issue_count": len(issues),
            "high_priority_count": len(high),
            "priority_rule": "Rule level first, then unresolved records, then fire-safety risks before equipment alerts."}


def _recent(res, n: int = 8) -> dict:
    """Latest fire-relevant source records and latest survey-video analyses (real data only)."""
    tagged = [e for e in res.evidence.values() if e.kind in ("incident", "construction", "asset_service", "inspection_check")
              and e.timestamp and {t["tag"] for t in e.tags} - {"checklist_pass"}]
    tagged.sort(key=lambda e: e.timestamp, reverse=True)
    vids = []
    for v in state.videos.list():
        a = state.videos.latest_analysis(v["video_id"], only_ok=True)
        if a:
            obs = sorted(a.get("observations", []), key=lambda o: (o["category"] in ("other", "signage_or_emergency_lighting"),
                                                                  o["visible_certainty"] != "clearly_visible"))
            vids.append({"video_id": v["video_id"], "filename": v["filename"], "zone": v.get("zone"),
                         "zone_label": v["zone_label"], "recorded_at": v.get("recorded_at"),
                         "analysed_at": a["created_at"], "observations": len(a.get("observations", [])),
                         "summary": _ai_text(a.get("summary")), "model": a.get("model"),
                         "top": [{k: o.get(k) for k in ("time_start_s", "category", "observation", "visible_certainty")}
                                 for o in obs[:3] if _ai_text(o.get("observation"))]})
    vids.sort(key=lambda x: x["analysed_at"] or "", reverse=True)
    return {"records": [_ev(e) for e in tagged[:n]], "videos": vids}


@app.get("/api/overview")
def overview():
    """Two separate sections: building equipment alerts and fire-risk alerts."""
    res = state.get()
    eq = [a for a in res.equipment_alerts if _is_active(a.alert_id)]
    fire = [a for a in res.alerts if _is_active(a.alert_id)]
    ai = [state.ai.status(a, res) for a in fire]
    rank_key = lambda a: (-_rank(a.severity), -(a.last_seen.timestamp() if a.last_seen else 0))
    return {
        "generated_at": res.generated_at.isoformat(),
        "equipment": {
            "active": len(eq), "by_level": dict(Counter(a.severity for a in eq)),
            "critical_open": len({a.asset_id or a.alert_id for a in eq if a.critical and a.open_items}),
            "meters_with_findings": sum(1 for a in eq if a.fields.get("kind") == "meter"),
            "top": [_eq_summary(a) for a in sorted(eq, key=rank_key)[:5]]},
        "fire": {
            "active": len(fire), "by_level": dict(Counter(a.severity for a in fire)),
            "needs_check": [_alert_summary(a, res) for a in sorted(fire, key=rank_key)
                            if _rank(a.severity) >= _rank("warning") or a.open_items][:5],
            "others": [_alert_summary(a, res) for a in sorted(fire, key=rank_key)
                       if not (_rank(a.severity) >= _rank("warning") or a.open_items)][:5],
            "zones": sorted({a.zone_label for a in fire}),
            "ai": dict(Counter(x["code"] for x in ai)), "ai_labels": {k: v[0] for k, v in STATE_LABELS.items()},
            "ai_configured": MuseConfig.load().configured},
    }


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
    eq_by_id = {e.alert_id: e for e in res.equipment_alerts}
    related = [_eq_summary(eq_by_id[r["equipment_alert_id"]]) | {"reasons": r["reasons"]}
               for r in a.related_equipment if r["equipment_alert_id"] in eq_by_id]
    rule_explanation = [{"signal_id": s["signal_id"], "pathway": s["pathway"], "title": s["title"],
                         "severity": s["severity"], "mechanism": s["mechanism"],
                         "consequence": s["fields"]["consequence"], "risk_chain": s["fields"]["risk_chain"],
                         "trigger_condition": s["fields"]["trigger_condition"],
                         "possible_causes": s["fields"]["possible_causes"],
                         "context_evidence": s["fields"].get("context_evidence", []),
                         "origin": "rule"} for s in sigs]
    latest_ok = state.store.latest_investigation(alert_id, only_ok=True)
    for sg in sigs:
        sg["fields"] = _tx_fields(sg["fields"])
    for rx in rule_explanation:
        rx["context_evidence"] = [_tx(dict(x), ("title", "status")) for x in rx.get("context_evidence") or []]
    return {"alert": a.to_dict(), "summary": _alert_summary(a, res), "fields": _tx_fields(a.fields), "signals": sigs,
            "ai_status": state.ai.status(a, res), "related_equipment": related, "rule_explanation": rule_explanation,
            "evidence": evidence, "timeline": timeline, "trends": trends,
            "meters": {m: {"meta": METERS.get(m), "calendar": res.meter_calendars.get(m, [])[-90:]} for m in meters},
            "maintenance_history": history,
            "verification": state.store.current_status(alert_id), "status_log": state.store.status_log(alert_id),
            "history": state.store.alert_history(alert_id),
            "investigation": _investigation_view(latest_ok),
            "last_attempt": _investigation_view(state.store.latest_investigation(alert_id)),
            "investigations": state.store.investigations(alert_id),
            "media": [m for m in media_inventory(res)["items"] if m["evidence_id"] in ev_ids],
            "survey_videos": [_tx_video(v) for v in state.videos.for_zone(a.zone)],
            "survey_video_refs": [r for r in state.videos.reference_status(res.video_refs)
                                  if r.get("zone") == a.zone and not r["on_this_computer"]],
            "data_quality": [_tx(dict(q), ("title",)) for q in res.data_quality if q.get("evidence_id") in ev_ids]}


@app.post("/api/alerts/{alert_id}/investigate")
def run_investigation(alert_id: str, wait: bool = False):
    """Re-analyse with Muse Spark on request. Default: queued in the background (the UI polls ai_status).
    wait=true runs it in this request and returns the stored record (previous behaviour)."""
    res, a = _alert(alert_id)
    if wait:
        rec = state.ai.run_one(alert_id, "button")
        return rec
    out = state.ai.request(alert_id, "button")
    return out | {"ai_status": state.ai.status(a, res)}


@app.get("/api/alerts/{alert_id}/ai-status")
def ai_status(alert_id: str):
    res, a = _alert(alert_id)
    return state.ai.status(a, res)


class StatusIn(BaseModel):
    status: str
    note: str | None = None
    by: str | None = None


@app.post("/api/alerts/{alert_id}/status")
def set_status(alert_id: str, body: StatusIn):
    if alert_id.startswith("EQ-"):
        _eq_alert(alert_id)
    else:
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
    d["in_equipment_alerts"] = [a.alert_id for a in res.equipment_alerts if evidence_id in a.evidence_ids]
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
    name = _asset_name(asset_id)
    return {"asset_id": asset_id, "name": name, "name_en": _en(name)[0] if name else None, "meta": ASSETS.get(asset_id) or METERS.get(asset_id),
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
    return {"sources": _sources_en(res.source_status),
            "issues": [_tx(dict(i, sheet_en=SHEET_EN.get(i.get("sheet"), i.get("sheet"))), ("title", "detail"))
                       for i in res.data_quality]}


def _sources_en(sources: list[dict]) -> list[dict]:
    """Source status with English tab names for display (the original tab name stays in `sheet`)."""
    return [dict(x, sheet_en=SHEET_EN.get(x.get("sheet"), x.get("sheet"))) for x in sources]


@app.get("/api/media")
def media():
    return media_inventory(state.get())


# --- Building survey videos (prepared; no real video yet) ---------------------------------------------------------
@app.post("/api/videos")
async def upload_video(request: Request, filename: str, zone: str | None = None, floor: str | None = None,
                       area: str | None = None, room: str | None = None, recorded_at: str | None = None,
                       duration_s: float | None = None, note: str | None = None):
    """Raw-body upload (the browser sends the file itself as the request body; metadata in the query)."""
    meta = {"zone": zone or None, "floor": floor, "area": area, "room": room, "recorded_at": recorded_at,
            "duration_s": duration_s, "note": note}
    try:
        from .video import clean_meta
        clean_meta(meta)
        tmp = state.videos.incoming_path(filename)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    size = 0
    try:
        with open(tmp, "wb") as f:
            async for chunk in request.stream():
                size += len(chunk)
                if size > 1_073_741_824:
                    raise HTTPException(413, "file larger than 1 GiB (Meta Files API limit)")
                f.write(chunk)
        v = state.videos.add_file(tmp, filename, meta)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    finally:
        if tmp.exists():
            tmp.unlink()
    return v


def _tx_video(v: dict) -> dict:
    v = dict(v)
    for k in ("room", "area", "floor", "note"):
        if isinstance(v.get(k), str):
            en, origin = _en(v[k])
            if en is None and v[k].startswith("Linked in the asset register to: "):   # translate the names inside
                parts = [_en(x)[0] or x for x in v[k][len("Linked in the asset register to: "):].split("; ")]
                en, origin = "Linked in the asset register to: " + "; ".join(parts), "composed"
            v[f"{k}_en"], v[f"{k}_en_origin"] = en, origin
    v["equipment"] = [dict(e, name_en=_en(e.get("name"))[0], name_en_origin=_en(e.get("name"))[1]) for e in v.get("equipment") or []]
    return v


@app.get("/api/videos")
def list_videos():
    res = state.get()
    local = {v.get("drive_file_id"): v for v in state.videos.list() if v.get("drive_file_id")}
    drive = []
    for it in drive_video_items(res.video_catalog, res.video_refs):
        ref = it["ref"] or {}
        v = local.get(it["drive_file_id"])
        drive.append({"drive_file_id": it["drive_file_id"], "title": it["title"], "size": it["size"],
                      "folder": it["folder"], "drive": it["drive"], "linked_in_register": bool(it["ref"]),
                      "equipment": ref.get("equipment", []), "zone": (v or {}).get("zone") or ref.get("zone"),
                      "zone_label": ZONE_LABELS.get((v or {}).get("zone") or ref.get("zone") or "", "Not assigned"),
                      "zone_source": ref.get("zone_source") if ref else "not linked in the asset register",
                      "video_id": (v or {}).get("video_id"), "on_this_computer": bool(v),
                      "analysis_status": (v or {}).get("analysis_status")})
    for d_ in drive:
        d_["equipment"] = [dict(e, name_en=_en(e.get("name"))[0]) for e in d_["equipment"]]
    return {"videos": [_tx_video(v) for v in state.videos.list()], "old_after_days": OLD_VIDEO_DAYS, "zones": ZONE_LABELS,
            "ai_configured": MuseConfig.load().configured, "inbox": str(INBOX_DIR), "drive": drive,
            "referenced": state.videos.reference_status(res.video_refs),
            "drive_sync": {"configured": SyncConfig.load().configured, **video_settings(),
                           "progress": state.drive_videos.progress,
                           "listing_at": (res.video_catalog and max((c.get("checked_at") or "") for c in res.video_catalog.values())) or None}}


@app.post("/api/videos/drive-sync")
def drive_videos_now():
    if not SyncConfig.load().configured:
        raise HTTPException(400, "Google Drive sync is not set up. Run setup_drive_sync.bat.")
    return {"started": state.start_drive_videos(), "progress": state.drive_videos.progress}


@app.post("/api/videos/import")
def import_videos():
    """Register the video files placed in the inbox folder (matched to the asset-register references)."""
    res = state.get()
    out = state.videos.import_folder(INBOX_DIR, res.video_refs)
    state.attach_video_context(res)
    return out


def _video(video_id: str) -> dict:
    v = state.videos.get(video_id)
    if not v:
        raise HTTPException(404, f"video {video_id} not found")
    return v


@app.get("/api/videos/{video_id}")
def video_detail(video_id: str):
    v = _video(video_id)
    res = state.get()
    fire = [{"alert_id": a.alert_id, "severity": a.severity, "headline": a.fields.get("headline")}
            for a in res.alerts if v.get("zone") and a.zone == v["zone"]]
    return {"video": _tx_video(v), "analysis": state.videos.latest_analysis(video_id), "fire_alerts_in_zone": fire}


class VideoMetaIn(BaseModel):
    zone: str | None = None
    floor: str | None = None
    area: str | None = None
    room: str | None = None
    recorded_at: str | None = None
    note: str | None = None


@app.post("/api/videos/{video_id}/meta")
def video_meta(video_id: str, body: VideoMetaIn):
    _video(video_id)
    try:
        v = state.videos.update_meta(video_id, body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    res = state.get()
    state.attach_video_context(res)
    return v


def _no_video_in_demo():
    if demo_mode():
        raise HTTPException(403, "Original survey videos are hidden in demo mode (they can show building names)")


@app.get("/api/videos/{video_id}/file")
def video_file(video_id: str):
    _no_video_in_demo()
    v = _video(video_id)
    p = state.videos.path(video_id)
    if not p:
        raise HTTPException(404, "video file missing")
    return FileResponse(p, media_type=v["mime"])     # supports HTTP Range, so the player can jump to a time


@app.get("/api/videos/{video_id}/frame")
def video_frame(video_id: str, t: float = 0):
    _no_video_in_demo()
    p = state.videos.path(video_id)
    if not p:
        raise HTTPException(404, "video file missing")
    out = state.videos.video_dir / "frames" / f"{video_id}_{int(t * 10):07d}.jpg"
    if not out.exists():
        try:
            if not extract_frame(p, t, out):
                raise HTTPException(501, "ffmpeg is not installed; open the clip instead")
        except Exception as exc:
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(500, f"frame extraction failed: {type(exc).__name__}")
    return FileResponse(out, media_type="image/jpeg")


@app.post("/api/videos/{video_id}/analyse")
def analyse_video_endpoint(video_id: str):
    """User-requested only (videos can show people; sending them to Meta is a deliberate step)."""
    v = _video(video_id)
    if not v["analysable"]:
        raise HTTPException(400, v["analysable_reason"])
    if not MuseConfig.load().configured:
        raise HTTPException(400, "Meta Muse Spark is not configured (no MODEL_API_KEY)")
    started = state.videos.analyse_in_background(video_id, state.ai.client_factory,
                                                 state.video_context_text(v, state.get()), on_done=state.on_video_analysed)
    return {"started": started, "video": state.videos.get(video_id)}


@app.get("/api/video-findings")
def video_findings():
    """AI video findings (Meta Muse Spark survey-video review v2), separate from rule-based alerts, plus coverage."""
    from .video_findings import collect
    out = collect(state.videos, state.get(), state.store, _is_active, localizer=state.localizer)
    for f in out["findings"]:
        for k in ("title", "what_is_visible", "fire_safety_link", "potential_consequence_if_confirmed",
                  "recommended_check", "records_to_collect", "area_label"):
            f[k] = _ai_text(f.get(k)) or (None if f.get(k) else f.get(k))
    out["top"] = [f for f in out["findings"] if f["finding_id"] in {t["finding_id"] for t in out["top"]}][:3]
    out["prompt_version"] = VIDEO_PROMPT_VERSION
    out["drive_sync"] = state.drive_videos.progress
    return out


@app.post("/api/video-findings/{finding_id}/status")
def video_finding_status(finding_id: str, body: StatusIn):
    """Only a person sets the status of a video finding. It never changes a rule level."""
    if not finding_id.startswith("VF-"):
        raise HTTPException(404, "unknown finding")
    try:
        state.store.set_status(finding_id, body.status, body.note, body.by)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return state.store.current_status(finding_id)


@app.get("/api/localization")
def localization_status():
    """SAM 3.1 visual localization: background state, daily limit and item status counts."""
    cfg = sam_settings()
    return {"status": state.localizer.status, "counts": state.localizer.counts(), "daily_limit": cfg["daily_limit"],
            "requests_today": state.localizer.requests_today(), "auto": cfg["auto"],
            "backlog_boundary_analysis_id": state.localizer.auto_boundary(), "model": "sam-3.1"}


@app.get("/api/localization/{analysis_id}/{kind}/{index}")
def localization_item(analysis_id: int, kind: str, index: int):
    if kind not in ("finding", "observation"):
        raise HTTPException(404, "unknown item kind")
    return state.localizer.item_result(analysis_id, kind, index)


@app.get("/api/frames/{folder}/{name}")
def localization_frame(folder: str, name: str):
    """Private still frame extracted for localization (served only by this local dashboard)."""
    if not re.fullmatch(r"[0-9a-f]{16}", folder) or not re.fullmatch(r"t\d{6}\.jpg", name):
        raise HTTPException(404, "not found")
    if demo_mode():                     # demo: only the blurred copy, never the original
        p = demo_frame_path(f"{folder}/{name}")
        if not p:
            raise HTTPException(404, "no blurred demo copy for this frame")
    else:
        p = FRAMES_DIR / folder / name
    if not p.exists():
        raise HTTPException(404, "frame not available")
    return FileResponse(p, media_type="image/jpeg")


@app.get("/api/zones")
def zones():
    return ZONE_LABELS


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(WEB_DIR / "index.html")
