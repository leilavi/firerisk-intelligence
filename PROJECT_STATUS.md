# Project status — 2026-10-28 23:10 (UTC+7)

| Area | Status | Evidence |
|---|---|---|
| Baseline recorded | Done | tag `baseline-pre-hackathon` |
| Rules audit / compliance checklist | Done, maintained | `HACKATHON_COMPLIANCE.md` |
| Meta API connection | Verified live | `evidence/api_check_20261027_133317.json` |
| Real-data engine (ported + new rules, correlation, pipeline hardening, 14 fields) | Done | 87 tests passing |
| Muse Spark investigation | **Live run verified** on author's PC (14:19) | `evidence/investigation_ZONE-B1_20261027_1419_summary.json` |
| Dashboard v2 + backend | Built; browser-tested (desktop, tablet) in Claude's workspace; live check on PC pending | Playwright |
| Two alert systems (equipment / fire risk) + Overview | Done; browser-tested on a copy of real data | `test_two_systems.py`, Playwright |
| Automatic Muse Spark analysis | Built; mock-tested; live automatic run pending on PC | `ai/auto.py` |
| Survey videos | Architecture built per official docs; **no real video, never sent to Meta** | `firerisk/video.py`, `test_video.py` |
| Photos | Prepared; **no real photos yet** | `firerisk/media.py` |
| SAM 3.1 visual localization | **Live verified**: API, client, real run over 76 items (35 located, 29 not located, 12 not applicable, 0 errors, 171 images ≈ $0.43); background localization of new analyses built and tested; dashboard overlay Playwright-tested 1440/390; live dashboard check on PC pending | `evidence/sam_*.json`, `tests/test_sam.py`, `tests/test_localize*.py` |
| Automatic Drive sync | Built and mock-tested; author's one-time setup + first real run pending | `tests/test_drive_sync.py` |
| Dashboard 0.8 (dark, unified building view, AI Risk Briefing, English-only) | Built; Playwright-checked on a copy of real data (0 Vietnamese strings visible); live check on PC pending | `test_unified_briefing.py` |
| Muse Spark video review | **Live verified** on PC: 8 videos, 64 observations | PC database `video_analyses` 1–8 |
| Public GitHub repo | **Published** | https://github.com/leilavi/firerisk-intelligence |
| Demo video | Not started | — |

Deadline: Wed Nov 4, 9:00 PM ET = **Thu Nov 5, 09:00 UTC+7**.
