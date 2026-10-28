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
