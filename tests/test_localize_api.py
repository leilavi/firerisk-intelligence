"""Continuous SAM 3.1 localization inside the dashboard: a newly analysed video is localized in the background,
results reach /api/video-findings, and a SAM outage changes nothing else. TEST video + FAKE Meta/SAM only."""

import importlib
import json
import time

import pytest
from fastapi.testclient import TestClient

from fixtures import build_snapshot
from test_localize import FF, FakeSam, _mp4
from test_video_review import FakeMetaV2, _client
from firerisk.sam import SamModelNotFound

needs_ffmpeg = pytest.mark.skipif(not FF, reason="ffmpeg not available")


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    snap = build_snapshot(tmp_path / "snap")
    for k, v in {"FIRERISK_SNAPSHOT_DIR": snap, "FIRERISK_DB": tmp_path / "t.db", "FIRERISK_VIDEO_DIR": tmp_path / "v",
                 "FIRERISK_FRAMES_DIR": tmp_path / "frames", "MODEL_API_KEY": "TEST-KEY",
                 "META_API_BASE_URL": "http://fake-meta.invalid/v1", "FIRERISK_AUTO_AI": "0"}.items():
        monkeypatch.setenv(k, str(v))
    import firerisk.video as video
    import firerisk.localize as localize
    importlib.reload(video)
    importlib.reload(localize)
    import firerisk.api as api
    api = importlib.reload(api)
    import test_video_review as tvr
    answer = json.loads(json.dumps(tvr.V2_ANSWER))
    for f in answer["findings"]:
        f["segment_phrase"] = "cardboard box"                 # schema v2.1: Muse gives the phrase itself
    monkeypatch.setattr(tvr, "V2_ANSWER", answer)
    fake = FakeMetaV2()
    api.state.ai.client_factory = lambda: _client(api, fake)
    c = TestClient(api.app)
    src = tmp_path / "TEST.mp4"
    _mp4(src, 12)
    return api, c, src


def _analyse_new_video(api, c, src):
    r = c.post("/api/videos?filename=TEST_survey.mp4&zone=B1&duration_s=12", content=src.read_bytes(),
               headers={"Content-Type": "application/octet-stream"})
    vid = r.json()["video_id"]
    api.state.videos.analyse(vid, api.state.ai.client_factory(), on_done=api.state.on_video_analysed)
    t = api.state.localizer.thread
    if t:
        t.join(30)
    return vid


@needs_ffmpeg
def test_new_video_is_localized_automatically_and_shown(app_env, monkeypatch):
    api, c, src = app_env
    alerts_before = [(a["alert_id"], a["severity"]) for a in c.get("/api/fire-alerts").json()]
    sam = FakeSam()
    monkeypatch.setattr(api, "SamClient", lambda: sam)
    _analyse_new_video(api, c, src)
    f = c.get("/api/video-findings").json()["findings"][0]
    loc = f["localization"]
    assert loc["status"] == "located" and loc["segment_phrase"] == "cardboard box" and loc["phrase_source"] == "spark_v2"
    assert [fr["frame_time_s"] for fr in loc["frames"]] == [5.5, 6.5, 7.5]       # inside the finding's 5-8 s
    assert loc["frames"][0]["objects"][0]["confidence"] == 0.8
    img = c.get(f"/api/frames/{loc['frames'][0]['frame_file']}")
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert f["official_level"] is None                                     # still no level from SAM
    assert [(a["alert_id"], a["severity"]) for a in c.get("/api/fire-alerts").json()] == alerts_before
    st = c.get("/api/localization").json()
    assert st["model"] == "sam-3.1" and sum(st["counts"].values()) >= 1


@needs_ffmpeg
def test_sam_offline_changes_nothing_else(app_env, monkeypatch):
    api, c, src = app_env
    alerts_before = [(a["alert_id"], a["severity"]) for a in c.get("/api/fire-alerts").json()]

    class Down(FakeSam):
        def locate(self, jpeg, phrase):
            raise SamModelNotFound("TEST no access")
    monkeypatch.setattr(api, "SamClient", lambda: Down())
    vid = _analyse_new_video(api, c, src)
    assert api.state.videos.latest_analysis(vid)["status"] == "ok"          # Muse result saved
    vf = c.get("/api/video-findings").json()
    assert len(vf["findings"]) == 1 and vf["findings"][0]["localization"]["status"] == "error"   # not "not located"
    assert st_ok(c)
    assert [(a["alert_id"], a["severity"]) for a in c.get("/api/fire-alerts").json()] == alerts_before
    assert c.get("/api/alerts/ZONE-B1").status_code == 200


def st_ok(c):
    return c.get("/api/localization").json()["counts"].get("error", 0) >= 1


def test_frame_endpoint_rejects_paths(app_env):
    _, c, _ = app_env
    assert c.get("/api/frames/..%2F..%2Fsecret/t000001.jpg").status_code == 404
    assert c.get("/api/frames/0123456789abcdef/../../x.jpg").status_code == 404
    assert c.get("/api/frames/0123456789abcdef/t000001.jpg").status_code == 404     # well-formed but absent
