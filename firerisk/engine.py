"""End-to-end deterministic analysis: sources -> evidence -> rules -> signals -> zone alerts.

ORIGIN: NEW orchestration. Works without any AI call (requirement: useful when AI is down).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .config import LOCAL_TZ, METERS, OPS_SOURCE_TITLE, SOURCE_CADENCE_DAYS, VEHICLE_SOURCE_TITLE
from .correlation import aggregate_alerts
from .equipment import EquipmentAlert, build_equipment_alerts, link_to_fire_alerts
from .sources.register import ASSET_TAB, load_asset_register
from .alert_fields import enrich_alerts
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
    equipment_alerts: list[EquipmentAlert] = field(default_factory=list)
    asset_register: dict[str, dict] = field(default_factory=dict)   # 'Asset' tab (context, display names)
    video_refs: list[dict] = field(default_factory=list)            # survey-video references from the register
    video_catalog: dict[str, dict] = field(default_factory=dict)    # videos known from Drive (listing / metadata)
    power_links: object = None                                      # confirmed drawing links (power_links.PowerLinks)


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
                "label": ep.label, "note": ep.note, "derived_from": ep.evidence_ids, "ongoing": ep.ongoing,
                "near_zero": ep.near_zero, "end": ep.end.isoformat(), "unit": meta.get("unit"),
                "unit_verified": bool(meta.get("multiplier")) and meta.get("multiplier_verified", True)},
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

    ops_meta = files.get("ops_data", {})
    ops_path = snapshot_dir / ops_meta.get("local_file", "ops_data.xlsx")
    if ops_path.exists():
        ev, st = load_ops_workbook(ops_path, ops_meta.get("title", OPS_SOURCE_TITLE))
        evidence.extend(ev)
        for sheet, s in st.items():
            row = {"source": "ops_data", "sheet": sheet, **s,
                   "drive_modified_time": ops_meta.get("drive_modified_time"), "snapshot_at": ops_meta.get("downloaded_at"),
                   "sync_error": ops_meta.get("sync_error")}
            if "error" not in s:
                row.update(_freshness(s.get("latest_record"), now, SOURCE_CADENCE_DAYS.get(sheet)))
            status.append(row)
        register, video_refs, rst = load_asset_register(ops_path, ops_meta.get("title", OPS_SOURCE_TITLE))
        if rst.get("present"):
            status.append({"source": "ops_data", "sheet": ASSET_TAB, **{k: v for k, v in rst.items() if k != "present"},
                           "role": "equipment register (context)", "snapshot_at": ops_meta.get("downloaded_at")})
        catalog = manifest.get("video_catalog", {})
        for ref in video_refs:                        # file title / size recorded when the Drive files were checked
            ref["drive"] = catalog.get(ref["drive_file_id"])
    else:
        register, video_refs = {}, []
        status.append({"source": "ops_data", "sheet": None, "error": f"file not found: {ops_path.name}"})

    veh_meta = files.get("vehicles", {})
    veh_path = snapshot_dir / veh_meta.get("local_file", "vehicles.xlsx")
    vehicles: list[Evidence] = []
    if veh_path.exists():
        try:
            vehicles, vst = load_vehicle_workbook(veh_path, veh_meta.get("title", VEHICLE_SOURCE_TITLE))
            evidence.extend(vehicles)
            status.append({"source": "vehicles", "sheet": f"{vst['sheets']} monthly sheets", "rows_read": vst["days"],
                           "in_scope": vst["days"], "latest_record": vst["latest_record"],
                           "sheet_month_mismatch": len(vst["sheet_month_mismatch"]),
                           **_freshness(vst["latest_record"], now, SOURCE_CADENCE_DAYS["vehicles"]),
                           "drive_modified_time": veh_meta.get("drive_modified_time"),
                           "snapshot_at": veh_meta.get("downloaded_at"), "sync_error": veh_meta.get("sync_error")})
        except Exception as exc:
            status.append({"source": "vehicles", "sheet": None,
                           "error": f"workbook unreadable: {type(exc).__name__}: {exc}"})
    else:
        status.append({"source": "vehicles", "sheet": None, "error": f"file not found: {veh_path.name}"})

    apply_record_checks(evidence, now)
    tag_evidence(evidence)

    # PORTED meter rules
    veh_by_day = {e.timestamp.date(): e.values["vehicles"] for e in vehicles if e.timestamp}
    cals, eps, issues = {}, {}, {}
    for meter, readings in M.readings_by_meter(evidence).items():
        cal, iss = M.daily_consumption(readings, meter)
        M.detect_spikes(cal, meter)
        cals[meter], issues[meter] = cal, iss
        eps[meter] = M.episodes(cal, meter)
    records_by_asset: dict[str, list] = {}
    for e in evidence:
        if e.kind in ("incident", "asset_service") and e.asset_id and e.timestamp:
            records_by_asset.setdefault(e.asset_id, []).append(e.timestamp.date())
    for meter in eps:
        M.label_episodes(eps[meter], eps, veh_by_day, records_by_asset)
        M.mark_ongoing(eps[meter], cals[meter])
    episode_ev = [_episode_evidence(ep) for meter in eps for ep in eps[meter]]
    evidence.extend(episode_ev)

    index = {e.evidence_id: e for e in evidence}
    fire_signals = evaluate(evidence, now)              # NEW fire-hazard pathway rules R1-R7, R9
    meter_sigs = meter_signals(episode_ev, now)         # PORTED meter rules (skill §5A.8) = equipment findings
    signals = fire_signals + meter_sigs
    # Fire-risk alerts are built ONLY from fire-hazard pathway signals. Meter findings are equipment alerts and are
    # linked to a fire-risk alert only with a stated reason; they never set or raise the fire-risk level.
    alerts = aggregate_alerts(fire_signals, index, now)
    enrich_alerts(alerts, signals, index, status, now)
    from .config import ASSETS as _ASSETS, METERS as _METERS
    from .power_links import current as _power_links
    known = set(register) | set(_ASSETS) | set(_METERS) | {e.asset_id for e in evidence if e.asset_id}
    power = _power_links(known)                         # confirmed drawing links only (rule EQ-D1)
    equipment_alerts = build_equipment_alerts(evidence, meter_sigs, now, register, power=power)
    link_to_fire_alerts(equipment_alerts, alerts, index)
    for a in alerts:                                    # what life-safety equipment the floor has (confirmed links)
        a.life_safety = power.floor_inventory(a.zone) if power and power.links else {}

    dq = []
    for meter, iss in issues.items():
        for i in iss:
            dq.append({"meter": meter, **i})
    for s_ in status:
        if s_.get("error"):
            dq.append({"type": "source_unavailable", "source": s_["source"], "sheet": s_.get("sheet"), "detail": s_["error"]})
        elif s_.get("stale"):
            dq.append({"type": "stale_source", "source": s_["source"], "sheet": s_.get("sheet"),
                       "latest_record": s_.get("latest_record"), "age_days": s_.get("age_days")})
    for e in evidence:
        for f in e.flags:
            if f in DQ_FLAGS:
                dq.append({"type": f, "evidence_id": e.evidence_id, "title": e.title[:80]})

    return AnalysisResult(
        generated_at=now, evidence=index, signals=signals, alerts=alerts, equipment_alerts=equipment_alerts,
        asset_register=register, video_refs=video_refs, video_catalog=manifest.get("video_catalog", {}),
        meter_calendars={m: [{"day": d.day.isoformat(), "value": d.value, "flag": d.flag, "spike": d.spike,
                              "median": d.median, "raw": d.raw} for d in cal] for m, cal in cals.items()},
        meter_episodes={m: [e.to_dict() for e in v] for m, v in eps.items()},
        meter_issues=issues, source_status=status, data_quality=dq, power_links=power)


DQ_FLAGS = {"test_record", "placeholder_text", "undated", "missing_timestamp", "invalid_reading", "duplicate_record_id",
            "unmapped_status", "missing_status", "duration_recomputed_from_start_end", "duration_mismatch",
            "future_timestamp", "status_possibly_stale", "overdue"}


def _parse_date(v) -> datetime | None:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=LOCAL_TZ)
    if isinstance(v, str) and v:
        try:
            d = datetime.fromisoformat(v.strip())
            return d if d.tzinfo else d.replace(tzinfo=LOCAL_TZ)
        except ValueError:
            return None
    return None


def apply_record_checks(evidence: list[Evidence], now: datetime) -> None:
    """Record-level checks that need the analysis time (NEW; 'Quá hạn' and stale 'Đang thi công' are PORTED ideas
    from skill §2.4 / §10.4)."""
    from datetime import timedelta
    for e in evidence:
        if e.timestamp and e.timestamp > now + timedelta(days=1):
            e.flags.append("future_timestamp")
        cls = e.values.get("status_class")
        if e.kind == "construction" and cls == "in_progress":
            done = _parse_date(e.values.get("done"))
            if done and done < now:
                e.flags.append("status_possibly_stale")
        if e.kind == "asset_service" and e.is_open:
            due = _parse_date(e.values.get("expected_completion"))
            if due and due < now:
                e.flags.append("overdue")
                e.values["overdue_days"] = round((now - due).total_seconds() / 86400, 1)


def _freshness(latest_iso: str | None, now: datetime, cadence: float | None) -> dict:
    if not latest_iso:
        return {"age_days": None, "stale": True, "expected_cadence_days": cadence}
    latest = datetime.fromisoformat(latest_iso)
    age = (now - latest).total_seconds() / 86400
    return {"age_days": round(age, 1), "stale": cadence is not None and age > cadence, "expected_cadence_days": cadence}
