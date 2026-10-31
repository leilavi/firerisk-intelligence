"""Drawing links panel -> life-safety equipment (rule EQ-D1). TEST data only; secrets are TEST strings that must
never appear in what can leave the computer."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from openpyxl import Workbook

from firerisk.config import LOCAL_TZ
from firerisk.power_links import COLUMNS, describe, load, summary

SECRET_PANEL = "DB-TESTSECRET9"
SECRET_CIRCUIT = "TESTCIRC-77"


def write_links(path: Path, rows: list[dict], sheet: str = "Links") -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(COLUMNS)
    for r in rows:
        ws.append([r.get(c, "") for c in COLUMNS])
    wb.save(path)
    return path


def row(**k):
    base = {"confirmed": "Y", "floor": "B1", "panel_label": "", "asset_id": "", "feeds": "emergency_light", "count": 1}
    base.update(k)
    return base


# --- loader ---------------------------------------------------------------------------------------------
def test_only_confirmed_valid_rows_are_used_and_every_rejection_is_explained(tmp_path):
    p = write_links(tmp_path / "l.xlsx", [
        row(panel_label="DB-B1", asset_id="P-TESTDB01", count=6),                       # 2 used
        row(panel_label="db b1", feeds="exit_sign", count=2),                            # 3 used (same panel, no asset)
        row(confirmed="", panel_label="DB-F1", asset_id="P-TESTDB02"),                   # 4 not confirmed
        row(confirmed="N", panel_label="DB-F2"),                                         # 5 not confirmed
        row(floor="B2", panel_label="DB-X"),                                             # 6 bad floor
        row(feeds="lamp", panel_label="DB-X"),                                           # 7 bad feeds
        row(count="2.5", panel_label="DB-X"),                                            # 8 not whole
        row(count=-1, panel_label="DB-X"),                                               # 9 negative
        row(panel_label="", asset_id=""),                                                # 10 no panel/asset
        row(panel_label="DB-X", asset_id="P-UNKNOWN"),                                   # 11 unknown asset
        row(panel_label="MSB", feeds="sub_panel", fed_panel_label=""),                   # 12 sub_panel w/o target
        row(panel_label="MSB", feeds="sub_panel", fed_panel_label="msb"),                # 13 feeds itself
        row(asset_id="P-TESTDB01", feeds="sub_panel", fed_panel_label="DB-F1"),          # 14 no supplying label
    ])
    pl = load(p, known_assets={"P-TESTDB01", "P-TESTDB02"})
    assert [l.row for l in pl.links] == [2, 3]
    assert pl.rows_total == 13 and pl.rows_unconfirmed == 2
    assert [x["row"] for x in pl.problems] == list(range(6, 15))
    assert all(x["problem"] for x in pl.problems)
    assert pl.links[1].asset_id == "P-TESTDB01"                       # panel's asset carried to its other rows


def test_one_panel_linked_to_two_assets_is_rejected_not_guessed(tmp_path):
    p = write_links(tmp_path / "l.xlsx", [row(panel_label="DB-B1", asset_id="P-A"), row(panel_label="DB-B1", asset_id="P-B"),
                                          row(panel_label="DB-F1", asset_id="P-C")])
    pl = load(p)
    assert [l.panel for l in pl.links] == ["DBF1"] and len(pl.problems) == 2


def test_missing_broken_or_wrong_files_never_raise(tmp_path):
    assert load(tmp_path / "none.xlsx").present is False
    assert load(write_links(tmp_path / "w.xlsx", [row(panel_label="X")], sheet="Sheet1")).error.startswith("sheet")
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"not an xlsx")
    r = load(bad)
    assert r.present and r.error and r.links == []
    wb = Workbook(); wb.active.title = "Links"; wb.active.append(["confirmed", "floor"]); wb.save(tmp_path / "c.xlsx")
    assert "columns missing" in load(tmp_path / "c.xlsx").error


# --- dependency tree -------------------------------------------------------------------------------------
def test_dependents_follow_downstream_panels_aggregate_counts_and_survive_cycles(tmp_path):
    p = write_links(tmp_path / "l.xlsx", [
        row(panel_label="MSB", asset_id="P-MSB", feeds="sub_panel", fed_panel_label="DB-B1", count=""),
        row(panel_label="DB-B1", asset_id="P-DBB1", feeds="sub_panel", fed_panel_label="MSB", count=""),   # cycle
        row(panel_label="DB-B1", feeds="emergency_light", count=4),
        row(panel_label="DB-B1", feeds="emergency_light", count=2),
        row(panel_label="DB-B1", feeds="exit_sign", count=""),
        row(panel_label="MSB", floor="B1", feeds="fire_pump", count=1),
    ])
    pl = load(p)
    msb = {(d["equipment"], d["via"]): d for d in pl.dependents("P-MSB")}
    assert msb[("fire_pump", "direct")]["count"] == 1
    assert msb[("emergency_light", "through a downstream panel")]["count"] == 6
    assert msb[("exit_sign", "through a downstream panel")]["count_known"] is False
    db = {(d["equipment"], d["via"]) for d in pl.dependents("P-DBB1")}
    assert ("emergency_light", "direct") in db and ("fire_pump", "through a downstream panel") in db   # cycle ok
    assert pl.dependents("P-OTHER") == [] and pl.dependents(None) == []
    assert describe(pl.dependents("P-DBB1")).startswith("B1: 6 emergency lights")


def test_what_may_leave_the_computer_has_no_panel_labels_or_circuits(tmp_path):
    p = write_links(tmp_path / "l.xlsx", [row(panel_label=SECRET_PANEL, asset_id="P-TESTDB01", circuits=SECRET_CIRCUIT,
                                              note="TESTNOTE", source="TESTPAGE", count=3)])
    pl = load(p)
    out = json.dumps(summary(pl, asset_id="P-TESTDB01")) + json.dumps(summary(pl, floor="B1")) + describe(pl.dependents("P-TESTDB01"))
    for s in ("TESTSECRET", "TESTCIRC", "TESTNOTE", "TESTPAGE", "DB-"):
        assert s not in out
    assert '"count": 3' in out and '"floor": "B1"' in out


# --- rules -------------------------------------------------------------------------------------------------
def _fault(eid, asset, days_ago, now):
    from firerisk.models import Evidence
    return Evidence(eid, "asset_service", now - timedelta(days=days_ago), asset, "B1", "TEST panel tripped", "TEST",
                    "open", True, values={"service_type": "Repair needed"})


def test_rule_eq_d1_treats_a_panel_supplying_emergency_lighting_as_critical_only_when_confirmed(tmp_path):
    from firerisk.equipment import build_equipment_alerts
    now = datetime(2026, 10, 31, 9, tzinfo=LOCAL_TZ)
    ev = [_fault("TEST-1", "P-TESTDB01", 3, now)]
    plain = build_equipment_alerts(ev, [], now)[0]
    assert plain.severity == "watch" and not plain.critical and not plain.power_dependents

    unconfirmed = load(write_links(tmp_path / "u.xlsx", [row(confirmed="", panel_label="DB-B1", asset_id="P-TESTDB01")]))
    assert build_equipment_alerts(ev, [], now, power=unconfirmed)[0].severity == "watch"

    pl = load(write_links(tmp_path / "c.xlsx", [row(panel_label="DB-B1", asset_id="P-TESTDB01", count=6),
                                                row(panel_label="DB-B1", feeds="exit_sign", count=2)]))
    a = build_equipment_alerts(ev, [], now, power=pl)[0]
    assert a.critical and a.severity == "warning"
    assert "rule EQ-D1" in a.rules[0]["basis"]
    f = a.fields
    assert "B1: 6 emergency lights, 2 exit signs" in f["consequence"]
    assert any("on battery" in x and "B1" in x for x in f["preventive_actions"])
    assert any("Battery" in u for u in f["unknowns"])
    assert "DB" not in f["consequence"]                                  # no drawing label in the alert text


def test_link_to_the_fire_alert_of_the_supplied_floor_with_the_reason(tmp_path):
    from types import SimpleNamespace
    from firerisk.equipment import build_equipment_alerts, link_to_fire_alerts
    now = datetime(2026, 10, 31, 9, tzinfo=LOCAL_TZ)
    pl = load(write_links(tmp_path / "c.xlsx", [row(panel_label="DB-B1", asset_id="P-TESTDB01", count=6)]))
    eq = build_equipment_alerts([_fault("TEST-1", "P-TESTDB01", 3, now)], [], now, power=pl)
    b1 = SimpleNamespace(alert_id="ZONE-B1", zone="B1", evidence_ids=[], related_equipment=[])
    f2 = SimpleNamespace(alert_id="ZONE-F2", zone="F2", evidence_ids=[], related_equipment=[])
    link_to_fire_alerts(eq, [b1, f2], {})
    assert [l["fire_alert_id"] for l in eq[0].fire_links] == ["ZONE-B1"]
    assert "supplies life-safety equipment on this floor (B1: 6 emergency lights" in b1.related_equipment[0]["reasons"][0]
    assert f2.related_equipment == []


# --- Muse Spark tool -------------------------------------------------------------------------------------
def test_agentic_tool_gives_muse_spark_the_simplified_links_only(tmp_path):
    from firerisk.ai.agentic import TOOL_NAMES, EvidenceTools
    from firerisk.ai.redact import Redactor
    assert "get_fire_safety_supply" in TOOL_NAMES
    pl = load(write_links(tmp_path / "c.xlsx", [row(panel_label=SECRET_PANEL, asset_id="P-TESTDB01", count=6,
                                                    circuits=SECRET_CIRCUIT)]))
    tools = EvidenceTools({}, {}, Redactor(), power_links=pl)
    res, trace = tools.run("get_fire_safety_supply", json.dumps({"asset_id": "P-TESTDB01"}))
    assert res["links"][0]["supplies"][0] == {"floor": "B1", "equipment": "emergency_light", "count": 6,
                                              "count_known": True, "via": "direct"}
    assert "TESTSECRET" not in json.dumps(res) and "TESTCIRC" not in json.dumps(res)
    assert trace["returned"] == 1
    by_zone, _ = tools.run("get_fire_safety_supply", json.dumps({"zone": "B1"}))
    assert by_zone["links"][0]["asset_id"] == "P-TESTDB01"
    assert "error" in tools.run("get_fire_safety_supply", "{}")[0]
    none, _ = EvidenceTools({}, {}, Redactor()).run("get_fire_safety_supply", json.dumps({"zone": "B1"}))
    assert none["links"] == [] and "no confirmed" in none["note"]


# --- end to end through the API ------------------------------------------------------------------------
def test_api_uses_confirmed_links_and_reports_their_status(tmp_path, monkeypatch):
    from test_two_systems import make_client
    import firerisk.power_links as plm
    links = write_links(tmp_path / "power_links.xlsx", [
        row(floor="F3", panel_label=SECRET_PANEL, asset_id="P-ML900", count=4),
        row(confirmed="", floor="F3", panel_label=SECRET_PANEL, feeds="exit_sign", count=9),
        row(floor="Z9", panel_label="DB-X", count=1)])
    monkeypatch.setattr(plm, "LINKS_FILE", links)
    plm._CACHE.clear()
    api, c = make_client(tmp_path, monkeypatch, None, key="", hvac_fault=True)
    eq = {a["asset_id"]: a for a in c.get("/api/equipment-alerts").json()}
    a = eq["P-ML900"]
    assert a["severity"] == "warning" and a["critical"]                     # was Watch without the link (test above)
    assert a["power_dependents"] == [{"floor": "F3", "equipment": "emergency_light", "equipment_label": "emergency lights",
                                      "count": 4, "count_known": True, "via": "direct"}]
    st = c.get("/api/status").json()["power_links"]
    assert (st["confirmed_used"], st["unconfirmed"], st["rejected"]) == (1, 1, 1)
    body = json.dumps(c.get(f"/api/equipment-alerts/{a['alert_id']}").json())
    assert "TESTSECRET" not in body and "4 emergency lights" in body
    plm._CACHE.clear()


def test_floor_inventory_works_without_a_known_panel_and_mezzanine_counts_as_floor_1(tmp_path):
    pl = load(write_links(tmp_path / "l.xlsx", [
        row(floor="B1", panel_label="CP-B1", feeds="emergency_light", count=12),
        row(floor="B1", panel_label="CP-B1", feeds="exit_sign", count=7),
        row(floor="F1", panel_label="CP-F1", feeds="emergency_light", count=11),
        row(floor="Tầng lửng", panel_label="CP-F1", feeds="emergency_light", count=6),
        row(floor="Mái", panel_label="CP-R", feeds="exit_sign", count=7),
    ]))
    assert pl.problems == []
    inv = pl.floor_inventory("B1")
    assert {(e["equipment"], e["count"]) for e in inv["equipment"]} == {("emergency_light", 12), ("exit_sign", 7)}
    assert inv["supplying_panel_known"] is False
    assert pl.floor_inventory("F1")["equipment"][0]["count"] == 17
    assert pl.floor_inventory("Roof")["equipment"][0]["count"] == 7
    assert pl.floor_inventory("F3") == {}
    s = json.dumps(summary(pl, floor="B1"))
    assert "CP-B1" not in s and "CPB1" not in s and '"count": 12' in s


def test_supplying_asset_found_through_the_main_panel(tmp_path):
    pl = load(write_links(tmp_path / "l.xlsx", [
        row(floor="B1", panel_label="MAIN", asset_id="P-MAIN", feeds="sub_panel", fed_panel_label="CP-B1", count=""),
        row(floor="B1", panel_label="CP-B1", feeds="emergency_light", count=12)]))
    inv = pl.floor_inventory("B1")
    assert inv["supplying_panel_known"] and inv["equipment"][0]["supplying_assets"] == ["P-MAIN"]


def test_investigation_package_carries_the_floor_inventory_and_reanalyses_once(tmp_path):
    from types import SimpleNamespace
    from firerisk.ai.investigation import build_package, fingerprint
    now = datetime(2026, 10, 31, 9, tzinfo=LOCAL_TZ)
    alert = SimpleNamespace(alert_id="ZONE-B1", zone="B1", zone_label="Basement", severity="warning", severity_basis=[], links=[],
                            signal_ids=[], evidence_ids=[], context_ids=[], related_equipment=[], video_context=[],
                            life_safety={})
    fp0 = fingerprint(alert, {})
    pkg, _, _ = build_package(alert, [], {}, now)
    assert "life_safety_equipment_on_this_floor" not in pkg
    pl = load(write_links(tmp_path / "l.xlsx", [row(panel_label=SECRET_PANEL, count=12)]))
    alert.life_safety = pl.floor_inventory("B1")
    pkg, _, _ = build_package(alert, [], {}, now)
    ls = pkg["life_safety_equipment_on_this_floor"]
    assert ls["equipment"][0]["count"] == 12 and ls["supplying_panel_known"] is False
    assert "TESTSECRET" not in json.dumps(pkg)
    assert fingerprint(alert, {}) != fp0 and fingerprint(alert, {}) == fingerprint(alert, {})
