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


# --- rendered dashboard (Playwright) at 1440 and 390 px -------------------------------------------------------
@needs_ffmpeg
@pytest.mark.parametrize("width", [1440, 390])
def test_evidence_overlay_renders_aligned_and_english_only(app_env, monkeypatch, width, tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    import socket
    import threading as th
    import uvicorn
    api, c, src = app_env
    monkeypatch.setattr(api, "SamClient", lambda: FakeSam())
    _analyse_new_video(api, c, src)
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    server = uvicorn.Server(uvicorn.Config(api.app, host="127.0.0.1", port=port, log_level="error"))
    t = th.Thread(target=server.run, daemon=True); t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    try:
        with pw.sync_playwright() as p:
            try:
                b = p.chromium.launch()
            except Exception as exc:
                pytest.skip(f"chromium not available: {exc}")
            page = b.new_page(viewport={"width": width, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/#/media"); page.wait_for_load_state("networkidle")
            page.wait_for_selector("#samg .samcard")
            assert "1 located" in page.inner_text("#samg")
            page.click("#samg .samcard"); page.wait_for_selector("#drawer .evblock img")
            page.wait_for_function("() => document.querySelector('#drawer .evblock img').complete")
            txt = page.text_content("#drawer")
            assert "AI observation (Muse Spark)" in txt and "Visual model detected (SAM 3.1)" in txt
            assert "Located in frame at 00:05 (confidence 0.80)" in txt and "Video Timestamp" in txt
            img = page.eval_on_selector("#drawer .ev-frame img", "e => { const r = e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; }")
            rect = page.eval_on_selector("#drawer .ev-frame svg rect", "e => { const r = e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; }")
            sx, sy = img[2] / 160, img[3] / 120                        # frame is 160x120; box x1=10 y1=10 w=40 h=30
            assert abs(img[2] / img[3] - 160 / 120) < 0.02             # image not distorted
            assert abs(rect[0] - (img[0] + 10 * sx)) < 3 and abs(rect[1] - (img[1] + 10 * sy)) < 3
            assert abs(rect[2] - 40 * sx) < 3 and abs(rect[3] - 30 * sy) < 3
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            vi = page.evaluate("() => /[\\u00C0-\\u1EF9\\u0110\\u0111]/.test(document.body.innerText)")
            assert not vi
            page.screenshot(path=str(tmp_path / f"evidence_{width}.png"), full_page=False)
            assert errors == []
            b.close()
    finally:
        server.should_exit = True
        t.join(timeout=5)


def test_drawer_evidence_uses_only_same_room_or_equipment_videos(app_env):
    """A frame from another room on the same floor must not illustrate a risk (author's report 2026-10-29: the
    wastewater blower risk showed a cable frame from the MSB room)."""
    pw = pytest.importorskip("playwright.sync_api")
    import socket
    import threading as th
    import uvicorn
    api, c, _ = app_env
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    server = uvicorn.Server(uvicorn.Config(api.app, host="127.0.0.1", port=port, log_level="error"))
    t = th.Thread(target=server.run, daemon=True); t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    floor = {"alert_id": "ZONE-B1", "reason": "Same floor (asset register) and the finding group matches this risk"}
    findings = [
        {"finding_id": "VF-msb", "filename": "MSB Room.mp4", "area_label": "MSB Room", "category": "ignition_source",
         "links": [floor], "localization": {"status": "located"}, "title": "TEST cable on floor"},
        {"finding_id": "VF-ww-ladder", "filename": "Wastewater Treatment Room.mp4", "area_label": "", "category": "egress_access",
         "links": [], "localization": {"status": "located"}, "title": "TEST ladder"},
        {"finding_id": "VF-ww-motor", "filename": "Wastewater Treatment Room.mp4", "area_label": "", "category": "ignition_source",
         "links": [], "localization": {"status": "located"}, "title": "TEST open motor terminal box"},
        {"finding_id": "VF-eq", "filename": "Some video.mp4", "area_label": "", "category": "ignition_source",
         "links": [{"alert_id": "EQ-1", "reason": "The video is linked to this equipment in the asset register"}],
         "localization": {"status": "not_located"}, "title": "TEST equipment"},
        # author's report 2026-10-29 08:36: MSB video linked by equipment to ANOTHER risk of the same zone alert
        {"finding_id": "VF-msb-eq-other-risk", "filename": "MSB Room.mp4", "area_label": "", "category": "ignition_source",
         "links": [{"alert_id": "ZONE-B1", "signal_id": "R1_WATER", "reason": "The video is linked to the same equipment in the asset register"}],
         "localization": {"status": "located"}, "title": "TEST other risk"}]
    try:
        with pw.sync_playwright() as p:
            try:
                b = p.chromium.launch()
            except Exception as exc:
                pytest.skip(f"chromium not available: {exc}")
            page = b.new_page()
            page.goto(f"http://127.0.0.1:{port}/"); page.wait_for_load_state("networkidle")
            res = page.evaluate("""(F) => { VF = { findings: F }; const ids = (i) => evidenceMatches(i).map((m) => m.f.finding_id);
              return {
                ww: ids({ kind: "fire_risk", alert_id: "ZONE-B1", signal_id: "R3_MOTOR", risk_type: "motor_overheat", place: "Wastewater air blower AB-01A (XLNT)" }),
                msbRisk: ids({ kind: "fire_risk", alert_id: "ZONE-B1", signal_id: "R1_WATER", risk_type: "water_electrical", place: "Basement" }),
                msb: ids({ kind: "fire_risk", alert_id: "ZONE-B1", risk_type: "water_electrical", place: "MSB room, transformer (MBA) room" }),
                other: ids({ kind: "fire_risk", alert_id: "ZONE-B1", signal_id: "R7_PA", risk_type: "pa_system", place: "Public address system" }),
                eq: ids({ kind: "equipment", alert_id: "EQ-1", title: "Generator", place: "Generator" }) }; }""", findings)
            b.close()
    finally:
        server.should_exit = True
        t.join(timeout=5)
    assert res["ww"][0] == "VF-ww-motor" and "VF-msb" not in res["ww"]      # same room, relevant group first
    assert "VF-msb-eq-other-risk" not in res["ww"]                          # equipment link of another risk ignored
    assert res["msbRisk"] == ["VF-msb-eq-other-risk"]                        # ... but used for its own risk
    assert set(res["msb"]) == {"VF-msb", "VF-msb-eq-other-risk"}             # both MSB videos, by room name
    assert res["other"] == []                                               # same floor only -> no picture
    assert res["eq"] == ["VF-eq"]
