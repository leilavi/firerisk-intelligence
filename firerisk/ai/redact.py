"""Pseudonymise personal data before anything is sent to an external model.

ORIGIN: NEW. Operational logs contain staff e-mails and names (requesters, technicians, guards).
They are not needed for fire-risk reasoning, so they are replaced with stable placeholders.
The mapping stays in memory on the user's machine and is never sent.
"""

from __future__ import annotations

import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
# Vietnamese honorific/role + capitalised name, e.g. "Anh Nam", "KTV Văn Hùng", "Chị Lan"
_HONORIFIC_NAME = re.compile(
    r"\b(Anh|Chị|Chú|Cô|Bác|KTV|Kỹ thuật viên|Bạn)\s+((?:[A-ZĐÀ-Ỹ][\wÀ-ỹ]*)(?:\s+[A-ZĐÀ-Ỹ][\wÀ-ỹ]*){0,2})")


class Redactor:
    def __init__(self) -> None:
        self.mapping: dict[str, str] = {}

    def _token(self, original: str, kind: str) -> str:
        key = original.strip().lower()
        if key not in self.mapping:
            self.mapping[key] = f"<{kind}-{len(self.mapping) + 1}>"
        return self.mapping[key]

    def add_known(self, names: list[str]) -> None:
        for n in names:
            if n and len(n.strip()) >= 2:
                self._token(n, "email" if "@" in n else "person")

    def text(self, s: str | None) -> str:
        if not s:
            return ""
        out = _EMAIL.sub(lambda m: self._token(m.group(0), "email"), s)
        out = _HONORIFIC_NAME.sub(lambda m: f"{m.group(1)} {self._token(m.group(2), 'person')}", out)
        for original, token in sorted(self.mapping.items(), key=lambda kv: -len(kv[0])):
            if "@" in original:
                continue
            out = re.sub(re.escape(original), token, out, flags=re.IGNORECASE)
        return out
