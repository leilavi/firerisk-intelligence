"""Asset register tab ('Asset') and the survey-video references it contains. ORIGIN: NEW.

The 'Asset' tab is the building's equipment register (one row per equipment item or room). Since 2026-10-27 the
author links survey videos to equipment rows in the `Reference_File` column (Google Drive links).

What is used:
  * equipment name, category, floor, area, location, status, last maintenance and next due date
    (context and display names only - no rule uses them as findings);
  * every Drive link in `Reference_File` becomes a survey-video REFERENCE linked to that equipment.
Zone of a video = the `Floor` of a row that links it (B1, F1..F4, Rooftop -> Roof). When no linking row has a floor,
the zone stays unassigned (nothing is guessed from names); the user can set it in the dashboard.
The tab is optional: when it is missing, the analysis runs as before and the source is listed as not present.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from ..config import LOCAL_TZ, ZONE_LABELS
from ..rules.scope import in_scope

ASSET_TAB = "Asset"
FLOOR_TO_ZONE = {"B1": "B1", "F1": "F1", "F2": "F2", "F3": "F3", "F4": "F4", "Rooftop": "Roof", "Roof": "Roof"}
DRIVE_ID = re.compile(r"(?:/d/|[?&]id=)([A-Za-z0-9_-]{20,})")


def _s(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _d(v) -> str | None:
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=LOCAL_TZ)).isoformat()
    return _s(v)


def load_asset_register(path: Path, source_title: str) -> tuple[dict[str, dict], list[dict], dict]:
    """Returns (register by equipment ID, video references, source stats)."""
    from .workbook import list_tabs, read_tab
    try:
        if ASSET_TAB not in set(list_tabs(path)):
            return {}, [], {"present": False, "note": "tab not in workbook (optional source)"}
        tab = read_tab(path, ASSET_TAB)
    except Exception as exc:
        return {}, [], {"present": True, "error": f"tab could not be processed: {type(exc).__name__}: {exc}"}
    register: dict[str, dict] = {}
    by_file: dict[str, dict] = {}
    for row_no, r in tab.rows:
        eid = _s(r.get("Equipment_ID"))
        if not eid or not in_scope(_s(r.get("Branch")), _s(r.get("Location_ID")), eid):
            continue
        floor = _s(r.get("Floor"))
        item = {"equipment_id": eid, "name": _s(r.get("Equipment_Name")), "category": _s(r.get("Main_Category")),
                "work_item": _s(r.get("Work_Item")), "floor": floor, "zone": FLOOR_TO_ZONE.get(floor or ""),
                "area": _s(r.get("Area")), "unit": _s(r.get("Unit")), "location_id": _s(r.get("Location_ID")),
                "notes": _s(r.get("Equipment_Notes")), "status": _s(r.get("Assets_Status")),
                "last_maintenance": _d(r.get("Last_Maintenance_Date")), "next_due": _d(r.get("Next_Due_Date")),
                "daily_inspection": r.get("Daily_Inspection"),
                "source": {"source_key": "ops_data", "source_title": source_title, "sheet": ASSET_TAB, "row": row_no,
                           "record_id": eid}}
        register.setdefault(eid, item)
        m = DRIVE_ID.search(_s(r.get("Reference_File")) or "")
        if m:
            fid = m.group(1)
            ref = by_file.setdefault(fid, {"drive_file_id": fid, "url": _s(r.get("Reference_File")),
                                           "equipment": [], "zones": set(), "rows": []})
            ref["equipment"].append({"equipment_id": eid, "name": item["name"], "floor": floor, "notes": item["notes"]})
            ref["rows"].append(row_no)
            if item["zone"]:
                ref["zones"].add(item["zone"])
    refs = []
    for ref in by_file.values():
        zones = sorted(ref.pop("zones"))
        ref["zone"] = zones[0] if len(zones) == 1 else None
        ref["zone_source"] = ("asset register Floor" if len(zones) == 1 else
                              f"ambiguous: {', '.join(zones)}" if zones else "not in the register (set it in the dashboard)")
        ref["source"] = {"source_title": source_title, "sheet": ASSET_TAB, "rows": ref.pop("rows")}
        refs.append(ref)
    stats = {"present": True, "rows_read": tab.count, "in_scope": len(register), "video_references": len(refs),
             "latest_record": None}
    return register, refs, stats


def zone_label(z: str | None) -> str:
    return ZONE_LABELS.get(z or "", "Not assigned")
