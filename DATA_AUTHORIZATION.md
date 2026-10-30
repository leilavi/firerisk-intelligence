# Data authorization

FireRisk Intelligence is built and tested on the real operational data of one building. This page records that the
author has written permission from the data owner to use that data for this Hackathon project, and how each of the
owner's conditions is enforced.

## The approval

| | |
|---|---|
| Data owner | The company that operates the building (name withheld, see condition 3) |
| Approved by | The company's Founder & CEO, in writing (e-mail) |
| Request sent | 2026-10-30, by the author, describing the project, the documents and the safeguards |
| Approval received | 2026-10-30 |
| Scope | Solely the FireRisk Intelligence Hackathon project |
| Original e-mails | Kept by the author. They are not published here because they name the company, the building and the approver. They can be shown privately to the Hackathon organizers on request |

Materials covered by the approval: operational records (meter readings, incident and repair logs, generator runs,
safety checklists, asset register), fire-safety survey videos, building layouts and floor plans, electrical cable
routing drawings and fire protection system drawings.

## Conditions and how they are met

| # | Owner's condition (summary) | How the project meets it | Where to check |
|---|---|---|---|
| 1 | Use the listed data and documents only for this project | The data is used only by this app on the author's computer | — |
| 2 | Original technical drawings stay on the author's computer and are processed locally only; never uploaded to an external AI service. Only simplified, anonymised zone information (no dimensions, cable routes or equipment details) may appear in AI requests or the demo | Enforced in code: `firerisk/data_policy.py` refuses any document (PDF, CAD, office files) and anything named like a drawing, schematic, layout or manual before **every** upload to the Meta Model API (`video.upload_file`, `media.describe_image`, `SamClient.locate`), including a document saved under an image name (file content is checked). The Google Drive sync records such files **by name only** and never downloads them. The building map uses floor names only (B1, F1–F4, Roof); no drawing content is used anywhere in the app today | `tests/test_data_policy.py` (4 tests) |
| 3 | Keep the building and the company anonymous in the submission and public presentation; conceal staff names, faces and any visible identifying information | Repository: the building is written as "[Building]"; names live only in a private, git-ignored config. Before AI calls, staff names, e-mails and record IDs are replaced by codes (`firerisk/ai/redact.py`). Demo mode (`run_dashboard_demo.bat`) masks building names, serves only blurred frame copies and never plays original videos. Blurring: signs and labels located by SAM 3.1, faces located **locally** with OpenCV (SAM is never asked to find people), regions added by hand after a frame-by-frame review | `tests/test_demo.py`, `tests/test_ai_offline.py` (no e-mails, names or real record IDs in AI payloads), review sheet (private) |
| 4 | Raw records, original videos and technical drawings stay outside the public repository | `data/private/` and all media folders are git-ignored; the repository contains code, tests with **TEST** fixtures, and sanitized evidence summaries only | `git ls-files` |
| — | Implement the anonymisation, API storage settings, video expiry and deletion controls described in the request | Meta API requests ask for `store: false`; an uploaded video copy expires after 1 hour (`expires_after`, the minimum allowed) and is deleted right after the analysis; only pseudonymised excerpts are sent | `firerisk/video.py`, `firerisk/sam.py`, `tests/test_video*.py` |

## Limits stated openly

* Face detection is a classical local detector; it can miss small or turned faces. The blurred frames are therefore
  reviewed by eye before the demo, and the demo shows still frames only, never the original video.
* Documents outside the list above (for example an operation and maintenance manual) are treated like drawings:
  name only, never opened by the app or sent to an AI service, unless the owner extends the approval.
