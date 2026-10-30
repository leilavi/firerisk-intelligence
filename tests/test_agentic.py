"""OFFLINE tests of the agentic investigation (Meta Muse Spark tool calling) with a FAKE transport - not the real API.
The real API is checked by scripts/check_tool_calling.py and by the dashboard on the author's PC."""

import copy
import io
import json
import urllib.error
from datetime import timedelta

from firerisk.ai import agentic
from firerisk.ai.agentic import investigate_agentic
from firerisk.ai.muse import MuseClient, MuseConfig
from firerisk.hazards.tagging import tag_evidence
from firerisk.models import Evidence
from test_ai_offline import NOW, FakeResp, scenario

ANSWER = {"summary": "TEST", "situation": "TEST", "observed_facts": [{"statement": "TEST", "evidence_ids": ["E01", "E99"]}],
          "hypotheses": [], "scenarios": [], "escalation_pathway": [],
          "risk_assessment": {"ai_priority": "emergency", "agrees_with_rule_severity": False, "rationale": "x"},
          "missing_information": [], "recommended_actions": [], "limitations": [], "uncertainty": "x", "risk_briefings": []}


class Scripted:
    """Fake Meta transport. `turns` = list of tool-call lists (one per tool turn); then a plain answer; the final
    structured request returns ANSWER (with extra cited IDs). Records every request body."""

    def __init__(self, turns, final_cites=(), fail_tools=None):
        self.turns, self.final_cites, self.fail_tools, self.bodies = list(turns), list(final_cites), fail_tools, []

    def opener(self, req, timeout=0):
        body = json.loads(req.data)
        self.bodies.append(body)
        if "tools" in body and self.fail_tools:
            if self.fail_tools == "timeout":
                raise TimeoutError("TEST timeout")
            raise urllib.error.HTTPError(req.full_url, self.fail_tools, "err", {}, io.BytesIO(b'{"error":"TEST rejected"}'))
        if "tools" in body:
            if self.turns:
                calls = self.turns.pop(0)
                msg = {"role": "assistant", "content": "TEST: checking the switchboard history." if len(self.bodies) == 1 else None,
                       "reasoning_content": "TEST kept as returned",
                       "tool_calls": [{"id": f"call_{len(self.bodies)}_{n}", "type": "function",
                                       "function": {"name": name, "arguments": args}} for n, (name, args) in enumerate(calls)]}
                return self._resp(body, msg, "tool_calls")
            return self._resp(body, {"role": "assistant", "content": "TEST: checked the asset history."}, "stop")
        ans = copy.deepcopy(ANSWER)
        ans["observed_facts"].append({"statement": "TEST from tool", "evidence_ids": self.final_cites})
        return self._resp(body, {"role": "assistant", "content": json.dumps(ans)}, "stop")

    @staticmethod
    def _resp(body, msg, finish):
        return FakeResp(json.dumps({"model": body["model"], "choices": [{"message": msg, "finish_reason": finish}],
                                    "usage": {"total_tokens": 5}}).encode())


def _client(fake):
    return MuseClient(MuseConfig(api_key="TEST-KEY", base_url="http://fake.invalid/v1", timeout_s=5), opener=fake.opener)


def _world():
    alert, sigs, idx = scenario()
    # an older record of the same switchboard that the rules did NOT put in the package
    old = tag_evidence([Evidence("a:old", "asset_service", NOW - timedelta(days=200), "P-BG.TTC046", "B1",
                                 "TEST MSB room water stain 2026", "Chị Lan báo vết nước cũ", "4. Operational", False,
                                 persons=["Chị Lan"])])[0]
    idx = {**idx, old.evidence_id: old}
    return alert, sigs, idx


def test_muse_spark_looks_up_records_and_may_cite_them_and_ids_stay_private():
    alert, sigs, idx = _world()
    before = copy.deepcopy({k: v.to_dict() for k, v in idx.items()})
    fake = Scripted([[("get_asset_history", '{"asset_id": "P-BG.TTC046"}'), ("list_assets", '{"zone": "B1"}')],
                     [("search_records", '{"text": "MSB", "zone": "B1"}')]], final_cites=["E03"])
    rec = investigate_agentic(alert, sigs, idx, NOW, _client(fake))
    assert rec["status"] == "ok" and rec["mode"] == "agentic"
    tr = rec["agent"]["trace"]
    assert [t["tool"] for t in tr if t["type"] == "tool"] == ["get_asset_history", "list_assets", "search_records"]
    assert tr[-1]["type"] == "note" and rec["agent"]["stop"] == "model_finished"
    assert tr[0] == {"turn": 1, "type": "intent", "text": "TEST: checking the switchboard history.", "seconds": tr[0]["seconds"]}
    assert rec["agent"]["records_looked_up"] == 1                    # a:old became E03 through a tool
    assert rec["agent"]["cited_beyond_package"] == ["a:old"]           # cited, mapped back to the real record
    assert "E99" in rec["validation"]["invalid_evidence_ids"]          # never shown -> dropped and reported
    # tool protocol: assistant message sent back unchanged, one tool message per call with its id
    second = fake.bodies[1]["messages"]
    assert second[2]["tool_calls"][0]["id"] == "call_1_0" and second[2]["reasoning_content"] == "TEST kept as returned"
    assert [m["tool_call_id"] for m in second[3:]] == ["call_1_0", "call_1_1"]
    assert all(b.get("tool_choice") == "auto" for b in fake.bodies if "tools" in b)
    sent = json.dumps(fake.bodies, ensure_ascii=False)
    for secret in ("a:old", "inc:1", "a:1", "Chị Lan", "Anh Nam", "staff1@example.com"):
        assert secret not in sent                                      # real IDs and names never leave the app
    assert {k: v.to_dict() for k, v in idx.items()} == before          # tools are read-only
    assert rec["rule_level"] == alert.severity                         # the model never sets the level


def test_bad_arguments_and_unknown_tools_return_errors_the_model_can_read():
    alert, sigs, idx = _world()
    fake = Scripted([[("get_asset_history", "{not json"), ("drop_table", "{}"), ("get_meter_readings", '{"meter_id": "X"}'),
                      ("search_records", "{}"), ("get_asset_history", '{"asset_id": "P-BG.TTC046", "since": "yesterday"}')]])
    rec = investigate_agentic(alert, sigs, idx, NOW, _client(fake))
    assert rec["status"] == "ok"
    errs = [t["error"] for t in rec["agent"]["trace"] if t["type"] == "tool"]
    assert all(errs) and len(errs) == 5
    tool_msgs = [json.loads(m["content"]) for m in fake.bodies[1]["messages"] if m["role"] == "tool"]
    assert all("error" in m for m in tool_msgs)


def test_turn_and_call_caps_end_the_loop_and_the_final_answer_is_still_requested(monkeypatch):
    alert, sigs, idx = _world()
    fake = Scripted([[("list_assets", "{}")]] * 20)
    rec = investigate_agentic(alert, sigs, idx, NOW, _client(fake))
    assert rec["agent"]["stop"] == "turn_limit" and rec["agent"]["tool_calls"] == agentic.MAX_TURNS
    assert "response_format" in fake.bodies[-1] and "tools" not in fake.bodies[-1]
    monkeypatch.setattr(agentic, "MAX_CALLS", 3)
    fake = Scripted([[("list_assets", "{}")] * 5])
    rec = investigate_agentic(alert, sigs, idx, NOW, _client(fake))
    assert rec["agent"]["stop"] == "call_limit"
    assert [t.get("error") for t in rec["agent"]["trace"]].count("call_limit") == 2


def test_rejected_tool_request_falls_back_to_the_single_call_investigation():
    alert, sigs, idx = _world()
    fake = Scripted([], fail_tools=400)
    rec = investigate_agentic(alert, sigs, idx, NOW, _client(fake))
    assert rec["status"] == "ok" and rec["mode"] == "single_call"
    assert rec["agentic_fallback"]["reason"] == "bad_response"
    assert "tools" not in fake.bodies[-1] and "response_format" in fake.bodies[-1]


def test_api_down_is_recorded_as_failed_without_a_second_full_attempt(monkeypatch):
    alert, sigs, idx = _world()
    monkeypatch.setattr("firerisk.ai.muse.time.sleep", lambda s: None)
    fake = Scripted([], fail_tools="timeout")
    rec = investigate_agentic(alert, sigs, idx, NOW, _client(fake))
    assert rec["status"] == "failed" and rec["error_kind"] == "timeout"
    assert all("tools" in b for b in fake.bodies)                      # no single-call fallback request


def test_tool_definitions_follow_the_documented_format():
    for t in agentic.TOOLS:
        f = t["function"]
        assert t["type"] == "function" and f["name"].replace("_", "").isalnum()
        assert f["parameters"]["type"] == "object" and set(f["parameters"]["required"]) <= set(f["parameters"]["properties"])
