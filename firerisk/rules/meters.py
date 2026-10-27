"""Daily meter consumption, data gaps and spike/drop detection.

ORIGIN: PORTED from skill v2.2 Stage 2B and §5A:
  - consumption day d = increase from the ~06:00 reading on day d to the reading on day d+1;
  - gaps > 1.5 days are spread evenly and marked "averaged over gap" (never assigned to one day);
  - decreasing readings are excluded and listed for verification;
  - baseline = median and MAD of the previous 28 valid days (excluding spikes and averaged days);
    fewer than 14 days -> whole-period baseline marked "preliminary";
  - spike day: |x - median| > 3 * MAD * 1.4826, or x < 50% / > 150% of median, AND |x - median| >= min_delta;
  - consecutive spike days in the same direction form one episode;
  - EVN vs MSB cross-check: MSB-only spike while EVN is normal -> MSB reading error, not a load change.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from ..config import MAD_BASELINE_DAYS, MAD_K, MAD_SCALE, METERS
from ..models import Evidence


@dataclass
class DayValue:
    day: date
    value: float | None
    flag: str = ""            # "" | "averaged_gap" | "missing" | "negative_excluded"
    evidence_ids: list[str] = field(default_factory=list)
    spike: str = ""           # "" | "up" | "down"
    median: float | None = None
    preliminary: bool = False


@dataclass
class Episode:
    meter: str
    direction: str
    start: date
    end: date
    days: int
    peak: float
    median: float
    pct: float
    evidence_ids: list[str]
    label: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["start"], d["end"] = self.start.isoformat(), self.end.isoformat()
        return d


def readings_by_meter(evidence: list[Evidence]) -> dict[str, list[Evidence]]:
    out: dict[str, list[Evidence]] = defaultdict(list)
    for e in evidence:
        if e.kind == "meter_reading" and e.asset_id in METERS and e.values.get("reading") is not None and e.timestamp:
            out[e.asset_id].append(e)
    for v in out.values():
        v.sort(key=lambda e: e.timestamp)
    return out


def daily_consumption(readings: list[Evidence], meter_id: str) -> tuple[list[DayValue], list[dict]]:
    """Return a full calendar of consumption days plus a list of issues needing verification."""
    mult = METERS.get(meter_id, {}).get("multiplier") or 1
    issues: list[dict] = []
    days: dict[date, DayValue] = {}
    # keep the first reading of each calendar date; extra same-day readings are reported
    by_date: dict[date, Evidence] = {}
    for e in readings:
        d = e.timestamp.date()
        if d in by_date:
            issues.append({"type": "duplicate_same_day", "evidence_id": e.evidence_id, "date": d.isoformat()})
            continue
        by_date[d] = e
    ordered = sorted(by_date.values(), key=lambda e: e.timestamp)
    for prev, cur in zip(ordered, ordered[1:]):
        delta = (cur.values["reading"] - prev.values["reading"]) * mult
        span = (cur.timestamp - prev.timestamp).total_seconds() / 86400
        start = prev.timestamp.date()
        n_days = max(1, round(span))
        if delta < 0:
            issues.append({"type": "decreasing_reading", "evidence_id": cur.evidence_id,
                           "date": cur.timestamp.date().isoformat(), "delta": delta})
            for i in range(n_days):
                days[start + timedelta(days=i)] = DayValue(start + timedelta(days=i), None, "negative_excluded",
                                                           [prev.evidence_id, cur.evidence_id])
            continue
        if span > 1.5:
            per = delta / n_days
            for i in range(n_days):
                days[start + timedelta(days=i)] = DayValue(start + timedelta(days=i), per, "averaged_gap",
                                                           [prev.evidence_id, cur.evidence_id])
        else:
            days[start] = DayValue(start, delta, "", [prev.evidence_id, cur.evidence_id])
    if not days:
        return [], issues
    first, last = min(days), max(days)
    cal: list[DayValue] = []
    d = first
    while d <= last:
        cal.append(days.get(d, DayValue(d, None, "missing")))
        d += timedelta(days=1)
    return cal, issues


def _median_mad(vals: list[float]) -> tuple[float, float]:
    med = statistics.median(vals)
    mad = statistics.median([abs(v - med) for v in vals])
    return med, mad


def detect_spikes(cal: list[DayValue], meter_id: str) -> list[DayValue]:
    """Mark spike days in place (direction + baseline median). Returns the calendar."""
    min_delta = METERS.get(meter_id, {}).get("min_delta", 0)
    clean_all = [dv.value for dv in cal if dv.value is not None and dv.flag == ""]
    for i, dv in enumerate(cal):
        if dv.value is None or dv.flag:
            continue
        window = [x for x in cal[max(0, i - MAD_BASELINE_DAYS):i] if x.value is not None and x.flag == "" and not x.spike]
        vals = [x.value for x in window]
        preliminary = len(vals) < 14
        if preliminary:
            vals = clean_all
        if len(vals) < 3:
            continue
        med, mad = _median_mad(vals)
        dev = dv.value - med
        dv.median, dv.preliminary = med, preliminary
        is_stat = mad > 0 and abs(dev) > MAD_K * mad * MAD_SCALE
        is_ratio = med > 0 and (dv.value < 0.5 * med or dv.value > 1.5 * med)
        if (is_stat or is_ratio) and abs(dev) >= min_delta:
            dv.spike = "up" if dev > 0 else "down"
    return cal


def episodes(cal: list[DayValue], meter_id: str) -> list[Episode]:
    out: list[Episode] = []
    cur: list[DayValue] = []

    def close():
        if not cur:
            return
        direction = cur[0].spike
        peak = max(x.value for x in cur) if direction == "up" else min(x.value for x in cur)
        med = cur[0].median or 0
        ev: list[str] = []
        for x in cur:
            ev.extend(i for i in x.evidence_ids if i not in ev)
        out.append(Episode(meter_id, direction, cur[0].day, cur[-1].day, len(cur), peak, med,
                           round((peak - med) / med * 100, 1) if med else 0.0, ev))

    for dv in cal:
        if dv.spike and cur and cur[-1].spike == dv.spike and (dv.day - cur[-1].day).days == 1:
            cur.append(dv)
        elif dv.spike:
            close()
            cur = [dv]
        else:
            close()
            cur = []
    close()
    return out


def label_episodes(eps: list[Episode], all_eps_by_meter: dict[str, list[Episode]],
                   vehicles_by_day: dict[date, float]) -> list[Episode]:
    """Skill §5A.5-7 conclusion labels."""
    evn_days = {d for e in all_eps_by_meter.get("P-BG.TTC076", [])
                for d in (e.start + timedelta(days=i) for i in range(e.days))}
    veh_vals = list(vehicles_by_day.values())
    veh_med = statistics.median(veh_vals) if veh_vals else None
    for ep in eps:
        ep_days = [ep.start + timedelta(days=i) for i in range(ep.days)]
        if ep.meter == "P-BG.TTC071" and not any(d in evn_days for d in ep_days):
            ep.label, ep.note = "Reading error (MSB only)", "EVN main meter normal on the same day(s); skill §5A.5"
            continue
        same_dir_recent = [o for o in all_eps_by_meter.get(ep.meter, [])
                           if o is not ep and o.direction == ep.direction and abs((o.start - ep.start).days) <= 30]
        veh = [vehicles_by_day[d] for d in ep_days if d in vehicles_by_day]
        if ep.direction == "up" and veh and veh_med and max(veh) >= 1.4 * veh_med:
            ep.label, ep.note = "Reasonable variation", f"vehicle count {int(max(veh))} >= 140% of median {int(veh_med)}"
        elif ep.days >= 3 or same_dir_recent:
            ep.label = "Evidence-based risk"
            ep.note = "lasted >= 3 days" if ep.days >= 3 else f"repeated within 30 days ({len(same_dir_recent)} other episode(s))"
        elif not veh:
            ep.label, ep.note = "Anomaly to monitor", "no vehicle count available for these days"
        else:
            ep.label, ep.note = "Anomaly to monitor", "no activity explanation found"
    return eps
