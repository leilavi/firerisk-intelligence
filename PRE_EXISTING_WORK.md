# Pre-Existing Work (before the Meta Global AI Developer Hackathon)

Per the Participant Guide §3, kickoff was **Mon, Oct 26, 2026** and the **building period is Oct 27 – Nov 4, 2026 (ET)**. Everything listed here existed **before** that date and must not be presented as Hackathon work.

## 1. What existed

**"skill cảnh báo rủi ro" (risk-alert skill), version 2.2** — a Claude Agent Skill (a single Markdown instruction file, `SKILL.md`, ~600 lines, Vietnamese) used by the author to monitor building operations at one commercial building ([Building], operated under the [Operator] brand).

It is **a prompt/specification, not an application**. It contains **no source code**, no Meta model integration, and no standalone UI. It runs only inside Claude, using Claude's Google Drive and Gmail connectors.

### Functional scope of the original skill (as specified in the file)

| Area | What the skill instructs Claude to do |
|---|---|
| Data sources | Read fixed Google Sheets / Drive files: daily electricity & water meter readings, asset damage/repair log, incident & construction log, generator diesel log, electricity/water cost files, parking revenue, vehicle counts |
| Data quality | Detect missing days, duplicates, meter rollbacks, row-limit export truncation, test records |
| Anomaly detection | Per-meter daily consumption; spike/drop detection using median + MAD (28-day baseline) with minimum-delta thresholds per meter |
| Cross-checking | Compare electricity changes with vehicle counts, construction, generator runs; EVN vs MSB meter comparison to separate real load changes from reading errors |
| Classification | 4 conclusion labels (Reasonable variation / Anomaly to monitor / Evidence-based risk / Insufficient data); 5 severity levels (Normal → Emergency) based on consequence and time remaining |
| Alert content | 14 mandatory fields per alert (problem, evidence, baseline, possible causes, basis per cause, consequence, risk chain, trigger, urgency, prevention, deadline, closure condition, confidence, source) |
| Forecasting | Qualitative early-warning signals; explicitly forbids invented probabilities or failure dates |
| Outputs | Vietnamese HTML dashboard built from a fixed template; reports saved to Drive with timestamps; e-mail for High/Emergency alerts; alert log sheet with stable IDs, dedup, escalation and reminders |

### Scope boundaries of the original skill (verified by reading the file)

- Domain: **general building operations** (energy, water, diesel, parking, equipment). Fire safety appears only indirectly (PCCC is listed as a "critical system"; generator battery example).
- No dedicated fire/explosion risk model, no event-timeline object, no explicit evidence graph, no image/video analysis.
- No code: all logic is natural-language instructions executed by Claude.
- No Meta model is used anywhere.

## 2. Evidence of pre-existence

| Evidence | Value | How verified |
|---|---|---|
| Google Drive file `skill cảnh báo rui ro` (folder "Skill") | created 2026-10-08T07:09:40Z, **last modified 2026-10-15T02:28:02Z**, 73,071 bytes | Drive API metadata read on 2026-10-27 |
| Version header inside the file | "Phiên bản: 2.2 (08/10/2026 14:10 GMT+7)" | Read from file |
| Installed skill copy used for this audit | 73,080 bytes, SHA-256 `26ec7c375f9cee72d9f00c15627f7eb7e4ee90426458156df9beedf237b894ec` | `sha256sum` on 2026-10-27 |
| Published report template `mau_bao_cao_canh_bao_rui_ro.html` | created/modified 2026-10-08T07:04:21Z | Drive API metadata |

Note: the Drive copy and the installed copy differ by 9 bytes. The exact difference has not yet been inspected (follow-up task).

## 3. Copy kept in this repository

`baseline/skill-canh-bao-rui-ro_v2.2_REDACTED.md` — the original text with personal e-mail, Google Drive file IDs and Gmail message IDs replaced by placeholders. **No other change was made.** The unredacted original remains in the author's private Google Drive.

## 4. Pre-existing data (not published)

The skill reads real operational data of a private building. That data is **not** part of this repository and will not be published. Hackathon demos use synthetic data only.
