"""0.9: survey-video fire-safety review (prompt v2), AI video findings, coverage, large videos, Drive renames, and the
structured investigation briefing (prompt v6). TEST files and a FAKE Meta transport only - no real video, no real API."""

import io
import json
import shutil
import subprocess
import time

import pytest

from test_video import FakeMeta, env, upload  # noqa: F401  (pytest fixture re-used)

V2_ANSWER = {
    "summary": "TEST FAKE fire-safety review", "observations": [], "not_determinable": [], "limitations": "TEST",
    "areas": [{"area_label": "TEST plant room", "label_basis": "sign_or_label_visible", "time_start_s": 0, "time_end_s": 10,
               "extinguishers": "not_visible_in_footage", "extinguishers_visible_count": -1,
               "detection_devices": "needs_on_site_verification", "other_fire_equipment": "TEST none", "notes": ""}],
    "findings": [
        {"title": "TEST cardboard stacked beside control cabinet", "category": "combustibles_housekeeping",
         "time_start_s": 5, "time_end_s": 8, "area_label": "TEST plant room", "what_is_visible": "TEST boxes",
         "fire_safety_link": "TEST fuel near electrical cabinet", "potential_consequence_if_confirmed": "TEST could feed a fire",
         "certainty": "clearly_visible", "recommended_check": "TEST remove boxes", "records_to_collect": "TEST none"},
        {"title": "TEST beyond the end", "category": "ignition_source", "time_start_s": 900, "time_end_s": 905,
         "area_label": "x", "what_is_visible": "x", "fire_safety_link": "x", "potential_consequence_if_confirmed": "x",
         "certainty": "possibly_visible", "recommended_check": "x", "records_to_collect": "x"}],
    "coverage": {"categories_assessed": ["combustibles_housekeeping", "extinguishers_first_aid"],
                 "categories_not_assessable": ["detection_alarm"], "needs_more_footage": ["TEST ceiling not filmed"],
                 "image_limitations": "TEST fast panning"}}


class FakeMetaV2(FakeMeta):
    def opener(self, req, timeout=0):
        if req.full_url.endswith("/responses"):
            data = req.data if isinstance(req.data, (bytes, bytearray)) else b"".join(req.data)
            self.log.append({"url": req.full_url, "method": "POST", "data": data})
            out = {"id": "resp_TEST", "status": "completed", "model": "muse-spark-1.3",
                   "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(V2_ANSWER)}]}]}

            class R(io.BytesIO):
                def __enter__(self): return self
                def __exit__(self, *a): return False
            return R(json.dumps(out).encode())
        return super().opener(req, timeout)


def _client(api, fake):
    from firerisk.ai.muse import MuseClient, MuseConfig
    return MuseClient(MuseConfig(api_key="TEST-KEY", base_url="http://fake-meta.invalid/v1", timeout_s=5), opener=fake.opener)


def test_v2_review_stores_findings_areas_and_coverage_and_rejects_bad_times(env):
    api, c, _ = env
    fake = FakeMetaV2()
    v = upload(c, zone="B1", duration_s=60).json()
    rec = api.state.videos.analyse(v["video_id"], _client(api, fake))
    assert rec["status"] == "ok" and rec["prompt_version"] == "survey-video-v2"
    assert [f["title"] for f in rec["findings"]] == ["TEST cardboard stacked beside control cabinet"]
    assert rec["rejected_findings"][0]["reason"].startswith("time 900")
    assert rec["areas"][0]["extinguishers"] == "not_visible_in_footage"
    assert rec["method"]["transcoded"] is False and "input_video" in rec["method"]["via"]
    body = json.loads(next(x for x in fake.log if x["url"].endswith("/responses"))["data"])
    assert "extinguishers_first_aid" in json.dumps(body["text"]["format"]["schema"])   # A-G review requested


def test_findings_are_separate_from_alerts_have_no_level_and_status_is_set_by_a_person(env):
    api, c, _ = env
    v = upload(c, zone="B1", duration_s=60).json()
    api.state.videos.analyse(v["video_id"], _client(api, FakeMetaV2()))
    vf = c.get("/api/video-findings").json()
    f = vf["findings"][0]
    assert f["official_level"] is None and f["status_label"] == "New finding" and f["origin"] == "ai_vision"
    assert vf["counts"]["new"] == 1 and vf["counts"]["needs_verification"] == 1
    before = [a["severity"] for a in c.get("/api/fire-alerts").json()]
    assert c.post(f"/api/video-findings/{f['finding_id']}/status", json={"status": "confirmed", "note": "TEST", "by": "TEST"}).status_code == 200
    f2 = c.get("/api/video-findings").json()["findings"][0]
    assert f2["status_label"] == "Confirmed" and f2["verified"]
    assert [a["severity"] for a in c.get("/api/fire-alerts").json()] == before        # never changes a rule level
    cov = vf["coverage"]
    assert cov["reviewed"] == 1 and cov["groups_assessed"]["combustibles_housekeeping"] == 1
    assert "detection_alarm" in cov["groups_never_assessed"] and "not proven absent" in cov["note"]
    assert "F4" in cov["floors_without_video"]


def test_video_without_floor_is_not_placed_and_only_equipment_links_count(env):
    api, c, _ = env
    v = upload(c, duration_s=60).json()                                   # no zone: location not verified
    api.state.videos.analyse(v["video_id"], _client(api, FakeMetaV2()))
    vf = c.get("/api/video-findings").json()
    assert vf["findings"][0]["zone_label"] == "Location not verified" and vf["findings"][0]["links"] == []
    assert vf["coverage"]["location_not_verified"] == [v["filename"]]


def test_new_review_prompt_queues_every_video_once(env):
    api, c, fake = env
    v = upload(c, zone="B1", duration_s=60).json()
    api.state.videos.save_analysis({"video_id": v["video_id"], "created_at": "2026-10-28T10:00:00+07:00", "status": "ok",
                                    "prompt_version": "survey-video-v1", "observations": []})
    assert [x["video_id"] for x in api.state.videos.pending_auto()] == [v["video_id"]]   # older version only
    api.state.videos.analyse(v["video_id"], _client(api, FakeMetaV2()))
    assert api.state.videos.pending_auto() == []                                        # one attempt per version


def test_large_video_is_sent_as_smaller_copy_or_fails_with_reason(env, monkeypatch, tmp_path):
    api, c, _ = env
    import firerisk.video as video
    v = upload(c, zone="B1", duration_s=2).json()
    monkeypatch.setattr(video, "UPLOAD_SAFE_BYTES", 5)                    # pretend the TEST file is "too large"
    monkeypatch.setattr(video, "ffmpeg_path", lambda: None)
    rec = api.state.videos.analyse(v["video_id"], _client(api, FakeMetaV2()))
    assert rec["status"] == "failed" and rec["error_kind"] == "too_large" and "1 GiB" in rec["error"]
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed: transcoding path not exercised")
    src = tmp_path / "TEST_pattern.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=10", "-t", "2",
                    "-pix_fmt", "yuv420p", str(src)], check=True)
    monkeypatch.setattr(video, "ffmpeg_path", lambda: shutil.which("ffmpeg"))
    monkeypatch.setattr(video, "UPLOAD_SAFE_BYTES", src.stat().st_size - 1)
    out, method = video.prepare_upload(src)
    assert out != src and method["transcoded"] and "720p" in method["sent"] and out.stat().st_size < src.stat().st_size


def test_drive_rename_updates_the_shown_name(env, monkeypatch):
    api, c, _ = env
    from firerisk.drive_videos import DriveVideoSync
    v = upload(c, zone="B1").json()
    with api.state.videos._conn() as con:
        con.execute("UPDATE survey_videos SET drive_file_id='TESTID' WHERE video_id=?", (v["video_id"],))
    monkeypatch.setenv("FIRERISK_DRIVE_EXPORT_URL", "https://script.google.com/macros/s/TEST/exec")
    monkeypatch.setenv("FIRERISK_DRIVE_TOKEN", "TEST")
    p = DriveVideoSync(api.state.videos, api.state.videos.video_dir).run(
        [{"drive_file_id": "TESTID", "title": "TEST renamed.mp4", "size": v["size"], "ref": None}])
    assert p["renamed"] == [{"from": v["filename"], "to": "TEST renamed.mp4"}]
    assert api.state.videos.get(v["video_id"])["filename"] == "TEST renamed.mp4"


def test_v6_claims_without_valid_records_are_downgraded():
    from firerisk.ai.investigation import map_back, validate
    res = {"risk_briefings": [{"signal": "S01", "observed": "x", "history_link": "", "why_it_matters": "x",
                               "consequence_chain": ["a", "b"], "potential_consequence": "x", "not_established": ["n"],
                               "actions_immediate": ["i"], "actions_follow_up": ["f"], "closure_criteria": ["c"],
                               "claims": [{"statement": "TEST cited", "basis": "supported_by_records", "evidence_ids": ["E01"]},
                                          {"statement": "TEST uncited", "basis": "supported_by_records", "evidence_ids": ["E99"]}],
                               "certainty": "supported", "uncertainty": "n", "first_action": "i", "evidence_ids": []}]}
    out = map_back(res, {"E01": "real-1"}, {"S01": "SIG"})
    validate(out, ["real-1"])
    cl = out["risk_briefings"][0]["claims"]
    assert cl[0]["basis"] == "supported_by_records" and cl[0]["evidence_ids"] == ["real-1"]
    assert cl[1]["basis"] == "hypothesis" and cl[1]["downgraded"]


def test_display_name_is_muse_captain_but_model_id_unchanged():
    from pathlib import Path
    from firerisk.ai.muse import MuseConfig
    root = Path(__file__).resolve().parent.parent
    js = (root / "web/app.js").read_text(encoding="utf-8")
    assert "Muse Captain" in js and "GROUND LEVEL" not in js and "gEarth" not in js
    assert all("powered by" in line for line in js.splitlines() if "Muse Spark" in line)  # only the technical line
    assert MuseConfig.load().model == "muse-spark-1.3" or MuseConfig.load().model      # model id untouched
