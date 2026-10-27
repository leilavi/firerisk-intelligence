"""Image / video evidence - prepared integration (no real media available yet).

ORIGIN: NEW.
Status (2026-10-27):
  * The source logs already REFERENCE photos (AppSheet columns such as Hình_ảnh_1 or
    'Inspection_Logs_Images/...jpg'), but the image files are not in the user's Google Drive, so they
    are listed as "referenced, not available".
  * Media files placed in data/private/media/ (or a configured folder) are matched by file name to the
    records that reference them, and become viewable in the dashboard.
  * Video: frames are sampled with ffmpeg (if installed) into data/private/media/frames/.
  * Muse Spark image description uses the verified Chat Completions image format
    (https://dev.meta.ai/docs/image-understanding). It has NOT yet been run on a real photo.
  * SAM 3.1 segmentation: model `sam-3.1` exists for this key (verified model list), but the output
    format/parsing has not been verified -> not implemented yet (no guessed payloads).
"""

from __future__ import annotations

import base64
import mimetypes
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEDIA_DIR = Path(os.environ.get("FIRERISK_MEDIA_DIR", ROOT / "data" / "private" / "media"))
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXT = {".mp4", ".mov"}


def _local_index() -> dict[str, Path]:
    if not MEDIA_DIR.exists():
        return {}
    return {p.name.lower(): p for p in MEDIA_DIR.rglob("*") if p.is_file()}


def media_inventory(result) -> dict:
    """List every media reference found in the evidence and whether the file is available locally."""
    local = _local_index()
    items = []
    for e in result.evidence.values():
        for ref in e.media_refs:
            name = ref.replace("\\", "/").split("/")[-1].lower()
            path = local.get(name)
            items.append({"evidence_id": e.evidence_id, "kind": e.kind, "reference": ref,
                          "type": "video" if Path(name).suffix in VIDEO_EXT or ref.startswith("http") and "video" in ref.lower()
                          else "image",
                          "available": bool(path), "local_path": str(path.relative_to(MEDIA_DIR)) if path else None})
    extra = [str(p.relative_to(MEDIA_DIR)) for p in local.values()
             if p.suffix.lower() in IMAGE_EXT | VIDEO_EXT and str(p.relative_to(MEDIA_DIR)) not in
             {i["local_path"] for i in items}]
    return {"summary": {"references": len(items), "available": sum(i["available"] for i in items),
                        "unlinked_local_files": len(extra), "media_dir": str(MEDIA_DIR)},
            "items": items, "unlinked_local_files": extra}


def extract_frames(video: Path, every_seconds: float = 5.0, out_dir: Path | None = None) -> list[Path]:
    """Sample one frame every N seconds with ffmpeg. Returns the frame files written."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is not installed; install it to extract video frames")
    out_dir = out_dir or (MEDIA_DIR / "frames" / video.stem)
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(video), "-vf", f"fps=1/{every_seconds}",
                    str(out_dir / "frame_%05d.jpg")], check=True)
    return sorted(out_dir.glob("frame_*.jpg"))


def image_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


VISION_SCHEMA = {
    "name": "FireSafetyImageObservation",
    "strict": True,
    "schema": {
        "type": "object", "additionalProperties": False,
        "required": ["description", "fire_safety_observations", "limitations"],
        "properties": {
            "description": {"type": "string"},
            "fire_safety_observations": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["observation", "category", "visible_certainty"],
                "properties": {"observation": {"type": "string"},
                               "category": {"type": "string", "enum": ["water_or_moisture", "heat_or_burn_marks", "electrical_condition",
                                                                       "obstruction", "fire_equipment_condition", "housekeeping", "other"]},
                               "visible_certainty": {"type": "string", "enum": ["clearly_visible", "possibly_visible", "not_determinable"]}}}},
            "limitations": {"type": "string"},
        },
    },
}


def describe_image(client, path: Path, context: str) -> dict:
    """Ask Muse Spark what is visible in a photo that matters for fire safety (verified request format)."""
    import json
    body = {
        "model": client.config.model,
        "messages": [
            {"role": "system", "content": "Describe only what is visible in the photo. Do not infer causes. "
                                          "Say when something cannot be determined from the image."},
            {"role": "user", "content": [
                {"type": "text", "text": f"Context from the building log: {context}"},
                {"type": "image_url", "image_url": {"url": image_data_url(path)}}]},
        ],
        "response_format": {"type": "json_schema", "json_schema": VISION_SCHEMA},
        "reasoning_effort": "low",
        "max_completion_tokens": 3000,
    }
    resp = client._post("/chat/completions", body)
    return json.loads(resp["choices"][0]["message"]["content"])
