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
                 • agentic: Muse Spark chooses read-only lookups (tool calling) before answering;
                   falls back to one call with the rule-assembled package if tool calling fails
                 • personal names/e-mails pseudonymised before sending
                 • every cited evidence ID validated; unknown IDs removed and reported
                 • rule severity stays authoritative; AI priority shown next to it
            └─ SQLite: analysis runs, alert history, verification status, AI results
                 └─ Dashboard (FastAPI + vanilla JS)
```
The dashboard still works when the AI service is unavailable: the rule-based alert is always produced.

## Meta AI usage
Status as of 2026-10-30. "Live" means run with the real Meta Model API on the author's PC; evidence in `evidence/`
(sanitized, no keys) and in the private database on that PC.

| Model | Use | Status |
|---|---|---|
| `muse-spark-1.3` (Chat Completions, `response_format: json_schema`, `strict: true`) | Root-cause investigation of a zone alert (prompt `investigation-v7`): observed facts, hypotheses with supporting and contradicting evidence, escalation pathway, missing information, recommended actions, one briefing per risk | **Live.** First real call 2026-10-27 (`evidence/api_check_20261027_133317.json`), first live investigation 14:19 (`evidence/investigation_ZONE-B1_20261027_1419_summary.json`). Runs automatically in the background; 21 successful live investigations so far, latest 2026-10-30 19:06 (agentic mode) |
| `muse-spark-1.3` video input (Files API + Responses API `input_video`) | Survey-video fire-safety review (prompt `survey-video-v2`): findings with timestamps, areas and fire equipment seen, coverage, a `segment_phrase` per item for SAM | **Live.** All 14 survey videos from Google Drive reviewed (latest reviews 2026-10-28 16:29 – 2026-10-29 09:57), 34 findings; each uploaded copy deleted after the call |
| `muse-spark-1.3` tool calling (Chat Completions `tools`, `tool_choice: auto`) | Agentic investigation (`firerisk/ai/agentic.py`): Muse Spark decides which records to look up - asset history, record search, meter readings, equipment alerts, survey-video findings, asset list - then answers in the same strict schema; every lookup is shown on the dashboard | **Tool protocol verified live** 2026-10-30 18:57 on the author's PC with synthetic records (`evidence/tool_calling_check_20261030_185751.json`: Muse Spark called 2 tools in one round, used the results, answered in the strict schema; tools + `response_format` accepted together). **Live on the building data** 2026-10-30 19:06: both zone alerts analysed automatically in agentic mode (ZONE-B1: 3 lookups, 46.6 s, 52.7k tokens; ZONE-Building: 3 lookups, 23.2 s, 15.4k tokens), 0 invalid citations, no fallback; Muse Spark checked repeat faults and related records and reported that none existed beyond the rule package (`evidence/agentic_investigation_live_20261030.json`). Falls back to the single call automatically |
| `muse-spark-1.3` text | English translation of Vietnamese source records (marked as translation) | Live |
| `sam-3.1` (Responses API, `meta-sam-parser`) | Outlines the object a Muse Spark finding refers to in still frames of the video (box + mask, confidence only when SAM returns one); also finds signs/labels to blur for demo copies | **Live.** 511 frame results stored (299 located, 212 not located, 0 errors), runs in the background after every new video review; live checks in `evidence/sam_check_*.json`, `evidence/sam_client_check_*.json`, `evidence/sam_localization_run_20261028.json` |
| `muse-spark-1.3` image input (`image_url`) | Describe fire-safety observations in single inspection photos | Implemented (`firerisk/media.py`), **not run live**: no inspection photos are available yet. Visual evidence currently comes from the survey videos |

Model output never sets or changes a rule level. SAM shows where an object appears; it does not confirm a safety
conclusion. A video finding stays a finding (no risk level) until a person verifies it.

## Data
* Real data of one building ([Building]), used with the **written permission of the data owner** (approval of
  2026-10-30; conditions and how each is enforced: [`DATA_AUTHORIZATION.md`](DATA_AUTHORIZATION.md)). It is **private** and **not in this repository**. The app reads a
  snapshot from `data/private/snapshot/` (git-ignored) described by `manifest.json`.
* Sources used: `Operations Data` (tabs: daily meter readings and checklists, asset repairs, incident and
  works log, generator log) and the vehicle-count workbook.
* Survey videos: 14 videos of the building recorded 2026-10-27 to 2026-10-28, read from the author's Google Drive.
* Known limits: one building only; daily checklists keep only the latest result; **no temperature, smoke or gas
  sensor telemetry** (no such feed is connected, so the risk assessment uses records, rules and video, and the
  dashboard says that "no active alert" does not mean safe); photos referenced by the logs are not yet accessible;
  generator-connected loads are not recorded; technical drawings and manuals are **never** opened by the app or sent
  to an AI service (owner's condition, enforced in `firerisk/data_policy.py`), so the building map uses floor names only; 9 of the 14 videos are linked to a room in the asset register that has
  no floor recorded, so they are not placed on a floor (the floor is never guessed).

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

**Agentic investigation (tool calling).** Muse Spark receives the rule-assembled evidence package plus six read-only
tools over the whole record store and decides what else to check (e.g. the history of the same asset, earlier
incidents in the room, meter readings around the fault date). Each call is validated and executed locally; records
get opaque aliases and names are redacted before anything is sent. Limits: 6 tool rounds, 16 lookups, 25 records per
lookup. The final answer uses the same strict JSON schema and citation check; records found by lookups may be cited.
The dashboard lists every lookup in order ("How Meta Muse Spark investigated"). If the API rejects the tool
conversation or the answer is malformed or cut off, the proven single-call investigation runs instead and the record
says why; if the API is unreachable the attempt is recorded as failed. `FIRERISK_AI_TOOLS=0` switches tool calling off.
Statuses shown: *Not Analysed by Meta Muse Spark · Meta Muse Spark Analysis Running · Meta Muse Spark Analysis
Complete · Meta Muse Spark Analysis Failed · Rule-Based Explanation*. Every cited evidence ID is checked;
unknown IDs are removed and reported. If the AI fails, the alert, its level and the rule-based explanation stay.

## Survey videos (read from Google Drive)
After the one-time Drive setup (`setup_drive_sync.bat`, which also restricts the script to read-only), the app reads
the Drive folder of the operations sheet, including sub-folders such as *Video Uploaded*, and the `Asset` tab, whose
`Reference_File` column links videos to equipment. Each video not yet on the computer is downloaded with a short-lived
read-only token (a token that could modify Drive is refused), registered with zone and equipment from the register
(no zone is guessed), and reviewed by Muse Spark automatically through the Meta video API (Files API + Responses API
`input_video`; uploaded copy expires after 1 hour and is deleted after the call). Observations are dated context for
the zone's fire-risk alerts: a video shows the situation when it was recorded, never the current state.
Settings: `FIRERISK_DRIVE_VIDEOS` (`1`), `FIRERISK_AUTO_VIDEO_AI` (`1`), `FIRERISK_VIDEO_AI_DAILY_LIMIT` (`20`).

**Video findings.** The review returns findings (what is visible, why it matters, consequence if confirmed, check to
do, certainty) with a time range that is validated against the video length. Findings have no risk level; a finding
is linked to an existing alert only for a stated reason (same equipment in the asset register, or same floor and a
matching fire-safety group). A person records the on-site result (Needs verification / Confirmed / Resolved / Not
confirmed).

## Visual localization with SAM 3.1
`Muse Spark finding → segment_phrase → 1–3 still frames inside the finding's time range → SAM 3.1 → stored box/mask →
dashboard overlay`. Results are stored per frame (no duplicate requests, resumable), limited to 300 images per day,
and run in the background after each new video review; `run_locate_findings.bat` (with a dry-run cost estimate)
processes older items. "Not located" is a valid answer, not an error. Details: [ARCHITECTURE.md](ARCHITECTURE.md).

## Demo mode (names hidden)
`run_dashboard_demo.bat` starts the same dashboard with building names replaced by "[name hidden]", shows only
blurred copies of video frames (signs and labels found by SAM 3.1, faces found locally with OpenCV - SAM is never
asked to find people - plus regions added by hand after a frame-by-frame review) and never plays the original videos. Original frames are not modified.

## Dashboard
* **Overview** — **Meta Muse Spark – Risk Briefing** (highest-priority issue: location, consequence, first action,
  analysis status; titled "rule-based" until a Muse Spark result exists); building summary; **Building Risk Map** with
  a marker per floor (fire-safety risks and equipment alerts together, each keeping its own classification); context
  panel; **Survey Video Findings** with a survey-coverage drawing of the floors (which floors a reviewed video covers,
  findings to verify per floor, top findings with their real SAM frame); system health, recent events, data sources.
* **Fire Safety Risks** — one card per risk with filters; detail in six sections (What Was Detected, Why This Matters,
  Supporting Evidence, Meta Muse Spark analysis, Recommended Actions, History), with a matching video frame only when
  the video is of the same room or equipment.
* **Equipment & Systems**, **Event History**, **Data & Evidence** (sources & sync, photos & videos with SAM overlays).
* All text is English. Vietnamese source records keep their original text; English display text comes from a glossary
  or a Muse Spark translation (marked), and untranslated text is marked "translation pending".
Every piece of content is labelled **SOURCE**, **DERIVED**, **RULE**, **META MUSE SPARK**, **META SAM 3.1** or **TEST**.
The UI names each model part after the Meta model that made it; model IDs are `muse-spark-1.3` and `sam-3.1`.

## Tests
`python -m pytest -q` — **203 tests (201 pass, 2 skipped** when the private real-data snapshot is absent; last run
2026-10-30). They cover: ported rules, labels and levels, new hazard rules, correlation, pipeline robustness on **test
fixture** workbooks (duplicates, invalid values, missing/corrupt sources, late arrivals); the API; offline AI tests
with a fake HTTP transport (clearly not the real API); Google Drive sync against a local mock of the Apps Script web
app; the two alert systems and automatic analysis (no duplicate calls, failures, fallback, level unchanged); survey
videos and video findings with TEST files and a fake Meta API; the agentic investigation (tool protocol, read-only tools, privacy of what is sent, caps, fallback); the data owner's
conditions (documents and drawings refused before every AI upload, faces blurred locally); the SAM 3.1
client and parser, localization and its
background run (fake SAM); demo-mode masking; and browser checks of the rendered pages with Playwright (English-only
text, briefing, map, drawers). Live runs against the real Meta API are recorded in `evidence/` and
`DEVELOPMENT_LOG.md`, not in the test suite.

## What is new in the Hackathon
The earlier work was a Claude skill: a Markdown instruction file with **no code**. It is kept, redacted, in
`baseline/` and described in [PRE_EXISTING_WORK.md](PRE_EXISTING_WORK.md). All code in this repository was
written during the building period (Oct 27 – Nov 4, 2026). [FEATURE_ORIGIN_MATRIX.md](FEATURE_ORIGIN_MATRIX.md)
lists each component as Existing, Modified (ported rule) or New.

## AI-Assisted Development
This project was designed, directed, and validated by the author, with Claude serving as an AI development
assistant. The author defined the architecture, established technical requirements, made implementation decisions,
reviewed the generated code, and validated the system's functionality. All final design and development decisions
remain under the author's responsibility.

## Development history (how to verify what is new)
* **Building period:** Oct 27 – Nov 4, 2026. Every commit on `main` is dated inside it (first commit 2026-10-27 11:54
  UTC+7). `git log --reverse --date=iso` shows the full sequence; commit messages say what was built.
* **Baseline:** commit `b79223f` (branch [`baseline`](https://github.com/leilavi/firerisk-intelligence/tree/baseline)) contains only the redacted pre-existing
  skill (`baseline/`, a Markdown instruction file, no code), `PRE_EXISTING_WORK.md` and `.gitignore`.
  `git diff baseline main --stat` lists everything added during the Hackathon.
* **Per-step record:** [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md) (what was asked, built, checked live, and what failed,
  with times), [CHANGELOG.md](CHANGELOG.md), [FEATURE_ORIGIN_MATRIX.md](FEATURE_ORIGIN_MATRIX.md) (Existing / Modified /
  New per component), `evidence/` (sanitized results of real Meta API calls). Source files carry `ORIGIN: NEW` or
  `ORIGIN: PORTED` markers.
* **Disclosed history rewrites:** (1) 2026-10-27 14:34–14:40, before the first publication: personal data and the
  building's name replaced in file contents with `git filter-repo`; author/committer dates and messages kept, hashes
  changed. (2) 2026-10-29: commit `e379dc4`, which had the building's name in two code comments, was replaced on `main` minutes
  after it was pushed. Both are described in DEVELOPMENT_LOG.md.

## Repository
```
firerisk/            Python package (sources, rules, hazards, correlation, ai (investigation, agentic, auto), store, api, video, video_findings,
                     sam, localize, demo, media)
web/                 dashboard (index.html, app.js, styles.css)
tests/               pytest suite + offline mock of the Meta API
scripts/             Meta API, tool-calling and SAM checks, Google Drive sync setup, SAM backfill, demo-copy blurring
apps_script/         Google Apps Script export web app (template, no IDs or token)
evidence/            sanitized evidence of real API calls (no keys)
baseline/            redacted copy of the pre-existing skill
*.bat                Windows launchers
```

## Settings (`.env`, never committed)
`MODEL_API_KEY` (Meta Model API key) · `META_API_BASE_URL`, `META_REASONING_MODEL` (optional) ·
`FIRERISK_AUTO_AI` (`1` default, `0` = only on request) · `FIRERISK_AI_MIN_LEVEL` (default `watch`) ·
`FIRERISK_AI_DAILY_LIMIT` (default `20`) · `FIRERISK_AI_TOOLS` (`1` default, `0` = single call, no tool calling) · `FIRERISK_DRIVE_EXPORT_URL`, `FIRERISK_DRIVE_TOKEN`, `FIRERISK_SYNC_MINUTES` (Drive sync).
Still frames use the ffmpeg binary installed with `imageio-ffmpeg`. `FIRERISK_DEMO_MODE=1` = demo mode (set by `run_dashboard_demo.bat`).

## License
To be decided by the author before publication (see HACKATHON_COMPLIANCE.md, U-04). Dependencies:
FastAPI (MIT), Uvicorn (BSD-3), openpyxl (MIT), imageio-ffmpeg (BSD-2; bundles ffmpeg, LGPL/GPL), meta-sam-parser
(SAM License), pytest (MIT), Playwright (Apache-2.0, tests only).
