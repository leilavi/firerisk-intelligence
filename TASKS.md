# Tasks

## Next
- [x] Author: install + dashboard + first live Muse investigation (2026-10-27 14:19).
- [x] Claude: read investigation from PC DB, saved evidence (public summary / private full), added opaque evidence-ID aliases (prompt v2).
- [ ] Author: one-time Drive setup (`setup_drive_sync.bat`, incl. the read-only appsscript.json) — then the app reads the sheet, the Asset tab and all 8 videos by itself. Set the zone of the 3 videos the register does not place.
- [ ] Author: provide daily guard photos (Drive folder).
- [ ] Author: open the new dashboard on the PC; first automatic Muse run (prompt v3) happens at start-up — Claude reviews it from the PC database.
- [x] Claude: two alert systems, automatic Muse analysis, survey-video architecture (0.4.0).
- [x] Claude: SAM 3.1 — official docs, connection check, client + parser, phrases, localization tables, backfill, background processing, dashboard overlay (2026-10-28).
- [x] Author: SAM backfill run on the PC (21:09–21:22): 171 SAM requests, 0 errors.
- [ ] Author: restart `run_dashboard`; Claude checks the evidence frames on the live dashboard.
- [x] Claude: `scripts/mask_labels_for_demo.py` + demo mode (2026-10-29).
- [ ] Author: run `run_mask_labels.bat`, check review.html with Claude, then record the demo with `run_dashboard_demo.bat`.
- [x] Claude: automatic Google Drive sync (Apps Script web app; chosen over an OAuth desktop client because it needs no Google Cloud project and its access does not expire after 7 days in testing mode).
- [ ] ~~Postponed (author, 16:53)~~ resumed 2026-10-28 10:54: author will add new data files first. Then: Claude extends the script to read a Drive folder (and parsers for the new files); author runs run `setup_drive_sync.bat` once (deploy the script in own Google account), then confirm the first real sync.
- [ ] Author: confirm U-05 (authority to process data / send redacted excerpts to Meta API).

- [x] Claude: unified dark dashboard with AI Risk Briefing and floor markers (0.8).
- [ ] Author: restart `run_dashboard` once; Claude then checks the v5 briefings and the record translations from the PC database.

## Later
- [x] Public GitHub repo created and history pushed (2026-10-27), checked for data/secrets.
- [ ] Demo script (≤ 3 min) showing only new work; record video without staff names.
- [ ] Final compliance review.
