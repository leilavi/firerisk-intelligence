# Feature Origin Matrix

Status as of **2026-10-27 12:00 (UTC+7)** — initial audit. Nothing in the "New" rows has been implemented yet. A row moves to "Implemented" only with verification evidence (commit hash, test result, API log).

Origin: **Existing** = specified in the pre-existing skill (logic exists only as natural-language instructions, no code) · **Modified** = existing idea re-implemented/extended in code during the Hackathon · **New** = not present in the baseline.

| Component or Feature | Current Status | Origin: Existing / Modified / New | Recommended Action | Verification Evidence |
|---|---|---|---|---|
| Risk-alert skill v2.2 (SKILL.md, Vietnamese prompt) | Exists, works inside Claude only; no code | Existing | Keep unchanged as baseline; use as specification reference | `baseline/` redacted copy; Drive modifiedTime 2026-10-15; SHA-256 in `PRE_EXISTING_WORK.md` |
| Google Drive / Sheets data reading (real building data) | Exists as instructions for Claude connectors | Existing | Do **not** reuse in the public app (private data, Claude-only connectors). Replace with file-based loaders for synthetic data | Skill §2 |
| Data-quality checks (missing days, duplicates, rollback, row-limit truncation) | Specified in prose | Modified | Re-implement the generic checks in Python with tests | Skill §4 Stage 2/2B |
| Spike/drop detection (median + MAD, 28-day baseline, min-delta) | Specified in prose | Modified | Port to a deterministic, tested Python module; generalise from water/electricity meters to temperature, load, gas | Skill §5A |
| 4 conclusion labels + 5 severity levels | Specified in prose | Modified | Reuse the taxonomy in the rule engine; add fire-specific escalation states (observed anomaly / elevated risk / plausible pathway / confirmed alarm) | Skill §5, §7 |
| 14-field alert structure | Specified in prose | Modified | Convert into a JSON schema used for Muse Spark structured output | Skill §8 |
| Rule: no invented probabilities / dates; facts vs hypotheses labels (DL/BT/GT/DB/KN) | Specified in prose | Modified | Enforce in schema (`claim_type` field) and in validation code | Skill §5, §9 |
| HTML report template (Vietnamese, Chart.js) | Exists on Drive | Existing | Not reused; new English dashboard | Drive metadata 2026-10-08 |
| E-mail alerts, Alert_Log, reminders via Gmail/Drive | Specified for Claude connectors | Existing | Out of MVP scope; at most an alert-status field in the app | Skill §10 |
| Fire-safety-specific data model (fire alarm panel events, smoke/heat/gas sensors, HVAC/ventilation status, suppression system status) | Not present | New | Define canonical schema + synthetic dataset | — |
| Synthetic demo dataset (telemetry, maintenance, events, image) | Not present | New | Generate reproducibly with a seeded script; label as synthetic | — |
| Cross-source evidence correlation (same asset / zone / time window / system dependency) | Not present (baseline only compares meters with vehicle counts) | New | Core module; explicit, testable linking rules with a reason per link | — |
| Event timeline construction | Not present | New | Build ordered, source-linked timeline per incident cluster | — |
| Root-cause investigation with evidence chain, alternatives, missing information | Partly specified as prose ("possible causes + basis") | New (code + Muse) | Muse Spark reasoning over the correlated evidence package; output validated against schema; every claim cites evidence IDs | — |
| Fire/explosion escalation-pathway assessment | Not present | New | Rule-based escalation states + Muse explanation; no numeric probabilities | — |
| Response recommendations with urgency | Specified generally | Modified | Generate per pathway; deterministic urgency floor from rules | — |
| Meta Model API client (Muse Spark, `muse-spark-1.3`) | Not present | New | OpenAI-compatible client, timeouts, retries, schema validation, offline mode clearly labelled | Docs verified 2026-10-27 (see below) |
| SAM 3.1 visual evidence (`sam-3.1`) | Not present | New (optional, Priority 6) | Segment e.g. cable tray / panel / blocked vent in a prepared image; attach as evidence item | — |
| Muse Spark image understanding | Not present | New (optional) | Describe segmented region as supporting evidence | — |
| Evidence traceability (claim → evidence → source row) | Partly specified (source field) | Modified | Evidence IDs end to end; UI drill-down | — |
| AI-failure fallback (deterministic alert still produced) | Not present | New | Rule engine output always shown; AI section marked unavailable | — |
| Dashboard: building/zone-level fire-risk alert + evidence detail screen | Not present (old dashboard is operations, Vietnamese) | New | English web UI | — |
| Automated tests | Not present | New | pytest for loaders, rules, correlation, schema validation, API error handling | — |

## Verified Meta Model API facts (official docs, read 2026-10-27)

| Fact | Value | Source |
|---|---|---|
| Base URL | `https://api.meta.ai/v1` (OpenAI-compatible) | dev.meta.ai/docs/quickstart |
| Auth | `Authorization: Bearer <key>`; docs use env var `MODEL_API_KEY` | quickstart |
| Endpoints | `/v1/chat/completions`, `/v1/responses` | protocols/chat-completions |
| Reasoning model ID | `muse-spark-1.3` (also `muse-spark-1.1`) | quickstart |
| Structured output | `response_format: {type: "json_schema", json_schema: {...}}`, optional `strict` | structured-output |
| Unsupported on chat completions | `stop`, `logprobs`, `n>1`, `frequency/presence_penalty`, `reasoning_effort: "none"` | protocols/chat-completions |
| Errors | 400 invalid/too long, 429 rate limit (backoff), 504 long non-streaming | protocols/chat-completions |
| SAM model ID | `sam-3.1` via `/v1/responses`; text noun-phrase or point/box prompt; image or video; output is special-token text parsed by `@meta-sam/parser` | sam/overview |
| Multimodal input for 1.3 | text, image, video, PDF (reported by a third-party integration page; to be confirmed on official model page) | promptfoo docs — **unverified on official page** |
| Pricing / rate limits | Not yet read | — |
