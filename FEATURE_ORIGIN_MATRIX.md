# Feature Origin Matrix

Status as of **2026-10-27 16:20 (UTC+7)**. A row is "Implemented" only with verification evidence.

Origin: **Existing** = in the pre-existing skill v2.2 (natural-language instructions only, no code) ·
**Modified** = existing rule re-implemented in code during the Hackathon (marked `ORIGIN: PORTED` in code) ·
**New** = not present in the baseline (marked `ORIGIN: NEW`).

Direction change 2026-10-27 13:48 (author): use the **real operational data** instead of a synthetic scenario;
add real photos/video when provided.

| Component or Feature | Current Status | Origin | Recommended Action | Verification Evidence |
|---|---|---|---|---|
| Risk-alert skill v2.2 (SKILL.md) | Unchanged; still used inside Claude | Existing | Keep as baseline | `baseline/`, `PRE_EXISTING_WORK.md`, tag `baseline-pre-hackathon` |
| Claude-only Drive/Gmail workflow, Vietnamese HTML report, e-mail alerts | Unchanged, not part of this app | Existing | Keep running separately | Skill §10–14 |
| Real-data loaders with row-level source references (`firerisk/sources`) | Implemented | New | Add live Google Drive sync | `test_real_snapshot.py`: every meter row loaded and traceable; 1,254 evidence records from real snapshot |
| Scope filter and test-record flags (`rules/scope.py`) | Implemented | Modified (skill §2.3) | — | `test_rules_ported.py` (2 tests) |
| Daily consumption, gaps, decreasing readings (`rules/meters.py`) | Implemented | Modified (skill Stage 2B) | — | 4 tests |
| Median/MAD spike & drop detection, episodes, EVN/MSB cross-check, labels | Implemented | Modified (skill §5A) | — | 5 tests; real run reproduces skill observations (e.g. XLNT meter drop 21/10 & 23/10) |
| Severity scale and "consequence, not % change" principle | Implemented as vocabulary | Modified (skill §7) | — | `config.py`, `RISK_RULES.md` |
| Fire-safety hazard tagging of Vietnamese records (`hazards/tagging.py`) | Implemented | New | Extend vocabulary as new records appear | `test_hazards_new.py` (3 tagging tests) |
| Hazard pathway rules R1–R9 (`hazards/pathways.py`) | Implemented | New | Review thresholds with the building's fire-safety officer | 5 rule tests; documented in `RISK_RULES.md` |
| Context / contradicting evidence (checklists, scheduled generator runs) | Implemented | New | — | Attached to signals; shown in dashboard |
| Cross-source evidence links with reasons (`correlation.py`) | Implemented | New | Tune link noise | `test_links_explain_their_reason_and_meter_dependency`; all link IDs resolve (`test_real_snapshot.py`) |
| Zone-level alert aggregation + compound-risk rule | Implemented | New | — | `test_compound_rule_raises_one_level_but_never_to_emergency` |
| Event timeline per alert | Implemented | New | — | Dashboard screenshot check |
| Personal-data pseudonymisation before AI calls (`ai/redact.py`) + opaque evidence-ID aliases (v2) | Implemented | New | — | Offline tests: no e-mails/names/real record IDs in payload; aliases mapped back |
| Meta Muse Spark client (`ai/muse.py`) | Implemented; connection verified live | New | — | Real call PASS `evidence/api_check_20261027_133317.json`; offline error-handling tests (401/429/400/invalid JSON/not configured) |
| Muse Spark root-cause investigation with evidence-ID validation (`ai/investigation.py`) | Implemented; **live run verified** 2026-10-27 14:19 | New | Review output quality over more runs | Live run on author's PC: 12 facts, 5 hypotheses, 3 escalation steps, 7 actions, 0 invalid citations (`evidence/investigation_ZONE-B1_20261027_1419_summary.json`); offline tests |
| SQLite store: runs, alert history, verification status, AI results (`store.py`) | Implemented | New (replaces skill's Sheet Alert_Log for this app) | — | API smoke test (status change saved) |
| Backend API (`api.py`) | Implemented | New | — | API smoke test on real snapshot |
| Dashboard: overview, alerts, alert detail (basis, verification, AI panel, signals, timeline, meter charts, links, evidence table, media), event history, data sources, media | Implemented | New | Live test on author's PC | Playwright run: no console errors; screenshots desktop + mobile |
| Evidence drawer with source file / tab / row / record ID | Implemented | New | — | Playwright screenshot |
| Status classes (open / degraded / paused / in progress / resolved / pass / unknown) with unmapped values flagged | Implemented | New | Map new status words as they appear | `test_unknown_status_is_not_treated_as_resolved`; real data: 2 unmapped-before values now mapped |
| Duplicate record IDs kept and flagged; invalid meter values flagged (not dropped); missing timestamps flagged | Implemented | New | — | `test_pipeline.py` (3 tests) |
| Generator duration 00:00 recomputed from start/end (skill §2.4 check) | Implemented | Modified (skill §2.4) | — | 6 real records corrected; test |
| Overdue repairs, stale "Đang thi công", future timestamps | Implemented | Modified (skill §2.4, §10.4 ideas) | — | test; real: 1 overdue, 1 possibly stale |
| Missing / corrupt workbook or tab → reported, analysis continues | Implemented | New | — | `test_missing_tab_does_not_stop_analysis`, `test_missing_and_corrupt_files_are_reported` |
| Late-arriving records detected across runs | Implemented | New | — | `test_late_arrival_detected_across_runs` |
| Exactly 4 conclusion labels for meter episodes | Implemented (corrected) | Modified (skill §5) | — | 4 tests; fifth label removed |
| Meter signal levels per skill §5A.8 | Implemented (corrected) | Modified (skill §5A.8) | — | `test_meter_severity_mapping_skill_5a8` |
| 14 alert fields per signal (skill §8) + short headline, assessment class, unknowns | Implemented | Modified (skill §8 structure) + New content | Review texts with site staff | `test_every_alert_has_the_14_fields` |
| Human-only "Confirmed on site" verification state; first-detection time | Implemented | New | — | `test_status_change_and_confirmed_state` |
| Dashboard v2: light theme, risk colours + icons + words, building zone panel, priority list, weekly fault chart, equipment page, 6-question alert detail, meter windows ±7 days, maintenance history, origin labels (source / derived / rule / AI / test) | Implemented | New | Live check on author's PC | Playwright desktop + tablet, no app errors (Google Fonts blocked in Claude's sandbox only) |
| Media inventory (photo references found in logs; local files matched by name) | Implemented | New | Connect the real photo/video folder | 1,006 photo references found; 0 files available yet |
| Video frame sampling (ffmpeg) | Implemented, not run | New | Test when a survey video is provided | — |
| Muse Spark image description (`media.describe_image`) | Implemented, **not run** | New | Run on first real photos | Request format from official docs |
| SAM 3.1 segmentation | **Not implemented** | New (planned) | Read official output-format docs, then implement | Model listed for the key |
| Live Google Drive sync (without Claude) | **Not implemented**; snapshot taken via Claude's Drive connector | New (planned) | OAuth desktop client or export folder | — |

## Verified Meta Model API facts
| Fact | Value | Source |
|---|---|---|
| Base URL / auth | `https://api.meta.ai/v1`, `Authorization: Bearer`, env `MODEL_API_KEY` | quickstart (docs) + real call |
| Models available to the author's key | `muse-image-1.0`, `muse-spark-1.1`, `muse-spark-1.2`, `muse-spark-1.2-contributor`, `muse-spark-1.3`, `muse-spark-1.3-contributor`, `muse-voice-transcribe-1.0`, `muse-wonder-1.0`, `sam-3.1` | real call 2026-10-27 13:33 |
| Structured output `json_schema` + `strict: true` on `muse-spark-1.3` | Works (HTTP 200, schema-valid, 2.7 s) | real call |
| Image input (Chat Completions) | `{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,…"}}`, ≤50 images, ≤50 MB each | docs/image-understanding |
| SAM 3.1 | `sam-3.1` on `/v1/responses`, noun-phrase or point/box prompts, image or video; special-token output parsed by `@meta-sam/parser` | docs/sam/overview (output parsing not yet verified) |
| Not used on purpose | `*-contributor` models (Meta may use prompts for training) | promptfoo docs; privacy decision |
