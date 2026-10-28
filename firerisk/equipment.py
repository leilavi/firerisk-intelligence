"""Building equipment alerts (one per equipment item or meter).

ORIGIN: PORTED. These are the alert topics of the pre-existing risk-alert skill v2.2, now in code:
  * skill §2C.A  - open or overdue faults, repeated faults on the same equipment, critical equipment
                   (electrical, generator, fire-safety, lifts, wastewater) treated as more serious;
  * skill §5A.8  - meter consumption episodes (Anomaly to monitor -> Watch, Evidence-based risk -> Warning,
                   main water rise / main electricity near zero still ongoing -> High) - the R8 meter signals;
  * skill §7     - five levels, judged by consequence and time left; §8 - the 14 alert fields;
  * skill §10.4  - an item past its deadline ("Quá hạn") is considered for a higher level.
The skill gives guidance, not numeric cut-offs, for §2C.A; the cut-offs below are PRELIMINARY rule parameters
written during the Hackathon and documented in RISK_RULES.md.

Equipment alerts are independent of fire-risk alerts: their level is never changed by the fire-risk module.
An equipment alert is linked to a fire-risk alert only when there is a stated reason (same record, same
equipment, or a meter that measures equipment in the fire-risk alert).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime

from .alert_fields import PATHWAY_KB, URGENCY, _confidence, _evidence_line
from .config import ASSETS, METER_FEEDS, METERS, SEVERITY_LABEL, SEVERITY_ORDER, ZONE_LABELS
from .hazards.tagging import tagset
from .models import Evidence, Signal

REPEAT_WINDOW_DAYS = 90       # preliminary: two fault records on the same equipment within 90 days = repeated
RECENT_HISTORY_DAYS = 90      # resolved faults older than this do not keep an equipment alert open
CRITICAL_ROLES = {"electrical_room", "electrical_panel", "backup_power", "fire_water", "smoke_control",
                  "fire_detection", "lightning", "motor_equipment"}   # skill §2C.A: điện, máy phát, PCCC, XLNT…
CRITICAL_WORDS = ("thang máy", "thang cuốn", "pccc", "báo cháy", "máy phát", "msb", "mba", "xlnt")

ROLE_CONSEQUENCE = {
    "electrical_room": "Loss of supply to part or all of the building; damaged switchgear or transformer.",
    "electrical_panel": "Loss of supply to the circuits fed by this panel.",
    "backup_power": "Standby power may be unavailable during a grid outage.",
    "fire_water": "Reduced water for fire fighting while the fault lasts.",
    "smoke_control": "Smoke exhaust may not run when needed.",
    "fire_detection": "Fire detection in the affected area may be delayed or missing.",
    "lightning": "Reduced lightning protection until checked.",
    "motor_equipment": "Equipment stops; a jammed or overloaded motor can overheat.",
    "hvac": "Loss of cooling in the served area; comfort and equipment-room temperature affected.",
}
GENERIC_CONSEQUENCE = "The equipment may stay out of service or fail again; operational impact depends on what it serves."


def _rank(s: str) -> int:
    return SEVERITY_ORDER.index(s)


def _up(s: str, cap: str = "high") -> str:
    return SEVERITY_ORDER[min(_rank(s) + 1, _rank(cap))] if _rank(s) < _rank(cap) else s


def _is_fault(e: Evidence) -> bool:
    return "fault" in tagset(e) or (e.values.get("service_type") or "").lower().startswith("repair needed")


@dataclass
class EquipmentAlert:
    alert_id: str
    asset_id: str | None
    asset_name: str | None
    zone: str | None
    zone_label: str
    critical: bool
    severity: str
    title: str
    rules: list[dict]                 # [{rule, severity, basis, evidence_ids}]
    evidence_ids: list[str]
    first_seen: datetime | None
    last_seen: datetime | None
    open_items: int
    origin: str = "PORTED"
    fields: dict = field(default_factory=dict)
    fire_links: list[dict] = field(default_factory=list)   # [{fire_alert_id, reasons}]

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("first_seen", "last_seen"):
            d[k] = d[k].isoformat() if d[k] else None
        return d


def _critical(asset_id: str | None, items: list[Evidence]) -> bool:
    role = (ASSETS.get(asset_id or "") or {}).get("fire_role")
    if role in CRITICAL_ROLES or (METERS.get(asset_id or "") or {}).get("role", "").endswith("main"):
        return True
    text = " ".join(f"{e.title} {e.text}".lower() for e in items)
    return any(w in text for w in CRITICAL_WORDS)


def _days(a: datetime, b: datetime) -> float:
    return abs((a - b).total_seconds()) / 86400


def build_equipment_alerts(evidence: list[Evidence], meter_sigs: list[Signal], now: datetime,
                           register: dict | None = None) -> list[EquipmentAlert]:
    register = register or {}
    recs = [e for e in evidence if e.kind in ("asset_service", "incident") and "test_record" not in e.flags]
    groups: dict[str, list[Evidence]] = defaultdict(list)
    for e in recs:
        if e.asset_id:
            groups[e.asset_id].append(e)
        elif e.is_open and _is_fault(e):          # open incident with no Equipment_ID: its own alert
            groups[f"record:{e.evidence_id}"].append(e)
    alerts: list[EquipmentAlert] = []

    for key, items in groups.items():
        asset = None if key.startswith("record:") else key
        faults = sorted((e for e in items if _is_fault(e)), key=lambda e: e.timestamp or now)
        if not faults:
            continue
        crit = _critical(asset, items)
        rules: list[dict] = []
        open_ = [e for e in faults if e.is_open]
        if open_:
            sev = "warning" if crit else "watch"
            basis = f"{len(open_)} open fault record(s) on {'critical ' if crit else ''}equipment (skill §2C.A)"
            overdue = [e for e in open_ if "overdue" in e.flags]
            rules.append({"rule": "EQ1_OPEN_FAULT", "severity": sev, "basis": basis,
                          "evidence_ids": [e.evidence_id for e in open_]})
            if overdue:
                days = max(e.values.get("overdue_days") or 0 for e in overdue)
                # skill §10.4: overdue -> consider a higher level (§7). High needs a serious consequence (§7), which an
                # overdue date alone does not show, so the raise stops at Warning (preliminary).
                rules.append({"rule": "EQ2_OVERDUE", "severity": _up(sev, cap="warning"),
                              "basis": f"open repair past its expected completion by {days:g} day(s)"
                                       + ("; raised one level (skill §10.4, overdue)" if sev == "watch" else
                                          "; already Warning - an overdue date alone does not justify High (skill §7)"),
                              "evidence_ids": [e.evidence_id for e in overdue]})
        dated = [e for e in faults if e.timestamp]
        repeated = any(_days(a.timestamp, b.timestamp) <= REPEAT_WINDOW_DAYS for a, b in zip(dated, dated[1:]))
        recent = dated and _days(dated[-1].timestamp, now) <= RECENT_HISTORY_DAYS
        if len(dated) >= 2 and (repeated or open_) and (recent or open_):
            burnt = any("burnt_overheat" in tagset(e) for e in dated)
            sev = "warning" if crit else "watch"
            basis = (f"{len(dated)} fault records on the same equipment"
                     + (f", two within {REPEAT_WINDOW_DAYS} days" if repeated else ", fault returned after an earlier repair")
                     + ("; one recorded a burnt/overheated motor" if burnt else "") + " (skill §2C.A, repeated faults)")
            rules.append({"rule": "EQ3_REPEATED_FAULT", "severity": sev, "basis": basis,
                          "evidence_ids": [e.evidence_id for e in dated]})
        if not rules:
            continue
        ev_ids = list(dict.fromkeys(i for r in rules for i in r["evidence_ids"]))
        alerts.append(_make(key, asset, items, crit, rules, ev_ids, open_, evidence, now, register=register))

    for s in meter_sigs:   # R8 meter signals = equipment alerts for meters (skill §5A.8 levels unchanged)
        items = [e for e in evidence if e.evidence_id in set(s.evidence_ids)]
        rules = [{"rule": "EQ4_METER_" + s.rule_id, "severity": s.severity, "basis": s.basis + " (skill §5A.8)",
                  "evidence_ids": list(s.evidence_ids)}]
        a = _make(s.asset_id, s.asset_id, items, _critical(s.asset_id, items), rules, list(s.evidence_ids),
                  [e for e in items if e.values.get("ongoing")], evidence, now, meter_signal=s, register=register)
        alerts.append(a)
    alerts.sort(key=lambda a: (-_rank(a.severity), -(a.last_seen.timestamp() if a.last_seen else 0)))
    return alerts


def _make(key, asset, items, crit, rules, ev_ids, open_, evidence, now, meter_signal: Signal | None = None,
          register: dict | None = None):
    sev = max((r["severity"] for r in rules), key=_rank)
    index = {e.evidence_id: e for e in evidence}
    found = [index[i] for i in ev_ids if i in index]
    times = [e.timestamp for e in found if e.timestamp]
    name = (ASSETS.get(asset or "") or METERS.get(asset or "") or {}).get("name") if asset else None
    reg = (register or {}).get(asset or "")
    if not name and reg and reg.get("name"):      # name from the asset register (Asset tab)
        name = reg["name"]
    if not name:   # equipment not in the configured list: show its ID and the record's own short text
        short = (found[0].title[:40] if found else "")
        name = f"{asset} ({short})" if asset and short else asset or short or key
    zone = (next((e.zone for e in found if e.zone), None) or (ASSETS.get(asset or "") or METERS.get(asset or "") or {}).get("zone")
            or (reg or {}).get("zone"))
    kind = "meter" if meter_signal else "equipment"
    alert_id = f"EQ-{asset}" if asset else f"EQ-{key.split(':', 1)[1]}"
    if meter_signal:
        headline = f"{name}: {len(found)} unusual consumption period(s) in 30 days"
    elif any(r["rule"] == "EQ2_OVERDUE" for r in rules):
        headline = f"{name}: repair overdue"
    elif open_:
        headline = f"{name}: open fault"
    else:
        headline = f"{name}: repeated faults"
    a = EquipmentAlert(alert_id=alert_id, asset_id=asset, asset_name=name, zone=zone,
                       zone_label=ZONE_LABELS.get(zone or "", zone or "Building"), critical=crit, severity=sev,
                       title=headline, rules=rules, evidence_ids=ev_ids, first_seen=min(times) if times else None,
                       last_seen=max(times) if times else None, open_items=len(open_))
    a.fields = equipment_fields(a, found, kind, meter_signal, now)
    return a


def equipment_fields(a: EquipmentAlert, items: list[Evidence], kind: str, meter_signal, now: datetime) -> dict:
    """The 14 skill §8 fields for an equipment alert. No cause is invented: when the records do not state one,
    the cause is 'not verified'."""
    urg, deadline, why = URGENCY.get(a.severity, URGENCY["watch"])
    conf, conf_why = _confidence(items, a)
    role = (ASSETS.get(a.asset_id or "") or {}).get("fire_role")
    if kind == "meter":
        kb = PATHWAY_KB[meter_signal.pathway]
        f = dict(meter_signal.fields) if getattr(meter_signal, "fields", None) else {}
        consequence, chain, actions, closure, unknowns = (kb["consequence"], kb["chain"], kb["actions"],
                                                          kb["closure"], kb["unknowns"])
        causes = f.get("possible_causes") or [{"cause": c, "status": "hypothesis", "basis": "not verified"}
                                              for c, _ in kb["causes"]]
        comparison = f.get("comparison") or a.rules[0]["basis"]
        trigger = "—"
    else:
        consequence = ROLE_CONSEQUENCE.get(role or "", GENERIC_CONSEQUENCE)
        chain = ["Fault recorded", "Fault stays open or returns", "Equipment unavailable or damaged"]
        actions = ["Inspect the equipment and record the finding (assigned technician)",
                   "Close the repair record with what was done, or set a new expected completion date"]
        if any(r["rule"] == "EQ3_REPEATED_FAULT" for r in a.rules):
            actions.append("Review the repeated faults together to find a common cause before the next repair")
        closure = "Repair record closed with the work described and the equipment checked in operation."
        unknowns = ["Cause of the fault (not verified)"]
        if a.asset_id is None:
            unknowns.append("Equipment_ID not recorded on the incident")
        causes = []
        comparison = "; ".join(r["basis"] for r in a.rules)
        trigger = "Continued operation while the fault is open." if a.open_items else "—"
    return {
        "problem": "; ".join(r["basis"] for r in a.rules),
        "evidence": [_evidence_line(e) for e in sorted(items, key=lambda e: e.timestamp or now)],
        "comparison": comparison,
        "possible_causes": causes,
        "cause_status": "Cause not verified",
        "consequence": consequence,
        "risk_chain": chain,
        "trigger_condition": trigger,
        "urgency": {"level": SEVERITY_LABEL[a.severity], "label": urg, "reason": why},
        "preventive_actions": actions,
        "deadline": {"text": deadline, "basis": f"preliminary rule for level {SEVERITY_LABEL[a.severity]}"},
        "closure_condition": closure,
        "confidence": {"level": conf, "reason": conf_why},
        "sources": sorted({_evidence_line(e)["source"] for e in items if e.source}),
        "unknowns": unknowns,
        "headline": a.title,
        "why_short": [r["basis"] for r in a.rules],
        "kind": kind,
    }


def link_to_fire_alerts(eq_alerts: list[EquipmentAlert], fire_alerts, evidence_index: dict) -> None:
    """Attach reasoned links equipment alert <-> fire-risk alert. Levels are not changed."""
    feeds = {m: set(v) for m, v in METER_FEEDS.items()}
    for fa in fire_alerts:
        fa_ids = set(fa.evidence_ids)
        fa_assets = {evidence_index[i].asset_id for i in fa.evidence_ids if i in evidence_index and evidence_index[i].asset_id}
        related = []
        for ea in eq_alerts:
            reasons = []
            shared = [i for i in ea.evidence_ids if i in fa_ids]
            if shared:
                reasons.append(f"{len(shared)} record(s) are evidence in both alerts")
            if ea.asset_id and ea.asset_id in fa_assets:
                reasons.append(f"same equipment {ea.asset_id}")
            measured = feeds.get(ea.asset_id or "", set()) & fa_assets
            if measured:
                reasons.append(f"meter {ea.asset_id} measures {', '.join(sorted(measured))}, which is part of this "
                               f"fire-risk alert")
            if reasons:
                ea.fire_links.append({"fire_alert_id": fa.alert_id, "reasons": reasons})
                related.append({"equipment_alert_id": ea.alert_id, "reasons": reasons, "severity": ea.severity})
        fa.related_equipment = related
