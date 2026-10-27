"""Cross-source evidence correlation and zone-level alert aggregation.

ORIGIN: NEW. The pre-existing skill compared meters with vehicle counts only; it did not link
incidents, asset repairs, inspections, generator runs and meter episodes into one evidence graph.

Every link carries an explicit `type` and a human-readable `reason`. Links are relationships
worth checking, NOT proof of causation.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from .config import ASSET_DEPENDENCIES, METER_FEEDS, SEVERITY_LABEL, SEVERITY_ORDER, ZONE_LABELS
from .hazards.pathways import PATHWAYS
from .models import Alert, Evidence, Signal

LINK_WINDOW_DAYS = 14
SUPPORTING_PATHWAYS = {"electrical_anomaly", "consumption_anomaly"}


def _rank(sev: str) -> int:
    return SEVERITY_ORDER.index(sev)


def _days(a: Evidence, b: Evidence) -> float | None:
    if a.timestamp and b.timestamp:
        return abs((a.timestamp - b.timestamp).total_seconds()) / 86400
    return None


def build_links(items: list[Evidence]) -> list[dict]:
    """One link per evidence pair, listing every reason found. Pairs whose only reason is
    'same zone and time window' are kept only when both records carry a hazard tag."""
    deps = {}
    for x, y, why in ASSET_DEPENDENCIES:
        deps[(x, y)] = deps[(y, x)] = why
    feeds = {(m, a) for m, assets in METER_FEEDS.items() for a in assets}
    weak_only_ok = lambda e: bool(_hazard_tags(e)) or e.kind == "meter_episode"
    links: list[dict] = []
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            if a.evidence_id == b.evidence_id:
                continue
            d = _days(a, b)
            reasons: list[tuple[str, str]] = []
            if a.asset_id and a.asset_id == b.asset_id:
                reasons.append(("same_asset", f"both records concern asset {a.asset_id}"))
            if a.asset_id and b.asset_id and (a.asset_id, b.asset_id) in deps:
                reasons.append(("system_dependency", deps[(a.asset_id, b.asset_id)]))
            for x, y in ((a, b), (b, a)):
                if x.kind == "meter_episode" and y.asset_id and (x.asset_id, y.asset_id) in feeds and d is not None and d <= 3:
                    reasons.append(("measured_by_meter",
                                    f"meter {x.asset_id} measures {y.asset_id}; {d:.1f} day(s) apart"))
                if x.kind == "generator_run" and "backup_power" in _hazard_tags(y):
                    reasons.append(("system_dependency", "generator run vs. generator/battery record"))
            shared = _hazard_tags(a) & _hazard_tags(b)
            if shared and d is not None and d <= 60:
                reasons.append(("same_hazard_type", f"both tagged {', '.join(sorted(shared))}; {d:.0f} day(s) apart"))
            if a.zone and a.zone == b.zone and d is not None and d <= LINK_WINDOW_DAYS and a.kind != b.kind:
                if reasons or (weak_only_ok(a) and weak_only_ok(b)):
                    reasons.append(("same_zone_time_window", f"same zone {a.zone}, {d:.1f} day(s) apart ({a.kind} / {b.kind})"))
            if reasons:
                links.append({"a": a.evidence_id, "b": b.evidence_id,
                              "types": sorted({t for t, _ in reasons}), "reasons": [r for _, r in reasons]})
    return links


def _hazard_tags(e: Evidence) -> set[str]:
    return {t["tag"] for t in e.tags} - {"fault", "motor_equipment", "checklist_pass"}


def aggregate_alerts(signals: list[Signal], evidence_index: dict[str, Evidence], now: datetime) -> list[Alert]:
    """One alert per zone that has at least one Watch-or-higher signal."""
    by_zone: dict[str, list[Signal]] = defaultdict(list)
    for s in signals:
        if _rank(s.severity) >= _rank("watch"):
            by_zone[s.zone or "Building"].append(s)
    alerts: list[Alert] = []
    for zone, sigs in by_zone.items():
        sigs.sort(key=lambda s: -_rank(s.severity))
        base = sigs[0].severity
        basis = [f"Highest single signal: {sigs[0].title} - {sigs[0].severity} ({sigs[0].basis})"]
        hazard_paths = {s.pathway for s in sigs if s.pathway not in SUPPORTING_PATHWAYS}
        open_paths = {s.pathway for s in sigs if s.is_open}
        sev = base
        if len(hazard_paths) >= 2 and open_paths and _rank(sev) < _rank("high"):
            sev = SEVERITY_ORDER[_rank(sev) + 1]
            basis.append(f"Raised one level: {len(hazard_paths)} distinct hazard pathways in the same zone, "
                         f"{len(open_paths)} with unresolved items (compound-risk rule)")
        elif len(hazard_paths) >= 2 and open_paths:
            basis.append(f"{len(hazard_paths)} distinct hazard pathways in the same zone, {len(open_paths)} with "
                         f"unresolved items. Already at {SEVERITY_LABEL[sev]}; the compound rule never raises to Emergency "
                         f"(Emergency requires a reported fire/smoke event)")
        elif len(hazard_paths) >= 2:
            basis.append(f"{len(hazard_paths)} distinct hazard pathways in the same zone, all resolved (no level change)")
        for s in sigs:
            if s.is_open:
                basis.append(f"Unresolved: {s.title} - {s.basis}")
        ev_ids: list[str] = []
        for s in sigs:
            ev_ids.extend(i for i in s.evidence_ids if i not in ev_ids)
        items = [evidence_index[i] for i in ev_ids if i in evidence_index]
        times = [e.timestamp for e in items if e.timestamp]
        links = build_links(items)
        open_items = sum(1 for e in items if e.is_open)
        titles = []
        for s in sigs:  # already sorted by severity
            t = PATHWAYS[s.pathway]["title"]
            if s.pathway not in SUPPORTING_PATHWAYS and t not in titles:
                titles.append(t)
        ctx: list[str] = []
        for s in sigs:
            ctx.extend(c for c in s.context_ids if c not in ctx and c not in ev_ids)
        alerts.append(Alert(
            alert_id=f"ZONE-{zone}", zone=zone, zone_label=ZONE_LABELS.get(zone, zone), severity=sev,
            title=f"{ZONE_LABELS.get(zone, zone)}: " + (", ".join(titles[:3]) if titles else "consumption anomalies"),
            summary=f"{len(sigs)} signal(s), {len(items)} evidence record(s), {len(links)} cross-source link(s), "
                    f"{open_items} unresolved record(s).",
            severity_basis=basis, pathways=sorted({s.pathway for s in sigs}), signal_ids=[s.signal_id for s in sigs],
            evidence_ids=ev_ids, links=links, first_seen=min(times) if times else None,
            last_seen=max(times) if times else None, open_items=open_items, context_ids=ctx))
    alerts.sort(key=lambda a: (-_rank(a.severity), -(a.last_seen.timestamp() if a.last_seen else 0)))
    return alerts
