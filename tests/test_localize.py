"""SAM 3.1 localization pipeline (firerisk/localize.py): phrases, frames, statuses, idempotency, limits, resume,
background processing. TEST videos (generated test pattern) and FAKE SAM / Muse clients only - no real API, no real
building video."""

import hashlib
import json
import sqlite3
import subprocess
import threading
from types import SimpleNamespace

import pytest

import firerisk.localize as L
from firerisk.localize import Localizer, item_status, items_of, sample_times
from firerisk.sam import SamModelNotFound, SamParse, SamObject, SamRateLimited, SamResult, SamTimeout
from firerisk.video import VideoStore, ffmpeg_path

FF = ffmpeg_path()
needs_ffmpeg = pytest.mark.skipif(not FF, reason="ffmpeg not available")


# --- fakes -----------------------------------------------------------------------------------------------------
class FakeSam:
    """locate() answers from a script: 'hit', 'miss', or an exception instance; default 'hit'."""

    def __init__(self, script=None, configured=True):
        self.script, self.calls, self.configured = list(script or []), [], configured

    def locate(self, jpeg, phrase):
        self.calls.append(phrase)
        what = self.script.pop(0) if self.script else "hit"
        if isinstance(what, Exception):
            raise what
        objs = [SamObject("0", 0, {"x1": 10, "y1": 10, "x2": 50, "y2": 40, "w": 40, "h": 30}, 0.8,
                          mask_svg_path="M0 0L1 0L1 1Z",
                          mask_box={"x": 10, "y": 10, "w": 40, "h": 30, "raster_w": 40, "raster_h": 30})] \
            if what == "hit" else []
        return SamResult(SamParse(objs, {0: (160, 120)}), "sam-3.1", {"images_processed": 1}, 0.1, "resp_TEST", 1, True)


class FakeMuse:
    def __init__(self, answer=None, fail=False):
        self.answer, self.fail, self.calls = answer, fail, 0

    def chat_json(self, system, user, schema, **kw):
        self.calls += 1
        if self.fail:
            raise TimeoutError("TEST muse down")
        items = json.loads(user)["items"]
        out = []
        for it in items:
            a = (self.answer or {}).get(it["ref"])
            out.append({"ref": it["ref"], "applicable": a is not None and a != "", "segment_phrase": a or "",
                        "reason": "TEST"})
        return SimpleNamespace(data={"items": out})


# --- fixtures --------------------------------------------------------------------------------------------------
def _mp4(path, seconds=12):
    subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"testsrc=size=160x120:rate=5:duration={seconds}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    str(path)], check=True, timeout=60)


ANALYSIS_V1 = {"prompt_version": "survey-video-v1", "observations": [
    {"time_start_s": 1, "time_end_s": 7, "category": "fire_equipment", "observation": "TEST red fire extinguisher on wall"},
    {"time_start_s": 2, "time_end_s": 2.5, "category": "storage_or_combustibles", "observation": "TEST cardboard boxes"},
    {"time_start_s": 3, "time_end_s": 9, "category": "fire_detection_or_alarm", "observation": "TEST no detector seen"}]}

ANALYSIS_V21 = {"prompt_version": "survey-video-v2", "schema_rev": "v2.1",
                "findings": [{"title": "TEST cables", "category": "ignition_source", "time_start_s": 4, "time_end_s": 8,
                              "what_is_visible": "TEST loose cables", "segment_phrase": "cable tray"},
                             {"title": "TEST no extinguisher", "category": "extinguishers_first_aid", "time_start_s": 0,
                              "time_end_s": 11, "what_is_visible": "TEST none in frame", "segment_phrase": ""}],
                "observations": [{"time_start_s": 5, "time_end_s": 5, "category": "other", "observation": "TEST",
                                  "segment_phrase": "a person near the door"}]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRERISK_SAM_DAILY_LIMIT", "300")
    db = tmp_path / "t.db"
    store = VideoStore(db, video_dir=tmp_path / "videos")
    loc = Localizer(db, store, frames_dir=tmp_path / "frames")
    return SimpleNamespace(db=db, store=store, loc=loc, tmp=tmp_path)


def add_video(e, analysis, name="TEST video.mp4", seconds=12):
    src = e.tmp / name
    _mp4(src, seconds)
    v = e.store.add_file(src, name, {"zone": "B1"})
    rec = {"video_id": v["video_id"], "created_at": "2026-10-28T12:00:00+07:00", "status": "ok", **analysis}
    rec["id"] = e.store.save_analysis(rec)
    return e.store.get(v["video_id"]), rec


def statuses(e, rec):
    return [e.loc.item_result(rec["id"], it["kind"], it["index"])["status"] for it in items_of(rec)]


# --- pure helpers ----------------------------------------------------------------------------------------------
def test_sample_times():
    assert sample_times(2, 8, 20) == [2.9, 5.0, 7.1]                     # beginning, middle, end
    assert sample_times(2, 2.4, 20) == [2.2]                             # short interval: one midpoint
    assert sample_times(15, 30, 20) == [15.8, 17.5, 19.2]                # clamped to the video length
    assert sample_times(None, None, 20) == [10.0]                        # no usable time: middle of the video
    assert sample_times(50, 60, 20) == [10.0]                            # starts after the end
    assert sample_times(5, 3, 20) == [5.0]                               # end before start


def test_item_status_rules():
    na = {"applicable": 0}
    ok = {"applicable": 1}
    assert item_status(na, []) == "not_applicable"
    assert item_status(ok, []) == "not_checked"
    assert item_status(ok, [{"status": "not_located"}, {"status": "located"}]) == "located"
    assert item_status(ok, [{"status": "not_located"}, {"status": "error"}]) == "error"   # failure != no match
    assert item_status(ok, [{"status": "not_located"}] * 3) == "not_located"


# --- phrases ---------------------------------------------------------------------------------------------------
@needs_ffmpeg
def test_phrase_sources(env):
    _, v1 = add_video(env, ANALYSIS_V1)
    muse = FakeMuse({"o0": "fire extinguisher", "o1": "", "o2": ""})
    p = env.loc.ensure_phrases(env.store.latest_analysis(v1["video_id"], only_ok=True), muse)
    assert p[("observation", 0)]["segment_phrase"] == "fire extinguisher"
    assert p[("observation", 0)]["phrase_source"] == "spark_derived"
    assert p[("observation", 2)]["applicable"] == 0                     # absence -> not applicable
    assert muse.calls == 1
    # new-schema record: phrases come from the record; people and empty phrases are not applicable
    _, v2 = add_video(env, ANALYSIS_V21, name="TEST b.mp4")
    p2 = env.loc.ensure_phrases(env.store.latest_analysis(v2["video_id"], only_ok=True), FakeMuse())
    assert p2[("finding", 0)]["phrase_source"] == "spark_v2" and p2[("finding", 0)]["segment_phrase"] == "cable tray"
    assert p2[("finding", 1)]["applicable"] == 0
    assert p2[("observation", 0)]["applicable"] == 0                    # "person" is never sent to SAM


@needs_ffmpeg
def test_muse_failure_uses_fixed_map_and_never_guesses(env):
    _, rec = add_video(env, ANALYSIS_V1)
    p = env.loc.ensure_phrases(env.store.latest_analysis(rec["video_id"], only_ok=True), FakeMuse(fail=True))
    assert p[("observation", 0)] == {**p[("observation", 0)], "segment_phrase": "fire extinguisher",
                                     "phrase_source": "category_map"}
    assert p[("observation", 1)]["segment_phrase"] == "cardboard box"
    assert ("observation", 2) not in p                                  # "no detector seen": no row, retried later


# --- run -------------------------------------------------------------------------------------------------------
@needs_ffmpeg
def test_end_to_end_statuses_frames_and_records_unchanged(env):
    v, rec = add_video(env, ANALYSIS_V1)
    before = sqlite3.connect(env.db).execute("SELECT record FROM video_analyses").fetchall()
    muse = FakeMuse({"o0": "fire extinguisher", "o1": "cardboard box", "o2": ""})
    sam = FakeSam(["hit", "miss", "miss", "miss"])
    out = env.loc.run(sam, muse)
    assert out["requested"] == 4 and out["located"] == 1 and out["not_located"] == 3
    assert statuses(env, rec) == ["located", "not_located", "not_applicable"]
    r = env.loc.item_result(rec["id"], "observation", 0)
    assert [f["frame_time_s"] for f in r["frames"]] == [1.9, 4.0, 6.1]
    assert r["frames"][0]["objects"][0]["box"]["w"] == 40 and r["frames"][0]["frame_w"] == 160
    assert all((env.tmp / "frames" / f["frame_file"]).exists() for f in r["frames"])
    after = sqlite3.connect(env.db).execute("SELECT record FROM video_analyses").fetchall()
    assert before == after                                              # Muse records never modified


@needs_ffmpeg
def test_rerun_makes_no_duplicate_rows_or_calls(env):
    add_video(env, ANALYSIS_V1)
    muse = FakeMuse({"o0": "fire extinguisher", "o1": "cardboard box"})
    env.loc.run(FakeSam(), muse)
    n = sqlite3.connect(env.db).execute("SELECT COUNT(*) FROM video_finding_locations").fetchone()[0]
    sam2 = FakeSam()
    out = env.loc.run(sam2, muse)
    assert sam2.calls == [] and out["requested"] == 0 and muse.calls == 1
    assert sqlite3.connect(env.db).execute("SELECT COUNT(*) FROM video_finding_locations").fetchone()[0] == n


@needs_ffmpeg
def test_new_analysis_of_same_video_reuses_answers(env):
    v, rec = add_video(env, ANALYSIS_V1)
    muse = FakeMuse({"o0": "fire extinguisher", "o1": "cardboard box"})
    env.loc.run(FakeSam(), muse)
    rec2 = {**rec, "created_at": "2026-10-28T13:00:00+07:00"}
    rec2.pop("id")
    rec2["id"] = env.store.save_analysis(rec2)                          # duplicate notification / re-analysis
    sam = FakeSam()
    out = env.loc.run(sam, muse)
    assert sam.calls == [] and out["reused"] == 4
    assert statuses(env, env.store.latest_analysis(v["video_id"], only_ok=True))[:2] == ["located", "located"]


@needs_ffmpeg
def test_error_is_not_no_match_and_is_retried(env):
    _, rec = add_video(env, ANALYSIS_V1)
    muse = FakeMuse({"o0": "fire extinguisher"})
    env.loc.run(FakeSam(["miss", SamTimeout("TEST"), "miss"]), muse)
    assert statuses(env, rec)[0] == "error"
    sam = FakeSam(["hit"])
    env.loc.run(sam, muse)                                              # transient error retried, others kept
    assert len(sam.calls) == 1 and statuses(env, rec)[0] == "located"


@needs_ffmpeg
def test_daily_limit_defers_work(env, monkeypatch):
    monkeypatch.setenv("FIRERISK_SAM_DAILY_LIMIT", "2")
    _, rec = add_video(env, ANALYSIS_V1)
    muse = FakeMuse({"o0": "fire extinguisher", "o1": "cardboard box"})
    out = env.loc.run(FakeSam(), muse)
    assert out["requested"] == 2 and out["deferred"] == 2 and out["stopped"] == "daily_limit"
    monkeypatch.setenv("FIRERISK_SAM_DAILY_LIMIT", "10")
    out = env.loc.run(FakeSam(), muse)
    assert out["requested"] == 2                                        # pending work picked up, not lost


@needs_ffmpeg
@pytest.mark.parametrize("exc", [SamModelNotFound("TEST"), SamRateLimited("TEST")])
def test_access_or_rate_problem_stops_the_batch(env, exc):
    _, rec = add_video(env, ANALYSIS_V1)
    sam = FakeSam([exc])
    out = env.loc.run(sam, FakeMuse({"o0": "fire extinguisher", "o1": "cardboard box"}))
    assert len(sam.calls) == 1 and out["stopped"] == exc.kind and out["deferred"] == 3


@needs_ffmpeg
def test_interrupted_run_resumes(env):
    _, rec = add_video(env, ANALYSIS_V1)
    muse = FakeMuse({"o0": "fire extinguisher", "o1": "cardboard box"})
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] > 2
    out = env.loc.run(FakeSam(), muse, stop=stop)
    assert out["stopped"] == "cancelled" and out["requested"] == 2
    sam = FakeSam()
    env.loc.run(sam, muse)
    assert len(sam.calls) == 2 and statuses(env, rec)[:2] == ["located", "located"]


@needs_ffmpeg
def test_missing_video_file_is_a_frame_error_not_a_sam_call(env):
    v, rec = add_video(env, ANALYSIS_V1)
    env.store.path(v["video_id"]).unlink()
    sam = FakeSam()
    env.loc.run(sam, FakeMuse({"o0": "fire extinguisher"}))
    r = env.loc.item_result(rec["id"], "observation", 0)
    assert sam.calls == [] and r["status"] == "error" and r["frames"][0]["error_kind"] == "frame_extraction"


@needs_ffmpeg
def test_not_configured_sam_leaves_everything_pending(env):
    _, rec = add_video(env, ANALYSIS_V1)
    out = env.loc.run(FakeSam(configured=False), FakeMuse({"o0": "fire extinguisher"}))
    assert out["stopped"] == "not_configured" and statuses(env, rec)[0] == "not_checked"


@needs_ffmpeg
def test_background_processing_of_a_new_video_and_one_uploaded_meanwhile(env, monkeypatch):
    add_video(env, ANALYSIS_V1)
    gate = threading.Event()

    class SlowSam(FakeSam):
        def locate(self, jpeg, phrase):
            gate.wait(5)
            return super().locate(jpeg, phrase)
    muse = FakeMuse({"o0": "fire extinguisher", "o1": "cardboard box", "o2": ""})
    assert env.loc.start(SlowSam, lambda: muse) is True
    _, rec2 = add_video(env, ANALYSIS_V1, name="TEST second.mp4")      # arrives while the first job runs
    assert env.loc.start(SlowSam, lambda: muse) is False                # queued as another pass, not a 2nd thread
    t = env.loc.thread
    gate.set()
    t.join(20)
    assert statuses(env, rec2)[:2] == ["located", "located"]


@needs_ffmpeg
def test_dry_run_script_does_not_touch_the_database(env, monkeypatch, capsys):
    add_video(env, ANALYSIS_V1)
    digest = hashlib.sha256(env.db.read_bytes()).hexdigest()
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location("lvf", L.ROOT / "scripts" / "locate_video_findings.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(sys, "argv", ["x", "--dry-run", "--db", str(env.db)])
    assert mod.main() == 0
    assert hashlib.sha256(env.db.read_bytes()).hexdigest() == digest
    assert "phrase still to derive" in capsys.readouterr().out
