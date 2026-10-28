"""0.8: unified building view (fire-safety risks + equipment alerts on one map), AI Risk Briefing, prompt v5
risk briefings, and the English-only rule (static files and rendered pages).
TEST fixture data only; Muse Spark results below are TEST records stored directly, clearly not real API output."""

import importlib
import re
import socket
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fixtures import build_snapshot

VI = re.compile(r"[À-ÖØ-öø-ỹĐđ]")
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def client(tmp_path, monkeypatch):
    snap = build_snapshot(tmp_path / "snap")
    monkeypatch.setenv("FIRERISK_SNAPSHOT_DIR", str(snap))
    monkeypatch.setenv("FIRERISK_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("FIRERISK_VIDEO_DIR", str(tmp_path / "videos"))
    monkeypatch.setenv("MODEL_API_KEY", "")
    import firerisk.api as api
    api = importlib.reload(api)
    return api, TestClient(api.app)


def test_map_combines_fire_risks_and_equipment_alerts_keeping_their_classification(client):
    api, c = client
    b = c.get("/api/building").json()
    eq = [a for a in c.get("/api/equipment-alerts").json()]
    issues = [i for f in b["floors"] for i in f["issues"]] + b["unassigned"]["issues"]
    assert {i["kind"] for i in issues} == {"fire_risk", "equipment"}
    assert len([i for i in issues if i["kind"] == "equipment"]) == len(eq)              # every equipment alert placed once
    by_id = {a["alert_id"]: a for a in eq}
    for i in issues:
        if i["kind"] == "equipment":
            a = by_id[i["alert_id"]]
            assert i["severity"] == a["severity"]                                         # original level kept
            assert (i["zone"] or "") == (a["zone"] or "")                                 # never moved to another floor
    for f in b["floors"]:
        assert f["map_state"] != "normal"
        if f["issues"]:
            assert f["map_state"] == max((i["severity"] for i in f["issues"]), key=api._rank)
            assert f["marker"]["count"] == len(f["issues"])
        else:
            assert f["marker"] is None and f["map_state"] in ("no_active_alert", "not_assessed")
    assert b["summary"]["issues_active"] == len(issues)
    assert b["summary"]["building_state_label"] in ("Emergency", "High Risk", "Warning", "Watch")


def test_briefing_priority_and_rule_fallback_when_no_ai(client):
    api, c = client
    br = c.get("/api/briefing").json()
    items = br["items"]
    ranks = [api._rank(i["severity"]) for i in items]
    assert ranks == sorted(ranks, reverse=True)                                           # highest level first
    top = items[0]
    assert top["kind"] == "fire_risk" and top["open"]
    assert top["ai"]["code"] == "unavailable" and top["ai"]["analysed_at"] is None        # never a fake "complete"
    assert top["first_action"]["origin"] == "rule" and top["potential_consequence"]["origin"] == "rule"
    assert top["observed"] is None                                                         # nothing invented
    for i in items:
        for k in ("observed", "why_it_matters", "potential_consequence", "uncertainty", "first_action"):
            assert not (i[k] and VI.search(i[k]["text"]))


def _store_ai(api, alert_id, briefings, current=True):
    res = api.state.get()
    a = next(x for x in res.alerts if x.alert_id == alert_id)
    fp = api.state.ai.status(a, res)["fingerprint"] if current else "older"
    api.state.store.save_investigation({
        "alert_id": alert_id, "created_at": datetime.now().isoformat(), "status": "ok", "model": "TEST-FAKE",
        "fingerprint": fp, "prompt_version": "investigation-v5", "base_url": "http://127.0.0.1:1/v1",
        "result": {"summary": "TEST", "situation": "TEST situation", "risk_briefings": briefings,
                   "risk_assessment": {"ai_priority": "high", "agrees_with_rule_severity": True, "rationale": "TEST"}}})


def test_briefing_uses_stored_ai_briefing_and_hides_non_english_ai_text(client):
    api, c = client
    top = c.get("/api/briefing").json()["items"][0]
    _store_ai(api, top["alert_id"], [{"signal": "S01", "signal_id": top["signal_id"], "observed": "TEST observed",
                                      "why_it_matters": "TEST why", "potential_consequence": "Có thể chập điện",
                                      "certainty": "partly_supported", "uncertainty": "TEST not established",
                                      "first_action": "TEST first action", "evidence_ids": []}])
    t = next(i for i in c.get("/api/briefing").json()["items"] if i["issue_id"] == top["issue_id"])
    assert t["ai"]["code"] == "complete" and t["ai"]["model"] == "TEST-FAKE" and t["ai"]["api_mode"] == "test"
    assert t["observed"] == {"text": "TEST observed", "origin": "ai"}
    assert t["first_action"]["origin"] == "ai"
    assert t["potential_consequence"]["origin"] == "rule"                                 # Vietnamese AI text not shown
    assert t["severity"] == top["severity"]                                               # AI never changes the level


def test_briefing_older_and_insufficient_evidence_states(client):
    api, c = client
    top = c.get("/api/briefing").json()["items"][0]
    _store_ai(api, top["alert_id"], [{"signal": "S01", "signal_id": top["signal_id"], "observed": "TEST",
                                      "why_it_matters": "TEST", "certainty": "insufficient_evidence",
                                      "potential_consequence": "Insufficient evidence to determine the potential consequence. Further inspection is required.",
                                      "uncertainty": "TEST", "first_action": "TEST", "evidence_ids": []}], current=False)
    t = next(i for i in c.get("/api/briefing").json()["items"] if i["issue_id"] == top["issue_id"])
    assert t["ai"]["code"] == "insufficient_evidence" and not t["ai"]["is_current"]


def test_v5_validation_maps_signals_and_drops_unknown_ones():
    from firerisk.ai.investigation import INSUFFICIENT_TEXT, map_back, validate
    res = {"risk_briefings": [
        {"signal": "S01", "observed": "x", "why_it_matters": "x", "potential_consequence": "fire soon",
         "certainty": "insufficient_evidence", "uncertainty": "x", "first_action": "x", "evidence_ids": ["E01", "E99"]},
        {"signal": "S07", "observed": "x", "why_it_matters": "x", "potential_consequence": "x",
         "certainty": "supported", "uncertainty": "x", "first_action": "x", "evidence_ids": []}]}
    out = map_back(res, {"E01": "real-1"}, {"S01": "SIG-A"})
    v = validate(out, ["real-1"])
    assert [b["signal_id"] for b in out["risk_briefings"]] == ["SIG-A"]
    assert out["risk_briefings"][0]["evidence_ids"] == ["real-1"]
    assert out["risk_briefings"][0]["potential_consequence"] == INSUFFICIENT_TEXT        # no consequence invented
    assert v["unknown_signals"] == ["S07"] and "E99" in v["invalid_evidence_ids"] and not v["ok"]


def test_web_files_contain_no_vietnamese_text():
    for f in ("web/app.js", "web/index.html", "web/styles.css"):
        bad = [n for n, line in enumerate((ROOT / f).read_text(encoding="utf-8").splitlines(), 1) if VI.search(line)]
        assert not bad, f"{f}: Vietnamese characters on lines {bad[:10]}"


# ---------------------------------------------------------------------------------------------------------------
# Rendered pages: no Vietnamese text visible anywhere, and the safety net never had to replace text.
# ---------------------------------------------------------------------------------------------------------------
def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def test_rendered_pages_are_english_only(client):
    pw = pytest.importorskip("playwright.sync_api")
    import uvicorn
    api, _ = client
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(api.app, host="127.0.0.1", port=port, log_level="error"))
    th = threading.Thread(target=server.run, daemon=True); th.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    js = """() => { const VI = /[\\u00C0-\\u00D6\\u00D8-\\u00F6\\u00F8-\\u1EF9\\u0110\\u0111]/; const out = [];
      const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let n = w.nextNode(); n; n = w.nextNode()) { const el = n.parentElement; if (!el || el.closest('[lang="vi"],script,style')) continue; if (VI.test(n.nodeValue)) out.push(n.nodeValue.slice(0, 60)); }
      document.querySelectorAll('[title],[placeholder],[aria-label]').forEach((el) => { if (el.closest('[lang="vi"]')) return;
        ['title','placeholder','aria-label'].forEach((a) => { const v = el.getAttribute(a); if (v && VI.test(v)) out.push('@' + a + ':' + v.slice(0, 60)); }); });
      return { left: out, replaced: window.__viReplaced }; }"""
    try:
        with pw.sync_playwright() as p:
            try:
                b = p.chromium.launch()
            except Exception as exc:                       # no browser installed on this machine
                pytest.skip(f"chromium not available: {exc}")
            page = b.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            base = f"http://127.0.0.1:{port}/"
            for h in ["#/", "#/fire", "#/fire/ZONE-B1", "#/equipment", "#/events", "#/data", "#/media"]:
                page.goto(base + h); page.wait_for_load_state("networkidle"); page.wait_for_timeout(300)
                if h == "#/":
                    page.focus(".mk"); page.keyboard.press("Enter")       # marker by keyboard (its ring is animated)
                    assert page.is_visible("#ctx .ctxhead") and "selected floor" in page.inner_text("#ctx").lower()
                    page.eval_on_selector("#ctx [data-issue]", "e => e.scrollIntoView({block: 'center'})")
                    page.click("#ctx [data-issue]")
                    page.wait_for_timeout(500)
                    assert page.is_visible("#drawer")                                  # View Details really opens
                    page.keyboard.press("Escape")
                r = page.evaluate(js)
                assert r["left"] == [] and r["replaced"] == 0, (h, r)
            assert errors == []
            b.close()
    finally:
        server.should_exit = True
        th.join(timeout=5)


def test_briefing_shows_real_older_muse_result_using_only_parts_that_cite_this_risk(client):
    api, c = client
    top = c.get("/api/briefing").json()["items"][0]
    mine, other = top["evidence_ids"][0], "some-other-record"
    res = api.state.get()
    api.state.store.save_investigation({
        "alert_id": top["alert_id"], "created_at": datetime.now().isoformat(), "status": "ok", "model": "TEST-FAKE",
        "fingerprint": "older", "prompt_version": "investigation-v3", "base_url": "http://127.0.0.1:1/v1",
        "result": {"summary": "TEST", "situation": "TEST zone situation",
                   "observed_facts": [{"statement": "TEST fact about this risk", "evidence_ids": [mine]},
                                      {"statement": "TEST fact about another risk", "evidence_ids": [other]}],
                   "recommended_actions": [{"action": "TEST action for another risk", "urgency": "routine", "evidence_ids": [other]},
                                           {"action": "TEST action for this risk", "urgency": "immediate", "evidence_ids": [mine]}],
                   "hypotheses": [], "scenarios": [],
                   "risk_assessment": {"ai_priority": "high", "agrees_with_rule_severity": True, "rationale": "TEST"}}})
    t = next(i for i in c.get("/api/briefing").json()["items"] if i["issue_id"] == top["issue_id"])
    assert t["ai"]["code"] == "complete_older" and t["ai"]["model"] == "TEST-FAKE"
    assert t["observed"] == {"text": "TEST fact about this risk", "origin": "ai"}
    assert t["first_action"] == {"text": "TEST action for this risk", "origin": "ai"}
    assert t["zone_ai"]["situation"] == "TEST zone situation"
    assert [a["action"] for a in t["zone_ai"]["actions"]] == ["TEST action for this risk"]
    assert t["videos"] == []                                                              # fixture has no video
