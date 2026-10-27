"""The 14 mandatory alert fields (skill v2.2 §8), filled deterministically from rules and evidence.

ORIGIN: PORTED structure (skill §8: 14 fields; §7 severity; "Nguyên nhân chưa được xác minh" when the cause is
unknown) + NEW content per fire-hazard pathway. No AI involved: Muse Spark output is stored separately.

Nothing here invents measurements, thresholds or probabilities. Candidate causes are phrased as hypotheses
to verify; a candidate is marked "supported" only when a source record literally mentions it.
"""

from __future__ import annotations

import re
from datetime import datetime

from .config import ASSETS, METERS, SEVERITY_LABEL
from .hazards.pathways import PATHWAYS

# ---------------------------------------------------------------------------------------------
# Per-pathway knowledge (NEW, generic fire-safety reasoning; reviewed as preliminary)
#   causes: (candidate cause, regex that counts as support when found in a record of the signal)
# ---------------------------------------------------------------------------------------------
PATHWAY_KB: dict[str, dict] = {
    "water_electrical": {
        "causes": [("Cracked walls / failed waterproofing let rainwater in", r"nứt|vết nứt|chống thấm|bơm keo|silicon"),
                   ("Heavy rain overwhelms drainage around the technical rooms", r"mưa"),
                   ("Leaking pipe or condensation inside the room", r"rò rỉ|đường ống|\bống nước|ngưng tụ")],
        "consequence": "Water on or near transformer/switchboard equipment can cause insulation failure, short circuit "
                       "or arcing (electrical ignition source) and loss of supply to the building.",
        "chain": ["Water enters the electrical room", "Moisture reaches cables, busbars or switchgear",
                  "Insulation degrades or a short circuit / arc occurs", "Fire in the electrical room or power loss"],
        "trigger": "Next heavy rain while the ingress path is not sealed.",
        "actions": ["Inspect MBA/MSB rooms for water, damp marks and cable-trench water (qualified electrician)",
                    "Keep water away from live equipment; do not dry energised equipment",
                    "Verify the sealing work and re-inspect after the next heavy rain, with photos"],
        "closure": "Signed inspection record showing the rooms dry after heavy rain, and the incident closed with the "
                   "permanent repair described.",
        "unknowns": ["Current moisture state of the rooms", "Whether the sealing work stopped the ingress"],
    },
    "detection_impairment": {
        "causes": [("Faulty monitor module or loose wiring", r"dây|module|mô đun|đầu vào|hộp"),
                   ("Moisture or dust in detector / module housing", r"ẩm|nước|bụi"),
                   ("Panel fault cleared by reset without root cause", r"reset|khởi động lại")],
        "consequence": "Automatic fire detection in the affected area may be delayed or missing.",
        "chain": ["Detector / monitor module faults recur", "Fault is cleared but cause not removed",
                  "Detection unavailable when a fire starts", "Late alarm and late response"],
        "trigger": "A fire starting while the module is in fault.",
        "actions": ["Functional test of the affected detection loop and module (fire-system maintainer)",
                    "Download the panel fault history since the first fault",
                    "Arrange compensatory checks per site procedure while faults recur"],
        "closure": "Loop test passed and no recurrence of the fault for at least 30 days.",
        "unknowns": ["Fault history stored in the fire alarm panel", "Whether the last fix removed the cause"],
    },
    "motor_overheat": {
        "causes": [("Seized bearing or jammed mechanical part overloads the motor", r"kẹt|bạc đạn|cơ khí"),
                   ("Worn or broken drive belt", r"curoa|cu roa|dây đai"),
                   ("Motor winding damage after a previous burn-out", r"cháy mô tơ|quấn lại")],
        "consequence": "An overloaded or jammed motor can overheat; a previous burn-out shows this has already happened.",
        "chain": ["Mechanical jam / wear", "Motor draws high current or stalls", "Winding overheats",
                  "Smoke or fire at the motor / control panel"],
        "trigger": "Restarting the jammed equipment before the mechanical fault is fixed.",
        "actions": ["Confirm the equipment is isolated and tagged out until repaired",
                    "Repair the mechanical fault, replace worn belt/bearings",
                    "Test run with current and temperature checks before returning to service"],
        "closure": "Repair record closed and a test run with normal current/temperature documented.",
        "unknowns": ["Isolation / lock-out status of the equipment", "Motor current and temperature data"],
    },
    "backup_power": {
        "causes": [("Starter batteries degraded", r"ắc quy|acquy|giảm hiệu năng"),
                   ("Charger or terminals faulty", r"sạc|đầu nối|siết")],
        "consequence": "The standby generator may fail to start during a grid outage; loads on the generator "
                       "(fire-safety loads not confirmed in the data) would lose power.",
        "chain": ["Battery / start system degrades", "Grid outage occurs", "Generator fails to start",
                  "Loss of backup power"],
        "trigger": "The next grid outage.",
        "actions": ["Check battery replacement record and battery test results",
                    "Run a start test under load and record it",
                    "Record which fire-safety loads are connected to the generator"],
        "closure": "Battery test and load-start test passed and recorded.",
        "unknowns": ["List of loads connected to the generator", "Battery test measurements"],
    },
    "fire_water": {
        "causes": [("Float switch / level control fault", r"phao"), ("Pump fault", r"bơm")],
        "consequence": "Less water may be available for fire-fighting if the tank or pump does not work.",
        "chain": ["Level control or pump fault", "Tank not refilled or pump not starting", "Insufficient fire water"],
        "trigger": "A fire while the fault persists.",
        "actions": ["Verify tank level and pump auto-start test", "Check the repaired float switch"],
        "closure": "Pump test and tank level check passed and recorded.",
        "unknowns": ["Recent fire pump test results"],
    },
    "smoke_control": {
        "causes": [("Fan or motor fault", r"quạt|mô tơ")],
        "consequence": "Smoke may spread in escape routes if exhaust fans do not run.",
        "chain": ["Smoke exhaust fault", "Fans do not start on alarm", "Smoke spreads"],
        "trigger": "A fire while the fault persists.",
        "actions": ["Functional test of smoke exhaust fans from the fire panel"],
        "closure": "Fan test from the fire panel passed and recorded.",
        "unknowns": ["Fan test results"],
    },
    "pa_system": {
        "causes": [("Audio switch / amplifier fault", r"switch|tín hiệu|âm thanh")],
        "consequence": "Evacuation announcements may be delayed.",
        "chain": ["PA fault", "Announcements unavailable", "Slower evacuation"],
        "trigger": "An evacuation while the fault persists.",
        "actions": ["Test PA announcements in all zones"],
        "closure": "PA test passed in all zones and recorded.",
        "unknowns": ["Latest PA test result"],
    },
    "electrical_anomaly": {
        "causes": [("Equipment stopped or changed load", r""), ("Meter reading or data-entry error", r"")],
        "consequence": "On its own, a consumption change is not a fire indicator; it can confirm that equipment "
                       "stopped or changed load around the time of another record.",
        "chain": ["Consumption deviates from baseline", "Cross-check with equipment records and outages"],
        "trigger": "—",
        "actions": ["Cross-check the meter readings with equipment logs and outage times",
                    "Verify the meter unit/multiplier where it is not verified"],
        "closure": "Deviation explained by a documented cause or by corrected readings.",
        "unknowns": ["Verified unit/multiplier of sub-meters", "Activity data for the same days"],
    },
    "consumption_anomaly": {
        "causes": [("Leak, valve or float fault", r""), ("Meter reading or data-entry error", r"")],
        "consequence": "Unexplained water use can mean a leak; relevant to fire safety if water reaches electrical "
                       "equipment or affects the fire-water supply.",
        "chain": ["Water use deviates from baseline", "Leak or control fault suspected", "Check affected areas"],
        "trigger": "—",
        "actions": ["Check valves, floats and visible pipework; compare with activity"],
        "closure": "Deviation explained or repaired.",
        "unknowns": ["Activity data for the same days"],
    },
    "fire_event": {
        "causes": [], "consequence": "Possible fire or smoke event.", "chain": ["Reported fire/smoke"],
        "trigger": "Now.", "actions": ["Follow the building's approved emergency procedure"],
        "closure": "Event investigated and closed by the responsible person.", "unknowns": ["Event confirmation"],
    },
}

URGENCY = {  # PORTED wording from skill §7 / §8 field 9 and 11; deadlines are preliminary rule parameters
    "emergency": ("Act immediately", "immediately", "possible immediate danger to people or a critical system"),
    "high": ("Act within the day", "within 24 hours", "serious consequence and an unresolved item"),
    "warning": ("Check within a few days", "within 7 days", "abnormal or recurring, needs a check"),
    "watch": ("Monitor", "at the next routine inspection", "early sign or resolved history"),
    "normal": ("No action", "—", "no notable sign"),
}

GLOBAL_UNKNOWNS = [
    "No temperature, smoke or gas sensor telemetry is connected; findings rely on manual logs and meters.",
    "Daily checklists keep only the latest result in the source (no checklist history).",
    "Photos referenced by the logs are not accessible yet.",
]


def _confidence(items, signal) -> tuple[str, str]:
    """skill §8 field 13: High / Medium / Low / Insufficient data, with the reason."""
    real = [e for e in items if "derived" not in e.flags]
    kinds = {e.kind for e in real}
    flagged = [e for e in real if {"test_record", "placeholder_text", "missing_status", "unmapped_status"} & set(e.flags)]
    if not real:
        return "Low", "based only on derived meter analysis (no direct record)"
    if flagged and len(flagged) == len(real):
        return "Insufficient data", "all supporting records carry data-quality flags"
    if len(real) >= 2 and len(kinds) >= 2:
        return "High", f"{len(real)} records from {len(kinds)} different record types"
    if len(real) >= 2:
        return "Medium", f"{len(real)} records of the same type"
    return "Medium", "one direct record"


def _evidence_line(e) -> dict:
    v = e.values
    measure = None
    if e.kind == "meter_episode":
        measure = {"value": v.get("peak"), "baseline_median": v.get("median"), "unit": v.get("unit"),
                   "unit_verified": v.get("unit_verified"), "pct": v.get("pct"), "days": v.get("days")}
    elif e.kind == "generator_run":
        measure = {"value": v.get("minutes"), "unit": "min", "fuel_stock_l": v.get("fuel_stock_l")}
    src = e.source
    return {"evidence_id": e.evidence_id, "time": e.timestamp.isoformat() if e.timestamp else None, "kind": e.kind,
            "title": e.title, "status": e.status, "unresolved": e.is_open, "measure": measure,
            "source": f"{src.source_title} › {src.sheet}" + (f" › row {src.row}" if src and src.row else "") if src else None,
            "record_id": src.record_id if src else None, "flags": e.flags}


def signal_fields(sig, index: dict, now: datetime) -> dict:
    kb = PATHWAY_KB.get(sig.pathway, PATHWAY_KB["electrical_anomaly"])
    items = [index[i] for i in sig.evidence_ids if i in index]
    ctx = [index[i] for i in sig.context_ids if i in index]
    causes = []
    for cause, pat in kb["causes"]:
        supported = [e.evidence_id for e in items if pat and re.search(pat, f"{e.title} {e.text}".lower())]
        causes.append({"cause": cause, "status": "hypothesis",
                       "basis": "mentioned in " + ", ".join(supported) if supported else "not mentioned in the records"})
    meters = [e for e in items if e.kind == "meter_episode"]
    if meters:
        comparison = "; ".join(f"{e.asset_id}: {e.values.get('peak'):g} vs baseline median {e.values.get('median'):g} "
                               f"{e.values.get('unit') or ''} ({e.values.get('pct'):+.0f}%)" for e in meters[:4])
    else:
        comparison = f"{len(items)} record(s) in this pathway; rule basis: {sig.basis}. No numeric baseline applies."
    urg, deadline, why = URGENCY.get(sig.severity, URGENCY["watch"])
    conf, conf_why = _confidence(items, sig)
    assets = sorted({e.asset_id for e in items if e.asset_id})
    return {
        "problem": f"{sig.title}: {sig.basis}",
        "evidence": [_evidence_line(e) for e in sorted(items, key=lambda e: e.timestamp or now)],
        "comparison": comparison,
        "possible_causes": causes,
        "cause_status": "Cause not verified (Nguyên nhân chưa được xác minh)",
        "consequence": kb["consequence"],
        "risk_chain": kb["chain"],
        "trigger_condition": kb["trigger"],
        "urgency": {"level": SEVERITY_LABEL[sig.severity], "label": urg, "reason": why},
        "preventive_actions": kb["actions"],
        "deadline": {"text": deadline, "basis": f"preliminary rule for level {SEVERITY_LABEL[sig.severity]}"},
        "closure_condition": kb["closure"],
        "confidence": {"level": conf, "reason": conf_why},
        "sources": sorted({_evidence_line(e)["source"] for e in items if e.source}),
        "context_evidence": [_evidence_line(e) for e in ctx],
        "affected_assets": [{"asset_id": a, "name": (ASSETS.get(a) or METERS.get(a) or {}).get("name")} for a in assets],
        "unknowns": kb["unknowns"],
        "mentioned_terms": sorted({t["term"] for e in items for t in e.tags if t["tag"] not in ("fault", "checklist_pass")})[:12],
    }


def short_text(sig, index: dict) -> str:
    """One short, plain sentence for lists and headlines (NEW). Facts only, from the signal's own evidence."""
    items = [index[i] for i in sig.evidence_ids if i in index]
    n_open = sum(1 for e in items if e.is_open)
    unresolved = f", {n_open} not fixed" if n_open else ", all marked fixed"
    p = sig.pathway
    if p == "water_electrical":
        return f"Water entering the electrical rooms ({len(items)} reports{unresolved})"
    if p == "detection_impairment":
        return f"Fire-detection fault reported {len(items)}× in the last 30 days{unresolved}"
    if p == "motor_overheat":
        burnt = any(t["tag"] == "burnt_overheat" for e in items for t in e.tags)
        name = (ASSETS.get(sig.asset_id or "") or {}).get("name", "Motor")
        return f"{name}: {'jammed again after a past motor burn-out' if burnt else 'motor or mechanical failure'}{unresolved}"
    if p == "backup_power":
        outages = sum(1 for e in items if e.kind == "generator_run")
        return f"Generator battery fault and {outages} grid outage(s) in 60 days{unresolved}"
    if p in ("electrical_anomaly", "consumption_anomaly"):
        name = (METERS.get(sig.asset_id or "") or {}).get("name", sig.asset_id)
        n = len(items)
        return f"{name}: {n} unusual consumption period(s) in 30 days"
    return f"{PATHWAYS[p]['title']} ({len(items)} record(s){unresolved})"


def assessment_class(alert, signals) -> tuple[str, str]:
    """NEW: distinguishes data anomaly / risk indicator / insufficient evidence. 'Confirmed' is only ever set by a
    person (verification status 'confirmed'), never by the rules or the AI."""
    from .correlation import SUPPORTING_PATHWAYS
    hazard = [s for s in signals if s.pathway not in SUPPORTING_PATHWAYS]
    confs = [s.fields["confidence"]["level"] for s in signals if getattr(s, "fields", None)]
    if hazard and confs and all(c == "Insufficient data" for c in confs):
        return "insufficient_evidence", "Not enough evidence to confirm (Chưa đủ dữ liệu để xác nhận)"
    if hazard:
        return "risk_indicator", "Risk indicator from recorded faults; not confirmed on site"
    return "data_anomaly", "Data anomaly only (meter pattern); not a fire-risk finding by itself"


def enrich_alerts(alerts, signals, index: dict, source_status: list[dict], now: datetime) -> None:
    by_id = {s.signal_id: s for s in signals}
    for s in signals:
        s.fields = signal_fields(s, index, now)
        s.fields["short"] = short_text(s, index)
    down = [f"{x['source']} / {x.get('sheet') or ''}: {x['error']}" for x in source_status if x.get("error")]
    stale = [f"{x['source']} / {x.get('sheet') or ''}: newest record {x.get('age_days')} days old" for x in source_status
             if x.get("stale")]
    for a in alerts:
        sigs = [by_id[i] for i in a.signal_ids if i in by_id]
        top = sigs[0]
        cls, cls_text = assessment_class(a, sigs)
        open_sigs = [s for s in sigs if s.is_open]
        headline_sig = open_sigs[0] if open_sigs else top
        why: list[str] = []
        def bare(txt):
            return re.sub(r", (\d+ not fixed|all marked fixed)\)?$", lambda m: ")" if m.group(0).endswith(")") else "", txt)
        meter_paths = ("electrical_anomaly", "consumption_anomaly")
        for s in sigs:
            if s.is_open:
                why.append(("Still ongoing: " if s.pathway in meter_paths else "Not fixed: ") + bare(s.fields["short"]))
        others = [s for s in sigs if not s.is_open and s.severity in ("warning", "high", "emergency")]
        for s in others[:2]:
            why.append(("Repeated: " if s.pathway in meter_paths else "Recurring, marked fixed: ") + bare(s.fields["short"]))
        hazard_types = {s.pathway for s in sigs} - {"electrical_anomaly", "consumption_anomaly"}
        if len(hazard_types) >= 2:
            why.append(f"{len(hazard_types)} kinds of fire-safety problem in the same zone")
        if not why:
            why.append(top.fields["short"])
        a.fields = {
            "headline": headline_sig.fields["short"],
            "why_short": why,
            "assessment_class": cls, "assessment_text": cls_text,
            "why": a.severity_basis,
            "urgency": top.fields["urgency"], "deadline": top.fields["deadline"],
            "affected_assets": sorted({(x["asset_id"], x["name"]) for s in sigs for x in s.fields["affected_assets"]}),
            "actions": [{"action": act, "pathway": s.pathway, "level": s.severity, "signal_id": s.signal_id}
                        for s in sigs if s.severity in ("emergency", "high", "warning") or s.is_open
                        for act in s.fields["preventive_actions"]],
            "unknowns": sorted({u for s in sigs for u in s.fields["unknowns"]}) + GLOBAL_UNKNOWNS
                        + [f"Source unavailable: {d}" for d in down] + [f"Source not updated: {d}" for d in stale],
            "confidence": top.fields["confidence"],
        }
