"""Two alert systems (building equipment / fire risk) and automatic Muse Spark analysis.

TEST fixture data only. Muse Spark is replaced by a FAKE HTTP transport (clearly not the real API).
Covers the required scenarios: equipment alerts still work, overview has both groups, not every equipment anomaly
becomes a fire-risk alert, cited evidence is validated, automatic analysis runs, reloads do not duplicate AI calls,
API errors/timeouts do not break alerts, fallback explanation, AI cannot change the rule level, origin labels,
no invented data, old endpoints still respond.
"""

import importlib
import io
import json
import urllib.error

import pytest
from fastapi.testclient import TestClient

from fixtures import build_snapshot


class FakeMuse:
    """Counts calls; answers with a v3-shaped result citing one real alias (E01) and one invented ID (E99)."""

    def __init__(self, mode="ok", ai_priority="emergency"):
        self.mode, self.calls, self.ai_priority = mode, 0, ai_priority

    def opener(self, req, timeout=0):
        self.calls += 1
        body = json.loads(req.data)
        if self.mode == "timeout":
            raise TimeoutError("timed out")
        if self.mode == "500":
            raise urllib.error.HTTPError(req.full_url, 500, "err", {}, io.BytesIO(b'{"error":"x"}'))
        answer = {
            "summary": "TEST FAKE RESPONSE", "situation": "TEST situation",
            "observed_facts": [{"statement": "TEST fact", "evidence_ids": ["E01", "E99"]}],
            "hypotheses": [], "scenarios": [{"scenario": "TEST scenario", "how_it_could_develop": "x",
                                             "plausibility": "possible", "supporting_evidence_ids": ["E01"],
                                             "weakening_evidence_ids": ["E77"], "what_would_confirm": "x"}],
            "escalation_pathway": [],
            "risk_assessment": {"ai_priority": self.ai_priority, "agrees_with_rule_severity": False, "rationale": "x"},
            "missing_information": [], "recommended_actions": [], "limitations": ["TEST limitation"],
            "uncertainty": "x"}
        out = json.dumps({"model": body["model"], "choices": [{"message": {"content": json.dumps(answer)}}],
                          "usage": {"total_tokens": 1}}).encode()

        class R(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return R(out)


def make_client(tmp_path, monkeypatch, fake: FakeMuse | None, key="TEST-KEY", **fixture):
    snap = build_snapshot(tmp_path / "snap", **fixture)
    monkeypatch.setenv("FIRERISK_SNAPSHOT_DIR", str(snap))
    monkeypatch.setenv("FIRERISK_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("MODEL_API_KEY", key)
    monkeypatch.setenv("META_API_BASE_URL", "http://fake-muse.invalid/v1")
    import firerisk.api as api
    api = importlib.reload(api)
    from firerisk.ai.muse import MuseClient, MuseConfig
    if fake:
        api.state.ai.client_factory = lambda: MuseClient(
            MuseConfig(api_key="TEST-KEY", base_url="http://fake-muse.invalid/v1", timeout_s=2), opener=fake.opener)
    return api, TestClient(api.app)


# 1, 13 -------------------------------------------------------------------------------------------------
def test_equipment_alerts_work_and_old_endpoints_still_respond(tmp_path, monkeypatch):
    api, c = make_client(tmp_path, monkeypatch, None, key="")
    eq = c.get("/api/equipment-alerts").json()
    blower = next(a for a in eq if a["asset_id"] == "P-BG.TTC167")
    assert blower["rules"][:2] == ["EQ1_OPEN_FAULT", "EQ2_OVERDUE"] and blower["severity"] == "warning"
    d = c.get(f"/api/equipment-alerts/{blower['alert_id']}").json()
    for k in ("problem", "evidence", "comparison", "possible_causes", "consequence", "risk_chain", "trigger_condition",
              "urgency", "preventive_actions", "deadline", "closure_condition", "confidence", "sources", "cause_status"):
        assert k in d["fields"], k                     # skill §8 fields
    assert d["fire_alerts"] and d["fire_alerts"][0]["alert_id"] == "ZONE-B1"
    for path in ("/api/status", "/api/alerts", "/api/assets", "/api/events", "/api/trends", "/api/quality",
                 "/api/media", "/api/zones", "/api/fire-alerts", "/api/overview"):
        assert c.get(path).status_code == 200, path
    st = c.post(f"/api/alerts/{blower['alert_id']}/status", json={"status": "investigating", "note": "TEST"}).json()
    assert st["status"] == "investigating"


# 2 ------------------------------------------------------------------------------------------------------
def test_overview_has_two_separate_groups(tmp_path, monkeypatch):
    api, c = make_client(tmp_path, monkeypatch, None, key="")
    o = c.get("/api/overview").json()
    assert o["equipment"]["active"] >= 1 and o["fire"]["active"] >= 1
    assert all(x["kind"] == "equipment" for x in o["equipment"]["top"])
    assert all(x["kind"] == "fire" for x in o["fire"]["needs_check"] + o["fire"]["others"])
    assert o["fire"]["ai_configured"] is False


# 4 ------------------------------------------------------------------------------------------------------
def test_ordinary_equipment_fault_does_not_create_fire_alert(tmp_path, monkeypatch):
    api, c = make_client(tmp_path, monkeypatch, None, key="", hvac_fault=True)
    eq = {a["asset_id"]: a for a in c.get("/api/equipment-alerts").json()}
    assert "P-ML900" in eq and eq["P-ML900"]["severity"] == "watch" and not eq["P-ML900"]["fire_links"]
    fire_zones = {a["zone"] for a in c.get("/api/alerts").json()}
    assert "F3" not in fire_zones


def test_meter_findings_never_set_fire_level():
    from datetime import datetime, timedelta
    from firerisk.config import LOCAL_TZ
    from firerisk.correlation import aggregate_alerts
    from firerisk.equipment import build_equipment_alerts
    from firerisk.models import Evidence, Signal
    now = datetime(2026, 10, 27, 12, tzinfo=LOCAL_TZ)
    ep = Evidence("ep:1", "meter_episode", now - timedelta(days=2), "P-BG.TTC078", "F2", "TEST episode", "", None,
                  None, values={"label": "Evidence-based risk"}, flags=["derived"])
    sig = Signal("R8_METER_ANOMALY:P-BG.TTC078", "R8_METER_ANOMALY", "electrical_anomaly", "F2", "P-BG.TTC078",
                 "warning", "TEST", "TEST", ["ep:1"], ep.timestamp, ep.timestamp, False, "PORTED")
    eq = build_equipment_alerts([ep], [sig], now)
    assert [a.severity for a in eq] == ["warning"]               # skill §5A.8 level kept
    assert aggregate_alerts([], {"ep:1": ep}, now) == []          # engine passes fire-pathway signals only


# 5, 6, 7, 10 ----------------------------------------------------------------------------------------------
def test_auto_analysis_runs_once_validates_citations_and_cannot_change_level(tmp_path, monkeypatch):
    fake = FakeMuse(ai_priority="emergency")
    api, c = make_client(tmp_path, monkeypatch, fake)
    alerts = c.get("/api/alerts").json()           # first analysis -> fire alerts queued automatically
    assert api.state.ai.wait_idle(20)
    calls_after_first = fake.calls
    assert calls_after_first == len(alerts)          # every fire alert analysed once
    for _ in range(3):                              # reloads and an unchanged re-analysis: no new AI calls
        c.get("/api/alerts"); c.get("/api/overview"); c.get(f"/api/alerts/{alerts[0]['alert_id']}")
    c.post("/api/refresh")
    assert api.state.ai.wait_idle(20)
    assert fake.calls == calls_after_first
    d = c.get("/api/alerts/ZONE-B1").json()
    assert d["ai_status"]["code"] == "done" and d["ai_status"]["label"] == "AI Analysis Complete"
    assert not d["ai_status"]["fallback"]
    inv = d["investigation"]
    assert inv["trigger"] == "auto" and inv["api_mode"] == "test"
    assert "E99" in inv["validation"]["invalid_evidence_ids"] and "E77" in inv["validation"]["invalid_evidence_ids"]
    cited = inv["result"]["observed_facts"][0]["evidence_ids"] + inv["result"]["scenarios"][0]["supporting_evidence_ids"]
    assert cited and all(i in api.state.get().evidence for i in cited)     # only real evidence IDs remain
    assert d["alert"]["severity"] == "high"          # AI said emergency; the rule level stays
    assert inv["result"]["risk_assessment"]["ai_priority"] == "emergency"


def test_user_reanalysis_is_queued_even_when_current(tmp_path, monkeypatch):
    fake = FakeMuse()
    api, c = make_client(tmp_path, monkeypatch, fake)
    c.get("/api/alerts"); api.state.ai.wait_idle(20)
    n = fake.calls
    r = c.post("/api/alerts/ZONE-B1/investigate").json()
    assert r["queued"] is True
    api.state.ai.wait_idle(20)
    assert fake.calls == n + 1


def test_changed_evidence_triggers_new_analysis(tmp_path, monkeypatch):
    fake = FakeMuse()
    api, c = make_client(tmp_path, monkeypatch, fake)
    c.get("/api/alerts"); api.state.ai.wait_idle(20)
    n = fake.calls
    res = api.state.get()
    b1 = next(a for a in res.alerts if a.alert_id == "ZONE-B1")
    e = res.evidence[b1.evidence_ids[0]]
    e.status = "TEST changed status"                # simulate a status change in the source
    api.state.ai.schedule(res)
    api.state.ai.wait_idle(20)
    assert fake.calls == n + 1


# 8, 9 ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["timeout", "500"])
def test_api_failure_keeps_alerts_and_uses_rule_explanation(tmp_path, monkeypatch, mode):
    fake = FakeMuse(mode=mode)
    api, c = make_client(tmp_path, monkeypatch, fake)
    monkeypatch.setattr("firerisk.ai.muse.time.sleep", lambda s: None)
    c.get("/api/alerts"); assert api.state.ai.wait_idle(30)
    d = c.get("/api/alerts/ZONE-B1").json()
    assert d["alert"]["severity"] == "high" and d["evidence"]
    st = d["ai_status"]
    assert st["code"] == "failed" and st["fallback"] and st["fallback_label"] == "Rule-Based Explanation"
    assert d["rule_explanation"] and all(x["origin"] == "rule" for x in d["rule_explanation"])
    assert d["rule_explanation"][0]["risk_chain"]
    n = fake.calls
    c.post("/api/refresh"); api.state.ai.wait_idle(10)
    assert fake.calls == n                           # no immediate automatic retry (15-minute rule)


def test_not_configured_shows_rule_explanation_without_calls(tmp_path, monkeypatch):
    api, c = make_client(tmp_path, monkeypatch, None, key="")
    d = c.get("/api/alerts/ZONE-B1").json()
    assert d["ai_status"]["code"] == "not_analysed" and d["ai_status"]["fallback"]
    assert "not configured" in (d["ai_status"]["not_queued_reason"] or "")
    assert d["investigation"] is None


def test_daily_limit_stops_automatic_calls(tmp_path, monkeypatch):
    fake = FakeMuse()
    monkeypatch.setenv("FIRERISK_AI_DAILY_LIMIT", "1")
    api, c = make_client(tmp_path, monkeypatch, fake)
    c.get("/api/alerts"); api.state.ai.wait_idle(20)
    assert fake.calls == 1


# 11, 12 ---------------------------------------------------------------------------------------------------
def test_origin_labels_and_no_invented_values(tmp_path, monkeypatch):
    api, c = make_client(tmp_path, monkeypatch, None, key="")
    d = c.get("/api/alerts/ZONE-B1").json()
    assert {e["origin"] for e in d["evidence"]} <= {"source", "derived"}
    assert all(x["origin"] == "rule" for x in d["rule_explanation"])
    # the fixture has no vehicle counts: no meter finding may claim a verified explanation
    for a in c.get("/api/equipment-alerts").json():
        for ev in c.get(f"/api/equipment-alerts/{a['alert_id']}").json()["evidence"]:
            if ev["kind"] == "meter_episode":
                assert ev["values"]["label"] != "Reasonable variation"
    # invalid meter value stays flagged, it is never turned into a number
    bad = [e for e in api.state.get().evidence.values() if "invalid_reading" in e.flags]
    assert bad and all(e.values.get("reading") is None for e in bad)


def test_new_passing_checklist_does_not_change_fingerprint():
    from datetime import datetime, timedelta
    from firerisk.ai.investigation import fingerprint
    from firerisk.config import LOCAL_TZ
    from firerisk.models import Alert, Evidence
    now = datetime(2026, 10, 27, 8, tzinfo=LOCAL_TZ)

    def chk(eid, day, status="Đạt", is_open=False, tag="checklist_pass"):   # TEST checklist records
        return Evidence(eid, "inspection_check", now - timedelta(days=day), "P-TEST", "B1", "TEST checklist", "",
                        status, is_open, tags=[{"tag": tag, "term": status}])
    finding = Evidence("inc:TEST", "incident", now - timedelta(days=5), None, "B1", "TEST fault", "", "Mới", True)
    index = {e.evidence_id: e for e in (finding, chk("c1", 1), chk("c2", 0), chk("c3", 0, "Không đạt", True, "fault"))}
    alert = Alert("ZONE-B1", "B1", "B1", "high", "t", "s", [], [], [], ["inc:TEST"], [], None, None, 1,
                  context_ids=["c1"])
    fp = fingerprint(alert, index)
    alert.context_ids = ["c2"]                       # next day's checklist, same result
    assert fingerprint(alert, index) == fp
    alert.context_ids = ["c3"]                       # failing result: a real change
    assert fingerprint(alert, index) != fp
    alert.context_ids = ["c1"]; index["inc:TEST"].is_open = False   # finding resolved: a real change
    assert fingerprint(alert, index) != fp
