"""Sample mode (fictional building for judges and fresh clones): firerisk/sample.py."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from firerisk import sample

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def built(tmp_path, monkeypatch):
    base = sample.build_sample(tmp_path / "sample")
    for k, v in sample.sample_env(base).items():
        monkeypatch.setenv(k, v)
    import firerisk.rules.scope as scope
    monkeypatch.setattr(scope, "BRANCH_PREFIX", sample.PREFIX)     # config was imported before the sample env
    import firerisk.power_links as pl
    monkeypatch.setattr(pl, "LINKS_FILE", base / "power_links.xlsx")
    return base


def test_every_data_path_points_at_the_sample_folder_and_drive_is_off(tmp_path):
    env = sample.sample_env(tmp_path)
    for k, v in env.items():
        assert "private" not in v, k
    assert env["FIRERISK_DRIVE_EXPORT_URL"] == "" and env["FIRERISK_DEMO_MODE"] == "0"
    for key in ("FIRERISK_SNAPSHOT_DIR", "FIRERISK_DB", "FIRERISK_POWER_LINKS", "FIRERISK_SITE_CONFIG", "FIRERISK_LOG_DIR",
                "FIRERISK_MEDIA_DIR", "FIRERISK_VIDEO_DIR", "FIRERISK_VIDEO_INBOX", "FIRERISK_FRAMES_DIR"):
        assert Path(env[key]).is_relative_to(tmp_path), key


def test_app_modules_read_only_sample_paths_in_a_fresh_process(tmp_path):
    env = {**os.environ, **sample.sample_env(tmp_path)}
    code = ("import json; from firerisk import config, api, power_links, localize, media, video, serve; "
            "print(json.dumps([config.BUILDING_NAME, str(config._SITE_FILE), str(api.SNAPSHOT_DIR), str(api.DB_PATH), "
            "str(power_links.LINKS_FILE), str(localize.FRAMES_DIR), str(media.MEDIA_DIR), str(video.VIDEO_DIR), "
            "str(video.INBOX_DIR), str(serve.LOG_DIR)]))")
    sample.build_sample(tmp_path)
    out = subprocess.run([sys.executable, "-c", code], env=env, cwd=ROOT, capture_output=True, text=True, check=True)
    vals = json.loads(out.stdout.strip().splitlines()[-1])
    assert vals[0] == sample.BUILDING
    assert all(Path(v).is_relative_to(tmp_path) for v in vals[1:]), vals


def test_the_rule_engine_finds_the_designed_scenario(built):
    from firerisk.engine import run_analysis
    res = run_analysis(built / "snapshot")
    rules = {s.rule_id for s in res.signals}
    assert {"R1_WATER_ELECTRICAL", "R2_DETECTION", "R3_MOTOR", "R4_BACKUP_POWER", "R6_SMOKE_CONTROL", "R7_PA",
            "R8_METER_ANOMALY"} <= rules
    b1 = next(a for a in res.alerts if a.zone == "B1")
    assert b1.severity == "high" and b1.impact_chain
    assert {e.asset_id for e in res.equipment_alerts} >= {"P-BG.TTC046", "P-BG.TTC071", "P-BG.TTC076", "P-BG.TTC217"}
    assert not [s for s in res.source_status if s.get("error")]
    assert res.power_links and len(res.power_links.links) == 25 and not res.power_links.problems
    assert not res.data_quality


def test_every_vietnamese_record_text_has_a_sample_translation(built):
    from firerisk.ai.translate import Translator, display_strings, needs
    from firerisk.engine import run_analysis
    res = run_analysis(built / "snapshot")
    tr = Translator(built / "t.db")
    missing = [s for s in display_strings(res) if needs(s) and tr.en(s)[0] is None]
    assert not missing, missing[:5]
    assert tr.en(sample.EN and next(iter(sample.EN)))[1] == "sample_translation"


def test_sample_translations_are_off_outside_sample_mode(built, monkeypatch):
    from firerisk.ai.translate import Translator
    monkeypatch.setenv("FIRERISK_SAMPLE_MODE", "0")
    tr = Translator(built / "t2.db")
    assert tr.en(next(iter(sample.EN))) == (None, None)
