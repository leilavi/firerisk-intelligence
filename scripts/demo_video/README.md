# Demo video tooling (2026-11-02)

How the submission video was made, kept for transparency. None of these files contain building data.

| File | What it does | Where it ran |
| --- | --- | --- |
| `record_demo5.py` | Starts the dashboard in **demo mode** on port 8777, waits until Meta Muse Spark has analysed the current evidence, then drives headless Microsoft Edge (Playwright) through the 8 scenes and records the real screen (DevTools screencast), the on-screen rectangles of every zoom target (`marks.json`), the texts shown (`facts.json`) and the blurred survey frames served in demo mode | Author's PC (`data/private/video/`) |
| `timing5.json`, `script.json` | Scene lengths, narration cues and the narration text | — |
| `compose5.py` | Edits the recording: zooms and spotlights from `marks.json`, journey bar, labels, subtitles, scene 1 cards, the SAM 3.1 sequence (box and mask drawn from the coordinates SAM returned) | Editing workspace (no network) |
| `music.py`, `mix5.py` | Original music synthesised in code; voice-over placement, ducking, light sound design, loudness | Editing workspace |

Paths inside the scripts point to the machines they ran on. Story, checks and limits: `docs/demo-video/`.
