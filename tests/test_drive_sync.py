"""Google Drive sync tests against a LOCAL MOCK of the Apps Script web app (TEST fixtures, no Google, no real data).

The mock reproduces the real flow: POST /exec -> 302 redirect -> GET returns JSON.
"""

import base64
import importlib
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from fixtures import build_ops_workbook, build_snapshot
from firerisk.sources.drive_sync import SyncConfig, SyncError, sync_from_drive, valid_webapp_url

TOKEN = "test-token-not-a-secret"


class MockAppsScript:
    """mode: ok | bad_token | html | corrupt_ops | missing_vehicles | google_error"""

    def __init__(self, files: dict[str, bytes]):
        self.files = files
        self.mode = "ok"
        self.requests: list[dict] = []
        mock = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                mock.requests.append({"path": self.path, "body": body.decode()})
                self.send_response(302)
                self.send_header("Location", "/echo?user_content_key=abc")
                self.end_headers()
                mock._last_token = json.loads(body or b"{}").get("token")

            def do_GET(self):
                if mock.mode == "html":
                    out, ctype = b"<!DOCTYPE html><html>Sign in</html>", "text/html"
                else:
                    out, ctype = json.dumps(mock.answer()).encode(), "application/json"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.end_headers()
                self.wfile.write(out)

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}/macros/s/TEST/exec"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def answer(self) -> dict:
        if self.mode == "bad_token" or self._last_token != TOKEN:
            return {"ok": False, "error": "unauthorized"}
        out = {"ok": True, "generated_at": "2026-10-27T10:00:00Z", "files": {}}
        for key, content in self.files.items():
            if self.mode == "missing_vehicles" and key == "vehicles":
                continue
            if self.mode == "google_error" and key == "vehicles":
                out["files"][key] = {"error": "Exception: No item with the given ID could be found."}
                continue
            data = b"not a workbook" if (self.mode == "corrupt_ops" and key == "ops_data") else content
            out["files"][key] = {"title": f"TEST {key}", "drive_file_id": f"TESTID-{key}", "mime_type": "test",
                                 "drive_modified_time": "2026-10-27T09:00:00Z", "size": len(data),
                                 "data_b64": base64.b64encode(data).decode()}
        return out

    def close(self):
        self.server.shutdown()


@pytest.fixture()
def setup(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    ops = build_ops_workbook(src / "ops_new.xlsx").read_bytes()
    import openpyxl
    wb = openpyxl.Workbook()
    wb.active.title = "TEST vehicles"
    wb.active.append(["TEST fixture - not real data"])
    wb.save(src / "veh_new.xlsx")
    veh = (src / "veh_new.xlsx").read_bytes()
    snap = build_snapshot(tmp_path / "snap")
    mock = MockAppsScript({"ops_data": ops, "vehicles": veh})
    cfg = SyncConfig(url=mock.url, token=TOKEN, timeout_s=10)
    yield snap, mock, cfg, {"ops_data": ops, "vehicles": veh}
    mock.close()


def test_sync_downloads_follows_redirect_and_replaces_files(setup):
    snap, mock, cfg, content = setup
    old_ops = (snap / "ops.xlsx").read_bytes()
    r = sync_from_drive(snap, cfg)
    assert r["ok"] and r["changed"]
    assert r["files"]["vehicles"]["status"] == "updated"
    man = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    assert man["files"]["vehicles"]["drive_modified_time"] == "2026-10-27T09:00:00Z"
    assert (snap / man["files"]["vehicles"]["local_file"]).read_bytes() == content["vehicles"]
    if old_ops != content["ops_data"]:
        assert (snap / "previous" / "ops.xlsx").read_bytes() == old_ops   # previous version kept
    # the token travels only in the POST body, never in the URL
    assert TOKEN in mock.requests[0]["body"] and TOKEN not in mock.requests[0]["path"]


def test_second_sync_reports_unchanged(setup):
    snap, mock, cfg, _ = setup
    sync_from_drive(snap, cfg)
    r = sync_from_drive(snap, cfg)
    assert r["ok"] and not r["changed"]
    assert {f["status"] for f in r["files"].values()} == {"unchanged"}


def test_wrong_token_changes_nothing(setup):
    snap, mock, cfg, _ = setup
    before = {p.name: p.read_bytes() for p in snap.iterdir() if p.is_file()}
    with pytest.raises(SyncError, match="refused the token"):
        sync_from_drive(snap, SyncConfig(url=mock.url, token="wrong", timeout_s=10))
    assert {p.name: p.read_bytes() for p in snap.iterdir() if p.is_file()} == before


def test_web_page_instead_of_data_explains_deployment_setting(setup):
    snap, mock, cfg, _ = setup
    mock.mode = "html"
    with pytest.raises(SyncError, match="Who has access"):
        sync_from_drive(snap, cfg)


def test_invalid_file_keeps_previous_file_and_is_reported(setup):
    snap, mock, cfg, _ = setup
    old_ops = (snap / "ops.xlsx").read_bytes()
    mock.mode = "corrupt_ops"
    r = sync_from_drive(snap, cfg)
    assert not r["ok"]
    assert r["files"]["ops_data"]["status"] == "failed" and r["files"]["ops_data"]["kept_previous"]
    assert r["files"]["vehicles"]["status"] == "updated"
    assert (snap / "ops.xlsx").read_bytes() == old_ops
    man = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    assert man["files"]["ops_data"]["sync_error"] == "not an .xlsx file"


@pytest.mark.parametrize("mode", ["missing_vehicles", "google_error"])
def test_missing_or_google_error_file_is_reported(setup, mode):
    snap, mock, cfg, _ = setup
    mock.mode = mode
    r = sync_from_drive(snap, cfg)
    assert not r["ok"] and r["files"]["vehicles"]["status"] == "failed"
    assert r["files"]["ops_data"]["status"] in ("updated", "unchanged")


def test_unreachable_web_app_raises_and_report_has_no_secret(tmp_path):
    snap = build_snapshot(tmp_path / "snap")
    cfg = SyncConfig(url="http://127.0.0.1:9/macros/s/X/exec", token=TOKEN, timeout_s=3)
    with pytest.raises(SyncError) as e:
        sync_from_drive(snap, cfg)
    assert TOKEN not in str(e.value) and "127.0.0.1" not in str(e.value)


def test_not_configured():
    with pytest.raises(SyncError, match="not set up"):
        sync_from_drive(Path("."), SyncConfig(url=None, token=None))


def test_webapp_url_validation():
    assert valid_webapp_url("https://script.google.com/macros/s/AKfycbx123/exec")
    assert not valid_webapp_url("https://script.google.com/macros/s/AKfycbx123/dev")
    assert not valid_webapp_url("https://example.com/exec")


def test_setup_helpers_render_script_and_keep_env(tmp_path):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import setup_drive_sync as s
    from firerisk.env import read_env_file, update_env_file
    assert s.extract_drive_id("https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWx/edit#gid=0") == \
        "1AbCdEfGhIjKlMnOpQrStUvWx"
    assert s.extract_drive_id("hello") is None
    js = s.render_script("TOK123", {"ops_data": "ID1", "vehicles": "ID2"})
    assert "const FIRERISK_TOKEN = 'TOK123';" in js and '{"ops_data": "ID1", "vehicles": "ID2"}' in js
    assert "__FIRERISK" not in js
    env = tmp_path / ".env"
    env.write_text("MODEL_API_KEY=keep-me\n", encoding="utf-8")
    update_env_file({"FIRERISK_DRIVE_TOKEN": "a"}, env)
    update_env_file({"FIRERISK_DRIVE_TOKEN": "b", "FIRERISK_DRIVE_EXPORT_URL": "u"}, env)
    assert read_env_file(env) == {"MODEL_API_KEY": "keep-me", "FIRERISK_DRIVE_TOKEN": "b", "FIRERISK_DRIVE_EXPORT_URL": "u"}


def test_api_sync_endpoint_reanalyses_and_hides_secrets(setup, tmp_path, monkeypatch):
    snap, mock, cfg, _ = setup
    monkeypatch.setenv("FIRERISK_SNAPSHOT_DIR", str(snap))
    monkeypatch.setenv("FIRERISK_DB", str(tmp_path / "api.db"))
    monkeypatch.setenv("MODEL_API_KEY", "")
    monkeypatch.setenv("FIRERISK_DRIVE_EXPORT_URL", mock.url)
    monkeypatch.setenv("FIRERISK_DRIVE_TOKEN", TOKEN)
    from fastapi.testclient import TestClient
    import firerisk.api as api
    api = importlib.reload(api)
    c = TestClient(api.app)
    before = c.get("/api/status").json()
    assert before["sources_down"]                         # fixture snapshot has no vehicles file yet
    r = c.post("/api/sync").json()
    assert r["ok"] and r["changed"] and r["analysis"]["run_id"] != before["run_id"]
    after = c.get("/api/status").json()
    assert after["sync"]["configured"] and after["sync"]["last"]["ok"]
    hist = c.get("/api/sync").json()
    blob = json.dumps([before, r, after, hist])
    assert TOKEN not in blob and mock.url not in blob
