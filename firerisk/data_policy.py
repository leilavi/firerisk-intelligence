"""Data owner's conditions, enforced in code (approval of 2026-10-30, see DATA_AUTHORIZATION.md).

ORIGIN: NEW.

Condition 2 of the approval: original technical drawings stay on the author's computer and are processed locally
only; they must never be uploaded to an external AI service. Only simplified, anonymised zone information (no
dimensions, cable routes or equipment details) may reach an AI request or the demo.

This module is the single place that decides whether a file may be sent to the Meta Model API. Every function that
uploads or embeds a file (`video.upload_file`, `media.describe_image`, `sam.SamClient.locate`) calls
`assert_may_send_to_ai` first. Documents (PDF, CAD drawings, office files) and anything named like a technical
drawing are refused, whatever the caller intended. The Drive sync records such files by name only and never
downloads them.
"""

from __future__ import annotations

import re
from pathlib import Path

# What may ever be sent to an AI service: survey video and still images taken from it (or inspection photos).
AI_ALLOWED_SUFFIXES = {".mp4", ".mov", ".m4v", ".jpg", ".jpeg", ".png", ".webp"}

# Documents that are never sent and never downloaded by the app (listed by name only).
DOCUMENT_SUFFIXES = {".pdf", ".dwg", ".dxf", ".dwf", ".ifc", ".rvt", ".skp", ".doc", ".docx", ".xls", ".ppt", ".pptx",
                     ".vsd", ".vsdx", ".zip", ".rar", ".7z"}
DOCUMENT_MIME_PREFIXES = ("application/pdf", "image/vnd.dwg", "image/vnd.dxf", "application/acad", "application/dxf",
                          "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml",
                          "application/vnd.openxmlformats-officedocument.presentationml", "application/vnd.ms-",
                          "application/zip", "application/x-rar", "application/x-7z")
# File or folder names that mark technical drawings or manuals, in English or Vietnamese.
DRAWING_NAME_RE = re.compile(
    r"tech[-_ ]?diag|drawing|schematic|layout|floor[-_ ]?plan|cable|wiring|single[-_ ]?line|riser|"
    r"o&m|o\s*and\s*m|manual|as[-_ ]?built|shop[-_ ]?drawing|"
    r"bản\s*vẽ|ban[-_ ]?ve|sơ\s*đồ|so[-_ ]?do|mặt\s*bằng|mat[-_ ]?bang|tuyến\s*cáp|tuyen[-_ ]?cap|hồ\s*sơ\s*hoàn\s*công",
    re.I)

LOCAL_ONLY_NOTE = ("Technical document: kept on the author's computer only, never downloaded by the app and never "
                   "sent to an AI service (data owner's condition 2).")


class LocalOnlyDocumentError(PermissionError):
    """Raised when code tries to send a local-only document to an AI service."""


# Strong markers: refuse even a video or image with this name (e.g. a screenshot of a drawing).
STRONG_DRAWING_RE = re.compile(r"tech[-_ ]?diag|drawing|schematic|floor[-_ ]?plan|bản\s*vẽ|ban[-_ ]?ve", re.I)
VIDEO_IMAGE_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".jpg", ".jpeg", ".png", ".webp", ".heic"}


def is_local_only_document(name: str, mime_type: str | None = None, folder: str | None = None) -> bool:
    """True for documents and technical drawings.

    Survey videos and photos are media, not documents: they are judged only by the strong drawing markers, so a
    video called "Cable tray B1.mp4" is still a survey video while "TECH-DIAG_riser.png" is refused. `folder` is the
    Drive folder path (or the file's parent folder); only its last two parts are considered."""
    mime = (mime_type or "").lower()
    name = name or ""
    suffix = Path(name).suffix.lower()
    folder_tail = "/".join(str(folder or "").replace("\\", "/").split("/")[-2:])
    if suffix in DOCUMENT_SUFFIXES or mime.startswith(DOCUMENT_MIME_PREFIXES):
        return True
    if mime.startswith("application/vnd.google-apps."):
        return not mime.endswith(("spreadsheet", "folder"))   # Google Docs / Slides / Drawings are documents
    if suffix in VIDEO_IMAGE_SUFFIXES or mime.startswith(("video/", "image/")):
        return bool(STRONG_DRAWING_RE.search(name) or STRONG_DRAWING_RE.search(folder_tail))
    return bool(DRAWING_NAME_RE.search(name) or DRAWING_NAME_RE.search(folder_tail))


def assert_may_send_to_ai(path: Path | str | None = None, *, data: bytes | None = None, mime_type: str | None = None) -> None:
    """Refuse documents and drawings before any upload to the Meta Model API."""
    if path is not None:
        p = Path(path)
        if is_local_only_document(p.name, mime_type, str(p.parent)):
            raise LocalOnlyDocumentError(f"{p.name}: {LOCAL_ONLY_NOTE}")
        if p.suffix and p.suffix.lower() not in AI_ALLOWED_SUFFIXES:
            raise LocalOnlyDocumentError(f"{p.name}: only survey video and still images may be sent to an AI service")
        head = p.read_bytes()[:8] if p.is_file() and data is None else (data or b"")[:8]
    else:
        head = (data or b"")[:8]
    if head.startswith((b"%PDF", b"PK\x03\x04", b"AC10", b"\xd0\xcf\x11\xe0")):   # PDF, zip/office, DWG, old office
        raise LocalOnlyDocumentError(f"{LOCAL_ONLY_NOTE} (content is a document, not an image or video)")


def local_only_documents(listing: list[dict]) -> list[dict]:
    """Names of local-only documents found in the Drive folder listing (metadata only, no content)."""
    return [{"title": f.get("title"), "mime_type": f.get("mime_type"), "size": f.get("size"),
             "folder": f.get("folder"), "drive_modified_time": f.get("modified_time"), "note": LOCAL_ONLY_NOTE}
            for f in listing or []
            if is_local_only_document(str(f.get("title") or ""), f.get("mime_type"), f.get("folder"))]
