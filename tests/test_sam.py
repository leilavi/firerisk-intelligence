"""SAM 3.1 parser + client, fully offline (fake transport and a local mock HTTP server). No real API, no real frames.

Mask payloads below are the official examples from the meta-sam-parser 0.0.6 README (Meta), not building data."""

import io
import json
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from firerisk.ai.muse import MuseConfig
from firerisk.sam import (SamBadRequest, SamBadResponse, SamClient, SamModelNotFound, SamNotConfigured,
                          SamRateLimited, SamTimeout, parse_output, phrase_problem)

M0 = "~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x("     # 27 x 60 lossless (README example)
M1 = "~!!!!J!0c[q=Pj_zs=*4C4(/./x#:/`S_GnD`=o3?X{emCgO$y@"           # 27 x 48 lossless (README example)


def rec(oid, x1, y1, x2, y2, mask, mh, mw, c=None, w=320, h=334):
    cc = f";c={c}" if c is not None else ""
    return (f"{oid}<|box;x1={x1};y1={y1};x2={x2};y2={y2};w={w};h={h}{cc}|>"
            f"<|mask;x=0;y=0;data={mh},{mw},{mask}|>")


TWO = "<0f>" + rec(0, 211, 228, 270, 254, M0, 27, 60, c=0.91) + "," + rec(2, 155, 228, 202, 254, M1, 27, 48) + "\n"


# --- parser ----------------------------------------------------------------------------------------------------
def test_empty_output_is_a_valid_no_match():
    p = parse_output("")
    assert p.objects == [] and p.complete and not p.located


def test_multiple_objects_sparse_ids_confidence_present_and_absent():
    p = parse_output(TWO, with_rle=True)
    assert [o.object_id for o in p.objects] == ["0", "2"]
    a, b = p.objects
    assert a.confidence == pytest.approx(0.91)
    assert b.confidence is None                     # absent stays absent, never 0
    assert a.box == {"x1": 211, "y1": 228, "x2": 271, "y2": 255, "w": 60, "h": 27}   # inclusive wire -> half-open
    assert a.mask_svg_path.startswith("M") and a.mask_box["raster_w"] == 60
    assert a.rle["size"] == [27, 60] and isinstance(a.rle["counts"], str)
    assert p.frame_sizes == {0: (320, 334)} and p.complete


def test_malformed_record_is_dropped_and_reported():
    bad = "<0f>0<|box;x1=211;y1=228;w=320;h=334|><|mask;x=0;y=0;data=27,60," + M0 + "|>," + rec(1, 155, 228, 202, 254, M1, 27, 48)
    p = parse_output(bad)
    # meta-sam-parser rejects the whole malformed line (conservative): nothing from it is drawn, and it is reported.
    assert p.objects == []
    assert not p.complete and any(d["code"] == "malformed_record" for d in p.diagnostics)
    # A valid line for another frame is still kept.
    good = rec(1, 155, 228, 202, 254, M1, 27, 48)
    p = parse_output(bad + "\n<1f>" + good + "\n", media="video")
    assert [(o.frame_index, o.object_id) for o in p.objects] == [(1, "1")] and not p.complete


def test_box_outside_frame_is_rejected():
    p = parse_output("<0f>" + rec(0, 211, 228, 900, 254, M0, 27, 60))
    assert p.objects == [] and not p.complete
    assert p.diagnostics[-1]["code"] == "invalid_box"


def test_invalid_mask_keeps_box_but_draws_no_mask():
    p = parse_output("<0f>" + rec(0, 211, 228, 270, 254, "!!!!zz", 27, 60))
    (o,) = p.objects
    assert o.mask_svg_path is None and o.mask_error and not p.complete


def test_multiple_frames_video_mode():
    line = rec(0, 211, 228, 270, 254, M0, 27, 60, c=0.5)
    p = parse_output(f"<0f>{line}\n<3f>{line}\n", media="video")
    assert [(o.frame_index, o.object_id) for o in p.objects] == [(0, "0"), (3, "0")] and p.complete


def test_image_mode_rejects_extra_frames():
    line = rec(0, 211, 228, 270, 254, M0, 27, 60)
    p = parse_output(f"<0f>{line}\n<3f>{line}\n")
    assert len(p.objects) == 1 and not p.complete


def test_unexpected_format_raises_instead_of_guessing():
    with pytest.raises(SamBadResponse):
        parse_output("I found an electrical panel in the top left.")


@pytest.mark.parametrize("phrase,ok", [
    ("fire extinguisher", True), ("electrical panel", True), ("cable tray", True),
    ("", False), ("missing smoke detector", False), ("person", False), ("face", False),
    ("panel near the door", False), ("extinguisher, panel", False), ("is there a fire extinguisher?", False),
    ("bình chữa cháy", False), ("a very long description of many things", False)])
def test_phrase_rules(phrase, ok):
    assert (phrase_problem(phrase) is None) == ok


# --- client (fake transport) -----------------------------------------------------------------------------------
class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def answer(text, **extra):
    body = {"id": "resp_test", "object": "response", "status": "completed", "model": "sam-3.1", "store": False,
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "images_processed": 1},
            "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}
    body.update(extra)
    return body


def opener(script, seen):
    """script: list of (status, body) returned in order."""
    def _open(req, timeout=0):
        seen.append(json.loads(req.data))
        assert req.headers["Authorization"] == "Bearer k"
        status, body = script.pop(0)
        if status == "timeout":
            raise TimeoutError("timed out")
        raw = json.dumps(body).encode() if isinstance(body, dict) else body
        if status != 200:
            raise urllib.error.HTTPError(req.full_url, status, "err", {}, io.BytesIO(raw))
        return FakeResp(raw)
    return _open


def client(script, seen, sleeps=None):
    return SamClient(MuseConfig(api_key="k"), opener=opener(script, seen),
                     sleep=(sleeps.append if sleeps is not None else (lambda s: None)))


def test_success_request_shape_and_result():
    seen = []
    r = client([(200, answer(TWO))], seen).locate(b"\xff\xd8jpeg", "Electrical Panel")
    body = seen[0]
    assert body["model"] == "sam-3.1" and body["store"] is False
    assert body["metadata"] == {"include_confidence": "true", "mask_encoding": "one_bit"}
    parts = body["input"][0]["content"]
    assert parts[0] == {"type": "input_text", "text": "electrical panel"}
    assert parts[1]["image_url"].startswith("data:image/jpeg;base64,")
    assert r.status == "located" and r.max_confidence == pytest.approx(0.91)
    assert r.images_billed == 1 and r.response_id == "resp_test" and r.store_disabled


def test_empty_answer_is_not_located():
    r = client([(200, answer(""))], []).locate(b"x", "fire extinguisher")
    assert r.status == "not_located" and r.max_confidence is None


def test_400_is_not_retried():
    seen = []
    with pytest.raises(SamBadRequest):
        client([(400, {"error": {"message": "invalid image"}})], seen).locate(b"x", "cable tray")
    assert len(seen) == 1


def test_400_on_store_parameter_resends_once_without_it():
    seen = []
    c = client([(400, {"error": {"message": "Unknown parameter: store"}}), (200, answer(TWO))], seen)
    r = c.locate(b"x", "cable tray")
    assert "store" in seen[0] and "store" not in seen[1] and r.status == "located"
    assert c.store_param_ok is False and not r.store_disabled


def test_404_model_not_found():
    seen = []
    with pytest.raises(SamModelNotFound) as e:
        client([(404, {"error": {"code": "model_not_found", "message": "no"}})], seen).locate(b"x", "cable tray")
    assert e.value.kind == "model_not_found" and len(seen) == 1


def test_429_then_success_uses_backoff():
    seen, sleeps = [], []
    r = client([(429, {"error": {}}), (503, {"error": {}}), (200, answer(TWO))], seen, sleeps).locate(b"x", "cable tray")
    assert r.status == "located" and len(seen) == 3 and len(sleeps) == 2 and sleeps[1] > sleeps[0] - 1


def test_rate_limit_gives_up_after_retries():
    with pytest.raises(SamRateLimited):
        client([(429, {})] * 4, []).locate(b"x", "cable tray")


def test_timeout_is_retried_then_reported():
    with pytest.raises(SamTimeout):
        client([("timeout", None)] * 4, []).locate(b"x", "cable tray")


@pytest.mark.parametrize("raw", [b"not json", json.dumps({"no": "output"}).encode(),
                                 json.dumps(answer("free text, not records")).encode()])
def test_malformed_responses(raw):
    def _open(req, timeout=0):
        return FakeResp(raw)
    with pytest.raises(SamBadResponse):
        SamClient(MuseConfig(api_key="k"), opener=_open).locate(b"x", "cable tray")


def test_not_configured_and_bad_phrase_make_no_request():
    with pytest.raises(SamNotConfigured):
        SamClient(MuseConfig(api_key=None)).locate(b"x", "cable tray")
    seen = []
    with pytest.raises(SamBadRequest):
        client([], seen).locate(b"x", "person")
    assert seen == []


# --- client against a real local HTTP mock server --------------------------------------------------------------
def test_against_local_mock_server():
    seen = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append((self.path, body["model"]))
            out = json.dumps(answer(TWO)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        cfg = MuseConfig(api_key="k", base_url=f"http://127.0.0.1:{srv.server_port}/v1")
        r = SamClient(cfg).locate(b"x", "fire extinguisher")
    finally:
        srv.shutdown()
    assert seen == [("/v1/responses", "sam-3.1")] and [o.object_id for o in r.parse.objects] == ["0", "2"]
