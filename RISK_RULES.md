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
| R8 Consumption anomaly (supporting) | PORTED meter episodes labelled "Evidence-based risk" or "Anomaly to monitor" in the last 30 days | Watch (supporting signal only) |
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

## Meter rules (PORTED, skill Stage 2B and §5A) — `firerisk/rules/meters.py`
Consumption day attribution, averaged gaps, excluded decreasing readings, 28-day median/MAD baseline
(3 × MAD × 1.4826, or <50% / >150% of median, with per-meter minimum deltas), episodes, EVN-vs-MSB
cross-check, conclusion labels with vehicle-count check (≥140% of median = reasonable variation).
