"""OFFLINE tests of the Muse Spark integration (fake HTTP transport - NOT the real API).
The real API is exercised by scripts/check_meta_api.py and by the dashboard on the user's PC."""

import io
import json
import urllib.error
from datetime import datetime, timedelta

import pytest

from firerisk.ai.investigation import SCHEMA, build_package, investigate, validate
from firerisk.ai.muse import MuseClient, MuseConfig
from firerisk.ai.redact import Redactor
from firerisk.config import LOCAL_TZ
from firerisk.correlation import aggregate_alerts
from firerisk.hazards.pathways import evaluate
from firerisk.hazards.tagging import tag_evidence
from firerisk.models import Evidence

NOW = datetime(2026, 10, 27, 14, 0, tzinfo=LOCAL_TZ)


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_opener(payload_check, content, status=200):
    def _open(req, timeout=0):
        body = json.loads(req.data)
        payload_check(body, req)
        if status != 200:
            raise urllib.error.HTTPError(req.full_url, status, "err", {}, io.BytesIO(b'{"error":"x"}'))
        return FakeResp(json.dumps({"model": body["model"], "choices": [{"message": {"content": content}}],
                                    "usage": {"total_tokens": 10}}).encode())
    return _open


def scenario():
    items = tag_evidence([
        Evidence("inc:1", "incident", NOW - timedelta(days=19), None, "B1", "Phòng MBA,MSB thấm nước",
                 "Trời mưa lớn phòng MBA,MSB có hiện tượng nước thấm vào bên trong", "3. Đang tìm PA", True,
                 persons=["staff1@example.com"]),
        Evidence("a:1", "asset_service", NOW - timedelta(days=37), "P-BG.TTC046", "B1", "Thấm nước từ tường vào phòng MSB",
                 "Anh Nam kiểm tra tường phòng MSB", "4. Operational", False, persons=["Anh Nam"]),
    ])
    sigs = evaluate(items, NOW)
    alerts = aggregate_alerts(sigs, {e.evidence_id: e for e in items}, NOW)
    return alerts[0], sigs, {e.evidence_id: e for e in items}


def test_redactor_removes_emails_and_names():
    r = Redactor()
    r.add_known(["Anh Nam"])
    out = r.text("Liên hệ staff1@example.com; Anh Nam đã xử lý; KTV Văn Hùng")
    assert "gmail" not in out and "Nam" not in out and "Văn Hùng" not in out


def test_package_is_redacted_and_cites_only_known_ids():
    alert, sigs, idx = scenario()
    pkg, _ = build_package(alert, sigs, idx, NOW)
    dumped = json.dumps(pkg, ensure_ascii=False)
    assert "gmail" not in dumped and "Nam" not in dumped
    assert {e["evidence_id"] for e in pkg["evidence"]} == {"inc:1", "a:1"}


def test_schema_is_strict_compatible():
    def walk(node):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
            for v in node["properties"].values():
                walk(v)
        if node.get("type") == "array":
            walk(node["items"])
    walk(SCHEMA["schema"])


def test_validate_drops_unknown_ids():
    pkg = {"evidence": [{"evidence_id": "inc:1"}]}
    res = {"observed_facts": [{"statement": "x", "evidence_ids": ["inc:1", "bogus"]},
                              {"statement": "y", "evidence_ids": ["bogus2"]}],
           "hypotheses": [], "escalation_pathway": [], "recommended_actions": []}
    v = validate(res, pkg)
    assert v["invalid_evidence_ids"] == ["bogus", "bogus2"] and v["unsupported_facts"] == ["y"]
    assert res["observed_facts"][0]["evidence_ids"] == ["inc:1"]


def test_investigate_end_to_end_with_fake_transport():
    alert, sigs, idx = scenario()
    answer = {"summary": "s", "observed_facts": [{"statement": "water in MSB room", "evidence_ids": ["inc:1"]}],
              "hypotheses": [], "escalation_pathway": [],
              "risk_assessment": {"ai_priority": "high", "agrees_with_rule_severity": True, "rationale": "r"},
              "missing_information": [], "recommended_actions": [], "uncertainty": "u"}

    def check(body, req):
        assert body["model"] == "muse-spark-1.3"
        assert body["response_format"]["type"] == "json_schema"
        assert req.headers["Authorization"] == "Bearer k"
        assert "gmail" not in json.dumps(body, ensure_ascii=False)

    client = MuseClient(MuseConfig(api_key="k"), opener=fake_opener(check, json.dumps(answer)))
    rec = investigate(alert, sigs, idx, NOW, client)
    assert rec["status"] == "ok" and rec["validation"]["ok"]


@pytest.mark.parametrize("status,kind", [(401, "auth"), (429, "rate_limited"), (400, "bad_response")])
def test_errors_are_reported_not_raised(status, kind):
    alert, sigs, idx = scenario()
    client = MuseClient(MuseConfig(api_key="k"), opener=fake_opener(lambda b, r: None, "{}", status=status))
    import firerisk.ai.muse as m
    m.time.sleep = lambda s: None   # no real waiting in tests
    rec = investigate(alert, sigs, idx, NOW, client)
    assert rec["status"] == "failed" and rec["error_kind"] == kind


def test_invalid_json_from_model_is_reported():
    alert, sigs, idx = scenario()
    client = MuseClient(MuseConfig(api_key="k"), opener=fake_opener(lambda b, r: None, "not json"))
    rec = investigate(alert, sigs, idx, NOW, client)
    assert rec["status"] == "failed" and rec["error_kind"] == "bad_response"


def test_not_configured():
    alert, sigs, idx = scenario()
    rec = investigate(alert, sigs, idx, NOW, MuseClient(MuseConfig(api_key=None)))
    assert rec["error_kind"] == "not_configured"
