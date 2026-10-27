"""Turn source tabs into Evidence records with exact source references.

ORIGIN: NEW (canonical evidence model). Uses PORTED scope/test-record rules.
Column names below are the real column names of the [Building] sources (read 2026-10-27).
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from pathlib import Path

from ..config import ASSETS, INSPECTION_CHECKLISTS, LOCAL_TZ, METERS, OPEN_STATUS
from ..models import Evidence, SourceRef
from ..rules.scope import classify_text_quality, in_scope
from .workbook import TabData, read_tab

OPS_TABS = {
    "meters": "chỉ số điện nước",
    "assets": "BC hư hỏng TS",
    "incidents": "NK thi công - sự cố",
    "generator": "Dầu M Phát điện",
}

_FLOOR_TOKEN = re.compile(r"^(B\d|F\d{1,2})$")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def _ts(v) -> datetime | None:
    if isinstance(v, datetime):
        return v.replace(tzinfo=LOCAL_TZ) if v.tzinfo is None else v
    if isinstance(v, date):
        return datetime.combine(v, time(0, 0), tzinfo=LOCAL_TZ)
    return None


def _s(v) -> str:
    if v is None:
        return ""
    return str(v).strip()


def zone_from_location(loc: str | None) -> str | None:
    """'BLD-A-B1-Chung-' -> 'B1';  'BLD-A-F4--T09_119' -> 'F4'."""
    if not loc:
        return None
    for tok in str(loc).split("-"):
        if _FLOOR_TOKEN.match(tok.strip()):
            return tok.strip()
    return None


_TEXT_ZONES = [
    (re.compile(r"tầng\s*hầm|\bhầm\b|\bB1\b", re.IGNORECASE), "B1"),
    (re.compile(r"phòng\s*(MBA|MSB)|\bMBA\b|\bMSB\b", re.IGNORECASE), "B1"),
    (re.compile(r"(tầng\s*2\b|\b2F\b|2F\s*-)", re.IGNORECASE), "F2"),
    (re.compile(r"(tầng\s*3\b|\b3F\b|3F\s*-)", re.IGNORECASE), "F3"),
    (re.compile(r"(tầng\s*1\b|\b1F\b)", re.IGNORECASE), "F1"),
    (re.compile(r"(tầng\s*4\b|\b4F\b)", re.IGNORECASE), "F4"),
]


def zone_from_text(text: str) -> str | None:
    for pat, zone in _TEXT_ZONES:
        if pat.search(text):
            return zone
    return None


def _persons(*vals) -> list[str]:
    out: list[str] = []
    for v in vals:
        s = _s(v)
        if s and s not in out:
            out.append(s)
        out.extend(e for e in _EMAIL.findall(s) if e not in out)
    return out


def _media(row: dict, cols: list[str]) -> list[str]:
    return [_s(row.get(c)) for c in cols if _s(row.get(c))]


def _open(status: str | None) -> bool | None:
    if not status:
        return None
    return OPEN_STATUS.get(status.strip())


# ---------------------------------------------------------------------------------------
def normalize_meters_tab(tab: TabData, source_title: str) -> list[Evidence]:
    """Meter readings (unique Log_ID per day) and daily inspection checklists (Log_ID 'C-...')."""
    out: list[Evidence] = []
    for rownum, r in tab.rows:
        log_id = _s(r.get("Log_ID"))
        asset = _s(r.get("Equipment_ID")) or None
        if not in_scope(branch=r.get("Branch"), asset_id=asset):
            continue
        ts = _ts(r.get("Thời_Điểm_Kiểm_Tra")) or _ts(r.get("Ngay_Kiem_Tra"))
        notes = " | ".join(x for x in (_s(r.get("Báo_Cáo_Bất_Thường")), _s(r.get("Lý_Do_Cần_Theo_Dõi")),
                                       _s(r.get("Hướng_Xử_Lý")), _s(r.get("Đánh_Giá_Cảm_Quan"))) if x)
        media = _media(r, ["Hình_ảnh_1", "Hình_ảnh_2", "Hình_ảnh_3", "Hình_ảnh_4", "Hình_ảnh_Chạy_Thử"])
        ref = SourceRef("ops_data", source_title, tab.sheet, rownum, log_id or None)
        cfg_asset = ASSETS.get(asset or "", {})
        if log_id.startswith("C-"):
            name = INSPECTION_CHECKLISTS.get(log_id, log_id)
            result = _s(r.get("Tình_Trạng_Thiết_Bị"))
            out.append(Evidence(
                evidence_id=f"insp:{log_id}:{ts.date().isoformat() if ts else rownum}",
                kind="inspection_check", timestamp=ts, asset_id=asset, zone=cfg_asset.get("zone"),
                title=f"Daily checklist - {name}: {result or 'no result'}",
                # text = observations only; the checklist instructions are guidance, not findings
                text=notes,
                status=result or None, is_open=(result not in ("Đạt", "")) if result else None,
                values={"checklist": log_id, "result": result, "shift": _s(r.get("Ca_Truc")),
                        "instructions": " ".join(x for x in (_s(r.get("Hướng_Dẫn_Chung")),
                                                             _s(r.get("Hướng_Dẫn_Chi_Tiết"))) if x)},
                media_refs=media, flags=classify_text_quality(notes), source=ref))
        else:
            reading = r.get("Chỉ_Số_Thiết_Bị")
            meter = METERS.get(asset or "", {})
            out.append(Evidence(
                evidence_id=f"meter:{asset}:{rownum}",
                kind="meter_reading", timestamp=ts, asset_id=asset, zone=meter.get("zone") or cfg_asset.get("zone"),
                title=f"Meter reading {asset}",
                text=notes, status=None, is_open=None,
                values={"reading": reading if isinstance(reading, (int, float)) else None,
                        "daily_entered": r.get("Tiêu_Thụ_Ngày"), "system_code": _s(r.get("Tên_Hệ_Thống"))},
                media_refs=media, flags=classify_text_quality(notes), source=ref))
    return out


def normalize_assets_tab(tab: TabData, source_title: str) -> list[Evidence]:
    out: list[Evidence] = []
    for rownum, r in tab.rows:
        asset = _s(r.get("Equipment_ID")) or None
        loc = _s(r.get("Location_ID")) or None
        if not in_scope(location=loc, asset_id=asset):
            continue
        log_id = _s(r.get("Log_ID"))
        status = _s(r.get("Current_Status")) or None
        ts = _ts(r.get("Latest_Activity_Date")) or _ts(r.get("Maintenance_Date"))
        problem, work = _s(r.get("Service_Details")), _s(r.get("Maintenance_Details"))
        text = " | ".join(x for x in (problem, work) if x)
        zone = zone_from_location(loc) or ASSETS.get(asset or "", {}).get("zone") or zone_from_text(text)
        out.append(Evidence(
            evidence_id=f"asset:{log_id or rownum}",
            kind="asset_service", timestamp=ts, asset_id=asset, zone=zone,
            title=problem or work or log_id, text=text, status=status, is_open=_open(status),
            values={"service_type": _s(r.get("Service Type")), "action_type": _s(r.get("Action_Type")),
                    "location_id": loc, "estimated_cost": r.get("Estimated_Cost"), "actual_cost": r.get("Actual_Cost"),
                    "expected_completion": _s(r.get("Expected_Completion_Date"))},
            persons=_persons(r.get("Requester"), r.get("Approving_Mgr"), r.get("Technician_Name")),
            flags=classify_text_quality(problem, work, _s(r.get("Technician_Name"))) + ([] if ts else ["undated"]),
            source=SourceRef("ops_data", source_title, tab.sheet, rownum, log_id or None)))
    return out


def normalize_incidents_tab(tab: TabData, source_title: str) -> list[Evidence]:
    out: list[Evidence] = []
    for rownum, r in tab.rows:
        code = _s(r.get("Mã sự cố/ nâng cấp"))
        branch = _s(r.get("Chi Nhánh"))
        if not in_scope(branch=branch, location=code):
            continue
        rtype = _s(r.get("Loại báo cáo"))
        status = _s(r.get("Trạng thái")) or None
        quick, detail, fix = _s(r.get("Báo cáo nhanh")), _s(r.get("Mô tả chi tiết")), _s(r.get("Hướng xử lý, khắc phục"))
        notes = " ".join(_s(r.get(f"Ghi chú H{i}")) for i in range(1, 6) if _s(r.get(f"Ghi chú H{i}")))
        text = " | ".join(x for x in (quick, detail, fix, notes) if x)
        zone = (_s(r.get("Tầng")) if _FLOOR_TOKEN.match(_s(r.get("Tầng"))) else None) or zone_from_location(code) \
            or zone_from_text(text)
        media = _media(r, [f"Hình ảnh {i}" for i in range(1, 6)] + ["Video_link_Url"])
        out.append(Evidence(
            evidence_id=f"inc:{code or rownum}",
            kind="incident" if rtype == "Báo cáo sự cố" else "construction",
            timestamp=_ts(r.get("Thời gian báo cáo")), asset_id=None, zone=zone,
            title=quick or code, text=text, status=status, is_open=_open(status),
            values={"report_type": rtype, "urgency": _s(r.get("Mức độ khẩn cấp")),
                    "start": _s(r.get("Tg bắt đầu TC")), "done": _s(r.get("Tg Hoàn thành"))},
            persons=_persons(r.get("Người báo cáo")), media_refs=media,
            flags=classify_text_quality(quick, detail),
            source=SourceRef("ops_data", source_title, tab.sheet, rownum, code or None)))
    return out


def normalize_generator_tab(tab: TabData, source_title: str) -> list[Evidence]:
    out: list[Evidence] = []
    for rownum, r in tab.rows:
        asset = _s(r.get("Thiết_Bị_Vận_Hành")) or None
        if not in_scope(branch=r.get("Branch"), asset_id=asset):
            continue
        rid = _s(r.get("ID"))
        dur = r.get("Thời_lượng_VH")
        minutes = dur.hour * 60 + dur.minute if isinstance(dur, time) else None
        reason = _s(r.get("Lý_do_Vận_Hành"))
        out.append(Evidence(
            evidence_id=f"gen:{rid or rownum}",
            kind="generator_run", timestamp=_ts(r.get("Ngày_Vận_Hành")), asset_id=asset, zone="B1",
            title=f"Generator run - {reason or 'unspecified'} ({minutes} min)" if minutes is not None else f"Generator run - {reason}",
            text=reason, status=None, is_open=None,
            values={"reason": reason, "minutes": minutes, "fuel_before_l": r.get("Chỉ_số_trước_VH"),
                    "fuel_after_l": r.get("Chỉ-số_sau_VH"), "fuel_used_l": r.get("Tiêu_hao_nhiên_liệu"),
                    "fuel_stock_l": r.get("Nhiên_liệu_tồn"), "start": _s(r.get("Tg_bắt_đầu_VH")), "end": _s(r.get("Tg_kết_thúc_VH"))},
            persons=_persons(r.get("Nhân_sự_VH")),
            source=SourceRef("ops_data", source_title, tab.sheet, rownum, rid or None)))
    return out


def load_ops_workbook(path: Path, source_title: str = "Operations Data") -> tuple[list[Evidence], dict]:
    """Load the four operational tabs. Returns (evidence, per-tab stats)."""
    from .workbook import suspicious_row_count
    evidence: list[Evidence] = []
    stats: dict = {}
    for key, sheet in OPS_TABS.items():
        tab = read_tab(path, sheet)
        fn = {"meters": normalize_meters_tab, "assets": normalize_assets_tab,
              "incidents": normalize_incidents_tab, "generator": normalize_generator_tab}[key]
        items = fn(tab, source_title)
        times = [e.timestamp for e in items if e.timestamp]
        stats[sheet] = {"rows_read": tab.count, "in_scope": len(items), "excluded_out_of_scope": tab.count - len(items),
                        "latest_record": max(times).isoformat() if times else None,
                        "test_records": sum("test_record" in e.flags for e in items),
                        "suspicious_row_count": suspicious_row_count(tab.count)}
        evidence.extend(items)
    return evidence, stats


def load_vehicle_workbook(path: Path, source_title: str = "Theo dõi lượt khách ra vào") -> tuple[list[Evidence], dict]:
    """Monthly sheets 'Thang MM.YYYY'; daily car and motorbike counts (skill §2.4: real counts)."""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    evidence: list[Evidence] = []
    stats = {"sheets": 0, "days": 0, "sheet_month_mismatch": []}
    try:
        for ws in wb.worksheets:
            m = re.match(r"Thang (\d{2})\.(\d{4})", ws.title)
            if not m:
                continue
            stats["sheets"] += 1
            rows = list(ws.iter_rows(values_only=True))
            car_col = bike_col = None
            for hdr in rows[:4]:
                for i, c in enumerate(hdr):
                    t = _s(c).upper().replace("\n", " ")
                    if "SL XE Ô TÔ" in t:
                        car_col = i
                    if "XE MÁY" in t and t.startswith("SL"):
                        bike_col = i
            if car_col is None or bike_col is None:
                continue
            for idx, row in enumerate(rows, start=1):
                d = row[1] if len(row) > 1 else None
                if not isinstance(d, datetime):
                    continue
                cars, bikes = row[car_col], row[bike_col]
                if not isinstance(cars, (int, float)) or not isinstance(bikes, (int, float)):
                    continue
                if (d.month, d.year) != (int(m.group(1)), int(m.group(2))):
                    stats["sheet_month_mismatch"].append(f"{ws.title} row {idx}: {d.date()}")
                evidence.append(Evidence(
                    evidence_id=f"veh:{d.date().isoformat()}", kind="vehicle_day", timestamp=_ts(d), asset_id=None,
                    zone="Building", title=f"Vehicles {d.date().isoformat()}: {int(cars)} cars, {int(bikes)} motorbikes",
                    text="", status=None, is_open=None, values={"cars": cars, "motorbikes": bikes, "vehicles": cars + bikes},
                    source=SourceRef("vehicles", source_title, ws.title, idx, None)))
                stats["days"] += 1
    finally:
        wb.close()
    # keep one record per day (later sheet wins) to avoid duplicates across sheets
    uniq = {e.evidence_id: e for e in evidence}
    stats["duplicates_dropped"] = len(evidence) - len(uniq)
    out = sorted(uniq.values(), key=lambda e: e.timestamp)
    stats["latest_record"] = out[-1].timestamp.isoformat() if out else None
    return out, stats
