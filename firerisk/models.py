"""Core data structures. ORIGIN: NEW (the pre-existing skill had no code data model)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SourceRef:
    """Exact location of a record in the original source - used for traceability."""
    source_key: str          # e.g. "ops_data"
    source_title: str        # original file title, e.g. "Operations Data"
    sheet: str               # tab name
    row: int                 # 1-based row number in the sheet (header = row 1)
    record_id: str | None    # the record's own ID column value, if any


@dataclass
class Evidence:
    """One normalized observation from a source record."""
    evidence_id: str
    kind: str                # meter_reading | inspection_check | incident | construction | asset_service | generator_run | vehicle_day
    timestamp: datetime | None
    asset_id: str | None
    zone: str | None
    title: str
    text: str
    status: str | None
    is_open: bool | None
    values: dict[str, Any] = field(default_factory=dict)
    persons: list[str] = field(default_factory=list)      # names/e-mails found in the record (for redaction)
    media_refs: list[str] = field(default_factory=list)   # image/video references found in the record
    flags: list[str] = field(default_factory=list)        # e.g. "test_record"
    tags: list[dict] = field(default_factory=list)        # hazard tags with matched term (filled by tagging)
    source: SourceRef | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat() if self.timestamp else None
        return d


@dataclass
class Signal:
    """A deterministic finding produced by a rule, pointing at evidence."""
    signal_id: str
    rule_id: str
    pathway: str             # hazard pathway key
    zone: str | None
    asset_id: str | None
    severity: str            # normal..emergency
    title: str
    basis: str               # human-readable explanation of why the rule fired
    evidence_ids: list[str]
    first_seen: datetime | None
    last_seen: datetime | None
    is_open: bool
    origin: str              # "PORTED" or "NEW"
    context_ids: list[str] = field(default_factory=list)   # context / possibly contradicting evidence
    fields: dict = field(default_factory=dict)              # the 14 skill alert fields (alert_fields.py)

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("first_seen", "last_seen"):
            d[k] = d[k].isoformat() if d[k] else None
        return d


@dataclass
class Alert:
    """Aggregated fire-risk alert at zone level (what the dashboard lists)."""
    alert_id: str
    zone: str
    zone_label: str
    severity: str
    title: str
    summary: str
    severity_basis: list[str]
    pathways: list[str]
    signal_ids: list[str]
    evidence_ids: list[str]
    links: list[dict]        # explicit relationships between evidence items, each with reasons
    first_seen: datetime | None
    last_seen: datetime | None
    open_items: int
    context_ids: list[str] = field(default_factory=list)
    fields: dict = field(default_factory=dict)
    related_equipment: list[dict] = field(default_factory=list)   # equipment alerts linked with reasons
    video_context: list[dict] = field(default_factory=list)       # survey-video observations (AI vision, context only)
    life_safety: dict = field(default_factory=dict)               # emergency lights / exit signs on the floor (drawings)

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("first_seen", "last_seen"):
            d[k] = d[k].isoformat() if d[k] else None
        return d
