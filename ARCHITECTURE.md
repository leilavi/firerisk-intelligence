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
| Survey videos (Drive folder + `Asset` tab `Reference_File`) | Automatic Drive sync, read-only token | Yes — 14 videos reviewed live by Muse Spark, findings localized by SAM 3.1 |
| Photos referenced by logs | Not accessible | No — media inventory only |
| Live sync without Claude | Built (`sources/drive_sync.py`); first real run on the author's PC 2026-10-28 11:35, then every 30 min while the dashboard runs | — |

## Failure behaviour
* A missing/corrupt workbook or tab → `source_unavailable` in Data sources and in the alert's "not verified" list;
  other sources still analysed.
* Muse Spark unavailable / no key / bad output → recorded as a failed AI attempt; rule alerts unchanged.
* Drive sync fails (no internet, wrong token, web page instead of data) → nothing changes, failure listed in Data
  sources. One file invalid or missing → that file keeps its previous version and `sync_error` is shown; the other
  file is still updated.
* Automatic AI analysis fails or times out → status "Meta Muse Spark Analysis Failed", the rule-based explanation is
  shown ("Rule-Based Explanation"); one automatic retry after 15 minutes, then only on request.
* SAM 3.1 unavailable → localization stays pending or "Localization unavailable"; Muse Spark findings, alerts and
  levels are unchanged.
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

## Survey video integration (built 2026-10-27; live since 2026-10-28)
| Step | How | Verified |
|---|---|---|
| Upload | Browser sends the file as the request body (`POST /api/videos?filename&zone&floor&area&room&recorded_at&duration_s`); stored in `data/private/media/videos/` (git-ignored); 1 GiB limit (Meta Files API) | TEST files |
| Metadata | Zone must be a known zone; recording time is entered by a person or "unknown" (file dates are not trusted); duration read by the browser | TEST |
| Analysis (automatic after download, daily limit; or on request) | `POST /v1/files` (purpose `user_data`, expires after 3600 s) → `POST /v1/responses` with `input_video` + `text.format` json_schema, `store: false` → `DELETE /v1/files/{id}` | **Live** on the author's PC since 2026-10-28 (all 14 videos; prompt `survey-video-v2` since 2026-10-28 16:29); fake transport in tests |
| Validation | Observations need a time range inside the video and a known category; others are set aside with the reason | TEST |
| Review | Player jumps to each observation (HTTP Range); still frame via ffmpeg when installed | TEST pattern |
| Use in alerts | Zone match → "Survey videos of this zone" in the fire-risk alert (section 9) and `survey_video_observations` in the Muse package, with recording date and "recording-time only" | TEST |
Answered by the live runs: the structured `text.format` schema is accepted on `/v1/responses`; videos over 1 GiB are
sent as a smaller copy; finding times are validated against the video length and the SAM frames are sampled inside
the finding's time range because timestamps are approximate.

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

## SAM 3.1 visual localization (2026-10-28)
Data flow:

`Muse Spark observation → segment_phrase → sampled video frames → SAM 3.1 visual localization → stored localization evidence → dashboard overlay`

**Rule: SAM localization must never change alert severity or rule-based decisions.** It also never changes a Muse
Spark record, never resolves an alert, and its confidence is never turned into a fire-risk score.

| Step | Module | Notes |
|---|---|---|
| Phrase | `firerisk/localize.py` | Schema v2.1 (prompt `survey-video-v2`): Muse Spark returns `segment_phrase` per finding / observation (`spark_v2`). Older items: one Muse Spark text-only request per analysis (`spark_derived`); fallback fixed keyword map (`category_map`); otherwise no phrase. Absence / no single object → `not_applicable`. Phrases checked by `sam.phrase_problem` (short English noun phrase, no people, no negation, no location). Stored in `finding_phrases`. |
| Frames | `localize.sample_times`, `extract_still` | Up to 3 times at 15 % / 50 % / 85 % of `[time_start_s, time_end_s]` (one midpoint for short or invalid ranges), clamped to the video length; ffmpeg auto-rotation; long side ≤ 1280 px; private `data/private/media/frames/<sha16>/t<0.1s>.jpg` (git-ignored); one file shared by every item needing the same frame. |
| SAM call | `firerisk/sam.py` | `POST /v1/responses`, `sam-3.1`, base64 JPEG + phrase, `include_confidence`, `one_bit` masks, `store:false`. Retries 429 / 5xx / timeout with backoff; 400 never resent unchanged; 404 `model_not_found` stops the batch. |
| Parse | `sam.parse_output` on Meta's `meta-sam-parser` | Empty output = valid no match. Malformed lines, out-of-frame boxes, undecodable masks are dropped and reported; confidence never invented. |
| Store | `video_finding_locations` | One row per frame, unique fingerprint sha256(video sha256, analysis, kind, index, phrase, frame time). Same video bytes + phrase + time → previous answer reused, no call. Item status: located / not_located / error / not_applicable / not_checked (an error is never shown as "not located"). |
| Run | `Localizer.run` | Shared by the backfill script (`scripts/locate_video_findings.py`, `--dry-run` on a database copy) and the dashboard's background pass after every new Muse Spark video analysis (`scope="new"`: analyses newer than the backlog boundary in `localizer_meta`). Daily limit `FIRERISK_SAM_DAILY_LIMIT` (default 300); over the limit work stays pending. Safe to stop and resume. |
| Show | `web/app.js` `evidenceBlock` | Frame + SVG box/mask in the frame's own pixel space (`viewBox` = frame size), labels "AI observation (Muse Spark)" and "Visual model detected (SAM 3.1)". |

Processing stages are tracked separately: video registered (`survey_videos`) → Muse Spark analysis (`video_analyses`
status + running set) → phrase (`finding_phrases`) → localization (`video_finding_locations`, `/api/localization`).
