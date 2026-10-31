# Project status — 2026-10-31 10:30 (UTC+7)

"Live" = run with the real Meta Model API / Google Drive on the author's PC. Numbers below were read from the PC
database on 2026-10-30.

| Area | Status | Evidence |
|---|---|---|
| Baseline recorded | Done | commit `b79223f`, branch `baseline` on GitHub |
| Rules audit / compliance checklist | Done, maintained; checklist and feature-origin matrix re-checked against the PC database 2026-10-30 20:00 | `HACKATHON_COMPLIANCE.md`, `FEATURE_ORIGIN_MATRIX.md` |
| Meta API connection | **Live** (2026-10-27) | `evidence/api_check_20261027_133317.json` |
| Real-data engine (ported + new rules, correlation, pipeline hardening) | Done | test suite |
| Muse Spark investigation (`investigation-v7`, per-risk briefings) | **Live**, automatic in the background: 21 successful runs, latest 2026-10-30 19:06 (agentic); 9 failed runs recorded (8 of them caused by the 8k completion budget, fixed 2026-10-29) | `evidence/investigation_ZONE-B1_20261027_1419_summary.json`, PC database `ai_investigations` |
| Automatic Google Drive sync (sheets, Asset tab, videos) | **Live** since 2026-10-28 11:35, every 30 min while the dashboard runs | `DEVELOPMENT_LOG.md` |
| Muse Spark survey-video review (`survey-video-v2`) | **Live**: all 14 videos reviewed, 34 findings with timestamps; uploaded copies deleted | PC database `video_analyses` |
| SAM 3.1 visual localization | **Live**: 511 frame results (299 located, 212 not located, 0 errors); background run after each new review; overlays on the dashboard | `evidence/sam_*.json`, PC database `video_finding_locations` |
| Demo mode (names hidden, blurred frames) | Done; 165 frames reviewed by eye, 7 regions added by hand | `run_dashboard_demo.bat`, `DEVELOPMENT_LOG.md` |
| Dashboard (Overview, Risk Briefing, Building Risk Map, Survey Video Findings, detail pages) | Done; checked on the author's PC 2026-10-29 | Playwright tests, live check |
| Single inspection photos (Muse Spark image input) | Implemented, **not run live** — no photos available | `firerisk/media.py` |
| Sensor telemetry (temperature / smoke / gas) | **Not available** — no feed connected; stated in the dashboard and README | — |
| Agentic investigation (Muse Spark tool calling, 7 read-only tools (7th: `get_fire_safety_supply`, added 2026-10-31; first live use pending the confirmed table), fallback to one call) | **Live**: protocol check 18:57 (PASS) and 2 automatic agentic investigations on the building data at 19:06 (3 lookups each, 0 invalid citations, no fallback; no records beyond the rule package found); 6 offline tests | `evidence/agentic_investigation_live_20261030.json`, `evidence/tool_calling_check_20261030_185751.json`, `firerisk/ai/agentic.py`, `tests/test_agentic.py` |
| Tests | 227 collected: 225 pass, 2 skipped (private snapshot absent) — 2026-10-30 | `python -m pytest -q` |
| Public GitHub repo | Published; README updated 2026-10-30 | https://github.com/leilavi/firerisk-intelligence |
| Asset register floors | 9 of 14 videos have no floor in the register (7 rows with an empty floor, 2 videos without a row) | author to fill |
| U-05 data / video rights confirmation | **Done**: written approval of the data owner's CEO, 2026-10-30, with 4 conditions; enforced in code | `DATA_AUTHORIZATION.md`, `firerisk/data_policy.py`, `tests/test_data_policy.py` |
| Technical drawings and O&M manual (3 PDFs added to Drive 2026-10-30) | **In scope** (referenced in the approved asset register; author's confirmation). Used under condition 2: originals processed on the author's computer only, never sent to an AI service; the app records them by name and does not upload them. The drawings are **scans** (author, 21:16). Step 1 ready: `run_drawing_ocr.bat` reads them with local OCR (RapidOCR on the CPU, no AI service, no network), keeps every text with its box privately and writes a review page; console shows counts only. (`run_drawing_probe.bat` reads the drawings on the author's PC (no AI, no network) and prints counts only.) Not yet used by the app | `manifest.json` → `local_only_documents` |
| Drawing OCR on the author's PC | **Run** 2026-10-30: cable/MSB drawing 3 pages, 1,703 texts (mean confidence 0.95); exit/emergency lighting drawing 8 pages, 1,634 texts (0.93) | `data/private/drawings/ocr/` (private) |
| Panel → life-safety equipment links (rule EQ-D1, 7th Muse Spark tool) | Implemented and tested with TEST data; first real draft 2026-10-31 12:17 (text only: 77 exit labels, 1 emergency-light label - emergency lights are drawn as symbols without text, so legend-based symbol search added 13:50); **real draft to be generated and checked by the author**; nothing is used until a row is confirmed | `firerisk/power_links.py`, `scripts/draft_power_links.py`, `tests/test_power_links.py`, `tests/test_draft_power_links.py` |
| Faces in demo frames | Local OpenCV face detection added to the demo blurring (SAM never asked to find people); **author to re-run** `run_mask_labels.bat` and review | `firerisk/demo.py`, `tests/test_demo.py` |
| Demo video (≤ 3 min) | Not started | — |

Deadline: Wed Nov 4, 9:00 PM ET = **Thu Nov 5, 09:00 UTC+7**.
Documentation rule (author, 2026-10-30): every change updates this file, README.md and CHANGELOG.md in the same commit.
