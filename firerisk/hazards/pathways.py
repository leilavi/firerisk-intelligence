"""Fire/explosion hazard pathway rules -> deterministic Signals.

ORIGIN: NEW. Severity vocabulary (Normal/Watch/Warning/High/Emergency) and the principle
"severity by consequence and time remaining, not by % change" are PORTED from skill v2.2 §7.

These are PRELIMINARY decision-support rules written for this Hackathon. They are not
certified fire-engineering criteria and do not estimate probabilities. Each rule records
its basis in plain language so a reviewer can disagree with it.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from ..config import ASSETS, RECURRENCE_WINDOW_DAYS
from ..models import Evidence, Signal
from .tagging import tagset

PATHWAYS: dict[str, dict] = {
    "water_electrical": {
        "title": "Water ingress into electrical rooms",
        "mechanism": "Water reaching transformer/switchboard equipment can cause insulation breakdown, "
                     "short circuits or arcing, which are recognised electrical ignition sources.",
    },
    "detection_impairment": {
        "title": "Fire detection / alarm system faults",
        "mechanism": "A faulty detector or monitor module can delay or prevent automatic fire detection "
                     "in the affected area.",
    },
    "motor_overheat": {
        "title": "Motor failure / overheating history",
        "mechanism": "Seized, jammed or previously burnt motors can overheat; a burnt winding is direct "
                     "evidence that overheating has already happened on that equipment.",
    },
    "backup_power": {
        "title": "Backup power readiness",
        "mechanism": "If the standby generator cannot start during a grid outage, loads connected to it "
                     "(which may include fire-safety loads - not confirmed in the data) lose power.",
    },
    "fire_water": {
        "title": "Fire-fighting water supply faults",
        "mechanism": "Faults in the fire water tank or fire pump can reduce water available to sprinklers/hydrants.",
    },
    "smoke_control": {
        "title": "Smoke exhaust system faults",
        "mechanism": "Smoke exhaust fans that do not run can let smoke spread in escape routes.",
    },
    "pa_system": {
        "title": "Public-address / evacuation announcement faults",
        "mechanism": "A non-working PA system can delay evacuation announcements.",
    },
    "electrical_anomaly": {
        "title": "Abnormal electrical consumption pattern",
        "mechanism": "Unexplained consumption changes on a meter can indicate equipment stopping, "
                     "abnormal load or metering problems; on its own it is not a fire indicator.",
    },
    "fire_event": {
        "title": "Reported fire / smoke event",
        "mechanism": "A record describing actual fire or smoke.",
    },
}


def _within(a: datetime | None, b: datetime | None, days: int) -> bool:
    return bool(a and b and abs((a - b).total_seconds()) <= days * 86400)


def _sig(rule: str, pathway: str, zone, asset, sev: str, title: str, basis: str, items: list[Evidence],
         is_open: bool, origin: str = "NEW") -> Signal:
    times = [e.timestamp for e in items if e.timestamp]
    key = asset or zone or "building"
    return Signal(signal_id=f"{rule}:{key}", rule_id=rule, pathway=pathway, zone=zone, asset_id=asset,
                  severity=sev, title=title, basis=basis, evidence_ids=[e.evidence_id for e in items],
                  first_seen=min(times) if times else None, last_seen=max(times) if times else None,
                  is_open=is_open, origin=origin)


def _group_by_asset_or_zone(items: list[Evidence]) -> dict[tuple, list[Evidence]]:
    groups: dict[tuple, list[Evidence]] = defaultdict(list)
    for e in items:
        groups[(e.asset_id or "", e.zone or "")].append(e)
    return groups


# Daily checklists relevant to each pathway (context evidence: what the latest inspection reported)
PATHWAY_CHECKLISTS: dict[str, list[str]] = {
    "water_electrical": ["C-TramBienAp", "C-tuPPDienTong"],
    "detection_impairment": ["C-tuBC"],
    "motor_overheat": ["C-tuXLNT"],
    "backup_power": ["C-MayPhatDien", "C-BinhAcQuy"],
    "fire_water": ["C-tuBomNPCCC"],
    "smoke_control": ["C-tuQuatHK"],
}


def _attach_context(signals: list[Signal], evidence: list[Evidence], now: datetime) -> None:
    checks = {e.values.get("checklist"): e for e in evidence if e.kind == "inspection_check"}
    sched = sorted((e for e in evidence if e.kind == "generator_run"
                    and (e.values.get("reason") or "").startswith("VH định kỳ") and _within(e.timestamp, now, 30)),
                   key=lambda e: e.timestamp)
    for s in signals:
        ctx = [checks[c].evidence_id for c in PATHWAY_CHECKLISTS.get(s.pathway, []) if c in checks]
        if s.pathway == "backup_power":
            ctx += [e.evidence_id for e in sched]
        s.context_ids = [c for c in ctx if c not in s.evidence_ids]


def evaluate(evidence: list[Evidence], now: datetime) -> list[Signal]:
    signals = _evaluate(evidence, now)
    _attach_context(signals, evidence, now)
    return signals


def _evaluate(evidence: list[Evidence], now: datetime) -> list[Signal]:
    recs = [e for e in evidence if e.kind in ("incident", "asset_service", "inspection_check")
            and "test_record" not in e.flags]
    signals: list[Signal] = []

    # --- R1 water ingress into electrical rooms -------------------------------------
    hits = [e for e in recs if {"water_ingress"} <= tagset(e) and
            ("electrical_room" in tagset(e) or ASSETS.get(e.asset_id or "", {}).get("fire_role") == "electrical_room")]
    if hits:
        open_ = [e for e in hits if e.is_open]
        zone = next((e.zone for e in hits if e.zone), "B1")
        if open_:
            sev, why = "high", f"{len(open_)} unresolved water-ingress record(s) in electrical rooms"
        elif len(hits) >= 2:
            sev, why = "warning", f"{len(hits)} water-ingress records; marked resolved but recurring"
        else:
            sev, why = "watch", "single resolved water-ingress record"
        signals.append(_sig("R1_WATER_ELECTRICAL", "water_electrical", zone, None, sev,
                            PATHWAYS["water_electrical"]["title"], why, hits, bool(open_)))

    # --- R2 fire detection faults ----------------------------------------------------
    det = [e for e in recs if "fire_detection" in tagset(e) and
           ("fault" in tagset(e) or (e.kind == "inspection_check" and e.is_open))]
    # grouped by zone: incident reports often carry no Equipment_ID although they describe the same device
    det_by_zone: dict[tuple, list[Evidence]] = defaultdict(list)
    for e in det:
        det_by_zone[("", e.zone or "")].append(e)
    for (_, zone), items in det_by_zone.items():
        items.sort(key=lambda e: e.timestamp or now)
        assets = sorted({e.asset_id for e in items if e.asset_id})
        asset = assets[0] if len(assets) == 1 else ""
        open_ = [e for e in items if e.is_open]
        recent = [e for e in items if _within(e.timestamp, now, RECURRENCE_WINDOW_DAYS)]
        if open_:
            sev, why = "high", "fire detection fault not resolved"
        elif len(items) >= 2 and any(_within(a.timestamp, b.timestamp, RECURRENCE_WINDOW_DAYS)
                                     for a, b in zip(items, items[1:])):
            sev, why = "warning", f"{len(items)} detection faults within {RECURRENCE_WINDOW_DAYS} days (recurring)"
        elif recent:
            sev, why = "watch", "one detection fault in the last 30 days, resolved"
        else:
            continue
        signals.append(_sig("R2_DETECTION", "detection_impairment", zone or None, asset or None, sev,
                            PATHWAYS["detection_impairment"]["title"], why, items, bool(open_)))

    # --- R3 motor failure / overheating -----------------------------------------------
    mot = [e for e in recs if ({"burnt_overheat", "mechanical_jam"} & tagset(e)) and
           ("motor_equipment" in tagset(e) or ASSETS.get(e.asset_id or "", {}).get("fire_role") == "motor_equipment")]
    for (asset, zone), items in _group_by_asset_or_zone(mot).items():
        burnt = [e for e in items if "burnt_overheat" in tagset(e)]
        open_ = [e for e in items if e.is_open]
        if open_ and burnt:
            sev, why = "high", "open motor failure on equipment with a recorded burnt/overheated motor"
        elif open_:
            sev, why = "warning", "open motor/mechanical failure"
        elif burnt or len(items) >= 2:
            sev, why = "watch", "past motor burn-out or repeated mechanical failure, currently resolved"
        else:
            continue
        signals.append(_sig("R3_MOTOR", "motor_overheat", zone or None, asset or None, sev,
                            PATHWAYS["motor_overheat"]["title"], why, items, bool(open_)))

    # --- R4 backup power readiness ----------------------------------------------------
    bp = [e for e in recs if "backup_power" in tagset(e) and "fault" in tagset(e)]
    outages = [e for e in evidence if e.kind == "generator_run" and "grid_outage" in tagset(e)
               and _within(e.timestamp, now, 60)]
    tests = [e for e in evidence if e.kind == "generator_run" and (e.values.get("reason") or "").startswith("VH định kỳ")
             and _within(e.timestamp, now, 30)]
    if bp:
        open_ = [e for e in bp if e.is_open]
        if open_ and outages:
            sev, why = "high", f"open backup-power fault and {len(outages)} grid outage(s) in 60 days"
        elif open_:
            sev, why = "warning", "open backup-power fault"
        elif outages:
            sev, why = "watch", (f"backup-power fault recorded (resolved) and {len(outages)} grid outage(s) in 60 days; "
                                 f"{len(tests)} scheduled generator run(s) logged in 30 days")
        else:
            sev, why = "watch", "backup-power fault recorded, resolved"
        signals.append(_sig("R4_BACKUP_POWER", "backup_power", "B1", None, sev, PATHWAYS["backup_power"]["title"],
                            why, bp + outages, bool(open_)))

    # --- R5/R6/R7 fire water, smoke control, PA ------------------------------------------
    for rule, path, tag in (("R5_FIRE_WATER", "fire_water", "fire_water"),
                            ("R6_SMOKE_CONTROL", "smoke_control", "smoke_control"),
                            ("R7_PA", "pa_system", "pa_system")):
        items = [e for e in recs if tag in tagset(e) and "fault" in tagset(e)]
        for (asset, zone), grp in _group_by_asset_or_zone(items).items():
            open_ = [e for e in grp if e.is_open]
            if open_:
                sev, why = ("high" if path == "fire_water" else "warning"), "fault not resolved"
            elif any(_within(e.timestamp, now, 60) for e in grp):
                sev, why = "watch", "fault in the last 60 days, resolved"
            else:
                continue
            signals.append(_sig(rule, path, zone or None, asset or None, sev, PATHWAYS[path]["title"], why, grp, bool(open_)))

    # --- R9 reported fire/smoke events -----------------------------------------------------
    fe = [e for e in recs if "fire_event" in tagset(e)]
    for e in fe:
        recent = _within(e.timestamp, now, 2)
        sev = "emergency" if (e.is_open and recent) else ("warning" if e.is_open else "watch")
        signals.append(_sig("R9_FIRE_EVENT", "fire_event", e.zone, e.asset_id, sev, PATHWAYS["fire_event"]["title"],
                            "record mentions fire/smoke", [e], bool(e.is_open)))
    return signals


def meter_signals(episode_evidence: list[Evidence], now: datetime) -> list[Signal]:
    """R8: meter episodes (PORTED detection) become supporting electrical-anomaly signals (NEW use)."""
    out: list[Signal] = []
    by_meter: dict[str, list[Evidence]] = defaultdict(list)
    for e in episode_evidence:
        if e.values.get("label") in ("Evidence-based risk", "Anomaly to monitor") and _within(e.timestamp, now, 30):
            by_meter[e.asset_id].append(e)
    for meter, items in by_meter.items():
        risky = [e for e in items if e.values.get("label") == "Evidence-based risk"]
        sev = "watch"
        why = f"{len(items)} unexplained consumption episode(s) in the last 30 days" + (
            f", {len(risky)} recurring/long" if risky else "")
        out.append(_sig("R8_METER_ANOMALY", "electrical_anomaly", items[0].zone, meter, sev,
                        f"Consumption anomalies on {meter}", why, items, False, origin="PORTED"))
    return out
