# Changelog

## Unreleased — SAM 3.1 visual localization (in progress)
- Local OCR of scanned drawings (`scripts/ocr_drawings.py`, `run_drawing_ocr.bat`): pages rendered with pypdfium2,
  read with RapidOCR on the CPU in overlapping tiles (also turned 90 degrees), duplicates removed; results and a review
  page stay in `data/private/drawings/ocr/`; console prints counts only. No AI service, no network. New dependencies
  `rapidocr`, `onnxruntime`, `pypdfium2`.
- Drawing probe (`scripts/probe_drawings.py`, `run_drawing_probe.bat`): reads the technical drawings on the author's PC
  with pdfplumber (no AI, no network) and prints counts only - page kinds (CAD text layer / scan / text), vector
  objects, generic label categories, floor mentions - to design the local extractor. New dependency `pdfplumber`.
- Docs: the 2 technical drawings and the O&M manual are in scope (referenced in the approved asset register); used
  under condition 2 (local processing only).
- Data owner's approval (2026-10-30) recorded without names in `DATA_AUTHORIZATION.md`; U-05 resolved; R-08 verified.
- `firerisk/data_policy.py`: documents (PDF, CAD, office files) and anything named like a drawing, schematic, layout or
  manual are refused before every upload to the Meta Model API (video upload, image description, SAM), also when a
  document is saved under an image name (content check). Drive sync records them by name only
  (`manifest.json` → `local_only_documents`) and never puts them in the video catalogue. Survey videos are unaffected.
- Demo blurring: faces detected locally with OpenCV Haar cascades and blurred (SAM is still never asked to find people);
  frames already processed by SAM get the face pass without any API call. New dependency `opencv-python-headless`.
- Tests: `tests/test_data_policy.py` (4), 2 new tests in `tests/test_demo.py`.
- Docs (2026-10-30 20:00): `FEATURE_ORIGIN_MATRIX.md` brought up to date (rows that still said "not yet run live",
  "mock-tested only", "no real video", "SAM 3.1 not implemented" now state the live status and counts from the PC
  database); `HACKATHON_COMPLIANCE.md` R-02 updated (21 investigations, prompt v7, SAM 511 frame results counted per
  frame, agentic tool calling). `test_docs_current.py` now also checks the matrix.
- Agentic investigation live on the building data (2026-10-30 19:06): ZONE-B1 and ZONE-Building analysed
  automatically with tool calling, 0 invalid citations, no fallback; sanitized summary
  `evidence/agentic_investigation_live_20261030.json`. Trace heading says "no records beyond the rule package found"
  when that is the case.
- Tool calling verified live (2026-10-30 18:57, synthetic records, `evidence/tool_calling_check_20261030_185751.json`):
  2 parallel tool calls in round 1, plain answer in round 2, strict-schema final answer; tools + response_format
  accepted together. The intent sentence Muse Spark writes next to its tool calls is now kept in the trace and shown
  as "Round n · intent".
- Agentic investigation (2026-10-30): Meta Muse Spark tool calling (`firerisk/ai/agentic.py`). Six read-only tools
  over the record store (asset list, asset history, record search, meter readings, equipment alerts, survey-video
  findings); validated arguments, aliases and redaction for everything returned, caps (6 rounds, 16 lookups, 25
  records), final answer in the existing strict schema with citations validated against all records shown.
  Automatic fallback to the single-call investigation when the tool conversation is rejected or the answer is
  malformed / cut off; API-down errors recorded as failed. Dashboard: "How Meta Muse Spark investigated" (every lookup
  in order, records cited beyond the rule package) in the briefing drawer and the investigation page, lookup count in
  the Risk Briefing and the analysis history. Client: `chat_tools`, `chat_json_messages`. Prompt `investigation-v7`.
  `FIRERISK_AI_TOOLS`. Live check script `scripts/check_tool_calling.py` + `run_tool_calling_check.bat` (synthetic
  data). 6 new tests; offline only so far.
- README "AI-Assisted Development" section (text written by the author, 2026-10-30).
- README "Development history" for judges (building period, baseline commit `b79223f` on branch `baseline`,
  `git diff baseline main`, disclosed history rewrites); wrong baseline references (`3219f8c`, tag
  `baseline-pre-hackathon`, which was never on GitHub) corrected in HACKATHON_COMPLIANCE, PROJECT_STATUS and
  FEATURE_ORIGIN_MATRIX and added to the outdated-wording test.
- Documents brought up to date with the live state (2026-10-30, after an outside review read the old README):
  README Meta AI usage table (video review and SAM 3.1 live, single photos not run, numbers from the PC database),
  data limits (one building, no sensor telemetry, floors not recorded), SAM / demo-mode sections, dashboard, tests
  (191), dependencies; PROJECT_STATUS rewritten (no more contradictory video rows); ARCHITECTURE, TASKS and
  HACKATHON_COMPLIANCE corrected (tool calling marked not implemented). New `tests/test_docs_current.py` fails when
  the README test count is wrong or an outdated status sentence remains; `CLAUDE.md` records the rule that every
  change updates the documents in the same commit.
- Survey Video Findings (Overview): survey-scan illustration added inside this section only (author's request
  2026-10-29). Isometric floor slabs drawn from the building's floor list and `/api/video-findings`: floors covered by
  a reviewed video (cyan schematic camera route), amber count of findings that still need verification per floor
  (opens that floor in "View video findings"), numbered top findings with their video timestamp, and a separate chip
  for videos without a verified floor. No room positions (none exist in the data); a scan line appears only while a
  review is actually running. Top findings now show their real SAM 3.1 frame (blurred copy in demo mode) when one is
  stored. Scoped `.vs-*` CSS appended; Building Risk Map, other sections, API and rules unchanged.
- Naming (author's decision 2026-10-29 19:50): the generic "AI" label and the display name "Muse Captain" are
  removed from the dashboard. Every model-made part is named after the Meta model that made it: "Meta Muse Spark"
  (analysis, video review, translations; tag META MUSE SPARK) and "Meta SAM 3.1" (object outlines; tag META SAM 3.1).
  The briefing is titled "Meta Muse Spark – Risk Briefing" when its text comes from a Meta Muse Spark analysis, and
  "Risk Briefing · rule-based until Meta Muse Spark completes" otherwise. Model IDs (`muse-spark-1.3`, `sam-3.1`) unchanged. Rule results keep
  the RULE tag. Test `test_display_names_are_meta_model_names_and_model_ids_unchanged`.
- Phase 1: `scripts/check_sam.py` + `run_sam_check.bat` — one real frame to `sam-3.1`; verified live on the author's PC
  (valid no-match for "electrical panel" on a close-up frame; 8 objects located for "push button").
- Phase 2: `firerisk/sam.py` — SAM client (MuseConfig / MODEL_API_KEY, backoff on 429/5xx/timeout, no blind retry on
  400, `model_not_found` reported, `store: false` with a single documented fallback) and parser on Meta's official
  `meta-sam-parser` (empty = no match; malformed lines, boxes outside the frame and undecodable masks reported, never
  guessed; confidence never invented). `scripts/check_sam_client.py` for a live check. 33 offline tests.
  Live client check PASS (`evidence/sam_client_check_20261028_203608.json`: 8 objects, `store:false` accepted).
- Phase 3: `segment_phrase` added to the video review schema (schema_rev v2.1; prompt version stays survey-video-v2 so
  no video is re-analysed). Separate tables `finding_phrases`, `video_finding_locations` (frame-level rows,
  fingerprint-unique, answers reused for the same video bytes + phrase + frame time), `localizer_meta`. Phrases for
  older items: Muse Spark text-only request (spark_derived), fallback fixed keyword map (category_map), else none.
  `scripts/locate_video_findings.py` (`--dry-run` works on a copy of the database; cost from the official price
  $2.50 / 1,000 images). Original Muse records are never modified.
- Phase 4: 1-3 upright frames per item inside its time range (ffmpeg), private under data/private/media/frames/.
  After every new Muse Spark video analysis the dashboard localizes its items in the background (daily limit
  FIRERISK_SAM_DAILY_LIMIT, default 300; FIRERISK_AUTO_SAM=0 turns it off). Analyses that existed when SAM was
  installed are the backlog for the script. New endpoints: /api/localization, /api/localization/{analysis}/{kind}/{i},
  /api/frames/{folder}/{file}; /api/video-findings carries each finding's localization. 19 new tests.
- Phase 5: evidence near the top of the finding drawer and of the risk / equipment drawer (marker or View Details):
  real frame, SAM box + mask overlay scaled from the original pixel size (no distortion), sampled-frame strip,
  source video + "open at" timestamp, location, and two labelled parts "AI observation (Muse Spark)" and
  "Visual model detected (SAM 3.1)" with the required status wording (Located in frame at mm:ss (confidence x.xx) /
  Not visually located in the sampled frames / Localization not checked / Localization unavailable / Not
  applicable / No Supporting Frame Available). Confidence tooltip states it is not a fire-risk probability.
  Photos & Videos: "Visual evidence for video findings" gallery. Playwright tests at 1440 and 390 px check
  alignment, no horizontal scroll, English only.
- Demo privacy (optional task, 2026-10-29): `scripts/mask_labels_for_demo.py` — SAM 3.1 finds "sign" and "label"
  objects in every evidence frame; ffmpeg blurs the padded boxes into copies under data/private/media/frames_demo/
  (originals never touched; manifest.json; `--dry-run`, `--max-requests`, `--add-box` for regions SAM missed,
  `--review` contact sheet, `--mark-reviewed`). Demo mode (`run_dashboard_demo.bat`, FIRERISK_DEMO_MODE=1): header
  "Demo building", building-name text masked on the page (patterns built from the private site_config.json, accent-
  and case-insensitive, both word orders, branch prefix, initials form, optional `extra_names`), frames served only as
  blurred copies, original videos and on-request frames not served. Not called anonymized until reviewed.
- Fix (author's report 2026-10-29 08:11): the evidence frame at the top of a risk / equipment drawer came from any
  video finding linked by "same floor + matching group", so the wastewater blower risk showed a cable frame from the
  MSB room. Now only a strong match is pictured: video linked to the same equipment in the asset register, or video /
  area name containing the room or equipment named in the issue (e.g. "Wastewater" -> Wastewater Treatment Room.mp4);
  the most relevant group and a located frame come first, and the reason is printed. Same-floor-only findings are
  mentioned in one line without a picture. Follow-up (08:36): an equipment link counts only for the risk it belongs
  to (a zone alert holds several risks; the MSB video is linked to the water-in-electrical-rooms risk, not AB-01A).
- Fix (found 2026-10-29 08:45 while checking the author's report that the dashboard still showed 28 Oct): the
  ZONE-B1 Muse Spark investigation (prompt v6) failed 7 times in a row since 28 Oct 16:38 with "model output is not
  valid JSON" - the answer was cut off at max_completion_tokens 8,000, which also counts reasoning tokens, and B1 has
  9 per-risk briefings. The dashboard therefore kept showing the last good analysis (28 Oct 15:06). Budget raised to
  32,000 for investigations; a cut-off answer (finish_reason "length") is now reported as error kind `truncated`.
- Fix: the "Source not updated / unavailable" lines now use the English tab name (a Vietnamese tab name reached the
  page once the data was more than 2 days old).

## 0.9.0 — 2026-10-28
- Overview: GROUND LEVEL removed from the Building Risk Map (geometry, line, label and gap); floors, markers, colours
  and selection unchanged; issues without location stay under "Location not recorded".
- Display name of the AI analyst: **Muse Captain** (UI only). The model called is unchanged: Meta Muse Spark,
  `muse-spark-1.3`, same endpoint, payloads and key; a "powered by" line names it in the header tooltip, Data & sources
  panel and footer.
- Investigation prompt v6: per-risk briefing specific to the records (dates, current vs past, history link, hazard
  mechanism, 2-5 step escalation chain, not-established list, Immediate / Follow-up / Closure criteria, key
  statements with basis Supported by records / Observed in video / Hypothesis / Not established; a "supported by
  records" statement without a valid record is downgraded to hypothesis). AI priority that differs from the rule
  level is shown with its reason; the rule level stays official.
- Progressive disclosure with one mechanism (`<details class="acc">`): AI analysis and related video findings in the
  briefing are closed by default; other alerts: open High Risk / Emergency stay visible, the rest behind "Show N more
  alerts" (count from data). Fixed: elements with the `hidden` attribute were still shown (CSS display override).
- Survey-video fire-safety review v2 (Muse Captain via the Meta video API): groups A-G (ignition sources,
  combustibles & housekeeping, escape routes & access, extinguishers, detection & alarm, suppression & smoke
  control, water near electrical plant), area-by-area extinguisher status (Visible and accessible / Visible but
  access may be obstructed / Not visible in the surveyed footage / Needs on-site verification), findings with
  timestamps, coverage. Every video is reviewed once more with the new prompt (one automatic attempt per prompt
  version; daily limit default 20).
- AI video findings (`GET /api/video-findings`, `POST /api/video-findings/{id}/status`): separate from rule-based
  alerts, no official level, status set only by a person (New finding / Needs verification / Confirmed / Resolved /
  Not confirmed on site), linked to an existing alert only for a stated reason (same equipment in the asset register,
  or same floor and matching group). Survey coverage report (videos on Drive / here / reviewed / failed / waiting,
  floors without video, locations not verified, possible overlaps, groups assessed or not, footage needed).
- Videos over 1 GiB (Files API limit) are downloaded and sent as a smaller 720p/540p/360p copy without audio
  (ffmpeg via the new `imageio-ffmpeg` requirement; also enables still frames on Windows). Drive renames are
  followed. `run_dashboard.bat` installs new requirements quietly.
- 125 tests.

## 0.8.1 — 2026-10-28
- The AI Risk Briefing now shows the stored real Muse Spark result directly, also when it was made with an earlier
  prompt (v3/v4): observed facts, scenario and suggested check are taken only from the parts of that result that cite
  this risk's own records; the zone situation, AI priority, hypotheses and checks are shown in a "Muse Spark analysis"
  pane. Status "AI Analysis Complete · Update Pending" while the new v5 analysis is due.
- Survey-video findings are back on the Overview: a "Survey video findings · Muse Spark" panel with every analysed video
  (summary + main observations, links to the clip), and in the briefing the videos of the same equipment (asset
  register), the same room name, or else the same floor. The risk drawer lists each video's observations.
- 117 tests.

## 0.8.0 — 2026-10-28
- Dark building-intelligence design (navy panels, cyan interaction, purple = AI content; risk colours only for levels).
- One unified building view: fire-safety risks **and** equipment alerts are placed on their own floor, each keeping its
  original classification and rule level (`issues`, `map_state`, `marker` in `GET /api/building`; issues without a
  recorded location in `unassigned`). Building condition = highest level among all active issues; "Assessment
  Incomplete" when nothing is active but floors are not assessed; never "safe".
- AI Risk Briefing at the top of Overview (`GET /api/briefing`): highest-priority issue (rule level, unresolved,
  fire-safety before equipment, most recent), location, observed condition, why it matters, potential consequence,
  what is not established, first action, evidence, analysis status (complete / older evidence / pending / failed /
  insufficient evidence / unavailable). Each line is labelled AI or RULE; without a Muse Spark result the rule
  explanation is shown and the AI state is stated. "View AI Analysis" expands the full analysis; other issues can be
  opened from a compact list.
- Investigation prompt v5: per-risk `risk_briefings` (signal aliases S01…, certainty enum; "insufficient_evidence"
  forces the fixed "Insufficient evidence…" text; unknown signals and invalid citations dropped and reported).
- Building Risk Map: front view with depth, ground line, underground B1, whole-building band; one marker per floor with
  the number of active issues (red = High Risk / Emergency, pulsing; yellow = Warning; blue = Watch); the floor of the
  briefing is highlighted; click a floor or marker for the context panel; compact geometry on phones.
- Compact issue cards everywhere (location · name, one-line description, level · count, classification); "View
  Details" opens a side drawer with the evidence, chain of events, actions and AI analysis.
- Navigation: Overview, Fire Safety Risks, Equipment & Systems (system-health strip), Event History, Data & Evidence
  (Sources & Sync, Photos & Videos). Old links (`#/quality`, `#/media`, `#/alert/…`) still work.
- English-only enforcement: no untranslated text shown by default (pending translations say "English translation
  pending"; originals only in a collapsed "original record" section of the source drawer); AI text that is not English
  is not shown; translations that still contain Vietnamese are rejected; names restored without diacritics; record IDs
  shown without diacritics; a page-level safety net replaces and logs any remaining untranslated text (0 on real data).
- 116 tests (incl. a Playwright test that renders every page and fails on any visible Vietnamese text).

## 0.7.0 — 2026-10-28
- Building-centred Overview: building summary (status = highest active risk, risks by severity, floors affected,
  urgent actions, last analysis / Drive sync), interactive Building Risk Map (front view, Roof–B1 + whole-building
  band; keyboard accessible), floor panel with the most important risk in plain English and expandable risk cards,
  urgent actions, equipment-alert summary, recent records and analysed survey videos. `GET /api/building`.
- Floor states: Emergency / High Risk / Warning / Watch from active risks; "No Active Fire-Risk Alert" when records
  exist but no rule fired; "Not Assessed" when there are no records. Green is never used (the rules cannot confirm a
  floor is safe; there are no smoke/heat/gas sensors). Watch is now blue, Warning yellow.
- One card per risk (rule signal): location, risk, why it matters (plain English, cautious), severity, status,
  evidence count, first action. Fire Safety Risks page with filters (severity, floor, status, risk type). Alert detail
  in six sections: What Was Detected, Why This Matters, Supporting Evidence, AI Analysis, Recommended Actions, History.
- English UI: AI status labels, rule texts, tab names and record statuses (deterministic glossary); free-text records
  and register names translated by Muse Spark in the background and cached, originals kept and marked
  (`*_en`, `*_en_origin`). Investigation prompt v4 (English only).
- Photos & Videos gallery with filters (floor, date, linked risk, text) and source links.
- Privacy fix: lower-case honorifics ("anh Nam") are now pseudonymised before AI calls.
- 108 tests.

## 0.6.1 — 2026-10-28
- First real run on the author's PC (11:40): Drive sync OK (9 files, 8 videos), automatic Muse Spark analysis of
  ZONE-B1 and ZONE-Building with prompt v3 (27 s, 22 s, both valid), 2 videos downloaded with MP4 recording times.
  The dashboard process stopped at 11:41:46 during the third download (cause unknown: no log file existed).
- Fixes: log file `data/private/logs/firerisk.log` (+ `crash.log` for Python crashes, thread errors logged), console
  shows warnings only; partial downloads resume with HTTP Range; an expired Drive token is renewed once; each video is
  analysed right after its download (and videos already downloaded are analysed first).
- 102 tests.

## 0.6.0 — 2026-10-28
- Everything is read from Google Drive: the Apps Script web app also returns a listing of the data folder (incl.
  sub-folders such as "Video Uploaded") and, on request, a short-lived read-only Drive token.
- `drive_videos.py`: every video in the folder or linked in the Asset tab is downloaded to the computer (smallest first,
  size-checked; tokens that can write to Drive are refused), registered with zone and equipment from the register, and
  reviewed by Muse Spark automatically (one at a time, one attempt per video, daily limit). Observations become context
  of the zone's fire-risk alerts, which are then re-analysed automatically.
- Photos & video page: "Videos in Google Drive" with status per video and download progress.
- 99 tests.

## 0.5.0 — 2026-10-28
- Skill §2B.7 ported (was missing): near-zero day followed by a day ≥ double → "possible late reading", listed for
  verification and spread over the two days. Real effect: main water meter High → Warning (11 such pairs; the remaining
  finding is the 13–16 Oct rise of about 156 m³ in 3 days).
- New optional source: the `Asset` tab (equipment register, 272 in-scope rows) — display names, floor/zone, and the
  survey-video links in `Reference_File` (7 videos, linked to equipment; zone from the register's Floor, never guessed).
- Survey-video import from a local folder: matched to the register by file name or size; recording time read from the
  MP4 header when present (labelled "camera clock, not verified"); longer network timeout for video analysis.
- 92 tests.

## 0.4.0 — 2026-10-27
- Two independent alert systems: building equipment alerts (PORTED skill rules EQ1–EQ4) and fire-risk alerts (NEW),
  linked only with stated reasons; meter findings are equipment alerts, no longer fire-risk signals.
- Automatic background Muse Spark analysis of fire-risk alerts: evidence fingerprint, no calls on page reload,
  one retry after 15 min, daily limit, Vietnamese status labels, rule-based fallback; prompt v3 (situation,
  scenarios with supporting/weakening evidence, limitations).
- Survey-video architecture: upload with zone/floor/area/room/recording time, player, still frames, Muse Spark video
  review via the documented Files + Responses APIs (not yet run), observations as dated context of fire-risk alerts.
- Dashboard: Overview with two sections; fire-risk list + 10-section detail; equipment list + detail; origin labels
  SOURCE / DERIVED / RULE / AI / TEST. Old `#/alert/...` links and `/api/alerts` still work.
- 87 tests.

## 0.3.0 — 2026-10-27
- Automatic updates from Google Drive: Apps Script export web app (author's own account, listed files only, token),
  `sources/drive_sync.py` (validated replacement, previous version kept, partial failures reported), background sync
  every 30 min, `POST /api/sync`, sync history in SQLite, "Update from Drive" button, Data sources panel,
  "new analysis available" notice. `setup_drive_sync.bat` for the one-time setup.
- 66 tests (11 new, against a local mock of the web app).

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
