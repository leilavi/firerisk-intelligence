# Changelog

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
