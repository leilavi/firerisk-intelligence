# Architecture and data flow

```
 Google Drive / Sheets (real operational sources, updated daily by staff via AppSheet)
        │  Apps Script web app in the author's own Google account (apps_script/FireRiskExport.gs):
        │  reads only the listed file IDs, answers only POSTs with the shared token, returns .xlsx
        │  sources/drive_sync.py: every 30 min + "Update from Drive" button; a file replaces the old one only
        │  after it opens as a workbook; old version kept in snapshot/previous/ → data/private/snapshot/ + manifest.json
        ▼
 sources/workbook.py      read tabs, keep Excel row numbers, detect round-number truncation
 sources/normalize.py     → Evidence records: timestamp (UTC+7), asset ID, zone, status + status class,
                            unit, media refs, persons, flags; duplicates kept and flagged; invalid values flagged;
                            missing/corrupt tab or file → reported, other sources still processed
 engine.apply_record_checks  future timestamps, overdue repairs, stale "in progress" works
 hazards/tagging.py       fire-safety tags from Vietnamese text (matched term stored)
 rules/meters.py (PORTED) daily consumption, gaps, median/MAD spikes, episodes, 4 conclusion labels
 hazards/pathways.py      R1–R7, R9 fire-hazard pathway rules + R8 meter signals (skill §5A.8 severities)
        │
        ├── TWO INDEPENDENT ALERT SYSTEMS (linked, never merged)
        │   equipment.py (PORTED)  building equipment alerts, one per equipment item / meter:
        │                          EQ1 open fault, EQ2 overdue, EQ3 repeated faults (skill §2C.A, §10.4),
        │                          EQ4 meter findings = R8 (skill §5A.8). Levels never changed by the fire module.
        │   correlation.py (NEW)   fire-risk alerts, one per zone, built ONLY from fire-hazard pathway signals;
        │                          compound-risk rule. Meter findings are NOT fire-risk signals.
        │   equipment.link_to_fire_alerts  equipment alert ↔ fire-risk alert only with a stated reason
        │                          (same record, same equipment, meter that measures equipment in the alert)
 alert_fields.py          the 14 skill alert fields, short headline, assessment class, unknowns
        │
        ├── store.py (SQLite, data/private/firerisk.db): runs, alert history, first detection,
        │   verification status (incl. human-only "confirmed"), evidence-seen log (late arrivals), AI results
        │
        ├── ai/ (Muse Spark, optional): redact names → opaque evidence IDs → JSON-schema request →
        │   validate citations → map IDs back → stored separately from rule results
        │   ai/auto.py: after each analysis run, fire-risk alerts whose EVIDENCE FINGERPRINT has no successful
        │   analysis are queued; one background worker; alert shown first, AI fills in later; page reloads never
        │   queue anything; failed attempt retried once after 15 min; daily limit; rule level never changed
        │
        ├── video.py (NEW, prepared): survey-video upload (stored locally) + zone/floor/area/room/recording time;
        │   Muse Spark video review via Files API + Responses API (`input_video`); validated observations
        │   become dated CONTEXT of the zone's fire-risk alerts (never a finding, never a level change)
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
| Operations Data: meter readings + daily checklists, repairs, incidents/works, generator log | Automatic Drive sync (after one-time setup); before setup: snapshot taken via Claude 13:49 | Yes |
| Vehicle counts workbook | Automatic Drive sync (after setup) | Yes (activity baseline) |
| Electricity / water bills, parking revenue | Available in Drive, not loaded | No (not fire-relevant for this phase) |
| Old skill Alert_Log | Available in Drive | No (the app keeps its own log) |
| Photos referenced by logs, survey video | Not accessible | No — media inventory only |
| Live sync without Claude | Built (`sources/drive_sync.py`); tested against a local mock of the web app; **first real run pending on the author's PC** | — |

## Failure behaviour
* A missing/corrupt workbook or tab → `source_unavailable` in Data sources and in the alert's "not verified" list;
  other sources still analysed.
* Muse Spark unavailable / no key / bad output → recorded as a failed AI attempt; rule alerts unchanged.
* Drive sync fails (no internet, wrong token, web page instead of data) → nothing changes, failure listed in Data
  sources. One file invalid or missing → that file keeps its previous version and `sync_error` is shown; the other
  file is still updated.
* Automatic AI analysis fails or times out → status "Phân tích AI thất bại", the rule-based explanation is shown
  ("Đang sử dụng giải thích theo quy tắc"); one automatic retry after 15 minutes, then only on request.
* No survey video → every function works; the alert shows "No survey video for this zone yet".
* Newest record older than the source's expected cadence → `stale_source`.

## Asset register and survey-video references (2026-10-28)
`sources/register.py` reads the optional `Asset` tab: equipment names, floor → zone, status, next due date (context and
display only), and Drive links in `Reference_File` as survey-video references. File title and size come from Drive
metadata recorded in the private manifest (`video_catalog`). Videos are brought to the computer by putting the
downloaded files in `data/private/media/survey_inbox/` and pressing Import; they are matched by name or size.

## Reading everything from Google Drive (0.6)
Apps Script web app (author's account, read-only scope): action `export` → spreadsheets as .xlsx + listing of every
file in the sheet's folder (3 levels of sub-folders); action `token` → short-lived read-only access token.
`drive_videos.DriveVideoSync`: token → scope check via Google tokeninfo (refuse write scopes) → Drive API
`files.get?alt=media` per missing video (header auth, size check) → `VideoStore.add_file` with register metadata →
automatic Muse Spark review (`FIRERISK_AUTO_VIDEO_AI`, daily limit) → observations attached to fire-risk alerts →
fire-risk alerts re-analysed (fingerprint changed). Runs after every Drive update and on the "Get new videos" button.

## Evidence fingerprint (when Muse Spark runs again)
`ai/investigation.fingerprint` hashes: prompt version, rule level, each finding record (ID, status, open/closed,
time, meter label, ongoing), what the context records SAY (kind, equipment, status, pass/fault — not their IDs, so
tomorrow's passing checklist is not a change), linked equipment alerts and their levels, and the survey-video
analyses attached to the zone. Same fingerprint → no new automatic call.

## Survey video integration (prepared 2026-10-27; no real video yet)
| Step | How | Verified |
|---|---|---|
| Upload | Browser sends the file as the request body (`POST /api/videos?filename&zone&floor&area&room&recorded_at&duration_s`); stored in `data/private/media/videos/` (git-ignored); 1 GiB limit (Meta Files API) | TEST files |
| Metadata | Zone must be a known zone; recording time is entered by a person or "unknown" (file dates are not trusted); duration read by the browser | TEST |
| Analysis (on request only) | `POST /v1/files` (purpose `user_data`, expires after 3600 s) → `POST /v1/responses` with `input_video` + `text.format` json_schema, `store: false` → `DELETE /v1/files/{id}` | Request shape against the official docs and a fake transport; **never run against the real API** |
| Validation | Observations need a time range inside the video and a known category; others are set aside with the reason | TEST |
| Review | Player jumps to each observation (HTTP Range); still frame via ffmpeg when installed | TEST pattern |
| Use in alerts | Zone match → "Survey videos of this zone" in the fire-risk alert (section 9) and `survey_video_observations` in the Muse package, with recording date and "recording-time only" | TEST |
Open questions for the first real run: maximum duration, frame-sampling behaviour (`fps` field exists), accuracy of
the model's timestamps, and whether `text.format` strict schema is accepted on `/v1/responses`.

## Building Risk Map (0.7)
`GET /api/building` builds one entry per floor (Roof, F4, F3, F2, F1, B1 — the floors used by the asset register
and the zone mapping) plus "Building" for whole-building risks. A floor's state is the highest severity among the
risks (rule signals) of its active fire-risk alerts (alerts marked Resolved / False alarm are excluded). Without
risks: "No Active Fire-Risk Alert" if source records for the floor were evaluated, otherwise "Not Assessed". No floor
is ever shown as normal/green. Building status = highest severity over all active risks. Urgent actions = open
risks at High Risk or Emergency. No numeric risk score is computed.

## English display layer (0.7)
`ai/translate.py`: glossary for fixed vocabularies (statuses, tab names, generator reasons); Muse Spark batch
translation for free text, pseudonymised, cached in SQLite `translations`, background after each analysis
(`FIRERISK_AUTO_TRANSLATE`, default on). The API adds `<field>_en` and `<field>_en_origin`
(`source` | `glossary` | `ai_translation`; null = pending) next to the original; the UI marks AI translations and
shows pending ones in the original with a "translation pending" tag.
