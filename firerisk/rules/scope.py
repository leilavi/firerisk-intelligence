"""Scope filter and test-record detection.

ORIGIN: PORTED from skill v2.2 §2.3:
  - keep only records of [Building] (Location/Branch starts with "BLD", or Equipment_ID starts with "P-");
  - flag test records ("Test", "Chỉ test", placeholder technician names, "AAAAA") and exclude them
    from statistics, EXCEPT safety-related test records, which stay visible as "unverified".
"""

from __future__ import annotations

import re

from ..config import ASSET_PREFIX, BRANCH_PREFIX

_TEST_PATTERNS = [
    re.compile(r"\btest\b", re.IGNORECASE),
    re.compile(r"chỉ\s*test", re.IGNORECASE),
    re.compile(r"A{5,}"),
]
_PLACEHOLDER_PATTERNS = [
    re.compile(r"hãy\s+nhập", re.IGNORECASE),
    re.compile(r"tên\s+ktv\s+sửa\s+chữa\s*\?", re.IGNORECASE),
    re.compile(r"hãy\s+mô\s+tả\s+chi\s+tiết", re.IGNORECASE),
    re.compile(r"nhập\s+nd\s+chi\s+tiết", re.IGNORECASE),
]
# Topics for which a test-looking record is still surfaced (skill §2.3 exception)
_SAFETY_WORDS = re.compile(r"thang máy|thang cuốn|điện|pccc|báo cháy|máy phát|cháy|khói", re.IGNORECASE)


def in_scope(branch: str | None = None, location: str | None = None, asset_id: str | None = None) -> bool:
    for v in (branch, location):
        if v and str(v).strip().startswith(BRANCH_PREFIX):
            return True
    if asset_id and str(asset_id).strip().startswith(ASSET_PREFIX):
        return True
    return False


def classify_text_quality(*texts: str | None) -> list[str]:
    """Return flags: 'test_record' and/or 'placeholder_text'; plus 'safety_test_record' when applicable."""
    joined = " ".join(t for t in texts if t)
    flags: list[str] = []
    if any(p.search(joined) for p in _TEST_PATTERNS):
        flags.append("test_record")
        if _SAFETY_WORDS.search(joined):
            flags.append("safety_test_record")
    if any(p.search(joined) for p in _PLACEHOLDER_PATTERNS):
        flags.append("placeholder_text")
    return flags
