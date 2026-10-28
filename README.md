# FireRisk Intelligence

**An AI-assisted fire-risk early-warning tool for buildings.** It links records from different building
systems, investigates possible root causes with **Meta Muse Spark**, and shows each zone-level alert with
the evidence behind it, traced back to the exact source row.

Built for the Meta Global AI Developer Hackathon 2026 (Indie track) as an upgrade of the author's earlier
risk-alert skill. See [What is new](#what-is-new-in-the-hackathon) below.

> Decision-support only. Rule severities are preliminary and documented in [RISK_RULES.md](RISK_RULES.md).
> AI output is labelled as hypothesis. It does not replace certified fire systems or qualified professionals,
> and it never controls alarms or suppression equipment.

## The problem
A building's logs already contain early fire-risk signals, but they are spread across systems and look minor
on their own: a water-seepage report in the switchboard room, a heat-detector module fault, a jammed blower
motor that once burnt out, a battery replacement, grid outages. A conventional alert repeats one symptom.
FireRisk connects them by zone, asset, time and system dependency, then asks Muse Spark to reason over the
whole evidence package.

## How it works
```
Real operational sources (Google Sheets / Excel snapshot)
  └─ loaders + normaliser ─────────── every record keeps file / tab / row / record ID
       └─ PORTED skill rules ───────── scope filter, test records, meter consumption, median/MAD spikes
       └─ NEW hazard tagging ───────── Vietnamese fire-safety vocabulary, matched term stored
       └─ NEW pathway rules R1–R9 ──── deterministic signals with plain-language basis
       └─ NEW correlation ──────────── evidence links with reasons → zone alerts (compound-risk rule)
            └─ NEW Muse Spark investigation (Meta Model API, JSON schema)
                 • personal names/e-mails pseudonymised before sending
                 • every cited evidence ID validated; unknown IDs removed and reported
                 • rule severity stays authoritative; AI priority shown next to it
            └─ SQLite: analysis runs, alert history, verification status, AI results
                 └─ Dashboard (FastAPI + vanilla JS)
```
The dashboard still works when the AI service is unavailable: the rule-based alert is always produced.

## Meta AI usage
| Model | Use | Status |
|---|---|---|
| `muse-spark-1.3` (Chat Completions, `response_format: json_schema`, `strict: true`) | Root-cause investigation of a zone alert: observed facts, hypotheses with supporting and contradicting evidence, escalation pathway, missing information, recommended actions, AI priority | Connection and structured output **verified with a real call** (`evidence/api_check_20261027_133317.json`). First live investigation run 2026-10-27 14:19 on the author's PC; automatic background analysis (0.4.0) tested with a fake transport |
| `muse-spark-1.3` image input (`image_url` data URL) | Describe fire-safety-relevant observations in inspection photos | Implemented (`firerisk/media.py`), **not yet run** — no photos available yet |
| `muse-spark-1.3` video input (Responses API `input_video`, Files API) | Review survey videos for visible fire-safety conditions with approximate times | Implemented from the official docs, tested with a fake transport, **not yet run** — no video yet |
| `sam-3.1` | Segment objects in photos/video frames | Available to the key; **not implemented** until its output format is verified |

## Data
* Real data of one building ([Building]). It is **private** and **not in this repository**. The app reads a
  snapshot from `data/private/snapshot/` (git-ignored) described by `manifest.json`.
* Sources used: `Operations Data` (tabs: daily meter readings and checklists, asset repairs, incident and
  works log, generator log) and the vehicle-count workbook.
* Known limits: daily checklists keep only the latest result; no temperature/smoke/gas telemetry; photos
  referenced by the logs are not yet accessible; generator-connected loads are not recorded.

## Install and run (Windows)
1. Install **Python 3.13** (Microsoft Store, publisher *Python Software Foundation*).
2. Double-click `setup_api_key.bat` and paste your Meta Model API key (stored only in `.env`).
3. Double-click `install.bat` (creates `.venv`, installs dependencies, runs the tests).
4. Double-click `setup_drive_sync.bat` once and follow the steps (see below). Without it, put a data snapshot in
   `data/private/snapshot/` (see `manifest.json` format in `firerisk/engine.py`).
5. Double-click `run_dashboard.bat` → http://127.0.0.1:8765

Other platforms:
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # add MODEL_API_KEY
python -m pytest -q
python -m firerisk.serve
```
`scripts/check_meta_api.py` (or `run_api_check.bat`) checks the Meta API connection on its own.

## Automatic updates from Google Drive
The data stays in the author's Google Drive. A small Apps Script web app (`apps_script/FireRiskExport.gs`), deployed
in the author's **own** Google account, exports the listed spreadsheets as `.xlsx`:
* it can read only the file IDs written into it (scope `drive.readonly`), and answers only POST requests that
  carry a random token stored in the local `.env` (`FIRERISK_DRIVE_TOKEN`, `FIRERISK_DRIVE_EXPORT_URL`);
* no Google Cloud project or OAuth client is needed; the filled-in script is written to `data/private/drive_sync/`
  (git-ignored) by `setup_drive_sync.bat`;
* while the dashboard runs it updates every `FIRERISK_SYNC_MINUTES` (default 30; `0` = button only), and the
  **Update from Drive** button runs it on demand;
* a downloaded file replaces the old one only after it opens as a workbook; otherwise the previous file is kept and
  the Data sources page says which file is older and why. Replaced files are kept in `snapshot/previous/`.

## Two alert systems
| | Building equipment alerts | Fire-risk alerts |
|---|---|---|
| What | Equipment faults, overdue or repeated repairs, meter consumption findings | Combinations of records that may point to a fire or fire-safety risk |
| Origin | PORTED from the earlier skill (§2C.A, §5A.8, §7, §8) | NEW pathway rules R1–R7, R9 + compound-risk rule |
| Unit | One per equipment item / meter | One per zone |
| AI | — | Muse Spark analyses automatically in the background |
An equipment alert becomes part of a fire-risk alert only with a stated reason (same record, same equipment, a meter
that measures equipment in the alert). Levels of one system are never changed by the other.

## Automatic Muse Spark analysis
Alerts appear immediately; Muse Spark runs afterwards in a background worker. It runs when a fire-risk alert is new,
when its evidence fingerprint changes (records added/removed, status or level changed, linked equipment alerts or
survey-video observations changed), or when the user presses Re-analyse. Reloading the page never calls the AI.
Statuses (Vietnamese, as requested by the author): *Chưa phân tích AI · Đang phân tích bằng Muse Spark · Đã hoàn tất
phân tích AI · Phân tích AI thất bại · Đang sử dụng giải thích theo quy tắc*. Every cited evidence ID is checked;
unknown IDs are removed and reported. If the AI fails, the alert, its level and the rule-based explanation stay.

## Survey videos (read from Google Drive)
After the one-time Drive setup (`setup_drive_sync.bat`, which also restricts the script to read-only), the app reads
the Drive folder of the operations sheet, including sub-folders such as *Video Uploaded*, and the `Asset` tab, whose
`Reference_File` column links videos to equipment. Each video not yet on the computer is downloaded with a short-lived
read-only token (a token that could modify Drive is refused), registered with zone and equipment from the register
(no zone is guessed), and reviewed by Muse Spark automatically through the Meta video API (Files API + Responses API
`input_video`; uploaded copy expires after 1 hour and is deleted after the call). Observations are dated context for
the zone's fire-risk alerts: a video shows the situation when it was recorded, never the current state.
Settings: `FIRERISK_DRIVE_VIDEOS` (`1`), `FIRERISK_AUTO_VIDEO_AI` (`1`), `FIRERISK_VIDEO_AI_DAILY_LIMIT` (`8`).

## Dashboard
* **Overview** — **AI Risk Briefing** (highest-priority issue: location, consequence, first action, analysis status);
  building summary; **Building Risk Map** with a marker per floor (fire-safety risks and equipment alerts together,
  each keeping its own classification); context panel; system health, recent events, data sources.
* **Fire Safety Risks** — one card per risk with filters; detail in six sections (What Was Detected, Why This Matters,
  Supporting Evidence, AI Analysis, Recommended Actions, History).
* **Equipment & Systems**, **Event History**, **Data & Evidence** (sources & sync, photos & videos).
* All text is English. Vietnamese source records keep their original text; English display text comes from a glossary
  or a Muse Spark translation (marked), and untranslated text is marked "translation pending".
Every piece of content is labelled **SOURCE**, **DERIVED**, **RULE**, **AI** (Muse Spark; *AI · video* for video
observations) or **TEST**.

## Tests
`python -m pytest -q` — 108 tests: ported rules, labels and levels, new hazard rules, correlation, pipeline robustness
on **test fixture** workbooks (duplicates, invalid values, missing/corrupt sources, late arrivals), API, offline AI tests
(fake HTTP transport, clearly not the real API), Google Drive sync against a local mock of the Apps Script web app
(redirect, wrong token, web page instead of data, invalid or missing file), the two alert systems and automatic AI
analysis with a fake Muse transport (no duplicate calls, failures, fallback, level unchanged), survey videos with TEST
files and a fake Meta API, and integration tests on the real snapshot (skipped when absent).

## What is new in the Hackathon
The earlier work was a Claude skill: a Markdown instruction file with **no code**. It is kept, redacted, in
`baseline/` and described in [PRE_EXISTING_WORK.md](PRE_EXISTING_WORK.md). All code in this repository was
written during the building period (Oct 27 – Nov 4, 2026). [FEATURE_ORIGIN_MATRIX.md](FEATURE_ORIGIN_MATRIX.md)
lists each component as Existing, Modified (ported rule) or New.

## Repository
```
firerisk/            Python package (sources, rules, hazards, correlation, ai, store, api, media)
web/                 dashboard (index.html, app.js, styles.css)
tests/               pytest suite + offline mock of the Meta API
scripts/             Meta API connection check, Google Drive sync setup
apps_script/         Google Apps Script export web app (template, no IDs or token)
evidence/            sanitized evidence of real API calls (no keys)
baseline/            redacted copy of the pre-existing skill
*.bat                Windows launchers
```

## Settings (`.env`, never committed)
`MODEL_API_KEY` (Meta Model API key) · `META_API_BASE_URL`, `META_REASONING_MODEL` (optional) ·
`FIRERISK_AUTO_AI` (`1` default, `0` = only on request) · `FIRERISK_AI_MIN_LEVEL` (default `watch`) ·
`FIRERISK_AI_DAILY_LIMIT` (default `20`) · `FIRERISK_DRIVE_EXPORT_URL`, `FIRERISK_DRIVE_TOKEN`, `FIRERISK_SYNC_MINUTES` (Drive sync).
Optional for video still frames: `ffmpeg` on the PATH.

## License
To be decided by the author before publication (see HACKATHON_COMPLIANCE.md, U-04). Dependencies:
FastAPI (MIT), Uvicorn (BSD-3), openpyxl (MIT), pytest (MIT).
