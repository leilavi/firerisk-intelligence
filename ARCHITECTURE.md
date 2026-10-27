# Architecture and data flow

```
 Google Drive / Sheets (real operational sources, updated daily by staff via AppSheet)
        │  snapshot (today: via Claude's Drive connector → data/private/snapshot/ + manifest.json)
        ▼
 sources/workbook.py      read tabs, keep Excel row numbers, detect round-number truncation
 sources/normalize.py     → Evidence records: timestamp (UTC+7), asset ID, zone, status + status class,
                            unit, media refs, persons, flags; duplicates kept and flagged; invalid values flagged;
                            missing/corrupt tab or file → reported, other sources still processed
 engine.apply_record_checks  future timestamps, overdue repairs, stale "in progress" works
 hazards/tagging.py       fire-safety tags from Vietnamese text (matched term stored)
 rules/meters.py (PORTED) daily consumption, gaps, median/MAD spikes, episodes, 4 conclusion labels
 hazards/pathways.py      R1–R9 hazard pathway rules + R8 meter signals (skill §5A.8 severities)
 correlation.py           evidence links with reasons; one alert per zone; compound-risk rule
 alert_fields.py          the 14 skill alert fields, short headline, assessment class, unknowns
        │
        ├── store.py (SQLite, data/private/firerisk.db): runs, alert history, first detection,
        │   verification status (incl. human-only "confirmed"), evidence-seen log (late arrivals), AI results
        │
        ├── ai/ (Muse Spark, optional): redact names → opaque evidence IDs → JSON-schema request →
        │   validate citations → map IDs back → stored separately from rule results
        │
        └── api.py (FastAPI) ──► web/ dashboard (vanilla JS, no build step)
```

## What is real, derived, rule, AI, test
| Label in the dashboard | Meaning |
|---|---|
| Source record | A row of a real source file (file / tab / row / record ID shown) |
| Derived from data | Computed by a documented rule from real values (e.g. a meter episode from daily readings) |
| Rule result | Output of the deterministic rule engine (level, basis, actions, deadline) |
| AI (Muse Spark) | Text produced by Muse Spark from the evidence package; hypothesis only |
| Test | Produced by a mock/test endpoint or test fixture; never real |

## Source status (2026-10-27)
| Source | Connected | Processed |
|---|---|---|
| Operations Data: meter readings + daily checklists, repairs, incidents/works, generator log | Snapshot (manual, via Claude) | Yes |
| Vehicle counts workbook | Snapshot | Yes (activity baseline) |
| Electricity / water bills, parking revenue | Available in Drive, not loaded | No (not fire-relevant for this phase) |
| Old skill Alert_Log | Available in Drive | No (the app keeps its own log) |
| Photos referenced by logs, survey video | Not accessible | No — media inventory only |
| Live sync without Claude | Not built | — |

## Failure behaviour
* A missing/corrupt workbook or tab → `source_unavailable` in Data sources and in the alert's "not verified" list;
  other sources still analysed.
* Muse Spark unavailable / no key / bad output → recorded as a failed AI attempt; rule alerts unchanged.
* Newest record older than the source's expected cadence → `stale_source`.
