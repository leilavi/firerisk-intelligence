"""Demo privacy: blurred copies of evidence frames and a demo mode that hides building names. ORIGIN: NEW (2026-10-29).

Why: frames from technical rooms show name plates (e.g. a transformer plate with the building name) and some records
or AI texts quote that name. For the public demo video the dashboard can run in DEMO MODE (FIRERISK_DEMO_MODE=1):
  * /api/frames serves ONLY the blurred copy from data/private/media/frames_demo/ (never the original);
  * original videos and on-request frames are not served (no blurred video copy exists);
  * the header shows "Demo building" and the page masks building-name text before it is shown.
Rules: originals are never modified; a blurred copy is supporting material for the demo, not inspection evidence;
nothing is called "anonymized" until the review sheet has been inspected (manifest field `reviewed`).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import unicodedata
from pathlib import Path

from .config import _SITE
from .localize import FRAMES_DIR

FRAMES_DEMO_DIR = Path(os.environ.get("FIRERISK_FRAMES_DEMO_DIR", FRAMES_DIR.parent / "frames_demo"))
MANIFEST = "manifest.json"
DEMO_BUILDING = "Demo building"
DEFAULT_PHRASES = ("sign", "label")
PAD = 0.06                                  # box padding, fraction of the box size (a sign edge must not show)


def demo_mode() -> bool:
    from .env import load_env
    return load_env().get("FIRERISK_DEMO_MODE", "0") == "1"


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFD", s.replace("Đ", "D").replace("đ", "d"))
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


GENERIC = {"plaza", "building", "tower", "center", "centre", "data", "the", "mall", "office"}


def name_patterns(site: dict | None = None) -> list[str]:
    """JavaScript-compatible regex sources (case-insensitive) for the building's names, built from the private
    site_config.json: the full names, the distinctive words in either order, and the branch prefix."""
    site = _SITE if site is None else site
    pats: list[str] = []
    for key in ("building_name", "ops_source_title", "branch_prefix"):
        v = (site.get(key) or "").strip()
        if not v:
            continue
        words = [w for w in re.split(r"[\s\-_.]+", _fold(v)) if w]
        if key == "branch_prefix":
            # e.g. "ĐT-Plaza" -> [ĐD]T[\s\-_]*Plaza
            parts = [re.escape(w) for w in words]
            first = parts[0].replace("D", "[DĐđd]", 1) if parts and parts[0][:1].upper() == "D" else parts[0]
            pats.append(r"[\s\-_]*".join([first] + parts[1:]))
            continue
        distinctive = [w for w in words if w.lower() not in GENERIC]
        if len(words) > len(distinctive) >= 1:          # full name first, e.g. "Acme Riverside Plaza"
            pats.append(r"[\s\-_]*".join(_accent_class(w) for w in words))
        if len(distinctive) >= 2:
            a, b = distinctive[0], distinctive[1]
            wa, wb = _accent_class(a), _accent_class(b)
            pats.append(rf"{wa}[\s\-_]*{wb}")          # e.g. "Acme Riverside", "ÀCMÉ RIVÈRSIDE", "AcmeRiverside"
        elif distinctive:
            pats.append(_accent_class(distinctive[0]))
    # short form used in some records: initials + generic word (e.g. "ĐT Plaza", "DT Plaza")
    bn = [w for w in re.split(r"\s+", _fold(site.get("building_name") or "")) if w]
    dist = [w for w in bn if w.lower() not in GENERIC]
    gen = [w for w in bn if w.lower() in GENERIC]
    if len(dist) >= 2 and gen:
        ini = "".join(_accent_class(w[0]) for w in dist)
        pats.append(rf"\b{ini}[\s\-_]*{re.escape(gen[0])}\b")
    for extra in site.get("extra_names") or []:          # optional private list, e.g. an operator brand
        if isinstance(extra, str) and extra.strip():
            pats.append(r"[\s\-_]*".join(_accent_class(w) for w in re.split(r"[\s\-_]+", _fold(extra.strip())) if w))
    return list(dict.fromkeys(pats))


_VOWEL_CLASS = {
    "a": "aàáảãạăằắẳẵặâầấẩẫậ", "e": "eèéẻẽẹêềếểễệ", "i": "iìíỉĩị", "o": "oòóỏõọôồốổỗộơờớởỡợ",
    "u": "uùúủũụưừứửữự", "y": "yỳýỷỹỵ", "d": "dđ"}


def _accent_class(word: str) -> str:
    out = []
    for ch in word:
        lo = ch.lower()
        if lo in _VOWEL_CLASS:
            cls = _VOWEL_CLASS[lo]
            out.append("[" + cls + cls.upper() + "]")
        else:
            out.append(re.escape(ch))
    return "".join(out)


def mask_text(text: str, patterns: list[str] | None = None, repl: str = "[name hidden]") -> str:
    for p in patterns if patterns is not None else name_patterns():
        text = re.sub(p, repl, text, flags=re.I)
    return text


# --- manifest ----------------------------------------------------------------------------------------------------
def load_manifest(root: Path = None) -> dict:
    p = (root or FRAMES_DEMO_DIR) / MANIFEST
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"frames": {}, "reviewed": False, "note": "Blurred demo copies. Not inspection evidence."}


def save_manifest(m: dict, root: Path = None) -> None:
    root = root or FRAMES_DEMO_DIR
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / (MANIFEST + ".part")
    tmp.write_text(json.dumps(m, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(root / MANIFEST)


def demo_frame_path(frame_file: str, root: Path = None) -> Path | None:
    """Blurred copy for a frame ('<sha16>/tNNNNNN.jpg') if it was made; None otherwise."""
    m = load_manifest(root)
    e = m["frames"].get(frame_file)
    if not e or e.get("status") not in ("blurred", "no_label_found"):
        return None
    p = (root or FRAMES_DEMO_DIR) / frame_file
    return p if p.exists() else None


# --- blurring ----------------------------------------------------------------------------------------------------
def padded(box: dict, w: int, h: int, pad: float = PAD) -> tuple[int, int, int, int]:
    px, py = box["w"] * pad + 2, box["h"] * pad + 2
    x1, y1 = max(0, int(box["x1"] - px)), max(0, int(box["y1"] - py))
    x2, y2 = min(w, int(box["x2"] + px + 0.999)), min(h, int(box["y2"] + py + 0.999))
    return x1, y1, x2, y2


def blur_regions(src: Path, out: Path, regions: list[tuple[int, int, int, int]], ffmpeg: str | None = None) -> Path:
    """Copy `src` to `out` with each region strongly blurred (ffmpeg crop -> boxblur -> overlay). Never edits src."""
    from .video import ffmpeg_path
    ff = ffmpeg or ffmpeg_path()
    if not ff:
        raise RuntimeError("ffmpeg is not available (run install.bat)")
    out.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() == out.resolve():
        raise ValueError("refusing to overwrite the original frame")
    tmp = out.with_suffix(".part.jpg")
    if not regions:
        cmd = [ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-q:v", "3", str(tmp)]
    else:
        chain, last = [], "0:v"
        for n, (x1, y1, x2, y2) in enumerate(regions):
            w, h = max(2, x2 - x1), max(2, y2 - y1)
            r = max(2, min(w, h) // 3)
            chain.append(f"[0:v]crop={w}:{h}:{x1}:{y1},boxblur={r}:3:{max(1, r // 2)}:3[b{n}]")
            chain.append(f"[{last}][b{n}]overlay={x1}:{y1}[o{n}]")
            last = f"o{n}"
        cmd = [ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-filter_complex", ";".join(chain),
               "-map", f"[{last}]", "-q:v", "3", str(tmp)]
    subprocess.run(cmd, check=True, timeout=120, capture_output=True)
    tmp.replace(out)
    return out
