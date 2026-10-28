"""SAM 3.1 connection check (Phase 1) for FireRisk Intelligence. ORIGIN: NEW (2026-10-28).

One real request, nothing in the app pipeline is changed:
  1. finds the survey video "Electrical Panel - B1" on this computer (or the file given with --video),
  2. extracts ONE still frame with ffmpeg (ffmpeg applies the phone's rotation flag by default),
  3. sends it to `sam-3.1` on POST /v1/responses with the noun phrase "electrical panel" and asks for confidence,
  4. parses the answer with Meta's official parser `meta-sam-parser` (pip; Python >= 3.10),
  5. writes a sanitized report to evidence/sam_check_<timestamp>.json (no key, no image, no mask payload) and a
     private overlay preview (frame + boxes + masks) to data/private/sam_check/ (git-ignored).

API facts used (official docs read 2026-10-28 16:50 UTC+7: dev.meta.ai/docs/sam/overview, /sam/segmenting,
/sam/reading-segmentation, /sam/client-libraries, /pricing-rate-limits; parser README of meta-sam-parser 0.0.6):
  * model `sam-3.1`, POST {base}/responses, same Bearer key as Muse Spark;
  * one user message = one `input_text` (short noun phrase, ONE concept) + one `input_image`
    (image_url = public URL or base64 data URL);
  * metadata values are strings: include_confidence "true", mask_encoding "one_bit";
  * output_text: one line per frame `<0f>id<|box;x1;y1;x2;y2;w;h[;c]|><|mask;x=0;y=0[;c];data=H,W,<~|!>base85|>`,
    records separated by commas; an EMPTY output_text is a valid "no match" answer, not an error;
  * 400 = permanent (do not retry unchanged), 404 model_not_found = this key has no access to the model.

Usage:  python scripts/check_sam.py [--video PATH] [--time SECONDS] [--phrase "electrical panel"]
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from firerisk.ai.muse import MuseConfig  # noqa: E402  (reuses MODEL_API_KEY / META_API_BASE_URL from .env)
from firerisk.video import INBOX_DIR, VIDEO_DIR, ffmpeg_path, mp4_info, responses_text  # noqa: E402

MODEL = "sam-3.1"
DEFAULT_PHRASE = "electrical panel"
TIMEOUT_S = 180
DB_PATH = ROOT / "data" / "private" / "firerisk.db"
PRIVATE_OUT = ROOT / "data" / "private" / "sam_check"
FRAME_DIR = ROOT / "data" / "private" / "media" / "frames" / "sam_check"
EVIDENCE_DIR = ROOT / "evidence"
MAX_SIDE = 1280          # long side of the frame sent to SAM (keeps the base64 request small)


# --- find the video --------------------------------------------------------------------------------------------
def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _looks_like_panel_b1(name: str) -> bool:
    n = _norm(name)
    return "panel" in n and "b1" in n.split()


def find_video(explicit: str | None) -> tuple[Path | None, list[str]]:
    """Return (path, candidates seen). Prefers the exact name, then any 'panel ... B1' name (Drive has renamed copies)."""
    if explicit:
        p = Path(explicit)
        return (p if p.exists() else None), [str(p)]
    found: dict[str, Path] = {}
    if DB_PATH.exists():
        try:
            con = sqlite3.connect(DB_PATH)
            for filename, stored in con.execute("SELECT filename, stored_name FROM survey_videos"):
                p = VIDEO_DIR / stored
                if p.exists() and _looks_like_panel_b1(filename):
                    found[filename] = p
            con.close()
        except sqlite3.Error:
            pass
    for folder in (VIDEO_DIR, INBOX_DIR, ROOT / "data" / "private"):
        if folder.exists():
            for p in folder.rglob("*"):
                if p.suffix.lower() in (".mp4", ".mov", ".m4v") and _looks_like_panel_b1(p.name):
                    found.setdefault(p.name, p)
    if not found:
        return None, []
    exact = [k for k in found if _norm(Path(k).stem) == "electrical panel b1"]
    pick = exact[0] if exact else sorted(found)[0]
    return found[pick], sorted(found)


# --- frame -----------------------------------------------------------------------------------------------------
def jpeg_size(data: bytes) -> tuple[int, int] | None:
    """Width and height from a JPEG header (SOF marker), standard library only."""
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h = int.from_bytes(data[i + 5:i + 7], "big")
            w = int.from_bytes(data[i + 7:i + 9], "big")
            return w, h
        seg = int.from_bytes(data[i + 2:i + 4], "big")
        i += 2 + seg
    return None


def extract(video: Path, at_s: float, out: Path) -> None:
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("ffmpeg not found - run install.bat (it installs imageio-ffmpeg)")
    out.parent.mkdir(parents=True, exist_ok=True)
    # ffmpeg rotates frames according to the video's display-matrix / rotate tag by default (autorotate),
    # so the still frame is upright like in a video player. We do NOT pass -noautorotate.
    scale = (f"scale=w='if(gte(iw,ih),min({MAX_SIDE},iw),-2)':h='if(gte(iw,ih),-2,min({MAX_SIDE},ih))'")
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(at_s, 0):.2f}", "-i", str(video),
                    "-frames:v", "1", "-vf", scale, "-q:v", "3", str(out)], check=True, timeout=90)
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError("ffmpeg produced no frame (time beyond the end of the video?)")


# --- request ---------------------------------------------------------------------------------------------------
def call_sam(cfg: MuseConfig, phrase: str, jpeg: bytes) -> tuple[int | None, dict | str, float]:
    payload = {
        "model": MODEL,
        "input": [{"role": "user", "content": [
            {"type": "input_text", "text": phrase},
            {"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")},
        ]}],
        "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
    }
    req = urllib.request.Request(f"{cfg.base_url}/responses", data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json",
                                          "Accept": "application/json"})
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            raw, status = resp.read().decode("utf-8"), resp.status
    except urllib.error.HTTPError as err:
        raw, status = err.read().decode("utf-8", errors="replace"), err.code
    secs = time.monotonic() - start
    try:
        return status, json.loads(raw), secs
    except json.JSONDecodeError:
        return status, raw[:2000], secs


# --- parsing ---------------------------------------------------------------------------------------------------
MASK_DATA_RE = re.compile(r"(data=\d+,\d+,[~!])[^|]*")


def strip_masks(text: str) -> str:
    """Raw output with every base85 mask payload replaced by its length (safe to print and save)."""
    return MASK_DATA_RE.sub(lambda m: f"{m.group(1)}<{len(m.group(0)) - len(m.group(1))} chars>", text)


def parse(text: str):
    try:
        import meta_sam_parser as msp
    except ImportError:
        return None, "meta-sam-parser is not installed (run install.bat or: pip install meta-sam-parser>=0.0.6)"
    parser = msp.image_segmentation_format().create_parser()
    parser.push(text)
    result = parser.finish(msp.CompletedOutcome()).result
    objects: dict[str, dict] = {}
    for rec in result.records:
        if rec.kind == "box":
            objects.setdefault(rec.object_id, {"object_id": rec.object_id})["box"] = {
                "x1": rec.left, "y1": rec.top, "x2": rec.right, "y2": rec.bottom,
                "w": rec.right - rec.left, "h": rec.bottom - rec.top}
            objects[rec.object_id]["confidence"] = rec.confidence
        elif rec.kind == "mask":
            o = objects.setdefault(rec.object_id, {"object_id": rec.object_id})
            o["mask_encoding"] = rec.mask.encoding
            o["mask_raster"] = [rec.mask.width, rec.mask.height]
            try:
                o["_svg_path"] = msp.decode_mask_to_svg_path(rec.mask)
                o["_bounds"] = rec.bounds
                o["mask_decoded"] = True
            except msp.InvalidSegmentationMaskError as err:
                o["mask_decoded"] = False
                o["mask_error"] = str(err)[:200]
            if o.get("confidence") is None:
                o["confidence"] = rec.confidence
    info = {
        "records": len(result.records),
        "text_records": sum(1 for r in result.records if r.kind == "text"),
        "diagnostics": [{"severity": d.severity, "code": d.code, "line": d.line} for d in result.diagnostics],
    }
    return (list(objects.values()), info), None


# --- overlay preview -------------------------------------------------------------------------------------------
COLORS = ["#ff5a36", "#2ec4ff", "#ffd23f", "#7cff6b", "#ff4fd8", "#b28dff"]


def write_overlay(out: Path, jpeg: bytes, size: tuple[int, int], objects: list[dict], title: str) -> None:
    w, h = size
    shapes = []
    for i, o in enumerate(objects):
        col = COLORS[i % len(COLORS)]
        if o.get("_svg_path") and o.get("_bounds") and o.get("mask_raster"):
            b, (mw, mh) = o["_bounds"], o["mask_raster"]
            sx, sy = (b.right - b.left) / mw, (b.bottom - b.top) / mh
            shapes.append(f'<path d="{o["_svg_path"]}" transform="translate({b.left} {b.top}) scale({sx} {sy})" '
                          f'fill="{col}" fill-opacity="0.35" fill-rule="evenodd"/>')
        bx = o.get("box")
        if bx:
            conf = "" if o.get("confidence") is None else f" c={o['confidence']:.2f}"
            shapes.append(f'<rect x="{bx["x1"]}" y="{bx["y1"]}" width="{bx["w"]}" height="{bx["h"]}" fill="none" '
                          f'stroke="{col}" stroke-width="{max(2, w // 300)}"/>'
                          f'<text x="{bx["x1"] + 4}" y="{bx["y1"] + max(18, w // 50)}" fill="{col}" '
                          f'font-size="{max(16, w // 45)}" font-family="sans-serif">#{html.escape(o["object_id"])}{conf}</text>')
    img = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
    out.write_text(f"""<!doctype html><meta charset="utf-8"><title>SAM 3.1 check</title>
<style>body{{background:#111;color:#eee;font:14px sans-serif;margin:16px}}.wrap{{position:relative;max-width:100%;
width:{w}px}}.wrap img{{display:block;width:100%;height:auto}}.wrap svg{{position:absolute;inset:0;width:100%;
height:100%}}</style><p>{html.escape(title)} - PRIVATE preview, do not publish (real building frame).</p>
<div class="wrap"><img src="{img}" alt="frame"><svg viewBox="0 0 {w} {h}" preserveAspectRatio="none">{''.join(shapes)}
</svg></div>""", encoding="utf-8")


# --- main ------------------------------------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="SAM 3.1 connection check (one real request)")
    ap.add_argument("--video")
    ap.add_argument("--time", type=float, help="seconds into the video (default: middle)")
    ap.add_argument("--phrase", default=DEFAULT_PHRASE)
    args = ap.parse_args()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print("=" * 64)
    print("FireRisk Intelligence - SAM 3.1 connection check (Phase 1)")
    print("=" * 64)

    cfg = MuseConfig.load()
    if not cfg.configured:
        print("[FAIL] MODEL_API_KEY not found. Run setup_api_key.bat first.")
        return 2
    print(f"[OK]   API key loaded ({len(cfg.api_key)} characters, value hidden); endpoint {cfg.base_url}/responses")

    video, seen = find_video(args.video)
    if not video:
        print("[FAIL] Video 'Electrical Panel - B1' not found on this computer.")
        print(f"       Looked in {VIDEO_DIR} and {INBOX_DIR}. Start the dashboard and press Update Data,")
        print("       or pass the file:  python scripts\\check_sam.py --video \"C:\\path\\Electrical Panel - B1.mp4\"")
        return 2
    print(f"[OK]   Video: {video.name}" + (f"   (other matches: {', '.join(s for s in seen if s != video.name)})"
                                           if len(seen) > 1 else ""))
    dur = None
    try:
        dur = mp4_info(video).get("duration_s")
    except Exception:  # header unreadable: fall back to 1 s
        pass
    at = args.time if args.time is not None else (dur / 2 if dur else 1.0)
    if dur:
        at = min(max(at, 0.0), max(dur - 0.1, 0.0))
    frame = FRAME_DIR / f"sam_check_{stamp}.jpg"
    extract(video, at, frame)
    jpeg = frame.read_bytes()
    size = jpeg_size(jpeg)
    print(f"[OK]   Frame at {at:.2f}s of {dur or '?'}s -> {size[0]}x{size[1]} px, {len(jpeg) // 1024} KB "
          f"(rotation applied by ffmpeg)")

    print(f"\n[..]   POST /responses  model={MODEL}  phrase=\"{args.phrase}\"  include_confidence=true")
    try:
        status, body, secs = call_sam(cfg, args.phrase, jpeg)
    except Exception as exc:
        status, body, secs = None, f"{type(exc).__name__}: {exc}", 0.0
    ev: dict = {
        "check": "sam_3_1_connection", "run_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "endpoint": f"{cfg.base_url}/responses", "model_requested": MODEL, "phrase": args.phrase,
        "request_metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
        "video": video.name, "video_duration_s": dur, "frame_time_s": round(at, 2),
        "frame_size": list(size) if size else None, "frame_bytes": len(jpeg),
        "http_status": status, "request_seconds": round(secs, 2),
    }
    PRIVATE_OUT.mkdir(parents=True, exist_ok=True)
    if isinstance(body, dict):   # full answer kept PRIVATE (has mask payloads) - needed to build parser fixtures
        (PRIVATE_OUT / f"sam_raw_{stamp}.json").write_text(json.dumps(body, ensure_ascii=False, indent=2), "utf-8")

    result = "FAIL"
    if status is None:
        print(f"[FAIL] Network error: {body}")
        ev["error"] = str(body)[:300]
    elif status != 200:
        text = json.dumps(body) if isinstance(body, dict) else str(body)
        err = body.get("error", {}) if isinstance(body, dict) else {}
        code = err.get("code") if isinstance(err, dict) else None
        ev["error"] = {"code": code, "message": (err.get("message") if isinstance(err, dict) else text)[:300]}
        hint = {401: "key invalid or not active", 403: "key lacks access",
                404: "model not found - this key may not have access to sam-3.1" if code == "model_not_found"
                else "not found", 400: "request rejected (permanent - do not resend unchanged)",
                429: "rate limit / no credits"}.get(status, "unexpected error")
        print(f"[FAIL] HTTP {status} in {secs:.1f}s - {hint}\n       {text[:400]}")
        result = "MODEL_NOT_FOUND" if code == "model_not_found" else "FAIL"
    else:
        text = responses_text(body) if isinstance(body, dict) else ""
        ev["model_returned"] = body.get("model") if isinstance(body, dict) else None
        ev["response_status"] = body.get("status") if isinstance(body, dict) else None
        ev["usage"] = body.get("usage") if isinstance(body, dict) else None
        ev["output_items"] = [{"type": it.get("type"), "content_types": [c.get("type") for c in it.get("content", [])
                                                                         if isinstance(c, dict)]}
                              for it in (body.get("output") or []) if isinstance(it, dict)]
        ev["output_text_chars"] = len(text)
        ev["output_text_lines"] = len([ln for ln in text.splitlines() if ln.strip()])
        ev["output_text_masks_removed"] = strip_masks(text)[:1500]
        wh = sorted(set(re.findall(r"w=(\d+);h=(\d+)", text)))
        ev["frame_size_in_answer"] = [[int(a), int(b)] for a, b in wh]
        print(f"[OK]   HTTP 200 in {secs:.1f}s, model {ev['model_returned']}, usage {ev['usage']}")
        print(f"       output_text: {len(text)} chars, {ev['output_text_lines']} line(s)")
        if not text.strip():
            result = "NO_MATCH"
            ev["objects"] = []
            print("[OK]   Empty output_text = valid NO-MATCH answer (API works; no 'electrical panel' found in "
                  "this frame). Try another --time.")
        else:
            parsed, perr = parse(text)
            if perr:
                print(f"[WARN] {perr}\n       Answer (masks removed): {strip_masks(text)[:400]}")
                ev["parser"] = perr
                result = "PARSER_MISSING"
            else:
                objects, info = parsed
                ev["parser"] = "meta-sam-parser " + _pkg_version()
                ev["parse_info"] = info
                bad = [d for d in info["diagnostics"] if d["severity"] == "error"]
                ev["format_matches_docs"] = bool(objects) and not bad and info["text_records"] == 0 \
                    and all(o.get("box") and o.get("mask_decoded") for o in objects)
                ev["frame_size_matches_sent_frame"] = (ev["frame_size_in_answer"] == [list(size)]) if size else None
                ev["objects"] = [{k: v for k, v in o.items() if not k.startswith("_")} for o in objects]
                for o in ev["objects"]:
                    b = o.get("box") or {}
                    print(f"       object #{o['object_id']}: box x1={b.get('x1')} y1={b.get('y1')} x2={b.get('x2')} "
                          f"y2={b.get('y2')}  confidence={o.get('confidence')}  mask {o.get('mask_raster')} "
                          f"decoded={o.get('mask_decoded')}")
                if info["diagnostics"]:
                    print(f"[WARN] parser diagnostics: {info['diagnostics']}")
                if objects:
                    result = "LOCATED" if ev["format_matches_docs"] else "FORMAT_DIFFERS"
                    prev = PRIVATE_OUT / f"sam_check_{stamp}.html"
                    write_overlay(prev, jpeg, size, objects,
                                  f"{video.name} @ {at:.2f}s - '{args.phrase}' - {len(objects)} object(s)")
                    ev["overlay_preview"] = str(prev.relative_to(ROOT)).replace("\\", "/") + " (private, git-ignored)"
                    print(f"[OK]   Overlay preview (private): {prev}")
                else:
                    result = "FORMAT_DIFFERS"
                    print("[WARN] Non-empty answer but no box/mask records: format differs from the docs. "
                          "Not guessing - see the private raw file.")
                if not ev.get("frame_size_matches_sent_frame", True):
                    print(f"[WARN] Frame size in answer {ev['frame_size_in_answer']} differs from sent frame {size}")

    ev["result"] = result
    text = json.dumps(ev, indent=2, ensure_ascii=False)
    if cfg.api_key and cfg.api_key in text:
        text = text.replace(cfg.api_key, "<REDACTED_KEY>")
    EVIDENCE_DIR.mkdir(exist_ok=True)
    out = EVIDENCE_DIR / f"sam_check_{stamp}.json"
    out.write_text(text, encoding="utf-8")
    print("\n" + "=" * 64)
    print(f"RESULT: {result}")
    print(f"Sanitized report (no key, no image, no mask data): {out}")
    print("=" * 64)
    return 0 if result in ("LOCATED", "NO_MATCH") else 1


def _pkg_version() -> str:
    try:
        from importlib.metadata import version
        return version("meta-sam-parser")
    except Exception:
        return "?"


if __name__ == "__main__":
    sys.exit(main())
