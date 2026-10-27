"""Tests for NEW capabilities: hazard tagging, pathway rules, correlation, zone aggregation."""

from datetime import datetime, timedelta

from firerisk.config import LOCAL_TZ
from firerisk.correlation import aggregate_alerts, build_links
from firerisk.hazards.pathways import evaluate
from firerisk.hazards.tagging import tag_evidence, tag_text
from firerisk.models import Evidence

NOW = datetime(2026, 10, 27, 14, 0, tzinfo=LOCAL_TZ)


def ev(eid, kind, text, days_ago, asset=None, zone="B1", is_open=False, values=None, status=None):
    return Evidence(evidence_id=eid, kind=kind, timestamp=NOW - timedelta(days=days_ago), asset_id=asset, zone=zone,
                    title=text, text=text, status=status, is_open=is_open, values=values or {})


def tags(text):
    return {t["tag"] for t in tag_text(text)}


def test_tagging_distinguishes_fire_alarm_from_burnt_motor():
    assert "fire_detection" in tags("Hệ thống báo cháy trung tâm báo lỗi")
    assert "burnt_overheat" not in tags("Hệ thống báo cháy trung tâm báo lỗi")
    assert "burnt_overheat" in tags("Bể bạc đạn, cháy mô tơ")
    assert "fire_event" not in tags("Kiểm tra bình chữa cháy định kỳ")


def test_tagging_water_ingress_in_electrical_room():
    t = tags("Trời mưa lớn phòng MBA,MSB có hiện tượng nước thấm vào bên trong")
    assert {"water_ingress", "electrical_room"} <= t


def test_passing_checklist_is_context_not_fault():
    chk = ev("insp:C-tuBC", "inspection_check", "", 0, asset="P-BG.TTC009", is_open=False,
             values={"checklist": "C-tuBC"}, status="Đạt")
    tag_evidence([chk])
    assert {t["tag"] for t in chk.tags} == {"checklist_pass"}


def test_open_water_ingress_in_electrical_room_is_high():
    items = tag_evidence([ev("inc:1", "incident", "Phòng MBA, MSB thấm nước", 19, is_open=True)])
    sig = [s for s in evaluate(items, NOW) if s.rule_id == "R1_WATER_ELECTRICAL"][0]
    assert sig.severity == "high" and sig.is_open


def test_recurring_detection_fault_is_warning():
    items = tag_evidence([
        ev("a:1", "asset_service", "Báo lỗi module giám sát báo nhiệt trục AB tầng hầm", 19, asset="P-BG.TTC009"),
        ev("i:2", "incident", "Mô đun GS báo nhiệt tầng hầm báo lỗi", 8),
    ])
    sig = [s for s in evaluate(items, NOW) if s.rule_id == "R2_DETECTION"][0]
    assert sig.severity == "warning" and set(sig.evidence_ids) == {"a:1", "i:2"}


def test_open_failure_after_burnt_motor_is_high():
    items = tag_evidence([
        ev("a:1", "asset_service", "Bể bạc đạn, cháy mô tơ | Quấn lại mô tơ", 90, asset="P-BG.TTC167"),
        ev("a:2", "asset_service", "Máy bơm thổi khí AB-01A hư phần cơ khí bị kẹt cứng", 6, asset="P-BG.TTC167", is_open=True),
    ])
    sig = [s for s in evaluate(items, NOW) if s.rule_id == "R3_MOTOR"][0]
    assert sig.severity == "high"


def test_no_rule_fires_on_routine_maintenance():
    items = tag_evidence([ev("a:1", "asset_service", "Bảo trì quạt hút khói EAF1-EAF2 | Kiểm tra vệ sinh", 10,
                             asset="P-BG.TTC005")])
    assert evaluate(items, NOW) == []


def test_compound_rule_raises_one_level_but_never_to_emergency():
    items = tag_evidence([
        ev("a:1", "asset_service", "Máy bơm thổi khí kẹt cứng", 3, asset="P-BG.TTC167", is_open=True),   # warning
        ev("a:2", "asset_service", "Phao nước bể PCCC đứt dây", 5, asset="P-BG.TTC072", is_open=False),  # watch
    ])
    sigs = evaluate(items, NOW)
    alerts = aggregate_alerts(sigs, {e.evidence_id: e for e in items}, NOW)
    assert alerts[0].severity == "high"
    items2 = tag_evidence([
        ev("b:1", "incident", "Phòng MSB thấm nước", 3, is_open=True),                                   # high
        ev("b:2", "asset_service", "Máy bơm thổi khí kẹt cứng", 3, asset="P-BG.TTC167", is_open=True),
    ])
    a2 = aggregate_alerts(evaluate(items2, NOW), {e.evidence_id: e for e in items2}, NOW)
    assert a2[0].severity == "high"


def test_links_explain_their_reason_and_meter_dependency():
    blower = ev("a:2", "asset_service", "Máy bơm thổi khí kẹt cứng", 6, asset="P-BG.TTC167", is_open=True)
    episode = ev("episode:P-BG.TTC226:x", "meter_episode", "drop", 6, asset="P-BG.TTC226")
    tag_evidence([blower])
    links = build_links([blower, episode])
    assert links and "measured_by_meter" in links[0]["types"] and links[0]["reasons"]
