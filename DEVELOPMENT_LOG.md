# Development Log

All times UTC+7 (Asia/Bangkok). Entries record only work that actually happened.

## 2026-10-27 11:52–12:05 — Phase 1–2: Initial audit (no application code yet)

**Work done**
- Read the pre-existing risk-alert skill (`SKILL.md`, 600 lines) in full.
- Read the official Participant Guide attached to the Claude Project.
- Read Meta Model API official docs: quickstart, chat completions, structured output, SAM overview.
- Checked Google Drive metadata of the original skill file (last modified 2026-10-15T02:28:02Z, before the build period).
- Created this repository; added a redacted baseline copy of the skill; committed and tagged it.
- Wrote `PRE_EXISTING_WORK.md`, `FEATURE_ORIGIN_MATRIX.md`, `HACKATHON_COMPLIANCE.md`, this log.

**Files**: `baseline/skill-canh-bao-rui-ro_v2.2_REDACTED.md`, `.gitignore`, `PRE_EXISTING_WORK.md` (commit `3219f8c`, tag `baseline-pre-hackathon`); audit documents (next commit).

**Tests**: none (no code yet).

**Findings / issues**
- The baseline is a prompt, not code: every line of application code will be new.
- `curl https://api.meta.ai/v1/models` from Claude's cloud workspace → `CONNECT tunnel failed, response 403`. Live API calls cannot be made from this workspace; they must run on the author's machine.
- Drive copy (73,071 B) and installed copy (73,080 B) of the skill differ by 9 bytes — not yet inspected.

**Open**: API key (author), track decision (author), organizer questions U-01…U-04.

## 2026-10-27 12:01–12:10 — Author decisions; Meta API connection check (offline-tested only)

**Author decisions (reported in chat):** Meta API credits claimed, API key created, **Indie track, solo**.

**Work done**
- `scripts/check_meta_api.py` (stdlib only): GET `/v1/models`, one structured-output POST `/v1/chat/completions` to `muse-spark-1.3`, writes sanitized evidence JSON. `setup_api_key.bat`, `run_api_check.bat` for Windows; `.env.example`.
- `tests/mock_meta_server.py`: local mock of the two endpoints.

**Tests (OFFLINE, mock server — not the real API)**: mode `ok` → PASS; mode `401` → FAIL reported; mode `badjson` → FAIL reported; grep confirmed the test key is absent from evidence files.

**Not yet done**: real API call (must run on author's Windows PC; Claude's workspace cannot reach api.meta.ai).

**Compliance**: R-04, R-15, R-18 → IN PROGRESS; R-07 → BLOCKED pending organizer answer U-02 (later reclassified IN PROGRESS at 12:30, see next entries).

## 2026-10-27 12:24–12:30 — R-07 reclassified
Author clarified the project is an upgrade of their own earlier skill. The guide is silent on Indie reuse; R-07 set to IN PROGRESS with documented interpretation; U-02 kept as an optional confirmation. Building-period dates corrected to Oct 27 – Nov 4 (guide §3). Commit `5343bdd`.

## 2026-10-27 13:15–13:33 — First REAL Meta Model API call: PASS
- Python 3.13 (Microsoft Store, Python Software Foundation) installed on the author's PC; `run_api_check.bat` launcher fixed to detect the Windows Store stub (commit after `5343bdd`).
- Author ran `run_api_check.bat` on their PC at 13:33 UTC+7.
- Result: `GET /v1/models` HTTP 200 (2.2 s), 9 models; `POST /v1/chat/completions` to `muse-spark-1.3` with strict JSON schema HTTP 200 (2.7 s), schema-valid output, 507 tokens (330 reasoning).
- Evidence: `evidence/api_check_20261027_133317.json` (checked: contains no key).

## 2026-10-27 13:48–15:00 — Direction change to real data; core engine, Muse integration, dashboard
**Author instruction (13:48):** use the real operational data, port skill rules to tested code, integrate Muse Spark with the real API, build a complete dashboard; prepare photo/video integration (no media yet); no synthetic data in place of real data.

**Real data pulled (Claude Google Drive connector, read-only):** `Operations Data` (ODS export → xlsx; 838 meter/checklist rows, 37 asset rows, 142 incident/works rows, 49 generator rows; newest record 2026-10-27 06:27) and `Theo dõi lượt khách ra vào` (13 monthly sheets, 243 days, newest 2026-09-30). Drive modifiedTime of the main sheet (2026-10-08) lags behind its rows; freshness is now judged by newest record. Photo files referenced by the logs were not found in the author's Drive.

**Code written:** `firerisk/` (config, models, sources/workbook+normalize, rules/scope+meters [PORTED], hazards/tagging+pathways [NEW], correlation [NEW], engine, ai/redact+muse+investigation [NEW], store, api, media, serve), `web/` dashboard, `tests/` (4 files), `requirements*.txt`, `install.bat`, `run_dashboard.bat`, `RISK_RULES.md`, `README.md`.

**Tests:** `pytest` 32 passed (ported rules 11, new hazard rules 9, offline AI 10 [fake transport, not the real API], real-snapshot integrity 2). Playwright: 8 dashboard views, no console errors; AI panel exercised end-to-end against `tests/mock_meta_server.py` in **mock** mode (results labelled MOCK, stored only in a temporary test database).

**Result on real data (deterministic, no AI):** Basement B1 = High risk — unresolved water ingress into MBA/MSB rooms (incident T10_140, repairs 059/060), open failure of XLNT blower AB-01A with a recorded burnt motor (Mainte-user3-034, Repair-user2-d0036), recurring heat-detector monitor fault (Repair-user1-068, T10_143), backup-power context (battery replacement, 3 grid outages). Four Watch-level zones (PA fault, meter anomalies).

**Not done / limits:** live Muse investigation not yet run (needs author's PC); SAM 3.1 not implemented; live Drive sync not implemented; no real photos/video yet.

## 2026-10-27 14:13–14:30 — First LIVE Muse Spark investigation in the app
- Author ran `install.bat` on the Windows PC: dependencies installed, **32 passed** on the PC (incl. real-snapshot tests). Console had been paused by QuickEdit "Select" mode; resumed with Esc.
- Author ran `run_dashboard.bat`; analysis run 1 at 14:17:51; pressed "Run Muse Spark investigation" on ZONE-B1.
- Result (read from the PC database `data/private/firerisk.db`, ai_investigations id 1): status ok, `muse-spark-1.3`, 38.9 s, 10,652 prompt + 6,535 completion tokens (2,363 reasoning), 33 evidence items sent (names/e-mails pseudonymised), validation ok (0 invalid IDs, 0 unsupported facts). Output: 12 observed facts, 5 hypotheses (incl. a data-quality alternative), 3 escalation steps, 6 missing-information items, 7 actions; AI priority High, agrees with rule severity; explicitly treats passing checklists as contradicting evidence and states coincidence ≠ causation.
- Privacy finding: source record IDs embed staff user names (e.g. `Repair-<user>-059`) and were sent as evidence IDs in prompt v1. Fixed in prompt v2: opaque aliases E01…; mapped back after the response. Tests updated (32 passed).
- Evidence: full result kept private (`data/private/evidence/`), public summary `evidence/investigation_ZONE-B1_20261027_1419_summary.json`.
- Compliance R-02 → VERIFIED.

## 2026-10-27 14:34–14:40 — Pre-publication privacy scrub (before the first push to GitHub)
- Scan before publishing: no API keys/secrets in any commit. Found personal data in 3 files (a staff e-mail and real names used as test strings; staff user names embedded in source record IDs quoted in this log and in the redacted baseline).
- Because nothing had been published yet, the history was rewritten once with `git filter-repo --replace-text` to replace these strings with fictional placeholders (e.g. `Repair-user1-064`). **Commit author/committer dates and messages were preserved**; only file contents changed, so commit hashes changed. Hashes quoted earlier in this log refer to the pre-scrub history; after both scrubs the baseline commit is `b79223f` (marker `baseline-pre-hackathon`). A full backup bundle of the pre-scrub history is kept privately by the author/Claude workspace.
- Tests after scrub: 32 passed.
- 14:40 Author decision: anonymise the building in the public repository. Building name, operator, tenants and branch codes replaced by placeholders ([Building], [Operator], BLD, SITE-2, [Tenant A]…) in files and commit messages across the unpublished history (dates preserved). The real values now live only in `data/private/site_config.json` (git-ignored). Tests: 32 passed with and without the private config.

## 2026-10-27 14:39–14:50 — Published to GitHub
- Author connected GitHub and installed the Claude GitHub App on `leilavi`. First push attempts returned HTTP 403 until the installation propagated; then `main` (12 commits, dates preserved) was pushed to https://github.com/leilavi/firerisk-intelligence.
- Git tags cannot be pushed through this environment's proxy (HTTP 403 on tag refs and on the refs API), so the baseline marker was published as branch `baseline-pre-hackathon` → `b79223f`.
- Verification: repository visibility `public`; fresh clone contains no `data/`, no `.env`, and no building/operator/staff identifiers in any commit; tests on the fresh clone: 30 passed, 2 skipped (real-data tests skip without the private snapshot, by design).

## 2026-10-27 15:53–16:20 — Pipeline hardening, skill alignment, dashboard v2
**Author instruction (15:53):** complete reading/normalising/analysing/linking of real data for fire-risk detection (no media yet); keep labels, levels and 14 fields; redesign the dashboard (light, risk colours, evidence-first detail).

**Audit findings on real data:** unmapped statuses ("3. Tạm dừng", "Đang thi công", empty); 6 generator runs with duration 00:00 although start ≠ end; one works record "Đang thi công" since August; a missing tab or corrupt file would have stopped the whole analysis. Gaps vs SKILL.md: a fifth episode label had been introduced; meter signals did not follow §5A.8 levels; alerts lacked several of the 14 §8 fields.

**Changes:** `config.py` (STATUS_CLASS), `sources/normalize.py` (status class, dedupe, invalid values, units, generator duration, resilient loader), `engine.py` (record checks, resilient sources, DQ flags), `rules/meters.py` (4 labels + related-record rule, ongoing/near-zero), `hazards/pathways.py` (R8 per §5A.8), `alert_fields.py` (new: 14 fields, short texts, assessment class), `store.py` (late arrivals, first detection, "confirmed"), `api.py` (new endpoints), `web/*` (dashboard v2), tests `fixtures.py` (TEST fixture workbooks), `test_pipeline.py`, `test_api.py`, extra rule tests, `ARCHITECTURE.md`, `RISK_RULES.md`.

**Tests:** 54 passed. Playwright on the real snapshot: overview, alerts, alert detail (+ AI panel against the mock server, labelled TEST), drawer, equipment, data sources, events, media, tablet 820 px — no application errors (only Google Fonts blocked by the sandbox proxy; fallback fonts used).

**Effect on real data:** B1 stays High risk (water ingress not fixed; jammed blower with past burn-out). Water main and floor-2 AC meter now Warning (recurring episodes, skill §5A.8). Roof and F3 no longer raise a signal: their October episodes are "Insufficient data" because no vehicle counts exist after 30 Sep.

**Not done:** live Drive sync; photos/video; SAM 3.1; live check of dashboard v2 on the author's PC.

## 2026-10-27 16:42–17:00 — Automatic updates from Google Drive
**Author instruction (16:42):** build the proposed automatic update from Google Drive.

**Design decision:** a Google Apps Script web app in the author's own account instead of an OAuth desktop client.
Reasons: no Google Cloud project, consent screen or client secret for a non-programmer; refresh tokens of OAuth
apps in "Testing" status expire after 7 days. Limits: the web app is reachable by anyone who has both its URL and
the token, so both live only in `.env`; the script reads only the listed file IDs, read-only scope.

**Files:** `apps_script/FireRiskExport.gs`, `apps_script/appsscript.json`, `firerisk/env.py`,
`firerisk/sources/drive_sync.py`, `scripts/setup_drive_sync.py`, `setup_drive_sync.bat`, `firerisk/store.py`
(sync_runs), `firerisk/engine.py` (sync_error in source status), `firerisk/api.py` (`/api/sync`, background sync),
`firerisk/serve.py`, `web/*`, `tests/test_drive_sync.py`, docs.

**Tests:** 66 passed. Drive sync tested only against a **local mock** of the web app (302 redirect then GET, as
Google does): download and replace, unchanged detection, wrong token, web page instead of data, invalid file,
missing file, Google error per file, unreachable host, secrets absent from API output. A copy of the real snapshot
was synced through the mock and shown in the dashboard (desktop + tablet screenshots).

**Not verified:** a real call to Google (Claude's workspace cannot reach Google; first real run on the author's PC).

## 2026-10-27 17:09–18:45 — Two alert systems, automatic Muse Spark analysis, survey-video architecture
**Author instructions:** attachment "Yêu cầu nâng cấp hệ thống cảnh báo tòa nhà và tích hợp AI phân tích nguy cơ PCCC"
(two independent alert systems, Overview with two sections, automatic background Muse analysis, fallback, origin
labels, 13 test scenarios) and section 9 (prepare survey-video integration without media; check official docs first).

**Note on timing:** backend work for this request started 17:09–17:14 in a session run that was interrupted; it
was reviewed and completed after the author re-sent the request at 18:12. No other process was writing in between.

**Docs checked (18:15):** dev.meta.ai video-understanding, file-handling, responses create + schemas,
structured-output. Muse Spark accepts mp4 video directly (`input_video`), so no frame-to-image workaround is needed;
max duration, sampling and timestamp accuracy are not documented.

**Files:** `firerisk/equipment.py`, `firerisk/ai/auto.py`, `firerisk/video.py` (new); `engine.py`, `models.py`,
`store.py`, `api.py`, `ai/investigation.py` (prompt v3, fingerprint, video context), `ai/muse.py` (`_send`),
`web/*`; tests `test_two_systems.py`, `test_video.py`, `fixtures.py`, `test_api.py`, `mock_meta_server.py`; docs.

**Fix during review:** the evidence fingerprint first included context record IDs, so every new daily checklist
would have caused a new AI call; it now uses what context records say (status, pass/fault).

**Tests:** 87 passed. Fake Muse transport and local mock only (no real API from Claude's workspace). Live check on a
copy of the real snapshot with the local mock (labelled TEST): 2 automatic analyses at start-up, 0 extra calls after
10 page loads; video upload of a generated TEST pattern, player, failure path, zone context (scratch database, not
kept). Playwright desktop + tablet: no application errors.

**Effect on real data:** fire-risk alerts: B1 High (linked to 4 equipment alerts: MSB meter, XLNT meter, XLNT blower,
water-ingress incident), whole-building PA Watch. Equipment alerts: 8 (7 Warning, 1 Watch).

**Not verified:** a real automatic Muse run with prompt v3; any real video analysis (no video yet).

## 2026-10-28 10:31–10:55 — New sheet data, skill §2B.7, Asset register, survey-video import
**Author (10:31):** survey-video content added to the operations sheet; run the fire-risk analysis.

**Data:** Drive export of `Operations Data` (modified 2026-10-27 21:05 UTC+7): 845 meter rows (newest 28 Oct 06:22),
new tab `Asset` (656 rows, 272 in scope). The incident tab's video columns hold no in-scope video. The `Asset` tab links
7 MP4 files in `Reference_File` (Drive metadata checked: 91–648 MB, uploaded 27 Oct 16:04–16:16; recording time
unknown). Previous snapshot kept in `snapshot/previous/`.

**Finding and fix:** the main water meter rose to High because days with an unchanged reading (0) lowered the baseline
and the next day's normal catch-up looked like a spike (16–27 Oct averaged 6.4 m³/day vs 5.9 in September). Skill
§2B.7 ("near zero then double → check late reading") had not been ported; it is now (preliminary 10% cut-off).
Result: Warning, driven by the 13–16 Oct rise (~156 m³ in 3 days); 11 possible late readings listed for verification.

**Rule results on the new data:** fire-risk B1 High (unchanged; 4 linked equipment alerts), whole-building PA Watch.
Equipment alerts: 7 Warning, 1 Watch; names now from the register (e.g. P-Th-Bi649 = UPS).

**Not done:** no video analysed — the files are on Drive only; Claude's workspace cannot reach the Meta API and cannot
download 2.7 GB through the connector. Tests: 92 passed.

## 2026-10-28 10:54–11:20 — Read everything from Drive, videos included
**Author (10:54):** the app must read everything on Drive by itself; videos uploaded and linked in the Asset tab must be
taken from there (no manual download).

**Drive check (connector, metadata only):** data folder = `Operations Data` sheet + sub-folder `Video Uploaded` with
8 MP4 files (7 linked in the Asset tab, 1 not linked: `VID_20261027_153559_757.mp4`, 84 MB).

**Design:** Apps Script web app extended with a folder listing and a short-lived read-only access token; the app
downloads videos itself with the Drive API (videos are too large for Apps Script responses). Token scope is checked;
write scopes are refused. Automatic Muse video review with a daily limit. Folder import kept as a fallback.

**Files:** `apps_script/FireRiskExport.gs`, `firerisk/drive_videos.py` (new), `sources/drive_sync.py`, `video.py`,
`engine.py`, `api.py`, `web/app.js`, `scripts/setup_drive_sync.py`, tests `test_drive_videos.py`, `test_drive_sync.py`.

**Tests:** 99 passed (fake web app, tokeninfo, Drive and Muse transports; TEST bytes). **Not verified:** the real
Apps Script deployment, a real Drive download and a real Muse video analysis — they need the author's one-time setup.

## 2026-10-28 11:35–11:50 — First real Drive + automatic Muse run on the author's PC
Author deployed the Apps Script (read-only manifest) and started the dashboard. Read from the PC database:
sync 11:40:18 ok (ops sheet updated, listing 9 files / 8 videos); ai_investigations 4 (ZONE-B1, auto, prompt v3,
26.99 s, ok) and 5 (ZONE-Building, auto, v3, 21.7 s, ok); 2 videos downloaded and registered
(`VID_20261027_153559_757.mp4` recorded 27 Oct 15:35 per MP4 header, 13.5 s; `Electrical Panel - B1.mp4` 15:36,
15.7 s; neither has a zone in the register). The process stopped during the third download (.part left at 36.7 MB,
browser "Failed to fetch"); no video analysed yet because analysis waited for all downloads. Fixed in 0.6.1 (see
CHANGELOG). Compliance R-02: automatic analysis now also verified live.

## 2026-10-28 14:07–15:10 — Dashboard redesign around the building (0.7)
**Author:** attachment "Thiết kế lại Dashboard FireRisk Intelligence" (building risk map, plain English, levels of
detail, English UI, separate equipment alerts, real data only).

**Read from the author's PC before starting:** all 8 Drive videos downloaded (11:41–12:33) and analysed live by
Muse Spark through the video API (video_analyses 1–8, 89–408 s each, 5.3k–33.8k tokens, 64 observations, every
uploaded copy deleted). ZONE-B1 re-analysed automatically after each new video (ai_investigations 6–11). Sync runs
every 30 min until 12:56. Video recording times 27 Oct 15:23–15:39 from the MP4 headers.

**Audit:** 252 distinct Vietnamese strings reached the UI (records, statuses, tab names, register names, AI labels).

**Built:** `/api/building`, per-risk cards (`alert_fields.signal_card`, `PLAIN_WHY`), English glossary + Muse
translation cache (`ai/translate.py`), new Overview / Fire Safety Risks / six-section detail / gallery (`web/*`),
English labels everywhere, prompt v4. Alert-generation rules unchanged (all 102 earlier tests still pass).

**Tests:** 108 passed. Playwright on a copy of the author's real data and database (videos themselves not copied):
desktop 1440, tablet 820, phone 390 — no application errors (only the absent video files return 404 in the sandbox).
Translations could not be produced in Claude's workspace (no Meta API access); they are generated on the PC.

## 2026-10-28 14:36–15:45 — Unified, dark, briefing-first dashboard (0.8)
**Author:** two attachments: "Technology-Style Building-Centered Dashboard Redesign" (dark control-room look, one
unified building view, red risk markers on floors, new navigation, English-only as acceptance criterion) and
"Critical Design Update: AI Risk Briefing First, Minimal Cards". The reference image mentioned in the first was not
attached; the palette given in the text was used.

**Built:** `_issues` / `_map_floor` / `/api/briefing` in `api.py`; prompt v5 `risk_briefings`; translator rejects
non-English output and romanises restored names; new `web/styles.css` (dark), `web/index.html` (navigation), Overview,
briefing, SVG building, context panel, compact cards, issue drawer, Fire Safety Risks / Equipment & Systems lists,
Data & Evidence sub-navigation and English-only safety net in `web/app.js`. Rules that generate alerts unchanged.

**Checked on a copy of the author's real data and database:** Playwright visited every page and main interaction at
1440 and 390 px: 0 visible Vietnamese strings, 0 safety-net replacements, no page errors (fonts blocked in the sandbox
only). Found and fixed on the way: record IDs inside rule text and a tab-name tooltip showed Vietnamese characters.
Real map: B1 High Risk (9 issues: 5 fire-safety, 4 equipment), F2 Warning (1), F3 Watch (1), whole building Warning (2),
UPS without location. Muse Spark could not be called from Claude's workspace, so the briefing there shows the rule
explanation with "AI Analysis Unavailable"; on the PC prompt v5 re-analyses the 2 fire-risk alerts once.

**Tests:** 116 passed.

## 2026-10-28 15:12–15:40 — Show Muse results and video findings directly (0.8.1)
**Author:** "why not show Muse's analysis directly, and where did the video analysis go?" Correct: 0.8.0 used only the
new per-risk v5 briefing, so the eight real v3 analyses of B1 stayed behind a button, and the Overview had lost the
video panel. Now the real stored result is shown in the briefing (only the parts citing the risk's own records), and
all 8 analysed videos (64 observations) are on the Overview. Checked on the real-data copy: 0 Vietnamese strings, no
page errors. Note for the demo video: one transformer-room observation quotes a nameplate with the building name.

## 2026-10-28 15:46–16:40 — Overview clean-up, Muse Captain name, prompt v6, video fire-safety review v2 (0.9)
**Author:** two attachments (Overview changes 1-8; section 9-10: whole-building fire-safety review from all survey
videos).

**Checked first on the author's PC:** prompt v5 ran live at 15:06 (ZONE-B1 5 per-risk briefings, ZONE-Building 1);
231 translations stored. Drive (connector, 16:00): 11 videos in "Video Uploaded" - 3 new (VID_20261028_144806_762
0.57 GB, VID_20261028_145025_763 0.96 GB, VID_20261028_145705_765 1.69 GB, uploaded 15:41-15:46) and 2 renamed
("Electrical Panel 1 - B1", "Electricial Panel - B1"). The PC's last listing (15:25) still had 8. The 1.69 GB file is
above the 1 GiB Files API limit, so 0.9 sends a smaller copy.

**Built:** see CHANGELOG 0.9.0. The real v5 output was short and generic (e.g. "Seized or burnt motors can overheat"),
which prompt v6 addresses; v6 and video review v2 have NOT been run live yet (Claude's workspace cannot reach the Meta
API). Display rename only: no change to model ID, endpoint or payload.

**Tests:** 125 passed. Playwright on a copy of the PC's current data and database: 0 Vietnamese strings, no page
errors, alert list and analyses collapsed by default.

## 2026-10-28 20:22–20:26 — SAM 3.1 Phase 1: real connection check on the author's PC
`scripts/check_sam.py` (one frame of the B1 electrical-panel video, `VID-20261028-114134-4fa5.mp4` at 7.85 s, 1280x720,
rotation applied by ffmpeg), sent to `sam-3.1` on `POST /v1/responses` with the existing `MODEL_API_KEY`.
* `evidence/sam_check_20261028_202256.json` — phrase "electrical panel": HTTP 200, 1.99 s, `images_processed: 1`,
  empty `output_text` = valid NO-MATCH (the frame is a close-up of FAF-2 start/stop/trip controls, not a whole panel).
* `evidence/sam_check_20261028_202611.json` — phrase "push button", same frame: HTTP 200, 2.32 s, 1 line, 8 objects
  (ids 0-7), confidence 0.57-0.65 on every box and mask, `one_bit` masks all decoded, frame size in the answer
  (1280x720) equals the frame sent, 0 parser diagnostics. Overlay inspected visually: every box and mask sits on one of
  the 8 controls (2 selector switches, 2 start, 2 stop, 2 trip lamps). Format matches the docs and meta-sam-parser 0.0.6.
* Finding: the response echoes `"store": true`. Production client should send `store: false` (as the Muse video client
  does) if the SAM endpoint accepts it — to verify in Phase 2.
* Usage reports `images_processed`, tokens all 0. Private raw answers and the overlay stay in data/private/sam_check/.

## 2026-10-28 20:29–23:10 — SAM 3.1 Phases 2–6
**Author:** attachments "Integrate SAM 3.1 for Visual Evidence Localization…", "Continuously Uploaded Videos…",
"Automatically Capture and Display Video Evidence…".

**Checked first:** official pricing page read in the author's browser pane (dev.meta.ai/docs/pricing-rate-limits):
SAM 3.1 image segmentation $2.50 / 1,000 images, video $0.20 / 1,000 frames (min. 50 frames per video request),
3,000 RPM per team. The project note "64 findings" turned out to be the 64 **observations** of the first video review
(prompt v1); 5 videos had since been re-reviewed with v2. Decision: localize the findings and observations of the
latest successful analysis of each video (what the dashboard shows); superseded analyses are not localized.

**Built:** see CHANGELOG (Unreleased, phases 2–5). Live check of the production client:
`evidence/sam_client_check_20261028_203608.json`. Dry run on the PC database: 73 items, at most $0.55, database
unchanged (file timestamp identical before and after).

**Real run (author's PC, 21:09–21:22):** analysis 14 (MSB Room, 21:04) was produced live with schema v2.1 — Muse Spark
returned `segment_phrase` itself for 12 items (11 usable, 1 absence). Over the 76 items of the latest analyses:
35 located, 29 not located in the sampled frames, 12 not applicable, 0 errors, 0 not checked; 192 frame rows,
171 SAM requests (= images billed), 21 answers reused without a call, average 1.64 s per request; ≈ $0.43.
Four frames reviewed by eye (`evidence/sam_localization_run_20261028.json`): the cardboard box, the open-terminal motor
and small extinguishers at a pillar base are outlined correctly; one "network switch" frame is a SAM miss (the switch
is visible but not returned). "Not located" therefore keeps meaning "not outlined in these frames", never "absent".

**Known limitations:** some phrases chosen by Muse Spark are generic ("floor", "sign plate", "pipe"); frames of
technical rooms show name plates (keep private; check before the demo); SAM is never asked about people, but people
can appear in frames that are sent.

## 2026-10-29 08:00 — Demo privacy: blur names
**Author:** "ok làm mờ các tên gọi" (blur the names). **Checked first** (PC database copy): the building name appears
in (1) frames of technical rooms (name plates), (2) two Muse Spark observations quoting the transformer plate,
(3) record IDs and asset names using the branch prefix, (4) the dashboard header (from site_config.json).
**Built:** see CHANGELOG. Patterns are generated from the private site_config.json, so no building name is in the
repository; tests use invented TEST names. Original videos are not blurred: demo mode does not serve them at all.
**Incident:** the first push (e379dc4) had the real building name in two code comments; replaced within minutes by
a717f0e (force-push of that one commit). Main history no longer contains it; the old commit may stay reachable on
GitHub by its hash for a while.
**Also fixed:** Vietnamese tab name in the "Source not updated" line (found because the test data turned 2 days old).

## 2026-10-29 08:12–08:35 — Demo frames: real run and review
`run_mask_labels.bat` on the author's PC: 165 evidence frames, phrases "sign" and "label", 330 SAM requests
(≈ $0.83 at the official price), 0 errors; 90 copies with SAM regions, 75 with nothing found. Claude reviewed every
copy by eye from the PC: all room name plates and the transformer enclosure plate (which carries the building name)
were blurred. SAM missed 7 items, added as manual regions and rebuilt (14 more requests): two operating log sheets in
the generator room (unreadable but blurred), one dark door plate in the car park, and a handwritten tenant-store note
on the fresh-air fan panel (4 frames). Side effect noted: "label" also blurs the START/STOP legends on control panels.
Manifest marked `reviewed: true` (08:35). Original frames untouched; copies stay in data/private (git-ignored).

## 2026-10-29 08:36–08:50 — Author: "dashboard still shows 28 Oct" and wrong frame for AB-01A
Checked in the author's browser pane on the running dashboard. (1) The drawer of the AB-01A risk used an MSB video
linked by equipment to ANOTHER risk of the same zone alert (water in electrical rooms); equipment links now count
only for their own risk (d4c1c1d); verified live: AB-01A shows the open motor terminal box from the wastewater room.
(2) The "28 Oct 15:06" on the briefing was the last successful Muse Spark analysis of ZONE-B1: 8 runs since 28 Oct
16:38 had failed with invalid JSON because the answer was cut off at 8,000 completion tokens (reasoning included).
Budget raised to 32,000 (47737f5). Live re-analysis 08:49: ok in 39 s, 9,712 completion tokens (4,077 reasoning),
5 per-risk briefings, 0 invalid evidence citations - confirming the cause. Author confirmed the dashboard is correct.

## 2026-10-29 20:45–21:40 — Survey Video Findings illustration (UI only, scoped)
Changed only `web/app.js` (videoFindingsPanel + new vfScanSvg / vfTopRow / bindVfScan, one bind call, a data-vfz
attribute on the floor headings of the findings list) and appended `.vs-*` rules to `web/styles.css` (no existing rule
edited). Checked on a TEST snapshot with 3 TEST videos and a fake Meta/SAM: Overview HTML of every other section and
computed styles of map, KPI, panel and card elements identical before/after at 1440 px and 390 px; Building Risk Map
screenshot max pixel difference 1/255 (anti-aliasing); marker → floor list, number / row → finding drawer, tray chip,
keyboard and narrow re-render verified; no page errors. pytest 187 passed, 2 skipped (private snapshot absent).
Not yet viewed on the real data on the author's PC.

## 2026-10-30 16:00–16:40 — Documents updated to the live state
Author: an outside reviewer judged the project from the README (video "mock only", SAM "not integrated", 108 tests).
Checked against the PC database (copy, read only): 14/14 videos reviewed live with survey-video-v2 (34 findings),
511 SAM 3.1 frame results (299 located, 212 not located, 0 errors), 19 successful / 9 failed live investigations;
`pytest --collect-only`: 189 tests before this change. README, PROJECT_STATUS, ARCHITECTURE, TASKS,
HACKATHON_COMPLIANCE updated; true limits kept (no single photos run, no sensor telemetry, tool calling not
implemented, 9 videos without a floor). Author's rule recorded in CLAUDE.md and TASKS.md; guarded by
tests/test_docs_current.py. Suite: 189 passed, 2 skipped (191 collected).

## 2026-10-30 16:15–16:35 — Development history made checkable on GitHub
Checked the remote: refs are `main` and `baseline` (→ `b79223f`); no tags. Documents still named commit `3219f8c`
(pre-scrub hash) and a tag / branch `baseline-pre-hackathon` that does not exist on GitHub (the entry of 2026-10-27
14:39 says the marker branch was `baseline-pre-hackathon`; the published branch is `baseline`). Corrected; README now
has a "Development history" section. Commits on `main`: 47 before this change (18 on Oct 27, 15 on Oct 28, 13 on
Oct 29, 1 on Oct 30), all inside the building period. Commit identities used so far: "FireRisk Dev", "Claude",
"leilavi" (the last four, from 2026-10-29 evening, used a noreply e-mail by mistake; history not rewritten).

