"""Demo privacy (firerisk/demo.py, scripts/mask_labels_for_demo.py, demo mode in the API and page). TEST images,
FAKE SAM, invented TEST names - no real frame, no real building name."""

import importlib.util
import json
import shutil
import subprocess

import pytest

from firerisk.demo import blur_regions, load_manifest, mask_text, name_patterns, padded
from firerisk.sam import SamModelNotFound
from test_localize import FF, FakeSam, needs_ffmpeg

SITE = {"building_name": "Acme Riverside Plaza", "branch_prefix": "AR-Plaza", "ops_source_title": "Acme Riverside Plaza Data",
        "extra_names": ["Brandco"]}


def test_name_patterns_cover_variants_and_leave_other_text():
    p = name_patterns(SITE)
    for s in ["ACME RIVERSIDE PLAZA", "plate reads TTC PLAZA ACME RIVERSIDE", "Acme-Riverside", "ÀCMÉ Rivèrside",
              "inc:AR-Plaza----T10_140", "PC set - AR Plaza", "Brandco office"]:
        assert "[name hidden]" in mask_text(s, p), s
    for s in ["Electrical Panel - B1", "acme of riverside", "Fire Pump Room"]:
        assert mask_text(s, p) == s


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_patterns_compile_in_javascript():
    js = f"const P={json.dumps(name_patterns(SITE))};P.forEach(p=>new RegExp(p,'giu'));" \
         "console.log(P.map(p=>'TTC PLAZA ACME RIVERSIDE'.replace(new RegExp(p,'giu'),'X')).join('|'))"
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
    assert "X" in out


def test_padded_box_stays_inside_frame():
    assert padded({"x1": 0, "y1": 5, "x2": 118, "y2": 58, "w": 118, "h": 53}, 120, 60) == (0, 0, 120, 60)   # clamped
    assert padded({"x1": 20, "y1": 20, "x2": 70, "y2": 40, "w": 50, "h": 20}, 120, 60) == (15, 16, 75, 44)   # 6 % + 2 px


def _jpeg(path, w=160, h=120):
    subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={w}x{h}",
                    "-frames:v", "1", str(path)], check=True)


def _pixels(path):
    return subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "gray",
                           "-"], capture_output=True, check=True).stdout


@needs_ffmpeg
def test_blur_changes_only_the_region_and_never_the_original(tmp_path):
    src, out = tmp_path / "f.jpg", tmp_path / "demo" / "f.jpg"
    _jpeg(src)
    before = src.read_bytes()
    blur_regions(src, out, [(10, 10, 70, 60)])
    assert src.read_bytes() == before
    a, b = _pixels(src), _pixels(out)
    diff = lambda x0, y0, x1, y1: sum(abs(a[y * 160 + x] - b[y * 160 + x]) for y in range(y0, y1) for x in range(x0, x1)) / ((x1 - x0) * (y1 - y0))
    assert diff(15, 15, 65, 55) > 8 * diff(100, 80, 150, 115)            # blurred inside, (almost) unchanged outside
    with pytest.raises(ValueError):
        blur_regions(src, src, [(0, 0, 10, 10)])


def _script():
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("mask", Path(__file__).resolve().parents[1] / "scripts" / "mask_labels_for_demo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@needs_ffmpeg
def test_process_blurs_flags_misses_resumes_and_stops_on_access_error(tmp_path):
    mod = _script()
    frames, out = tmp_path / "frames", tmp_path / "frames_demo"
    for f in ("aaaaaaaaaaaaaaaa/t000010.jpg", "aaaaaaaaaaaaaaaa/t000020.jpg", "bbbbbbbbbbbbbbbb/t000030.jpg"):
        (frames / f).parent.mkdir(parents=True, exist_ok=True)
        _jpeg(frames / f)
    files = sorted(str(p.relative_to(frames)).replace("\\", "/") for p in frames.rglob("*.jpg"))
    # frame 1: sign found; frame 2: nothing found (2 phrases each); frame 3: model access error -> stop
    sam = FakeSam(["hit", "miss", "miss", "miss", SamModelNotFound("TEST")])
    st = mod.process(files, ["sign", "label"], sam, frames, out)
    assert (st["blurred"], st["no_label_found"], st["errors"], st["stopped"]) == (1, 1, 1, "model_not_found")
    m = load_manifest(out)
    assert m["frames"][files[0]]["status"] == "blurred" and m["frames"][files[1]]["status"] == "no_label_found"
    assert m["reviewed"] is False and (out / files[0]).exists() and not (out / files[2]).exists()
    sam2 = FakeSam(["miss", "miss"])
    st2 = mod.process(files, ["sign", "label"], sam2, frames, out)          # resume: only the failed frame
    assert st2["skipped"] == 2 and len(sam2.calls) == 2
    assert (frames / files[0]).exists()                                     # originals kept


@needs_ffmpeg
def test_demo_mode_serves_only_blurred_copies_and_hides_videos(tmp_path, monkeypatch):
    import importlib
    from fastapi.testclient import TestClient
    from fixtures import build_snapshot
    snap = build_snapshot(tmp_path / "snap")
    for k, v in {"FIRERISK_SNAPSHOT_DIR": snap, "FIRERISK_DB": tmp_path / "t.db", "FIRERISK_VIDEO_DIR": tmp_path / "v",
                 "FIRERISK_FRAMES_DIR": tmp_path / "frames", "FIRERISK_FRAMES_DEMO_DIR": tmp_path / "frames_demo",
                 "FIRERISK_AUTO_AI": "0", "FIRERISK_DEMO_MODE": "1"}.items():
        monkeypatch.setenv(k, str(v))
    import firerisk.video as video
    import firerisk.localize as localize
    import firerisk.demo as demo
    for m in (video, localize, demo):
        importlib.reload(m)
    import firerisk.api as api
    api = importlib.reload(api)
    c = TestClient(api.app)
    ff = "cccccccccccccccc/t000050.jpg"
    (tmp_path / "frames" / ff).parent.mkdir(parents=True)
    _jpeg(tmp_path / "frames" / ff)
    assert c.get(f"/api/frames/{ff}").status_code == 404                  # no blurred copy -> nothing shown
    blur_regions(tmp_path / "frames" / ff, tmp_path / "frames_demo" / ff, [(0, 0, 50, 50)])
    demo.save_manifest({"frames": {ff: {"status": "blurred"}}, "reviewed": False}, tmp_path / "frames_demo")
    r = c.get(f"/api/frames/{ff}")
    assert r.status_code == 200 and r.content == (tmp_path / "frames_demo" / ff).read_bytes()
    st = c.get("/api/status").json()
    assert st["demo_mode"] is True and st["building"] == "Demo building"
    up = c.post("/api/videos?filename=TEST.mp4", content=b"TEST", headers={"Content-Type": "application/octet-stream"})
    vid = up.json()["video_id"]
    assert c.get(f"/api/videos/{vid}/file").status_code == 403
    assert c.get(f"/api/videos/{vid}/frame?t=1").status_code == 403
    monkeypatch.setenv("FIRERISK_DEMO_MODE", "0")
    assert c.get(f"/api/frames/{ff}").content == (tmp_path / "frames" / ff).read_bytes()   # normal mode: original
    assert c.get("/api/status").json()["name_patterns"] == []


@needs_ffmpeg
def test_demo_page_masks_names_and_shows_blurred_frame(tmp_path, monkeypatch):
    """Rendered page in demo mode: building name masked everywhere, frame = blurred copy, no video element."""
    pw = pytest.importorskip("playwright.sync_api")
    import socket
    import threading
    import time
    import uvicorn
    import test_video_review as tvr
    from test_localize_api import _analyse_new_video
    monkeypatch.setenv("FIRERISK_FRAMES_DEMO_DIR", str(tmp_path / "frames_demo"))
    import importlib
    import firerisk.demo as demo
    importlib.reload(demo)
    answer = json.loads(json.dumps(tvr.V2_ANSWER))
    for f in answer["findings"]:
        f["segment_phrase"] = "cardboard box"
        f["what_is_visible"] = "TEST boxes under a plate reading TTC PLAZA ACME RIVERSIDE"
    monkeypatch.setattr(tvr, "V2_ANSWER", answer)
    from test_localize_api import app_env as _fixture  # noqa: F401
    import test_localize_api as tla
    gen = tla.app_env.__wrapped__(tmp_path, monkeypatch) if hasattr(tla.app_env, "__wrapped__") else None
    if gen is None:
        pytest.skip("fixture not callable directly")
    api, c, src = gen
    monkeypatch.setattr(api, "SamClient", lambda: FakeSam())
    _analyse_new_video(api, c, src)
    monkeypatch.setenv("FIRERISK_DEMO_MODE", "1")
    monkeypatch.setattr(api, "name_patterns", lambda: name_patterns(SITE))
    mod = _script()
    files = mod.frame_files(tmp_path / "t.db")
    mod.process(files, ["sign"], FakeSam(), tmp_path / "frames", demo.FRAMES_DEMO_DIR)
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    server = uvicorn.Server(uvicorn.Config(api.app, host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=server.run, daemon=True); t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    try:
        with pw.sync_playwright() as p:
            try:
                b = p.chromium.launch()
            except Exception as exc:
                pytest.skip(f"chromium not available: {exc}")
            page = b.new_page(viewport={"width": 1440, "height": 900})
            page.goto(f"http://127.0.0.1:{port}/#/media"); page.wait_for_load_state("networkidle")
            page.wait_for_selector("#samg .samcard img")
            page.click("#samg .samcard"); page.wait_for_selector("#drawer .evblock img")
            page.wait_for_timeout(300)
            body = page.text_content("body")
            assert "ACME" not in body.upper() and "[name hidden]" in body and "Demo mode" in body
            assert page.eval_on_selector_all("video", "l => l.length") == 0
            src_img = page.get_attribute("#drawer .ev-frame img", "src")
            got = page.evaluate(f"fetch('{src_img}').then(r => r.arrayBuffer()).then(b => b.byteLength)")
            ff = src_img.split("/api/frames/")[1]
            assert got == (demo.FRAMES_DEMO_DIR / ff).stat().st_size          # the blurred copy was served
            b.close()
    finally:
        server.should_exit = True
        t.join(timeout=5)


@needs_ffmpeg
def test_faces_are_blurred_locally_and_never_requested_from_sam(tmp_path, monkeypatch):
    """Data owner's condition 3 (faces concealed) without breaking the project rule that SAM never looks for people:
    faces come from a local detector, and frames already checked by SAM get the face pass with no API call."""
    mod = _script()
    frames, out = tmp_path / "frames", tmp_path / "frames_demo"
    f = "cccccccccccccccc/t000010.jpg"
    (frames / f).parent.mkdir(parents=True, exist_ok=True)
    _jpeg(frames / f)
    monkeypatch.setattr(mod, "local_face_boxes", lambda p: ([], "unavailable"))
    sam = FakeSam(["miss", "miss"])
    assert mod.process([f], ["sign", "label"], sam, frames, out)["no_label_found"] == 1
    assert all("person" not in c and "face" not in c for c in map(str, sam.calls))
    monkeypatch.setattr(mod, "local_face_boxes", lambda p: ([(20, 20, 60, 60)], mod.FACE_DETECTOR))
    sam2 = FakeSam([])
    st = mod.process([f], ["sign", "label"], sam2, frames, out)
    e = load_manifest(out)["frames"][f]
    assert sam2.calls == [] and st["faces"] == 1
    assert e["status"] == "blurred" and e["face_boxes"] == [[20, 20, 60, 60]] and e["face_detector"] == mod.FACE_DETECTOR
    assert load_manifest(out)["reviewed"] is False
    st3 = mod.process([f], ["sign", "label"], FakeSam([]), frames, out)
    assert st3["skipped"] == 1                                             # face pass done once


def test_local_face_detector_runs_offline_on_a_frame(tmp_path):
    pytest.importorskip("cv2")
    from firerisk.demo import FACE_DETECTOR, local_face_boxes
    p = tmp_path / "t.jpg"
    _jpeg(p)
    boxes, det = local_face_boxes(p)
    assert det == FACE_DETECTOR and boxes == []                            # a plain test pattern has no face
