"""Chain of effects across equipment (impact_chain.py). TEST data only."""

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

from firerisk.config import LOCAL_TZ
from firerisk.impact_chain import build, evidence_ids
from firerisk.models import Evidence
from firerisk.power_links import load

from test_power_links import _building_rows, write_links

NOW = datetime(2026, 11, 1, 9, tzinfo=LOCAL_TZ)


def ev(eid, kind, days, asset, title, open_=True, status="open", values=None):
    e = Evidence(eid, kind, NOW - timedelta(days=days), asset, "B1", title, "TEST", status, open_, values=values or {})
    return e


def alert(ids, zone="B1", related=()):
    return SimpleNamespace(alert_id=f"ZONE-{zone}", zone=zone, evidence_ids=list(ids), context_ids=[],
                           related_equipment=list(related))


def _index(*items):
    from firerisk.hazards.tagging import tag_evidence
    tag_evidence(list(items))
    return {e.evidence_id: e for e in items}


def test_seepage_in_the_msb_room_reaches_the_escape_lighting_and_shows_the_weak_generator_batteries(tmp_path):
    pl = load(write_links(tmp_path / "l.xlsx", _building_rows()))
    seep = ev("TEST-SEEP", "incident", 24, None, "Phòng MBA, MSB thấm nước")
    batt = ev("TEST-BATT", "asset_service", 33, "P-BG.TTC217", "Bình ắc quy yếu, cần thay",
              values={"service_type": "Repair needed"})
    idx = _index(seep, batt)
    ch = build(alert(["TEST-SEEP"]), idx, [], NOW, pl)
    assert ch["chains"], ch
    c = ch["chains"][0]
    assert c["start"] in ("msb", "transformer") and c["trigger"][0]["matched_by_name"] is True
    keys = [s["node"] for s in c["steps"]]
    assert keys[-1] == "evacuation" and "ats" in keys and "escape_lighting" in keys
    ats = next(s for s in c["steps"] if s["node"] == "ats")
    dep = [d for d in ats["depends_on"] if d["node"] == "gen_batteries"]
    assert dep and dep[0]["conditions"][0]["evidence_id"] == "TEST-BATT"
    assert "generator is started by these batteries" in dep[0]["why"]
    lights = next(s for s in c["steps"] if s["node"] == "escape_lighting")
    assert "36 on all floors" in lights["label"] and "19 on B1" in lights["label"]
    assert all(s["to_next"] for s in c["steps"][:-1]) and c["steps"][-1]["to_next"] is None
    assert any("fire pump" in g for g in ch["not_established"])
    assert any("batteries" in g for g in ch["not_established"])
    assert set(evidence_ids(ch)) == {"TEST-SEEP", "TEST-BATT"}


def test_without_the_power_table_the_chain_stops_where_the_links_are_not_recorded(tmp_path):
    seep = ev("TEST-SEEP", "incident", 5, "P-BG.TTC046", "MSB water")
    ch = build(alert(["TEST-SEEP"]), _index(seep), [], NOW, None)
    nodes = {s["node"] for c in ch["chains"] for s in c["steps"]}
    assert "escape_lighting" not in nodes and "ats" not in nodes        # not assumed without the confirmed table
    assert "basement_fire" in nodes


def test_no_chain_when_nothing_in_the_alert_has_a_recorded_problem(tmp_path):
    old = ev("TEST-OLD", "incident", 300, "P-BG.TTC046", "MSB old", open_=False, status="closed")
    other = ev("TEST-X", "incident", 2, "P-BG.TTC046", "MSB now")
    assert build(alert(["TEST-OLD"]), _index(old, other), [], NOW, None) == {}
    assert build(alert([]), _index(other), [], NOW, None) == {}


def test_linked_equipment_alert_starts_a_chain_and_motor_reaches_fire_detection():
    blower = ev("TEST-BLOW", "asset_service", 10, "P-BG.TTC167", "Máy thổi khí kẹt, cháy động cơ",
                values={"service_type": "Repair needed"})
    det = ev("TEST-DET", "incident", 12, "P-BG.TTC009", "Module báo nhiệt lỗi")
    ea = SimpleNamespace(alert_id="EQ-1", evidence_ids=["TEST-BLOW"])
    ch = build(alert([], related=[{"equipment_alert_id": "EQ-1"}]), _index(blower, det), [ea], NOW, None)
    c = ch["chains"][0]
    assert c["start"] == "xlnt_blower"
    steps = [s["node"] for s in c["steps"]]
    assert steps[:2] == ["xlnt_blower", "basement_fire"] and steps[-1] == "evacuation"
    assert any(s["node"] == "fire_alarm" and s["conditions"][0]["evidence_id"] == "TEST-DET" for s in c["steps"]) \
        or any(s["node"] == "fire_alarm" for ch_ in ch["chains"] for s in ch_["steps"])
    json.dumps(ch)


def test_muse_spark_gets_the_chain_with_aliases_and_its_story_is_validated(tmp_path):
    from firerisk.ai.investigation import SCHEMA, build_package, fingerprint, map_back, validate
    pl = load(write_links(tmp_path / "l.xlsx", _building_rows()))
    seep = ev("TEST-SEEP", "incident", 24, None, "Phòng MBA, MSB thấm nước")
    batt = ev("TEST-BATT", "asset_service", 33, "P-BG.TTC217", "Bình ắc quy yếu",
              values={"service_type": "Repair needed"})
    idx = _index(seep, batt)
    a = SimpleNamespace(alert_id="ZONE-B1", zone="B1", zone_label="Basement", severity="warning", severity_basis=[],
                        links=[], signal_ids=[], evidence_ids=["TEST-SEEP"], context_ids=[], related_equipment=[],
                        video_context=[], life_safety={})
    fp0 = fingerprint(a, idx)
    a.impact_chain = build(a, idx, [], NOW, pl)
    assert fingerprint(a, idx) != fp0
    pkg, _, alias_to_real = build_package(a, [], idx, NOW)
    s = json.dumps(pkg, ensure_ascii=False)
    assert "chain_of_effects" in pkg and "TEST-SEEP" not in s and "TEST-BATT" not in s
    roles = {alias_to_real[e["evidence_id"]]: e["role"] for e in pkg["evidence"]}
    assert roles == {"TEST-SEEP": "finding", "TEST-BATT": "chain_of_effects"}     # dependency record is citable
    assert "impact_story" in SCHEMA["schema"]["required"]
    batt_alias = next(k for k, v in alias_to_real.items() if v == "TEST-BATT")
    result = {"impact_story": {"headline": "h", "story": "s", "not_established": [], "steps": [
        {"text": "batteries weak", "basis": "supported_by_records", "evidence_ids": [batt_alias]},
        {"text": "made up", "basis": "supported_by_records", "evidence_ids": ["E99"]},
        {"text": "ATS switches", "basis": "link_from_rules", "evidence_ids": []}]}}
    v = validate(map_back(result, alias_to_real), alias_to_real.values())
    st = result["impact_story"]["steps"]
    assert st[0]["evidence_ids"] == ["TEST-BATT"] and st[1]["basis"] == "hypothesis" and st[1]["downgraded"]
    assert v["invalid_evidence_ids"] == ["E99"]


def test_whole_building_alert_shows_chains_from_every_floor_and_the_announcement_fault(tmp_path):
    pl = load(write_links(tmp_path / "l.xlsx", _building_rows()))
    seep = ev("TEST-SEEP", "incident", 24, "P-BG.TTC046", "MSB water")
    pa = ev("TEST-PA", "incident", 5, None, "Hệ thống loa thông báo không hoạt động")
    idx = _index(seep, pa)
    b1 = alert(["TEST-SEEP"])
    bw = alert(["TEST-PA"], zone="Building")
    ch = build(bw, idx, [], NOW, pl, [b1, bw])
    starts = {c["start"] for c in ch["chains"]}
    assert {"msb", "pa_system"} <= starts
    lights = next(s for c in ch["chains"] for s in c["steps"] if s["node"] == "escape_lighting")
    assert "B1 19" in lights["label"] and "F2 17" in lights["label"]
    assert {c["start"] for c in build(b1, idx, [], NOW, pl, [b1, bw])["chains"]} == {"msb"}   # floor view unchanged
