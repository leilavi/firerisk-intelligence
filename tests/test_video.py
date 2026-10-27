"""Survey-video architecture tests. TEST files only (a few bytes named .mp4, or a generated test pattern when
ffmpeg is available) and a FAKE Meta API transport - no real video, no real API call.
"""

import importlib
import io
import json
import shutil
import subprocess
import urllib.error

import pytest
from fastapi.testclient import TestClient

from fixtures import build_snapshot


class FakeMeta:
    """Answers /files (upload), /responses (video analysis), DELETE /files/{id}, /chat/completions (investigation)."""

    def __init__(self, fail_responses=False):
        self.log, self.fail = [], fail_responses

    def opener(self, req, timeout=0):
        url, method = req.full_url, req.get_method()
        data = req.data
        if data is not None and not isinstance(data, (bytes, bytearray)):
            data = b"".join(data)
        self.log.append({"url": url, "method": method, "data": data, "headers": dict(req.header_items())})
        if url.endswith("/files") and method == "POST":
            out = {"id": "file-TEST1", "object": "file"}
        elif "/files/" in url and method == "DELETE":
            out = {"id": "file-TEST1", "deleted": True}
        elif url.endswith("/responses"):
            if self.fail:
                raise urllib.error.HTTPError(url, 500, "err", {}, io.BytesIO(b"{}"))
            answer = {"summary": "TEST FAKE video summary", "observations": [
                {"time_start_s": 3, "time_end_s": 6, "location_in_video": "TEST corridor", "category": "obstruction",
                 "observation": "TEST boxes stored in front of a door", "visible_certainty": "clearly_visible",
                 "fire_safety_relevance": "TEST"},
                {"time_start_s": 900, "time_end_s": 905, "location_in_video": "x", "category": "other",
                 "observation": "TEST beyond the end", "visible_certainty": "possibly_visible",
                 "fire_safety_relevance": "x"}],
                "not_determinable": ["TEST whether the extinguisher is charged"], "limitations": "TEST"}
            out = {"id": "resp_TEST", "status": "completed", "model": "muse-spark-1.3",
                   "output": [{"type": "reasoning", "summary": []},
                              {"type": "message", "content": [{"type": "output_text", "text": json.dumps(answer)}]}],
                   "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}
        else:   # investigation (chat completions)
            body = json.loads(data)
            self.investigation_package = body["messages"][1]["content"]
            res = {"summary": "TEST", "situation": "TEST", "observed_facts": [], "hypotheses": [], "scenarios": [],
                   "escalation_pathway": [], "risk_assessment": {"ai_priority": "high", "agrees_with_rule_severity": True,
                                                                 "rationale": "x"},
                   "missing_information": [], "recommended_actions": [], "limitations": [], "uncertainty": "x"}
            out = {"model": "muse-spark-1.3", "choices": [{"message": {"content": json.dumps(res)}}], "usage": {}}

        class R(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return R(json.dumps(out).encode())


@pytest.fixture()
def env(tmp_path, monkeypatch):
    snap = build_snapshot(tmp_path / "snap")
    monkeypatch.setenv("FIRERISK_SNAPSHOT_DIR", str(snap))
    monkeypatch.setenv("FIRERISK_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("FIRERISK_VIDEO_DIR", str(tmp_path / "videos"))
    monkeypatch.setenv("MODEL_API_KEY", "TEST-KEY")
    monkeypatch.setenv("META_API_BASE_URL", "http://fake-meta.invalid/v1")
    monkeypatch.setenv("FIRERISK_AUTO_AI", "0")          # keep automatic fire analysis out of the way here
    import firerisk.video as video
    importlib.reload(video)
    import firerisk.api as api
    api = importlib.reload(api)
    fake = FakeMeta()
    from firerisk.ai.muse import MuseClient, MuseConfig
    api.state.ai.client_factory = lambda: MuseClient(
        MuseConfig(api_key="TEST-KEY", base_url="http://fake-meta.invalid/v1", timeout_s=5), opener=fake.opener)
    return api, TestClient(api.app), fake


def upload(c, name="TEST_survey.mp4", data=b"TEST-NOT-A-REAL-VIDEO", **meta):
    q = "&".join(f"{k}={v}" for k, v in {"filename": name, **meta}.items())
    return c.post(f"/api/videos?{q}", content=data, headers={"Content-Type": "application/octet-stream"})


def test_no_video_yet_everything_still_works(env):
    api, c, _ = env
    assert c.get("/api/videos").json()["videos"] == []
    d = c.get("/api/alerts/ZONE-B1").json()
    assert d["survey_videos"] == [] and d["alert"]["severity"] == "high"


def test_upload_stores_file_and_metadata(env):
    api, c, _ = env
    r = upload(c, zone="B1", floor="Basement", room="TEST MSB room", recorded_at="2026-10-20T09:30", duration_s=60)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["zone"] == "B1" and v["room"] == "TEST MSB room" and v["recorded_at"].startswith("2026-10-20T09:30")
    assert v["recorded_at_source"] == "entered_by_user" and v["analysable"] and v["analysis_status"] == "not_analysed"
    assert "not the current state" in v["recording_note"]
    assert api.state.videos.path(v["video_id"]).read_bytes() == b"TEST-NOT-A-REAL-VIDEO"
    no_date = upload(c, zone="B1").json()
    assert no_date["recorded_at"] is None and "unknown" in no_date["recording_note"].lower()


def test_upload_rejects_bad_input(env):
    api, c, _ = env
    assert upload(c, name="x.avi").status_code == 400
    assert upload(c, zone="F99").status_code == 400
    assert upload(c, recorded_at="yesterday").status_code == 400
    assert upload(c, data=b"").status_code == 400
    mov = upload(c, name="TEST.mov").json()
    assert mov["analysable"] is False and "mp4" in mov["analysable_reason"]
    assert c.post(f"/api/videos/{mov['video_id']}/analyse").status_code == 400


def test_clip_supports_range_requests(env):
    api, c, _ = env
    v = upload(c, zone="B1").json()
    r = c.get(f"/api/videos/{v['video_id']}/file", headers={"Range": "bytes=0-3"})
    assert r.status_code == 206 and r.content == b"TEST"


def test_video_analysis_uses_documented_api_and_becomes_context_only(env):
    api, c, fake = env
    v = upload(c, zone="B1", recorded_at="2026-10-20T09:30", duration_s=60).json()
    r = c.post(f"/api/videos/{v['video_id']}/analyse").json()
    assert r["started"]
    import time
    for _ in range(100):
        if api.state.videos.get(v["video_id"])["analysis_status"] != "running":
            break
        time.sleep(0.05)
    a = api.state.videos.latest_analysis(v["video_id"])
    assert a["status"] == "ok", a
    up, resp, delete = fake.log[0], fake.log[1], fake.log[2]
    assert up["url"].endswith("/v1/files") and b'name="purpose"\r\n\r\nuser_data' in up["data"]
    assert b'name="expires_after[seconds]"\r\n\r\n3600' in up["data"]
    assert up["data"].index(b'name="purpose"') < up["data"].index(b'name="file"')      # docs: file last
    body = json.loads(resp["data"])
    assert body["input"][0]["content"][1] == {"type": "input_video", "file_id": "file-TEST1"}
    assert body["text"]["format"]["type"] == "json_schema" and body["store"] is False
    assert delete["method"] == "DELETE" and delete["url"].endswith("/files/file-TEST1") and a["remote_file_deleted"]
    # validation: the observation beyond the end of a 60 s video is set aside
    assert [o["time_start_s"] for o in a["observations"]] == [3.0]
    assert a["rejected_observations"][0]["reason"].startswith("time 900")
    assert all(o["origin"] == "ai_vision" for o in a["observations"]) and a["timestamps_verified"] is False
    # context on the fire-risk alert: labelled, dated, level unchanged
    d = c.get("/api/alerts/ZONE-B1").json()
    sv = d["survey_videos"][0]
    assert sv["origin"] == "ai_vision" and sv["observations"][0]["category"] == "obstruction"
    assert "not the current state" in sv["recording_note"]
    assert d["alert"]["severity"] == "high"
    assert all(e["origin"] in ("source", "derived") for e in d["evidence"])   # video is not added as a record
    # and it reaches the Muse investigation package as dated context, outside evidence_ids
    res = api.state.get()
    b1 = next(x for x in res.alerts if x.alert_id == "ZONE-B1")
    from firerisk.ai.investigation import build_package
    pkg, _, _ = build_package(b1, res.signals, res.evidence, res.generated_at, res.equipment_alerts)
    svo = pkg["survey_video_observations"][0]
    assert svo["video"] == "V01" and svo["recorded_at"] == "2026-10-20" and "recording-time" in svo["origin"]


def test_video_analysis_failure_is_recorded_and_alerts_unaffected(env):
    api, c, fake = env
    fake.fail = True
    v = upload(c, zone="B1").json()
    rec = api.state.videos.analyse(v["video_id"], api.state.ai.client_factory(), "TEST")
    assert rec["status"] == "failed"
    assert any(x["method"] == "DELETE" for x in fake.log)          # uploaded copy deleted even on failure
    assert c.get("/api/alerts/ZONE-B1").json()["alert"]["severity"] == "high"
    assert c.get("/api/videos").json()["videos"][0]["analysis_status"] == "failed"


def test_analysis_needs_api_key(env, monkeypatch):
    api, c, _ = env
    v = upload(c, zone="B1").json()
    monkeypatch.setenv("MODEL_API_KEY", "")
    assert c.post(f"/api/videos/{v['video_id']}/analyse").status_code == 400


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_frame_extraction_from_test_pattern(env, tmp_path):
    api, c, _ = env
    src = tmp_path / "TEST_pattern.mp4"                 # generated test pattern, never shown in the real app
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=5",
                    "-t", "3", "-pix_fmt", "yuv420p", str(src)], check=True)
    v = upload(c, name="TEST_pattern.mp4", data=src.read_bytes(), zone="B1").json()
    r = c.get(f"/api/videos/{v['video_id']}/frame?t=1.5")
    assert r.status_code == 200 and r.content[:2] == b"\xff\xd8"
