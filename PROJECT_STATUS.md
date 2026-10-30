# Project status — 2026-10-30 16:30 (UTC+7)

"Live" = run with the real Meta Model API / Google Drive on the author's PC. Numbers below were read from the PC
database on 2026-10-30.

| Area | Status | Evidence |
|---|---|---|
| Baseline recorded | Done | commit `b79223f`, branch `baseline` on GitHub |
| Rules audit / compliance checklist | Done, maintained | `HACKATHON_COMPLIANCE.md` |
| Meta API connection | **Live** (2026-10-27) | `evidence/api_check_20261027_133317.json` |
| Real-data engine (ported + new rules, correlation, pipeline hardening) | Done | test suite |
| Muse Spark investigation (`investigation-v6`, per-risk briefings) | **Live**, automatic in the background: 19 successful runs, latest 2026-10-29 22:10; 9 failed runs recorded (8 of them caused by the 8k completion budget, fixed 2026-10-29) | `evidence/investigation_ZONE-B1_20261027_1419_summary.json`, PC database `ai_investigations` |
| Automatic Google Drive sync (sheets, Asset tab, videos) | **Live** since 2026-10-28 11:35, every 30 min while the dashboard runs | `DEVELOPMENT_LOG.md` |
| Muse Spark survey-video review (`survey-video-v2`) | **Live**: all 14 videos reviewed, 34 findings with timestamps; uploaded copies deleted | PC database `video_analyses` |
| SAM 3.1 visual localization | **Live**: 511 frame results (299 located, 212 not located, 0 errors); background run after each new review; overlays on the dashboard | `evidence/sam_*.json`, PC database `video_finding_locations` |
| Demo mode (names hidden, blurred frames) | Done; 165 frames reviewed by eye, 7 regions added by hand | `run_dashboard_demo.bat`, `DEVELOPMENT_LOG.md` |
| Dashboard (Overview, Risk Briefing, Building Risk Map, Survey Video Findings, detail pages) | Done; checked on the author's PC 2026-10-29 | Playwright tests, live check |
| Single inspection photos (Muse Spark image input) | Implemented, **not run live** — no photos available | `firerisk/media.py` |
| Sensor telemetry (temperature / smoke / gas) | **Not available** — no feed connected; stated in the dashboard and README | — |
| Agentic investigation (Muse Spark tool calling, 6 read-only tools, fallback to one call) | **Implemented 2026-10-30**, 6 offline tests (fake transport); **live check pending** on the PC | `firerisk/ai/agentic.py`, `tests/test_agentic.py`, `scripts/check_tool_calling.py` |
| Tests | 197 collected: 195 pass, 2 skipped (private snapshot absent) — 2026-10-30 | `python -m pytest -q` |
| Public GitHub repo | Published; README updated 2026-10-30 | https://github.com/leilavi/firerisk-intelligence |
| Asset register floors | 9 of 14 videos have no floor in the register (7 rows with an empty floor, 2 videos without a row) | author to fill |
| U-05 data / video rights confirmation | **Pending** (author) | `HACKATHON_COMPLIANCE.md` |
| Demo video (≤ 3 min) | Not started | — |

Deadline: Wed Nov 4, 9:00 PM ET = **Thu Nov 5, 09:00 UTC+7**.
Documentation rule (author, 2026-10-30): every change updates this file, README.md and CHANGELOG.md in the same commit.
