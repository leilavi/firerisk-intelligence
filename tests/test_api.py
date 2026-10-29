"""API tests against a TEST fixture snapshot (no real data, no network)."""

import importlib

import pytest
from fastapi.testclient import TestClient

from fixtures import build_snapshot


@pytest.fixture()
def client(tmp_path, monkeypatch):
    snap = build_snapshot(tmp_path / "snap")
    monkeypatch.setenv("FIRERISK_SNAPSHOT_DIR", str(snap))
    monkeypatch.setenv("FIRERISK_DB", str(tmp_path / "api.db"))
    monkeypatch.setenv("MODEL_API_KEY", "")
    import firerisk.api as api
    api = importlib.reload(api)
    return TestClient(api.app)


def test_status_and_overview_counts(client):
    s = client.get("/api/status").json()
    assert s["serious_alerts"] >= 1 and s["active_alerts"] >= s["serious_alerts"]
    assert s["sources_down"] and s["sources_down"][0]["source"] == "vehicles"   # missing file reported


def test_alert_list_is_concise_and_sorted(client):
    alerts = client.get("/api/alerts").json()
    ranks = ["normal", "watch", "warning", "high", "emergency"]
    assert [ranks.index(a["severity"]) for a in alerts] == sorted((ranks.index(a["severity"]) for a in alerts), reverse=True)
    a = alerts[0]
    assert {"headline", "why", "severity_label", "first_seen", "assessment_class", "deadline"} <= set(a)
    assert "links" not in a and "evidence" not in a


def test_alert_detail_has_evidence_fields_and_history(client):
    a = client.get("/api/alerts").json()[0]
    d = client.get(f"/api/alerts/{a['alert_id']}").json()
    assert d["fields"]["unknowns"] and d["signals"][0]["fields"]["closure_condition"]
    assert all(e["origin"] in ("source", "derived") for e in d["evidence"])
    assert d["investigation"] is None


def test_status_change_and_confirmed_state(client):
    a = client.get("/api/alerts").json()[0]["alert_id"]
    r = client.post(f"/api/alerts/{a}/status", json={"status": "confirmed", "note": "checked on site", "by": "tester"})
    assert r.status_code == 200 and r.json()["status"] == "confirmed"
    assert client.post(f"/api/alerts/{a}/status", json={"status": "bogus"}).status_code == 400


def test_investigation_without_key_fails_cleanly(client):
    a = client.get("/api/alerts").json()[0]["alert_id"]
    queued = client.post(f"/api/alerts/{a}/investigate").json()       # background request: refused, with reason
    assert queued["queued"] is False and "not configured" in queued["reason"]
    rec = client.post(f"/api/alerts/{a}/investigate?wait=true").json()  # synchronous run (previous behaviour)
    assert rec["status"] == "failed" and rec["error_kind"] == "not_configured"
    d = client.get(f"/api/alerts/{a}").json()
    assert d["alert"]["severity"] == "high"      # rule result unaffected by the AI failure
    assert d["ai_status"]["code"] == "failed" and d["ai_status"]["fallback"]
    assert d["ai_status"]["label"] == "Meta Muse Spark Analysis Failed"


def test_evidence_endpoint_traces_to_source_row(client):
    e = client.get("/api/evidence/gen:G1").json()
    assert e["source"]["sheet"] == "Dầu M Phát điện" and e["source"]["row"] == 2


def test_trends_assets_quality_media(client):
    assert "weeks" in client.get("/api/trends").json()
    assert any(r["asset_id"] == "P-BG.TTC167" for r in client.get("/api/assets").json())
    q = client.get("/api/quality").json()
    assert any(i["type"] == "invalid_reading" for i in q["issues"])
    assert client.get("/api/media").json()["summary"]["available"] == 0


def test_ui_files_are_versioned_and_revalidated(tmp_path, monkeypatch):
    import importlib
    from fastapi.testclient import TestClient
    from fixtures import build_snapshot
    monkeypatch.setenv("FIRERISK_SNAPSHOT_DIR", str(build_snapshot(tmp_path / "snap")))
    monkeypatch.setenv("FIRERISK_DB", str(tmp_path / "t.db"))
    import firerisk.api as api
    api = importlib.reload(api)
    c = TestClient(api.app)
    r = c.get("/")
    assert r.headers["cache-control"] == "no-cache"
    assert "/static/app.js?v=" in r.text and "/static/styles.css?v=" in r.text
    assert c.get("/static/app.js").headers["cache-control"] == "no-cache"
