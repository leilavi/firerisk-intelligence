# FireRisk rule set (v0.1, preliminary)

These rules produce the **deterministic** part of every alert. They run without any AI call. They are
decision-support rules written during the Hackathon for one real building; they are **not** certified
fire-engineering criteria and they do **not** compute probabilities or time-to-fire.

Origin: **PORTED** = from the pre-existing risk-alert skill v2.2 (natural-language spec), now in code.
**NEW** = written during the Hackathon.

## Severity scale (PORTED, skill §7)
Normal · Watch · Warning · High risk · Emergency. Severity is judged by consequence and how much time is
left to act, not by percentage change.

## Hazard pathway rules (NEW) — `firerisk/hazards/pathways.py`

| Rule | Fires when | Severity |
|---|---|---|
| R1 Water ingress into electrical rooms | A record is tagged *water ingress* AND mentions an electrical room (MBA/MSB/tủ điện) or concerns an asset classified as electrical room | High if any such record is unresolved; Warning if ≥2 records (resolved but recurring); Watch if one resolved record |
| R2 Fire detection faults | Fire-detection tag + fault word (grouped by zone, because incident reports often lack an Equipment_ID) | High if unresolved; Warning if ≥2 faults within 30 days; Watch if one fault in 30 days |
| R3 Motor failure / overheating | Burnt/overheat or jammed/mechanical-failure tag on motor equipment | High if unresolved AND the same asset has a recorded burnt motor; Warning if unresolved; Watch if history only |
| R4 Backup power readiness | Fault on generator/batteries; grid outages from the generator log (60 days) | High if unresolved fault AND outages; Warning if unresolved; Watch otherwise. Scheduled generator runs are attached as context |
| R5 Fire water supply | Fault tag on fire water tank / fire pump | High if unresolved; Watch if fault within 60 days |
| R6 Smoke exhaust | Fault tag on smoke exhaust fans | Warning if unresolved; Watch if within 60 days |
| R7 PA / evacuation announcement | Fault tag on PA system | Warning if unresolved; Watch if within 60 days |
| R8 Consumption anomaly | PORTED meter episodes (see "R8 meter signal levels") | Since 0.4.0 an **equipment alert** (EQ4), not a fire-risk signal; linked to a fire-risk alert only with a stated reason |
| R9 Reported fire/smoke | Text describes fire/smoke (cháy nổ, bốc cháy, có khói…) | Emergency only if unresolved and within 48 h; otherwise Warning/Watch |

Routine maintenance without a fault word does not fire any rule (it is context evidence).

## Zone aggregation (NEW) — `firerisk/correlation.py`
* One alert per zone with at least one Watch-level signal.
* Zone severity = highest signal severity.
* **Compound-risk rule:** if ≥2 distinct hazard pathways exist in the zone and at least one is unresolved,
  severity is raised one level — but never above High. Emergency requires R9.
* Context evidence (latest daily checklist of the relevant equipment, scheduled generator runs) is attached
  so that both the user and Muse Spark can see possibly contradicting evidence.

## Evidence links (NEW)
`same_asset`, `system_dependency` (configured asset dependencies), `measured_by_meter` (meter episode within
3 days of a record on the equipment that meter measures), `same_hazard_type` (shared hazard tag within 60
days), `same_zone_time_window` (same zone within 14 days — kept only with another reason or when both
records carry hazard tags). Links are relationships worth checking, not causation.

## Meter conclusion labels (PORTED, skill §5 table — exactly four)
Reasonable variation · Anomaly to monitor · Evidence-based risk · Insufficient data. Evaluation order:
MSB-only change with EVN normal → Insufficient data (reading error suspected, skill §5A.5) → activity explains a rise
(vehicles ≥ 140% of median) → Reasonable variation → ≥ 3 days, repeated within 30 days, or an incident/repair on
equipment the meter measures within 3 days → Evidence-based risk → no activity data → Insufficient data →
otherwise Anomaly to monitor. *(Change 2026-10-27: an earlier build used a fifth label "Reading error (MSB only)";
it was mapped back to the skill's four labels.)*

## R8 meter signal levels (PORTED, skill §5A.8)
Anomaly to monitor → Watch; Evidence-based risk → Warning; main water rise still ongoing on the latest reading, or
main electricity near zero (≤ 10% of baseline) on the latest reading → High. Reasonable variation and Insufficient data
never raise a signal. *(Change 2026-10-27: previously all meter signals were Watch.)*

## Deadlines and confidence (PORTED structure, skill §8 fields 11 and 13; values preliminary)
Emergency: immediately · High: within 24 hours · Warning: within 7 days · Watch: next routine inspection.
Confidence: High = ≥ 2 records of ≥ 2 record types; Medium = several records of one type or one record;
Low = derived meter analysis only; Insufficient data = all records carry data-quality flags.

## Assessment class (NEW)
Data anomaly (meter pattern only) · Risk indicator (recorded faults, not confirmed) · Not enough data to confirm ·
Confirmed — only when a person sets the verification status "Confirmed on site"; rules and AI never set it.

## Possible late reading (PORTED, skill §2B.7 — added 2026-10-28)
A day whose consumption is at most 10% of the next day's, with the next day at least double it (and ≥ the meter's
minimum delta), is listed as "possible late reading" for verification. Like a gap (§2B.4), the two days are spread
evenly (raw values kept). The averaged days are still checked for spikes but are not used in the baseline, so a real
jump stays visible. The 10% cut-off is a preliminary reading of the skill's "gần 0".

## Meter rules (PORTED, skill Stage 2B and §5A) — `firerisk/rules/meters.py`
Consumption day attribution, averaged gaps, excluded decreasing readings, 28-day median/MAD baseline
(3 × MAD × 1.4826, or <50% / >150% of median, with per-meter minimum deltas), episodes, EVN-vs-MSB
cross-check, conclusion labels with vehicle-count check (≥140% of median = reasonable variation).

## Building equipment alerts (PORTED, skill §2C.A, §5A.8, §7, §8, §10.4) — `firerisk/equipment.py`
One alert per equipment item or meter. Independent of fire-risk alerts; the fire module never changes these levels.
| Rule | Fires when | Level (preliminary cut-offs; the skill gives guidance, not numbers) |
|---|---|---|
| EQ1 Open fault | ≥ 1 open fault record on the equipment (or an open fault incident without Equipment_ID) | Warning on critical equipment (electrical rooms/panels, backup power, fire water, smoke control, fire detection, lightning, motors; lifts, MSB/MBA, XLNT by name); otherwise Watch |
| EQ2 Overdue | Open repair past its expected completion date (skill §10.4 "Quá hạn") | One level up, but not above Warning: an overdue date alone does not show a serious consequence (skill §7) |
| EQ3 Repeated faults | ≥ 2 dated fault records with two within 90 days, or a fault that returned after an earlier repair, and recent (90 days) or still open | Warning on critical equipment, otherwise Watch |
| EQ4 Meter finding | R8 meter signal | Skill §5A.8 level unchanged |
Equipment alert ↔ fire-risk alert link reasons: shared record, same equipment, or the meter measures equipment that
is part of the fire-risk alert. A fault with no fire-hazard meaning (e.g. an air-conditioner sensor fault) stays an
equipment alert only.

## Muse Spark (NEW) — never sets a level
The rule level is authoritative. Muse Spark gives its own priority with a rationale, shown next to the rule level.
Automatic analysis: every fire-risk alert at or above `FIRERISK_AI_MIN_LEVEL` (default Watch) whose evidence
fingerprint has no successful analysis; at most `FIRERISK_AI_DAILY_LIMIT` (default 20) automatic calls per day.

## Presentation rules (0.7, no change to alert logic)
* Map counts risks (rule signals) of active fire-risk alerts per floor; highest severity wins; equipment alerts are
  shown separately and never colour the map.
* "Why it matters" texts are fixed plain-English explanations per pathway (`alert_fields.PLAIN_WHY`, preliminary,
  cautious wording); they do not state that a fault or fire has happened.
