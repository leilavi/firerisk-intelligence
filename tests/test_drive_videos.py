"""Survey videos straight from Google Drive. FAKE web app, FAKE tokeninfo, FAKE Drive and FAKE Muse transports;
TEST bytes only - no Google, no Meta, no real video."""

import importlib
import io
import json
import urllib.error

import pytest
from fastapi.testclient import TestClient

from fixtures import build_snapshot
from test_video import FakeMeta

CONTENT = {"TESTVID00000000000000001": b"TEST-VIDEO-SMALL", "TESTVID00000000000000002": b"TEST-VIDEO-LARGER-BYTES"}


class FakeGoogle:
    def __init__(self, scope="https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/script.external_request"):
        self.scope, self.log, self.truncate = scope, [], False

    def opener(self, req, timeout=0):
        url = req.full_url
        self.log.append({"url": url, "headers": dict(req.header_items()), "data": req.data})
        if "script.google" in url:
            out = json.dumps({"ok": True, "access_token": "TEST-ACCESS-TOKEN", "expires_in_s": 3000}).encode()
        elif "tokeninfo" in url:
            out = json.dumps({"scope": self.scope}).encode()
        elif "/drive/v3/files/" in url:
            fid = url.split("/files/")[1].split("?")[0]
            if fid not in CONTENT:
                raise urllib.error.HTTPError(url, 404, "nf", {}, io.BytesIO(b""))
            out = CONTENT[fid][:-3] if self.truncate else CONTENT[fid]
        else:
            raise AssertionError(url)

        class R(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return R(out)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    snap = build_snapshot(tmp_path / "snap")
    for k, v in {"FIRERISK_SNAPSHOT_DIR": str(snap), "FIRERISK_DB": str(tmp_path / "t.db"),
                 "FIRERISK_VIDEO_DIR": str(tmp_path / "videos"), "FIRERISK_VIDEO_INBOX": str(tmp_path / "inbox"),
                 "MODEL_API_KEY": "TEST-KEY", "META_API_BASE_URL": "http://fake-meta.invalid/v1", "FIRERISK_AUTO_AI": "0",
                 "FIRERISK_DRIVE_EXPORT_URL": "https://script.google.com/macros/s/TEST/exec",
                 "FIRERISK_DRIVE_TOKEN": "TEST-SHARED-SECRET"}.items():
        monkeypatch.setenv(k, v)
    import firerisk.video as video
    importlib.reload(video)
    import firerisk.drive_videos as dv
    importlib.reload(dv)
    import firerisk.api as api
    api = importlib.reload(api)
    g, meta = FakeGoogle(), FakeMeta()
    api.state.drive_videos.opener = g.opener
    from firerisk.ai.muse import MuseClient, MuseConfig
    api.state.ai.client_factory = lambda: MuseClient(
        MuseConfig(api_key="TEST-KEY", base_url="http://fake-meta.invalid/v1", timeout_s=5), opener=meta.opener)
    res = api.state.get()
    res.video_catalog = {"TESTVID00000000000000002": {"title": "TEST Pump Room.mp4", "size": len(CONTENT["TESTVID00000000000000002"]),
                                                      "mime_type": "video/mp4", "folder": "TEST/Video Uploaded"},
                         "TESTVID00000000000000001": {"title": "TEST_unlinked.mp4", "size": len(CONTENT["TESTVID00000000000000001"]),
                                                      "mime_type": "video/mp4", "folder": "TEST/Video Uploaded"}}
    res.video_refs = [{"drive_file_id": "TESTVID00000000000000002", "zone": "B1", "zone_source": "asset register Floor",
                       "equipment": [{"equipment_id": "P-TEST1", "name": "TEST fire pump panel", "floor": "B1"}]}]
    return api, TestClient(api.app), g, meta


def run(api):
    from firerisk.drive_videos import wait
    assert api.state.start_drive_videos()
    assert wait(api.state.drive_videos, 30)
    return api.state.drive_videos.progress


def test_downloads_every_drive_video_registers_and_analyses(env):
    api, c, g, meta = env
    lst = c.get("/api/videos").json()
    assert [r["on_this_computer"] for r in lst["drive"]] == [False, False]
    p = run(api)
    assert not p["errors"], p["errors"]
    assert [d["title"] for d in p["downloaded"]] == ["TEST_unlinked.mp4", "TEST Pump Room.mp4"]   # smallest first
    vids = {v["filename"]: v for v in api.state.videos.list()}
    assert vids["TEST Pump Room.mp4"]["zone"] == "B1" and vids["TEST Pump Room.mp4"]["equipment"][0]["equipment_id"] == "P-TEST1"
    assert vids["TEST_unlinked.mp4"]["zone"] is None and "not linked" in vids["TEST_unlinked.mp4"]["note"]
    assert api.state.videos.path(vids["TEST Pump Room.mp4"]["video_id"]).read_bytes() == CONTENT["TESTVID00000000000000002"]
    # the Drive download used the token in a header only; the token never appears in API output
    dl = [x for x in g.log if "/drive/v3/files/" in x["url"]]
    assert all("TEST-ACCESS-TOKEN" not in x["url"] and x["headers"]["Authorization"] == "Bearer TEST-ACCESS-TOKEN" for x in dl)
    tokeninfo = next(x for x in g.log if "tokeninfo" in x["url"])
    assert "TEST-ACCESS-TOKEN" not in tokeninfo["url"]                      # sent in the POST body, not the URL
    blob = json.dumps([c.get("/api/videos").json(), p, c.get("/api/status").json()])
    assert "TEST-ACCESS-TOKEN" not in blob and "TEST-SHARED-SECRET" not in blob
    # automatic Muse analysis of both videos, recorded as trigger auto; observations reach the B1 alert
    assert [a["status"] for a in p["analysed"]] == ["ok", "ok"]
    a = api.state.videos.latest_analysis(vids["TEST Pump Room.mp4"]["video_id"])
    assert a["trigger"] == "auto"
    d = c.get("/api/alerts/ZONE-B1").json()
    assert d["survey_videos"] and d["survey_videos"][0]["observations"] and d["alert"]["severity"] == "high"
    # second run: nothing downloaded or analysed again
    calls = len(meta.log)
    p2 = run(api)
    assert p2["downloaded"] == [] and len(p2["skipped"]) == 2 and len(meta.log) == calls


def test_token_with_write_access_is_refused(env):
    api, c, g, _ = env
    g.scope = "https://www.googleapis.com/auth/drive"
    p = run(api)
    assert p["downloaded"] == [] and "can modify your Drive" in p["errors"][0]["error"]
    assert not any("/drive/v3/files/" in x["url"] for x in g.log)


def test_incomplete_download_is_not_registered(env):
    api, c, g, _ = env
    g.truncate = True
    p = run(api)
    assert p["downloaded"] == [] and all("incomplete" in e["error"] for e in p["errors"])
    assert api.state.videos.list() == []


def test_daily_limit_and_switch_off(env, monkeypatch):
    api, c, g, meta = env
    monkeypatch.setenv("FIRERISK_VIDEO_AI_DAILY_LIMIT", "1")
    p = run(api)
    assert len(p["downloaded"]) == 2 and len(p["analysed"]) == 1


def test_auto_video_analysis_can_be_switched_off(env, monkeypatch):
    api, c, g, meta = env
    monkeypatch.setenv("FIRERISK_AUTO_VIDEO_AI", "0")
    p = run(api)
    assert len(p["downloaded"]) == 2 and p["analysed"] == [] and meta.log == []


def test_not_set_up_does_nothing(env, monkeypatch):
    api, c, g, _ = env
    monkeypatch.setenv("FIRERISK_DRIVE_EXPORT_URL", "")
    assert api.state.start_drive_videos() is False
    assert c.post("/api/videos/drive-sync").status_code == 400
