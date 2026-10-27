# Changelog

## 0.2.0 — 2026-10-27
- Pipeline: status classes, duplicate IDs, invalid values, generator duration recompute, overdue / stale / future flags,
  missing or corrupt sources reported without stopping, late-arrival detection.
- Skill alignment: exactly 4 conclusion labels (fifth label removed), meter levels per skill §5A.8, 14 alert fields.
- Assessment classes; human-only "Confirmed on site" state; first-detection time.
- API: concise alert list, 6-part detail payload, trends, equipment, asset history.
- Dashboard v2 (light theme, zone panel, evidence-first alert detail, origin labels).
- 54 tests.

## 0.1.0 — 2026-10-27
- Real-data loaders for the [Building] sources with row-level traceability.
- PORTED skill rules in code: scope filter, test records, daily consumption, median/MAD spike detection, episodes, labels.
- NEW: fire-safety hazard tagging, pathway rules R1–R9, context evidence, cross-source links, zone alerts with compound-risk rule.
- NEW: Muse Spark investigation (structured JSON, evidence-ID validation, pseudonymisation), Meta API client with error handling.
- NEW: SQLite store (runs, alert history, verification status, AI results), FastAPI backend, dashboard.
- NEW: media inventory, frame extraction and image-description client (prepared, not yet run on real media).
- Windows launchers: setup_api_key.bat, install.bat, run_api_check.bat, run_dashboard.bat.
