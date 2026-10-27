"""Tests for business rules PORTED from the pre-existing skill v2.2 (no real data needed)."""

from datetime import date, datetime, timedelta

from firerisk.config import LOCAL_TZ
from firerisk.models import Evidence
from firerisk.rules import meters as M
from firerisk.rules.scope import classify_text_quality, in_scope


def reading(meter, day, value, hour=6, idx=0):
    ts = datetime.combine(day, datetime.min.time(), tzinfo=LOCAL_TZ).replace(hour=hour)
    return Evidence(evidence_id=f"m:{meter}:{day}:{idx}", kind="meter_reading", timestamp=ts, asset_id=meter,
                    zone="B1", title="", text="", status=None, is_open=None, values={"reading": value})


def series(meter, start, increments, start_value=1000):
    out, v = [], start_value
    out.append(reading(meter, start, v))
    for i, inc in enumerate(increments, start=1):
        v += inc
        out.append(reading(meter, start + timedelta(days=i), v))
    return out


# ---- scope (skill §2.3) ----
def test_scope_keeps_configured_building_and_p_assets():
    from firerisk.config import BRANCH_PREFIX
    assert in_scope(branch=BRANCH_PREFIX)
    assert in_scope(location=f"{BRANCH_PREFIX}-A-B1-Chung-")
    assert in_scope(asset_id="P-BG.TTC076")
    assert not in_scope(branch="SITE-2", location="SITE-2-B-F3-[Operator]-VP", asset_id="E-ML105")


def test_test_record_flags_and_safety_exception():
    assert "test_record" in classify_text_quality("Chỉ test hệ thống")
    flags = classify_text_quality("Test thang máy khẩn")
    assert "test_record" in flags and "safety_test_record" in flags
    assert "placeholder_text" in classify_text_quality("Hãy mô tả chi tiết vấn đề")
    assert classify_text_quality("Kiểm tra định kỳ") == []          # 'Kiểm tra' must not match 'test'


# ---- daily consumption (skill Stage 2B) ----
def test_consumption_assigned_to_previous_day_and_multiplier():
    rs = series("P-BG.TTC076", date(2026, 10, 1), [21, 22])   # raw x100 = kWh (EVN)
    cal, issues = M.daily_consumption(rs, "P-BG.TTC076")
    assert [d.day for d in cal] == [date(2026, 10, 1), date(2026, 10, 2)]
    assert [d.value for d in cal] == [2100, 2200]
    assert issues == []


def test_gap_is_averaged_not_assigned_to_one_day():
    rs = [reading("P-BG.TTC172", date(2026, 10, 1), 100), reading("P-BG.TTC172", date(2026, 10, 4), 130)]
    cal, _ = M.daily_consumption(rs, "P-BG.TTC172")
    assert [d.value for d in cal] == [10, 10, 10]
    assert all(d.flag == "averaged_gap" for d in cal)


def test_decreasing_reading_excluded_and_reported():
    rs = [reading("P-BG.TTC172", date(2026, 10, 1), 100), reading("P-BG.TTC172", date(2026, 10, 2), 90)]
    cal, issues = M.daily_consumption(rs, "P-BG.TTC172")
    assert cal[0].value is None and cal[0].flag == "negative_excluded"
    assert issues[0]["type"] == "decreasing_reading"


def test_duplicate_same_day_reported():
    rs = [reading("P-BG.TTC172", date(2026, 10, 1), 100), reading("P-BG.TTC172", date(2026, 10, 1), 101, hour=9, idx=1),
          reading("P-BG.TTC172", date(2026, 10, 2), 110)]
    _, issues = M.daily_consumption(rs, "P-BG.TTC172")
    assert issues[0]["type"] == "duplicate_same_day"


# ---- spikes and episodes (skill §5A) ----
def test_spike_up_and_down_detected_with_min_delta():
    incs = [20, 21, 19, 20, 22, 21, 20, 19, 21, 20, 20, 21, 19, 20, 21, 20] + [40, 41] + [20, 20] + [5]
    rs = series("P-BG.TTC076", date(2026, 9, 1), incs)
    cal, _ = M.daily_consumption(rs, "P-BG.TTC076")
    M.detect_spikes(cal, "P-BG.TTC076")
    spikes = [(d.day, d.spike) for d in cal if d.spike]
    assert spikes == [(date(2026, 9, 17), "up"), (date(2026, 9, 18), "up"), (date(2026, 9, 21), "down")]
    eps = M.episodes(cal, "P-BG.TTC076")
    assert [(e.direction, e.days) for e in eps] == [("up", 2), ("down", 1)]


def test_small_change_below_min_delta_is_not_a_spike():
    # XLNT meter min_delta = 4 raw units; a +3 change on a tiny baseline is ignored
    incs = [2] * 16 + [5]
    rs = series("P-BG.TTC226", date(2026, 9, 1), incs)
    cal, _ = M.daily_consumption(rs, "P-BG.TTC226")
    M.detect_spikes(cal, "P-BG.TTC226")
    assert not any(d.spike for d in cal)


def test_msb_only_spike_labelled_reading_error():
    msb = M.Episode("P-BG.TTC071", "up", date(2026, 10, 3), date(2026, 10, 3), 1, 250000, 190000, 31.6, [])
    out = M.label_episodes([msb], {"P-BG.TTC071": [msb], "P-BG.TTC076": []}, {})
    assert out[0].label == "Reading error (MSB only)"


def test_increase_with_high_vehicle_count_is_reasonable():
    ep = M.Episode("P-BG.TTC076", "up", date(2026, 9, 2), date(2026, 9, 2), 1, 2600, 2000, 30.0, [])
    veh = {date(2026, 9, d): 300 for d in range(1, 30)}
    veh[date(2026, 9, 2)] = 1400
    out = M.label_episodes([ep], {"P-BG.TTC076": [ep]}, veh)
    assert out[0].label == "Reasonable variation"


def test_long_episode_is_evidence_based_risk():
    ep = M.Episode("P-BG.TTC226", "down", date(2026, 10, 1), date(2026, 10, 3), 3, 2, 9, -77.8, [])
    out = M.label_episodes([ep], {"P-BG.TTC226": [ep]}, {date(2026, 10, 1): 300})
    assert out[0].label == "Evidence-based risk"
