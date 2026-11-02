# FireRisk Intelligence — QA Report (demo video, final v5)

Checked 2026-11-02 15:45 on the exported MP4 (not the edit timeline): 32 frames sampled across all scenes and
the end card viewed; subtitles read against the script.

## Export
| Item | Result |
| --- | --- |
| Container / codecs | MP4, H.264 video, AAC audio |
| Resolution / ratio / frame rate | 1920×1080, 16:9, 30 fps constant |
| Duration | 2:59.0 (limit 3:00) |
| Loudness | −15.5 LUFS integrated; music about 18 dB under the voice |

## Technical accuracy (checked against the recording's facts.json and the code)
| Claim in the video | Source on screen / in data | Result |
| --- | --- | --- |
| Water in switchboard rooms, 08 Oct, unresolved | incident record, status "Seeking a solution", "● unresolved" chip | OK |
| Starter batteries reported degraded, 29 Sep | asset repair record 29 Sep "Battery performance degraded" | OK (no number of batteries said) |
| One ATS for all six floors; generator meets grid at the ATS | chain node "ATS - one for the whole building", basis "operations team statement, 2026-11-02" | OK |
| 135 emergency lights and exit signs; ~2 h new; 15-min monthly test | chain label "135 on all floors", node text and "Links not recorded" | OK, conditional wording |
| Muse Spark chooses its own lookups, e.g. basement emergency-lighting supply | agent trace "get_fire_safety_supply zone B1 · 1 returned" (analysis 12:29) | OK |
| Citations checked, invalid ones removed | "Citations checked: 31 distinct records cited … none removed"; validate() drops unknown IDs | OK |
| Official level stays with the rules | "Muse Spark priority High · official rule severity High — agrees" | OK |
| 14 survey videos; SAM 3.1 outlines the finding | panel "14 videos"; frame 01:11 box + mask, confidence 0.67, "located in 1 of 3 frames" | OK |
| Finding linked to the floor's alert | drawer "Link to existing alerts → Water entering the electrical rooms" | OK |
| Recommended actions | "immediate — Inspect MBA and MSB rooms…", "within 24h — Verify generator starter batteries… load test" | OK, labelled "not yet done" |

Rule engine and Muse Spark are labelled separately (RULE / META MUSE SPARK tags and overlay labels). No tool call,
citation, record or dashboard screen was drawn or simulated; overlays are labels, number cards and the SAM box/mask
drawn from the returned coordinates.

## Privacy
- Dashboard recorded in demo mode: building name and staff names shown as "[name hidden]" (checked in the record drawer).
- Survey imagery: only blurred demo copies (MSB room 00:16, generator room 00:31, MSB room 01:11); no faces visible
  in the sampled frames; equipment labels blurred.
- No e-mails, keys, `.env` content, drawings or original videos in the video.

## Audio and subtitles
- Narration intelligible over music in all scenes; no clipping.
- `FireRisk_Intelligence_Subtitles.srt`: text = approved script; timing spread over each scene's voice by sentence
  length (approximate, within each sentence). Meta Muse Voice Transcribe was NOT run on this version yet
  (`transcribe_v5.bat` is ready on the author's PC); the end card makes no claim about it.

## Known limitations
- Scene 5 plays at 1.13× (the recorded take was 3 s longer than the scene).
- In scene 7 the first ~1 s still shows the alert page before the Overview loads.
- Scene 1 shows photos for two of the four incidents only (no survey footage of the speaker or the heat detector).
