# FireRisk Intelligence

**An AI-assisted fire-risk early-warning tool for buildings.** It links records from different building
systems, investigates possible root causes with **Meta Muse Spark**, and shows each zone-level alert with
the evidence behind it, traced back to the exact source row.

Built for the Meta Global AI Developer Hackathon 2026 (Indie track) as an upgrade of the author's earlier
risk-alert skill. See [What is new](#what-is-new-in-the-hackathon) below.

> Decision-support only. Rule severities are preliminary and documented in [RISK_RULES.md](RISK_RULES.md).
> AI output is labelled as hypothesis. It does not replace certified fire systems or qualified professionals,
> and it never controls alarms or suppression equipment.

## Demo video
2:59, English narration and subtitles: link on the submission page (YouTube, unlisted). Recorded automatically from
the real dashboard in demo mode (names hidden, blurred survey frames); every click is a real click in the app.
Storyboard, production report and QA checks (each claim matched to what the screen shows):
[docs/demo-video/](docs/demo-video/); recording and editing scripts: [scripts/demo_video/](scripts/demo_video/).

## Try it: sample mode (fictional building, no private data needed)
The real building's records are private and are not in this repository (see [Data](#data)), so a fresh clone has
nothing to analyse. **Sample mode** starts the same dashboard on a made-up building, *Acme Riverside Plaza*:

* **Windows:** install Python 3.13, then double-click `run_dashboard_sample.bat` (runs `install.bat` the first time).
* **macOS / Linux:** `./run_dashboard_sample.sh` (creates `.venv`, installs `requirements.txt`).
* Any platform with dependencies installed: `python -m firerisk.sample` → http://127.0.0.1:8765

What you see and where it comes from:
* **Every record is invented** (`firerisk/sample.py`): ~60 days of meter readings, daily checklists, repair and
  incident logs, generator runs, an asset register and a confirmed emergency-lighting supply table, written to
  `data/sample/` (git-ignored, re-created on each start with dates relative to today). No row, number or name comes
  from the real building. Every screen shows a "SAMPLE DATA · fictional building" banner.
* **The analysis is real:** the same rule engine computes the alerts, levels, timelines, chains of effects and
  recommended actions from those records; nothing on screen is typed in as a result. The scenario combines an
  abnormal electrical load (main and switchboard meters +60% for 4 days), a hot switchboard busbar repaired twice
  before, water seeping into the switchboard room, a failed generator starter battery after a grid outage, a
  fire-alarm loop fault, a smoke-fan fault and a jammed blower motor with a burn-out history.
* **Meta Muse Spark:** called only with **your own** Meta Model API key (`setup_api_key.bat`, or `MODEL_API_KEY` in
  `.env`); it then analyses the fictional records live. Without a key the dashboard says that no Meta AI analysis
  exists - it never shows an invented AI result. Live runs on the real building are shown in the demo video and in
  [`evidence/`](evidence/). English text of the Vietnamese-style sample records is written by the sample's author
  (not AI).
* Sample mode never reads `data/private/`: every data path is redirected to `data/sample/`, Google Drive sync and
  demo mode are off (`tests/test_sample.py` checks this in a fresh process). Survey videos and SAM 3.1 frames are
  not part of the sample (the real ones are private); those pages show "no survey video".

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
       └─ NEW chain of effects ─────── how a problem on one part reaches other equipment and people (each link
                                        with its basis; unknown links listed, never assumed)
            └─ NEW Muse Spark investigation (Meta Model API, JSON schema)
                 • agentic: Muse Spark chooses read-only lookups (tool calling) before answering;
                   falls back to one call with the rule-assembled package if tool calling fails
                 • personal names/e-mails pseudonymised before sending
                 • every cited evidence ID validated; unknown IDs removed and reported
                 • rule severity stays authoritative; AI priority shown next to it
                 • tells the chain of effects as a plain-language story ("butterfly effect"), each step cited
            └─ SQLite: analysis runs, alert history, verification status, AI results
                 └─ Dashboard (FastAPI + vanilla JS)
```
The dashboard still works when the AI service is unavailable: the rule-based alert is always produced.

## Meta AI usage
Status as of 2026-10-30. "Live" means run with the real Meta Model API on the author's PC; evidence in `evidence/`
(sanitized, no keys) and in the private database on that PC.

| Model | Use | Status |
|---|---|---|
| `muse-spark-1.3` (Chat Completions, `response_format: json_schema`, `strict: true`) | Root-cause investigation of a zone alert (prompt `investigation-v8`): the chain of effects across equipment told as a plain-language story, observed facts, hypotheses with supporting and contradicting evidence, escalation pathway, missing information, recommended actions, one briefing per risk | **Live.** First real call 2026-10-27 (`evidence/api_check_20261027_133317.json`), first live investigation 14:19 (`evidence/investigation_ZONE-B1_20261027_1419_summary.json`). Runs automatically in the background; 21 successful live investigations so far, latest 2026-10-30 19:06 (agentic mode) |
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
  snapshot from `data/private/snapshot/` (git-ignored) described by `manifest.json`. To run the app without it,
  use [sample mode](#try-it-sample-mode-fictional-building-no-private-data-needed) (fictional building).
* Sources used: `Operations Data` (tabs: daily meter readings and checklists, asset repairs, incident and
  works log, generator log) and the vehicle-count workbook.
* Survey videos: 14 videos of the building recorded 2026-10-27 to 2026-10-28, read from the author's Google Drive.
* Known limits: one building only; daily checklists keep only the latest result; **no temperature, smoke or gas
  sensor telemetry** (no such feed is connected, so the risk assessment uses records, rules and video, and the
  dashboard says that "no active alert" does not mean safe); photos referenced by the logs are not yet accessible;
  generator-connected loads are not recorded; the original drawings are never sent to an AI service (owner's
  condition, enforced in `firerisk/data_policy.py`): they are read on the author's computer (local OCR), and only
  links a person has checked against the drawing (panel -> emergency lights / exit signs / fire equipment per floor,
  `power_links.xlsx`) are used - see "Electrical supply of life-safety equipment" below; 9 of the 14 videos are linked to a room in the asset register that has
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

**Agentic investigation (tool calling).** Muse Spark receives the rule-assembled evidence package plus seven read-only
tools over the whole record store and decides what else to check (e.g. the history of the same asset, earlier
incidents in the room, meter readings around the fault date, which emergency lights and exit signs a faulty panel
supplies). Each call is validated and executed locally; records
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

## Electrical supply of life-safety equipment (from the building drawings)
The scanned electrical and emergency-lighting drawings are read **on the author's computer** (`run_drawing_ocr.bat`,
local OCR, no AI service). `run_draft_power_links.bat` finds the drawn symbols that carry no text (e.g. emergency lights) by cutting each
symbol from the drawing's own legend and searching the pages for it (OpenCV template matching, local, with a review
page), and turns text and symbols into a draft table "which panel supplies which
emergency lights, exit signs, fire pump, smoke control or fire alarm, on which floor"; the author checks every row
against the drawing and confirms it. Only confirmed rows are used (rule EQ-D1 in RISK_RULES.md): a panel that supplies
life-safety equipment is treated as critical, its alert says which floors lose emergency lighting if it fails and adds
a battery test, it is linked to the fire-risk alert of those floors, and Meta Muse Spark can look it up with the tool
`get_fire_safety_supply`; each fire-risk alert shows a section "Emergency lights and exit signs on this floor". What reaches Muse Spark is floor, equipment type and count only - never panel labels,
circuits or drawing content.

Supply path (technician, 2026-11-01): each floor has its own main panel; the floor control breaker (CP) inside it feeds
the floor's emergency lights and exit signs over a 2Cx2.5mm² cable, with no dedicated emergency circuit; the standby
generator re-supplies every floor main panel through the ATS. The app records this path (floor main panels and ATS are
not in the asset register, so no asset code is invented), marks the generator as the **standby** supply of all
emergency lights and exit signs (never as their normal supply), and tells Muse Spark the remaining exposure: if a floor
breaker trips or the floor panel is switched off, that floor's lights run on their batteries.

Operations team, 2026-11-02: there is **one ATS for the whole building** (all six floors) and the standby generator
supplies the whole building; the fittings have **built-in batteries** (about 2 hours when new, older ones vary), tested
every month by switching normal power off for 15 minutes (a fitting that goes dark is repaired, gets a new battery or
is replaced). The app states these facts with their basis (`LIGHT_BATTERY`, `STANDBY_SCOPE` in `power_links.py`) and
keeps the limit visible: the 15-minute test proves at least 15 minutes, not how long each older fitting really lasts,
and the app does not read the test results yet.

## Chain of effects across equipment ("butterfly effect")
A reader who does not know building equipment needs to see why a problem on one part matters for another part and,
in the end, for people. `firerisk/impact_chain.py` builds this for each fire-risk alert **without AI**: a small graph
of the building's systems where every link states why two parts are related and on what basis (asset relations in
the rule set, the confirmed drawing table, the technician's statement, or a general hazard mechanism). From each part
with a recorded problem it follows the links to the consequence for people and shows, on the way, the other parts it
depends on and their own recorded problems (e.g. the generator's starter batteries). Since 2026-11-02 the single ATS
is shown as a shared link: on generator power it is the path to every floor's emergency lights, the smoke exhaust fans
and the fire pump (operations team statement; the fire pump and smoke fan circuits are not checked on the drawings and
are listed as such). What is not recorded - the real battery autonomy of older light fittings - is listed as not
established, never assumed.

Meta Muse Spark receives the chain with the cited records and writes the **story behind the alert** (`impact_story`):
a headline, 4-8 plain sentences and the steps, each marked "record" (with citations, validated), "known link",
"hypothesis" or "not established". The dashboard shows the story and, below it, the rule-built chain as a step diagram
(section 2 of the alert page and the alert drawer). The **whole-building** alert's chains start from the records of
every fire-risk alert, because a problem in one floor's technical room reaches every floor; its story is shown on the
Overview, in the whole-building panel (live 2026-11-01 20:05, `evidence/impact_story_building_live_20261101.json`:
water in the basement electrical rooms -> weak generator batteries -> 135 emergency lights and exit signs on all six
floors -> plus the announcement-system and heat-detection faults). Status: **live 2026-11-01 19:49** on the author's PC: ZONE-B1 story written by Meta Muse Spark in agentic mode (50 s, 7 steps, 0 invalid citations) - water seepage in the MBA/MSB rooms -> grid loss -> ATS -> generator with weak starter batteries (29 Sep) -> 135 emergency lights and exit signs on their own batteries; public summary `evidence/impact_story_live_20261101.json`.

## Demo mode (names hidden)
The building's name is never shown on screen (header and whole-building panel use generic titles, 2026-11-01). In demo mode the staff user names inside asset-log record IDs (`asset:Repair-<user>-064`) are hidden too.
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
`python -m pytest -q` — **248 tests (246 pass, 2 skipped** when the private real-data snapshot is absent; last run
2026-11-02). They cover: ported rules, labels and levels, new hazard rules, correlation, pipeline robustness on **test
fixture** workbooks (duplicates, invalid values, missing/corrupt sources, late arrivals); the API; offline AI tests
with a fake HTTP transport (clearly not the real API); Google Drive sync against a local mock of the Apps Script web
app; the two alert systems and automatic analysis (no duplicate calls, failures, fallback, level unchanged); survey
videos and video findings with TEST files and a fake Meta API; the agentic investigation (tool protocol, read-only tools, privacy of what is sent, caps, fallback); the data owner's
conditions (documents and drawings refused before every AI upload, faces blurred locally); sample mode (only sample
paths read, the designed scenario found by the rules, every sample text translated); the local drawing probe
and local OCR of scanned drawings (numbers only, no network); the SAM 3.1
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
  after it was pushed. (3) 2026-10-30 21:05: the two latest commits (`33d9fd4`, `c9e0c74`, now `97de6fd`, `6574cf0`)
  had a personal e-mail as author; author re-set to the usual noreply identity, content and dates unchanged. All are
  (4) 2026-11-02 19:30: two code comments in `firerisk/demo.py` (commits from 2026-10-29 on) used an abbreviation
  of the real building as an example; replaced with a made-up name in every commit from `bdd500f` (was `a717f0e`)
  onward with `git filter-repo`; author/committer dates and messages kept, hashes of those commits changed (cited
  hashes updated in the docs). All are described in DEVELOPMENT_LOG.md.

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
*.bat                Windows launchers (run_dashboard_sample.bat / .sh: fictional sample building)
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
