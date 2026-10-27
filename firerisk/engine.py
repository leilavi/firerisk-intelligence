"""End-to-end deterministic analysis: sources -> evidence -> rules -> signals -> zone alerts.

ORIGIN: NEW orchestration. Works without any AI call (requirement: useful when AI is down).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .config import LOCAL_TZ, METERS, SOURCE_CADENCE_DAYS
from .correlation import aggregate_alerts
from .hazards.pathways import evaluate, meter_signals
from .hazards.tagging import tag_evidence
from .models import Alert, Evidence, Signal, SourceRef
from .rules import meters as M
from .sources.normalize import load_ops_workbook, load_vehicle_workbook


@dataclass
class AnalysisResult:
    generated_at: datetime
    evidence: dict[str, Evidence]
    signals: list[Signal]
    alerts: list[Alert]
    meter_calendars: dict[str, list[dict]]
    meter_episodes: dict[str, list[dict]]
    meter_issues: dict[str, list[dict]]
    source_status: list[dict]
    data_quality: list[dict] = field(default_factory=list)


def _episode_evidence(ep: M.Episode) -> Evidence:
    meta = METERS.get(ep.meter, {})
    from datetime import time
    ts = datetime.combine(ep.start, time(12, 0), tzinfo=LOCAL_TZ)
    return Evidence(
        evidence_id=f"episode:{ep.meter}:{ep.start.isoformat()}", kind="meter_episode", timestamp=ts,
        asset_id=ep.meter, zone=meta.get("zone"),
        title=f"{meta.get('name', ep.meter)}: consumption {'spike' if ep.direction == 'up' else 'drop'} "
              f"{ep.pct:+.0f}% ({ep.days} day(s) from {ep.start.isoformat()})",
        text=f"peak {ep.peak:g} vs baseline median {ep.median:g} {meta.get('unit', '')}; label: {ep.label} ({ep.note})",
        status=ep.label, is_open=None,
        values={"direction": ep.direction, "days": ep.days, "peak": ep.peak, "median": ep.median, "pct": ep.pct,
                "label": ep.label, "note": ep.note, "derived_from": ep.evidence_ids},
        flags=["derived"],
        source=SourceRef("derived", "FireRisk meter analysis (PORTED rule)", "chỉ số điện nước", 0, None))


def load_manifest(snapshot_dir: Path) -> dict:
    p = snapshot_dir / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def run_analysis(snapshot_dir: Path, now: datetime | None = None) -> AnalysisResult:
    now = now or datetime.now(LOCAL_TZ)
    manifest = load_manifest(snapshot_dir)
    files = manifest.get("files", {})
    evidence: list[Evidence] = []
    status: list[dict] = []

    ops_path = snapshot_dir / files.get("ops_data", {}).get("local_file", "ops_data.xlsx")
    if ops_path.exists():
        ev, st = load_ops_workbook(ops_path, files.get("ops_data", {}).get("title", "Operations Data"))
        evidence.extend(ev)
        for sheet, s in st.items():
            status.append({"source": "ops_data", "sheet": sheet, **s, **_freshness(s.get("latest_record"), now, SOURCE_CADENCE_DAYS.get(sheet)),
                           "drive_modified_time": files.get("ops_data", {}).get("drive_modified_time"),
                           "snapshot_at": files.get("ops_data", {}).get("downloaded_at")})
    else:
        status.append({"source": "ops_data", "error": f"file not found: {ops_path.name}"})

    veh_path = snapshot_dir / files.get("vehicles", {}).get("local_file", "theo_doi_luot_khach.xlsx")
    vehicles: list[Evidence] = []
    if veh_path.exists():
        vehicles, vst = load_vehicle_workbook(veh_path, files.get("vehicles", {}).get("title", "Theo dõi lượt khách ra vào"))
        evidence.extend(vehicles)
        status.append({"source": "vehicles", "sheet": f"{vst['sheets']} monthly sheets", "rows_read": vst["days"],
                       "in_scope": vst["days"], "latest_record": vst["latest_record"],
                       "sheet_month_mismatch": len(vst["sheet_month_mismatch"]),
                       **_freshness(vst["latest_record"], now, SOURCE_CADENCE_DAYS["vehicles"]),
                       "drive_modified_time": files.get("vehicles", {}).get("drive_modified_time"),
                       "snapshot_at": files.get("vehicles", {}).get("downloaded_at")})
    else:
        status.append({"source": "vehicles", "error": f"file not found: {veh_path.name}"})

    tag_evidence(evidence)

    # PORTED meter rules
    veh_by_day = {e.timestamp.date(): e.values["vehicles"] for e in vehicles if e.timestamp}
    cals, eps, issues = {}, {}, {}
    for meter, readings in M.readings_by_meter(evidence).items():
        cal, iss = M.daily_consumption(readings, meter)
        M.detect_spikes(cal, meter)
        cals[meter], issues[meter] = cal, iss
        eps[meter] = M.episodes(cal, meter)
    for meter in eps:
        M.label_episodes(eps[meter], eps, veh_by_day)
    episode_ev = [_episode_evidence(ep) for meter in eps for ep in eps[meter]]
    evidence.extend(episode_ev)

    index = {e.evidence_id: e for e in evidence}
    signals = evaluate(evidence, now) + meter_signals(episode_ev, now)
    alerts = aggregate_alerts(signals, index, now)

    dq = []
    for meter, iss in issues.items():
        for i in iss:
            dq.append({"meter": meter, **i})
    for s in status:
        if s.get("stale"):
            dq.append({"type": "stale_source", "source": s["source"], "sheet": s.get("sheet"),
                       "latest_record": s.get("latest_record"), "age_days": s.get("age_days")})
    for e in evidence:
        for f in e.flags:
            if f in ("test_record", "placeholder_text", "undated"):
                dq.append({"type": f, "evidence_id": e.evidence_id})

    return AnalysisResult(
        generated_at=now, evidence=index, signals=signals, alerts=alerts,
        meter_calendars={m: [{"day": d.day.isoformat(), "value": d.value, "flag": d.flag, "spike": d.spike,
                              "median": d.median} for d in cal] for m, cal in cals.items()},
        meter_episodes={m: [e.to_dict() for e in v] for m, v in eps.items()},
        meter_issues=issues, source_status=status, data_quality=dq)


def _freshness(latest_iso: str | None, now: datetime, cadence: float | None) -> dict:
    if not latest_iso:
        return {"age_days": None, "stale": True, "expected_cadence_days": cadence}
    latest = datetime.fromisoformat(latest_iso)
    age = (now - latest).total_seconds() / 86400
    return {"age_days": round(age, 1), "stale": cadence is not None and age > cadence, "expected_cadence_days": cadence}
