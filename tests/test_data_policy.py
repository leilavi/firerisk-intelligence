"""Data owner's condition 2 (approval 2026-10-30): technical drawings never reach an AI service. TEST data only."""

import json
from pathlib import Path

import pytest

from firerisk.data_policy import (LocalOnlyDocumentError, assert_may_send_to_ai, is_local_only_document,
                                  local_only_documents)

LISTING = [  # names shaped like the real Drive folder, contents never read
    {"id": "TESTPDF1", "title": "TECH-DIAG_Exit_and_Emergency_Lighting_Schematic_Diagram.pdf",
     "mime_type": "application/pdf", "size": 1, "folder": "TEST/User_Manual"},
    {"id": "TESTPDF2", "title": "TECH-DIAG_Electrical_Cable_Routing_and_MSB_Fire_Protection_Layout.pdf",
     "mime_type": "application/pdf", "size": 1, "folder": "TEST/User_Manual"},
    {"id": "TESTPDF3", "title": "Operation and Maintenance Manual (O&M Manual).pdf",
     "mime_type": "application/pdf", "size": 1, "folder": "TEST/User_Manual"},
    {"id": "TESTVID1", "title": "Floor 3.mp4", "mime_type": "video/mp4", "size": 1, "folder": "TEST/Video Uploaded"},
    {"id": "TESTVID2", "title": "Cable tray B1.mp4", "mime_type": "video/mp4", "size": 1, "folder": "TEST/Video Uploaded"},
    {"id": "TESTSHEET", "title": "TEST Operations Data", "mime_type": "application/vnd.google-apps.spreadsheet",
     "size": 1, "folder": "TEST"},
]


def test_drawings_and_manuals_are_local_only_but_survey_media_is_not():
    docs = {f["title"] for f in local_only_documents(LISTING)}
    assert docs == {LISTING[0]["title"], LISTING[1]["title"], LISTING[2]["title"]}
    assert not is_local_only_document("Floor 3.mp4", "video/mp4", "TEST/Video Uploaded")
    assert not is_local_only_document("Cable tray B1.mp4", "video/mp4")          # a survey video, not a drawing
    assert is_local_only_document("TECH-DIAG_riser.png", "image/png")             # a picture of a drawing
    assert is_local_only_document("ban ve dien.jpg", "image/jpeg")
    assert is_local_only_document("notes", "application/vnd.google-apps.document")
    assert not is_local_only_document("TEST Operations Data", "application/vnd.google-apps.spreadsheet", "User_Manual")


def test_no_ai_upload_of_a_document_even_when_renamed(tmp_path: Path):
    pdf = tmp_path / "TECH-DIAG_test.pdf"
    pdf.write_bytes(b"%PDF-1.7 test")
    with pytest.raises(LocalOnlyDocumentError):
        assert_may_send_to_ai(pdf)
    disguised = tmp_path / "frame_00001.jpg"                  # a drawing saved under an image name
    disguised.write_bytes(b"%PDF-1.7 test")
    with pytest.raises(LocalOnlyDocumentError):
        assert_may_send_to_ai(disguised)
    with pytest.raises(LocalOnlyDocumentError):
        assert_may_send_to_ai(data=b"%PDF-1.4 test")          # SAM receives bytes
    ok = tmp_path / "frame_00002.jpg"
    ok.write_bytes(b"\xff\xd8\xff\xe0 test jpeg")
    assert_may_send_to_ai(ok)                                 # survey frames still go through
    assert_may_send_to_ai(data=b"\xff\xd8\xff\xe0 test jpeg")


def test_every_ai_upload_path_checks_the_policy(tmp_path: Path):
    """video.upload_file, media.describe_image and SamClient.locate refuse a document before any network call."""
    from firerisk import media, video
    from firerisk.ai.muse import MuseConfig
    from firerisk.sam import SamClient

    class NoNetwork:                                          # any attribute access would mean a request was built
        config = type("C", (), {"model": "test", "base_url": "http://127.0.0.1:9", "api_key": "TEST"})()

        def __getattr__(self, name):
            raise AssertionError("network used")

    pdf = tmp_path / "TECH-DIAG_test.pdf"
    pdf.write_bytes(b"%PDF-1.7 test")
    with pytest.raises(LocalOnlyDocumentError):
        video.upload_file(NoNetwork(), pdf, mime="application/pdf")
    with pytest.raises(LocalOnlyDocumentError):
        media.describe_image(NoNetwork(), pdf, "TEST")
    def opener(*a, **k):
        raise AssertionError("network used")
    with pytest.raises(LocalOnlyDocumentError):
        SamClient(MuseConfig(api_key="TEST"), opener=opener).locate(b"%PDF-1.7 test", "fire extinguisher")

def test_drive_sync_lists_documents_by_name_only_and_never_catalogues_them(tmp_path: Path, monkeypatch):
    from firerisk.drive_videos import drive_video_items
    catalog = {f["id"]: {"title": f["title"], "mime_type": f["mime_type"], "folder": f["folder"]} for f in LISTING}
    ids = {i["drive_file_id"] for i in drive_video_items(catalog, [])}
    assert ids == {"TESTVID1", "TESTVID2"}
    docs = local_only_documents(LISTING)
    assert all(set(d) == {"title", "mime_type", "size", "folder", "drive_modified_time", "note"} for d in docs)
    assert "data_b64" not in json.dumps(docs)
