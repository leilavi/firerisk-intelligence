# FireRisk Intelligence — Storyboard (final, v5)
16:9 · 1920×1080 · 30 fps · 2:59 · narration Kokoro af_heart · original synthesised music

## 1. The butterfly effect · 0:00–0:20

**Narration:** Water in an electrical room. Weak generator batteries. A broken announcement system. A faulty heat detector. Four separate incidents. But they all lead to the same place: the people evacuating. This is the butterfly effect.

**Visuals:** Black title 'A BUILDING DOESN'T FAIL ALL AT ONCE.' -> two real blurred survey frames (MSB room 00:16, generator room 00:31) with slow push-in -> four record cards (08 Oct water, 29 Sep batteries, 15 Sep announcement system, 08 & 19 Oct heat detector) -> each card links to one EXIT 'people evacuating' (not to each other) -> 'THE BUTTERFLY EFFECT'.

## 2. FireRisk Intelligence · 0:20–0:37

**Narration:** This is FireRisk Intelligence, built during this hackathon on Meta Muse Spark and SAM 3.1. It connects what a building already records: logs, meters, assets and survey videos.

**Visuals:** Real Overview, full screen -> zoom on Building Risk Map (B1 red marker) -> zoom on KPI row ('Latest analysis / Drive synced'). No tab change.

## 3. Rule Engine · 0:37–0:58

**Narration:** First, a rule engine links the records through known relationships. Grid power and the backup generator meet at a single transfer switch. From there, power reaches all six floors, and every floor's emergency lights.

**Visuals:** Overview 'Chain of effects across the building' (RULE lines) -> click 'See each step' (tab change 1/3) -> real chain: ATS - one for the whole building, with 'Also depends on: generator starter batteries' and basis 'operations team statement, 2026-11-02' -> emergency lights (135 on all floors).

## 4. The risk chain (Muse Spark) · 0:58–1:37

**Narration:** Then Meta Muse Spark investigates, and tells the story. On October eighth, water was recorded in the switchboard rooms. It is still unresolved. A short could cut the grid supply. The generator must then start, but its starter batteries were reported degraded on September twenty-ninth. If it fails, one hundred thirty-five emergency lights and exit signs fall back on their own batteries. Newer ones last about two hours. For older ones, the real runtime is unknown: the monthly test lasts only fifteen minutes.

**Visuals:** Zoom on Meta Muse Spark story headline -> domino on the real chain (water 08 Oct unresolved -> normal supply -> ATS + batteries 29 Sep -> floor panels -> 135 lights) -> zoom on battery text; number cards 135 / ~2 h / older unknown / 15-min test.

## 5. Evidence traceability · 1:37–2:00

**Narration:** Every arrow states why two parts are connected, and on what basis. Every finding opens its source record. What cannot be verified is marked unknown. No speculation. Only evidence.

**Visuals:** Arrow basis -> click 08 Oct record chip -> source record drawer -> Equipment & Systems -> 'MBA, MSB room water seepage' -> 'Linked fire-safety risk · Why linked' -> click to B1 alert (tab change 2/3) -> 'Links not recorded'.

## 6. Muse Spark agentic investigation · 2:00–2:18

**Narration:** Muse Spark does not just summarize. It chooses its own lookups, like the emergency lighting supply of the basement. Every citation is checked, and invalid ones are removed. The official risk level stays with the rules.

**Visuals:** Section 4 -> 'How Meta Muse Spark investigated: 5 lookups' -> real tool call get_fire_safety_supply zone B1 -> 'Citations checked: 31 distinct records … none removed' -> 'Muse Spark priority High · official rule severity High — agrees'.

## 7. Survey video + SAM 3.1 · 2:18–2:36

**Narration:** Muse Spark also reviewed fourteen survey videos. SAM 3.1 outlines each finding in the frame, and the app links it to that floor's alert. Video is supporting evidence, not proof.

**Visuals:** Survey Video Findings (14 videos) -> finding 'Cable lying on floor along wall' (MSB room) -> SAM 3.1 sequence: real blurred frame 01:11, push-in, SAM box then mask outline, 'confidence 0.67', 'located in 1 of 3 frames checked' -> 'Link to existing alerts' -> B1 alert (tab change 3/3).

## 8. Recommended actions and close · 2:36–2:58

**Narration:** The manager gets clear next steps: inspect the switchboard rooms for water, and load-test the generator batteries. Decision support, not a replacement for certified fire safety systems. FireRisk Intelligence. Because building risks rarely happen in isolation.

**Visuals:** Section 5 Recommended Actions: 'immediate — Inspect MBA and MSB rooms…', 'within 24h — Verify generator starter batteries…' -> Verification box -> Overview -> end card 'MAKE HIDDEN RISK CONNECTIONS VISIBLE.'

## Sound
Scene 1: low electrical hum and relay clicks as the frames/cards appear. Music: tense minor pad in scene 1, then ~108 BPM major progression with light bass and percussion, ducked about 18 dB under the voice. Soft chime at the citation check. No other effects.
