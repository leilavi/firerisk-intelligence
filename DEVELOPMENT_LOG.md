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
