# Hackathon Compliance Checklist

**Official source used:** `Rule in Meta hackathon.txt` — "Meta Global AI Developer Hackathon Participant Guide" (attached to the Claude Project; section numbers below refer to that guide).
**Not available:** any separate legal Terms & Conditions / Official Rules document. If one exists on the Cerebral Valley platform, it has not been reviewed yet (see U-01).
**Last updated:** 2026-10-27 12:10 (UTC+7)

Legend — Type: **M** mandatory · **C** conditional · **A** advisory / scoring. Basis: **EXPLICIT** (stated in the guide) · **INTERP** (our reading) · **DECISION** (our own choice, not a rule).

## 1. Requirements

| ID | Requirement | Source | Type | Basis | Project deliverable | Verification method | Status | Notes / follow-up |
|---|---|---|---|---|---|---|---|---|
| R-01 | Project must build toward one of two problem statements ("Build for Your World" or "Push the Frontier") | §1 | M | EXPLICIT | Positioning in README and video | Reviewer reads README + video | IN PROGRESS | Planned fit: **Build for Your World** (author's own building-operations domain). Stage One is pass/fail on theme fit (§8) |
| R-02 | Project must incorporate Meta's models (Muse Spark series, Muse Wonder, Muse Image, Muse Voice Transcribe, SAM 3.1 via Meta Model API; or open weights Muse Glimmer / Muse Spark Open; Muse Code agent) | §1, §8 Stage One | M | EXPLICIT | Muse Spark as reasoning engine; SAM 3.1 optional | Real API call logs (no secrets) + code | NOT STARTED | Blocked on API key (see B-01) |
| R-03 | Repository must be public | §4 | M | EXPLICIT | GitHub public repo | Open repo URL in a logged-out browser | NOT STARTED | Repo exists locally only |
| R-04 | Max 4 team members; solo allowed | §4 | M | EXPLICIT | Submission form | Check form | IN PROGRESS | Author decision 2026-10-27: **solo** (1 member). Verify on submission form |
| R-05 | Demo must only highlight features/code built during the Hackathon; judges must clearly identify what was created; failure ⇒ disqualification at judges' discretion | §4 | M | EXPLICIT | Video script, `FEATURE_ORIGIN_MATRIX.md`, README "What is new" | Script review against matrix | NOT STARTED | **Highest-risk rule.** Video must show only NEW items from the matrix |
| R-06 | New work only: what is presented must be built during the event and this must be clear in the submission | §4 | M | EXPLICIT | Git history from 2026-10-27, `DEVELOPMENT_LOG.md`, `PRE_EXISTING_WORK.md` | Commit dates ≥ build period; log review | IN PROGRESS | Baseline commit `3219f8c` tagged `baseline-pre-hackathon` |
| R-07 | "Startups may build on existing products or codebases" but must identify what is new | §4 | C | EXPLICIT (for startups) | Disclosure docs | — | BLOCKED | Author entered the **Indie** track, so this sentence does not explicitly cover us → **U-02 must be answered by organizers** |
| R-08 | Not violate legal, ethical or platform policies; no code/data/assets without rights | §4 | M | EXPLICIT | Synthetic demo data; license audit of dependencies | Dependency license list; data provenance note | NOT STARTED | Real building data must **not** be published (DECISION) |
| R-09 | Avoid generic "anti-projects" (medical advice, basic RAG, simple image analyzers, education chatbots, job screeners, nutrition, personality, sports, political/war) | §4 | A | EXPLICIT (list "not exhaustive") | Product scope | Scope review | VERIFIED (scope) | Fire-risk root-cause analysis is not on the list. Keep vision use as supporting evidence so it is not a "simple image analyzer" |
| R-10 | Submit by **Wed Nov 4, 9:00 PM ET** via the CV platform; late submissions not considered | §3, §7 | M | EXPLICIT | Submission | Submission confirmation | NOT STARTED | = **Thu Nov 5, 09:00 (UTC+7, Hanoi)** — INTERP: US DST ends Nov 1, so ET = EST (UTC−5). Internal target: Nov 4, 18:00 UTC+7 |
| R-11 | One submission per team; one Representative submits | §7 | M | EXPLICIT | Submission form | — | NOT STARTED | |
| R-12 | Three-minute demo video highlighting features built during the Hackathon; used as a primary judging artifact | §7 | M | EXPLICIT | Demo video | Measure duration; script check vs R-05 | NOT STARTED | INTERP: treat 3:00 as a hard maximum |
| R-13 | Repo publicly accessible, video link accessible, all contributors listed | §7 | M | EXPLICIT | Submission form | Logged-out access test | NOT STARTED | |
| R-14 | Code and live product are judged alongside the video | §7 | A | EXPLICIT | Runnable app + README | Fresh-clone install test | NOT STARTED | README is not named as mandatory; it is needed for judges to run the code (INTERP) |
| R-15 | Claim $150 Meta Model API credits individually by Nov 4, 9:00 PM ET; credit card required | §5 | A | EXPLICIT | — | Billing page shows credits | IN PROGRESS | Author reports credits claimed and API key created (2026-10-27 12:01). Will be VERIFIED by a successful real API call (evidence/api_check_*.json) |
| R-16 | Judging rubric: Impact 30%, Use of Meta AI tooling 25%, Technical depth 20%, Demo 25% | §8 | A | EXPLICIT | Whole product | — | NOT STARTED | Mapping in §3 below |
| R-17 | Optional bonus prizes (Most Viral on X by Nov 8, Best Open-Weight build, Community Vote, Best Agentic, Best Creative) | §9 | C | EXPLICIT | Optional | — | NOT APPLICABLE (for now) | "Best Agentic Use-Case" fits naturally; open-weight requires Muse Glimmer / Muse Spark Open on own or partner inference |
| R-18 | Track: Indie Developer or Startups | §9 | M | INTERP (must belong to one track) | Submission form | — | IN PROGRESS | Author decision 2026-10-27: **Indie Developer track**. Verify on submission form |

### Items NOT stated in the guide (our own measures — DECISION)

Git commit history, `DEVELOPMENT_LOG.md`, `CHANGELOG.md`, open-source license, `.env.example`, tests. None of these is listed as a requirement in the guide. We maintain them because they make R-05/R-06 verifiable and the code runnable (R-14).

## 2. Uncertainties to confirm with organizers (Discord `#questions`)

| ID | Question | Why it matters |
|---|---|---|
| U-01 | Is there a separate Official Rules / Terms document beyond the Participant Guide? | Licensing, eligibility and IP terms are not in the guide |
| U-02 | Can an **Indie** participant build on their own pre-existing non-code work (a Claude prompt/skill written Oct 8–15) if it is disclosed and all code is written during the event? | §4 explicitly allows reuse only for "Startups"; disqualification risk |
| U-03 | Is 3 minutes a hard maximum for the video? | R-12 |
| U-04 | Is any open-source license required for the public repo? | Not stated |

## 3. Judging criteria → product mapping (prioritisation)

| Criterion (weight) | What FireRisk must show |
|---|---|
| Impact (30%) | Real problem: isolated building alarms hide combined fire-risk patterns; decision-support for building managers |
| Use of Meta AI tooling (25%) | Muse Spark doing real cross-source reasoning with structured output (JSON schema), tool calling over the evidence store, visible in the UI; SAM 3.1 adding segmented visual evidence; go beyond a single chat call |
| Technical depth (20%) | Deterministic rule engine + evidence correlation + LLM reasoning, with traceability, fallback when AI fails, tests |
| Demo (25%) | Live end-to-end run: "conventional alert" vs "FireRisk investigation" side by side, within 3 minutes |

## 4. Blockers

| ID | Blocker | Owner |
|---|---|---|
| B-01 | ~~No API key~~ — resolved per author 2026-10-27; awaiting first real call result | Author |
| B-02 | Claude's cloud workspace cannot reach `api.meta.ai` (HTTP CONNECT 403, verified 2026-10-27). Live API tests must run on the author's computer or another allowed host | Claude + Author |
| B-03 | ~~Track/team undecided~~ — resolved: Indie, solo | — |
| B-04 | U-02 unanswered: reuse of pre-existing skill by an Indie participant | Author (ask on Discord) |
