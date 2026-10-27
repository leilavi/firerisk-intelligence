"""Fire-safety hazard tagging of free-text records (Vietnamese operational vocabulary).

ORIGIN: NEW. Deterministic and explainable: every tag stores the exact matched term, so the
dashboard can show *why* a record was tagged. Patterns were written against the real
vocabulary found in the building's real logs (2026-10-27).
"""

from __future__ import annotations

import re

from ..models import Evidence

# Phrases that contain "cháy" but are NOT about combustion; removed before burnt/fire checks.
_NON_COMBUSTION = re.compile(r"báo\s*cháy|chữa\s*cháy|pccc|phòng\s*cháy", re.IGNORECASE)

TAG_PATTERNS: dict[str, re.Pattern] = {
    "water_ingress": re.compile(r"thấm\s*nước|nước\s*thấm|\bthấm\b|\bdột\b|rò\s*rỉ\s*nước|ngập|tràn\s*nước", re.IGNORECASE),
    "electrical_room": re.compile(r"\bMBA\b|\bMSB\b|trạm\s*biến\s*áp|tủ\s*điện|tủ\s*phân\s*phối|máy\s*cắt", re.IGNORECASE),
    "fire_detection": re.compile(r"báo\s*cháy|báo\s*nhiệt|báo\s*khói|đầu\s*báo|module\s*giám\s*sát|mô\s*đun\s*gs", re.IGNORECASE),
    "burnt_overheat": re.compile(r"cháy\s*(mô\s*tơ|motor|dây|cuộn|tụ|board)|khét|quá\s*nhiệt|nóng\s*bất\s*thường|bốc\s*khói|chập\s*(điện|mạch)?", re.IGNORECASE),
    "mechanical_jam": re.compile(r"kẹt\s*cứng|\bkẹt\b|bể\s*bạc\s*đạn|đứt\s*(dây\s*)?cu\s*roa|đứt\s*dây\s*cuủoa|hư\s*phần\s*cơ\s*khí", re.IGNORECASE),
    "motor_equipment": re.compile(r"mô\s*tơ|motor|máy\s*thổi\s*khí|thổi\s*khí|máy\s*bơm|\bbơm\b", re.IGNORECASE),
    "backup_power": re.compile(r"ắc\s*quy|acquy|ac\s*quy|máy\s*phát", re.IGNORECASE),
    "fire_water": re.compile(r"bể\s*pccc|bơm\s*(n\s*)?pccc|chữa\s*cháy", re.IGNORECASE),
    "smoke_control": re.compile(r"hút\s*khói|\bEAF", re.IGNORECASE),
    "pa_system": re.compile(r"loa\s*thông\s*báo|loa\s*sơ\s*tán|phát\s*loa", re.IGNORECASE),
    "lightning": re.compile(r"chống\s*sét", re.IGNORECASE),
    "fire_event": re.compile(r"cháy\s*nổ|hỏa\s*hoạn|bốc\s*cháy|phát\s*hiện\s*khói|có\s*khói|ngọn\s*lửa", re.IGNORECASE),
}
FAULT_WORDS = re.compile(
    r"lỗi|\bhư\b|hỏng|sự\s*cố|không\s*hoạt\s*động|\bđứt\b|kẹt|cháy\s*mô\s*tơ|thấm|giảm\s*hiệu\s*năng|báo\s*lỗi|"
    r"không\s*có\s*nguồn|\bbể\b|ngưng|dột|không\s*lên", re.IGNORECASE)


def tag_text(text: str) -> list[dict]:
    tags: list[dict] = []
    if not text:
        return tags
    cleaned = _NON_COMBUSTION.sub(" ", text)
    for tag, pat in TAG_PATTERNS.items():
        src = cleaned if tag in ("burnt_overheat", "fire_event") else text
        m = pat.search(src)
        if m:
            tags.append({"tag": tag, "term": m.group(0)})
    return tags


def has_fault(text: str) -> str | None:
    m = FAULT_WORDS.search(text or "")
    return m.group(0) if m else None


def tag_evidence(items: list[Evidence]) -> list[Evidence]:
    for e in items:
        if e.kind == "inspection_check":
            # only the recorded result/notes are observations; a passing checklist is context evidence
            e.tags = tag_text(e.text)
            if e.is_open:
                e.tags.append({"tag": "fault", "term": f"checklist result: {e.status}"})
            else:
                e.tags.append({"tag": "checklist_pass", "term": e.status or ""})
            continue
        if e.kind in ("incident", "construction", "asset_service"):
            e.tags = tag_text(f"{e.title} | {e.text}")
            fault = has_fault(f"{e.title} | {e.text}")
            if fault and e.kind != "construction":
                e.tags.append({"tag": "fault", "term": fault})
        elif e.kind == "generator_run":
            reason = (e.values.get("reason") or "").lower()
            if "mất điện" in reason or "cắt điện" in reason:
                e.tags = [{"tag": "grid_outage", "term": e.values.get("reason")}]
    return items


def tagset(e: Evidence) -> set[str]:
    return {t["tag"] for t in e.tags}
