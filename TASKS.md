# Tasks

## Next
- [x] Author: install + dashboard + first live Muse investigation (2026-10-27 14:19).
- [x] Claude: read investigation from PC DB, saved evidence (public summary / private full), added opaque evidence-ID aliases (prompt v2).
- [x] Author: one-time Drive setup (`setup_drive_sync.bat`, incl. the read-only appsscript.json) — then the app reads the sheet, the Asset tab and all 8 videos by itself. Set the zone of the 3 videos the register does not place.
- [ ] Author: provide daily guard photos (Drive folder).
- [x] Author: open the new dashboard on the PC; first automatic Muse run (prompt v3) happens at start-up — Claude reviews it from the PC database.
- [x] Claude: two alert systems, automatic Muse analysis, survey-video architecture (0.4.0).
- [x] Claude: SAM 3.1 — official docs, connection check, client + parser, phrases, localization tables, backfill, background processing, dashboard overlay (2026-10-28).
- [x] Author: SAM backfill run on the PC (21:09–21:22): 171 SAM requests, 0 errors.
- [x] Author: restart `run_dashboard`; Claude checks the evidence frames on the live dashboard (2026-10-29).
- [x] Claude: `scripts/mask_labels_for_demo.py` + demo mode (2026-10-29).
- [x] Author: run `run_mask_labels.bat`, check review.html with Claude (2026-10-29, all 165 frames reviewed).
- [ ] Author: record the demo with `run_dashboard_demo.bat`.
- [x] Claude: automatic Google Drive sync (Apps Script web app; chosen over an OAuth desktop client because it needs no Google Cloud project and its access does not expire after 7 days in testing mode).
- [ ] ~~Postponed (author, 16:53)~~ resumed 2026-10-28 10:54: author will add new data files first. Then: Claude extends the script to read a Drive folder (and parsers for the new files); author runs run `setup_drive_sync.bat` once (deploy the script in own Google account), then confirm the first real sync.
- [ ] Author: confirm U-05 (authority to process data / send redacted excerpts to Meta API).

- [x] Claude: unified dark dashboard with AI Risk Briefing and floor markers (0.8).
- [x] Author: restart `run_dashboard` once; Claude then checks the v5 briefings and the record translations from the PC database.

- [x] Claude: Survey Video Findings illustration (2026-10-29) and "room · floor not recorded" labels.
- [x] Claude: README / status documents brought up to date with the live state (2026-10-30).
- [ ] Author: fill the floor of asset rows P-Th-Bi650, -652, -658, -660, -661, -662, -663 (and check that "Floor 4.mp4" is linked to the row named "Floor 3").

- [x] Claude: agentic investigation with Muse Spark tool calling + fallback + dashboard trace (2026-10-30, offline-tested).
- [x] Author: run `run_tool_calling_check.bat` (PASS 2026-10-30 18:57).
- [x] Author: restart `run_dashboard` (19:05; 2 agentic investigations ok at 19:06) so the alerts are re-analysed with tool calling; Claude checks the result from the PC database.

## Rule (author, 2026-10-30)
Every change or new feature updates README.md, PROJECT_STATUS.md, CHANGELOG.md and, when affected, ARCHITECTURE.md,
HACKATHON_COMPLIANCE.md and FEATURE_ORIGIN_MATRIX.md **in the same commit**. Never submit with outdated content.

## Later
- [x] Public GitHub repo created and history pushed (2026-10-27), checked for data/secrets.
- [ ] Demo script (≤ 3 min) showing only new work; record video without staff names.
- [ ] Final compliance review.
