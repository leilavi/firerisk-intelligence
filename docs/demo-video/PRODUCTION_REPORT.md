# FireRisk Intelligence — Production Report (demo video, final v5)

Date: 2026-11-02 · Final file: `FireRisk_Intelligence_Demo_Final.mp4` (2:59, 1920×1080, 30 fps, H.264 + AAC)

## What was inspected
- Repository `leilavi/firerisk-intelligence` at commit c905844 (+ the author's PC copy, same code): rule engine
  (`firerisk/impact_chain.py`, `power_links.py`, `equipment.py`), Meta Muse Spark investigation and agent
  (`firerisk/ai/investigation.py`, `ai/agentic.py`, citation check `validate()`), SAM 3.1 localization
  (`firerisk/localize.py`, `sam.py`), dashboard (`web/app.js`), demo mode (`firerisk/demo.py`).
- Live state on the author's PC at recording time (15:15): Meta Muse Spark analysis of ZONE-B1 created
  2026-11-02T12:29, agentic, citation check ok; whole-building story as shown.

## Footage
- **Dashboard**: recorded automatically on the author's PC by `scripts/demo_video/record_demo5.py` (headless Microsoft Edge, Playwright,
  1920×1080, DevTools screencast), from the real dashboard in **demo mode** (names hidden, blurred frames only), on a
  separate server with automatic analysis on; recording waited until both alerts' Meta Muse Spark analyses were current.
  0 script errors. Every click in the video is a real click in the app.
- **Scene 1 photos**: two real blurred survey frames served by the dashboard in demo mode (MSB room 00:16, generator
  room 00:31). No speaker or heat-detector footage exists, so those two incidents are shown as record cards only.
- **Scene 7 SAM sequence**: the real blurred frame 01:11 of the MSB-room survey video, with the box and mask outline
  returned by Meta SAM 3.1 (phrase "electrical cable", confidence 0.67).
  SAM did not locate the object in the other two frames (01:12, 01:13); the video says "located in 1 of 3 frames".
- No stock footage, no AI-generated imagery, no fire or disaster effects.

## Narration, music, sound
- Narration: Kokoro TTS voice `af_heart` (American English, female), speed 0.9, slight pitch-down; text = storyboard v5
  (user-approved, "two" removed from "starter batteries"). Voice total 141.4 s, placed mid-scene.
- Music: synthesised in code (`scripts/demo_video/music.py`), no samples; minor pad in scene 1, ~108 BPM major progression afterwards,
  ducked under the voice (about −18 dB).
- Sound design: synthesised electrical hum and relay clicks (scene 1), soft chime at the citation check.

## Editing
- Python (PIL) frame compositor `scripts/demo_video/compose5.py` + FFmpeg (libx264 CRF 17, AAC 192 kb/s, loudnorm −15 LUFS).
- Zooms and spotlights use the element rectangles measured in the browser during the take (`marks.json`).
- Scene timing: S2/S4/S6 trimmed at the tail (no speed change); S5 played at 1.13× (the take ran 26 s for a 23 s scene).

## Deviations from the proposed master instruction
- Scene 3 diagram follows the confirmed topology (grid and generator meet at the ATS), not "switchboard → ATS → generator".
- Scene 7 flow follows the implementation: Muse Spark observation → frame at that time → SAM 3.1 → floor (asset register) → alert.
- "Unknown" is shown grey/dashed, not yellow (yellow = Warning level on the dashboard).
- Cinematic layer replaced by real blurred survey frames (data-owner condition; no stock footage available).
- End card does not claim a Muse Voice Transcribe check for this version (not run on v5; `transcribe_v5.bat` is ready on the PC).
