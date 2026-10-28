"""Building Risk Map, plain-English risk cards, English UI labels and record translation.
TEST fixture data; Muse Spark replaced by a FAKE client (clearly not the real API)."""

import importlib
import json
import re

import pytest
from fastapi.testclient import TestClient

from fixtures import build_snapshot

VI = re.compile(r"[À-ỹĐđ]")


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


def test_floor_states_come_from_rules_and_records_never_green(client):
    api, c = client
    b = c.get("/api/building").json()
    floors = {f["zone"]: f for f in b["floors"]}
    assert list(floors) == ["Roof", "F4", "F3", "F2", "F1", "B1", "Building"]
    assert floors["B1"]["state"] == "high" and floors["B1"]["risk_count"] >= 2
    assert floors["B1"]["top_risk"]["severity"] == "high"                    # highest severity shown first
    for f in floors.values():
        assert f["state"] != "normal"                                       # rules never declare a floor safe
        if not f["risk_count"]:
            assert f["state"] == ("no_active_alert" if f["records_checked"] else "not_assessed")
    assert any(f["state"] == "not_assessed" for f in floors.values())       # fixture has floors without records
    s = b["summary"]
    assert s["overall"] == "high" and s["risk_count"] == sum(f["risk_count"] for f in floors.values())
    assert s["urgent_actions"] == sum(1 for f in floors.values() for r in f["risks"]
                                      if r["severity"] in ("high", "emergency") and r["open"])
    assert "not mean a floor is confirmed safe" in s["coverage_note"]


def test_resolved_alert_leaves_the_map_but_rules_are_unchanged(client):
    api, c = client
    c.post("/api/alerts/ZONE-B1/status", json={"status": "resolved", "note": "TEST", "by": "TEST"})
    b1 = next(f for f in c.get("/api/building").json()["floors"] if f["zone"] == "B1")
    assert b1["risk_count"] == 0 and b1["state"] == "no_active_alert"
    assert c.get("/api/alerts/ZONE-B1").json()["alert"]["severity"] == "high"   # the rule result itself stays


def test_risk_cards_have_plain_english_level_1_fields(client):
    api, c = client
    a = c.get("/api/alerts/ZONE-B1").json()
    for r in a["fields"]["risks"]:
        for k in ("risk", "location", "why_it_matters", "action", "evidence", "severity", "open"):
            assert r.get(k) not in (None, ""), k
        assert "fixed" not in r["risk"]                                     # status is shown separately
        assert not VI.search(r["why_it_matters"] + r["action"])
    water = next(r for r in a["fields"]["risks"] if r["risk_type"] == "water_electrical")
    assert water["open"] and "unresolved" in water["evidence"]
    assert "may" in water["why_it_matters"]                                 # cautious wording, no certainty


def test_user_facing_labels_are_english(client):
    from firerisk.ai.auto import STATE_LABELS
    api, c = client
    assert not any(VI.search(v[0] + v[1]) for v in STATE_LABELS.values())
    d = c.get("/api/alerts/ZONE-B1").json()
    assert not VI.search(json.dumps(d["ai_status"], ensure_ascii=False))
    assert not VI.search(d["fields"]["assessment_text"] + " ".join(d["fields"]["unknowns"]))
    b = c.get("/api/building").json()
    assert not VI.search(" ".join(f["state_label"] + f["label"] for f in b["floors"]))
    # source records keep their original text; English display fields sit next to it
    e = next(x for x in d["evidence"] if x["status"] == "6. Hoàn tất") if any(x["status"] == "6. Hoàn tất" for x in d["evidence"]) else None
    if e:
        assert e["status_en"] == "6. Completed" and e["status_en_origin"] == "glossary"
    src = next(x for x in d["evidence"] if x.get("source"))
    assert src["source"]["sheet_en"] and not VI.search(src["source"]["sheet_en"])


class FakeClient:
    """Returns a TEST translation per id; checks that names were pseudonymised before sending."""
    def __init__(self):
        self.sent = []

    def chat_json(self, system, user, schema, **kw):
        payload = json.loads(user)
        self.sent.append(payload)
        from firerisk.ai.muse import MuseResult
        items = [{"id": x["id"], "en": "TEST EN: " + x["vi"].replace("thấm nước", "water seepage")} for x in payload["items"]]
        return MuseResult(data={"items": items}, model="TEST-FAKE", usage=None, seconds=0, raw_content="")


def test_translation_is_cached_pseudonymised_and_marked(tmp_path):
    from firerisk.ai.translate import Translator, glossary
    t = Translator(tmp_path / "tr.db")
    assert glossary("Đạt") == "Passed" and glossary("Generator run - Mất điện lưới (7 min)") == "Generator run - Grid power outage (7 min)"
    src = ["Phòng MBA thấm nước, anh Nam kiểm tra", "Đạt", "Already English"]
    assert t.en(src[0]) == (None, None)                                     # pending: nothing invented
    fake = FakeClient()
    out = t.translate(fake, src)
    assert out["translated"] == 1 and out["remaining"] == 0                 # glossary/English strings not sent
    sent = fake.sent[0]["items"][0]["vi"]
    assert "Nam" not in sent and "<person-1>" in sent                       # name pseudonymised for the API
    en, origin = t.en(src[0])
    assert origin == "ai_translation" and "Nam" in en and "water seepage" in en   # name restored afterwards
    assert t.en("Already English") == ("Already English", "source")
    t2 = Translator(tmp_path / "tr.db")                                     # persisted in SQLite
    assert t2.en(src[0])[0] == en
    fake2 = FakeClient()
    t2.translate(fake2, src)
    assert fake2.sent == []                                                 # cached: no second call


def test_api_shows_translation_next_to_original(client):
    api, c = client
    title = next(x["title"] for x in c.get("/api/events").json() if VI.search(x["title"] or ""))
    api.state.translator.cache[title] = "TEST English title"
    rec = next(x for x in c.get("/api/events").json() if x["title"] == title)
    assert rec["title_en"] == "TEST English title" and rec["title_en_origin"] == "ai_translation" and rec["title"] == title
