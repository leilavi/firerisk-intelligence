"""SAMPLE MODE: the dashboard with a FICTIONAL building, for judges and anyone who clones the repository. ORIGIN: NEW.

    python -m firerisk.sample          (Windows: run_dashboard_sample.bat; macOS/Linux: ./run_dashboard_sample.sh)

Why: the real building's records are private (data owner's conditions, DATA_AUTHORIZATION.md) and are not in the
repository, so a fresh clone has no data to show. Sample mode writes a made-up building - "Acme Riverside Plaza" -
into `data/sample/` (git-ignored, re-created on every start) and starts the normal dashboard on it.

What is fictional and what is real:
  * EVERY record is invented for this sample (no row, number, name or text comes from the real building). The
    equipment codes are the codes already used in the public configuration (`firerisk/config.py`), so the rules
    work unchanged. Dates are relative to the day you start it, so the records are always "recent".
  * The ANALYSIS is real: the same rule engine, chain of effects and dashboard as on the real data compute every
    alert, level, timeline and action from these records. Nothing on screen is typed in as a result.
  * Meta Muse Spark is called only when YOU configure your own Meta Model API key (setup_api_key.bat or `.env`);
    then it analyses these fictional records live. Without a key the dashboard says that no Meta AI analysis exists -
    it never shows a made-up AI result. The English display text of the Vietnamese-style records below is written by
    the sample's author (labelled "sample translation"), not by AI.
  * Sample mode never reads `data/private/` (real data, Drive link, frames, videos, drawings): every path is
    redirected to `data/sample/`, Google Drive sync is switched off, demo mode is off.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = ROOT / "data" / "sample"
BUILDING = "Acme Riverside Plaza (fictional sample)"
PREFIX = "ARP"                       # fictional branch prefix used in the records
TZ = timezone(timedelta(hours=7), name="UTC+07:00")

# Vietnamese-style record text -> English display text (written by the sample's author, not by AI).
EN: dict[str, str] = {}


def _t(vi: str, en: str) -> str:
    EN[vi] = en
    return vi


def sample_env(base: Path = SAMPLE_DIR) -> dict[str, str]:
    """Environment that points every data path of the app at the sample folder."""
    return {
        "FIRERISK_SAMPLE_MODE": "1",
        "FIRERISK_SITE_CONFIG": str(base / "site_config.json"),
        "FIRERISK_SNAPSHOT_DIR": str(base / "snapshot"),
        "FIRERISK_DB": str(base / "firerisk_sample.db"),
        "FIRERISK_POWER_LINKS": str(base / "power_links.xlsx"),
        "FIRERISK_SAMPLE_TRANSLATIONS": str(base / "translations.json"),
        "FIRERISK_LOG_DIR": str(base / "logs"),
        "FIRERISK_MEDIA_DIR": str(base / "media"),
        "FIRERISK_VIDEO_DIR": str(base / "media" / "videos"),
        "FIRERISK_VIDEO_INBOX": str(base / "media" / "survey_inbox"),
        "FIRERISK_FRAMES_DIR": str(base / "media" / "frames"),
        "FIRERISK_DRIVE_EXPORT_URL": "",          # no Google Drive sync in sample mode
        "FIRERISK_DRIVE_TOKEN": "",
        "FIRERISK_DRIVE_VIDEOS": "0",
        "FIRERISK_DEMO_MODE": "0",
    }


# ----------------------------------------------------------------------------------------------------------------
# Column layouts of the operational workbook (same as the real sources, see firerisk/sources/normalize.py)
METER_COLS = ["Log_ID", "Equipment_ID", "Tên_Hệ_Thống", "Branch", "Ngay_Kiem_Tra", "Thời_Điểm_Kiểm_Tra", "Ca_Truc",
              "Hướng_Dẫn_Chung", "Chỉ_Số_Thiết_Bị", "Báo_Cáo_Bất_Thường", "Đánh_Giá_Cảm_Quan", "Tình_Trạng_Thiết_Bị",
              "Lý_Do_Cần_Theo_Dõi", "Hướng_Xử_Lý"]
ASSET_COLS = ["Log_ID", "Equipment_ID", "Location_ID", "Service Type", "Service_Details", "Maintenance_Details",
              "Current_Status", "Latest_Activity_Date", "Requester", "Approving_Mgr", "Estimated_Cost",
              "Expected_Completion_Date", "Maintenance_Date", "Technician_Name", "Action_Type", "Actual_Cost"]
INC_COLS = ["Mã sự cố/ nâng cấp", "Loại báo cáo", "Thời gian báo cáo", "Báo cáo nhanh", "Mô tả chi tiết",
            "Mức độ khẩn cấp", "Hướng xử lý, khắc phục", "Trạng thái", "Chi Nhánh", "Tầng", "Khu vực",
            "Người báo cáo", "Tg bắt đầu TC", "Tg Hoàn thành"]
GEN_COLS = ["ID", "Ngày_Vận_Hành", "Thiết_Bị_Vận_Hành", "Branch", "Tg_bắt_đầu_VH", "Tg_kết_thúc_VH", "Thời_lượng_VH",
            "Lý_do_Vận_Hành", "Tiêu_hao_nhiên_liệu", "Nhiên_liệu_tồn", "Nhân_sự_VH"]
REG_COLS = ["Equipment_ID", "Branch", "Equipment_Name", "Main_Category", "Floor", "Area", "Location_ID",
            "Assets_Status", "Last_Maintenance_Date", "Next_Due_Date", "Reference_File"]

STAFF = ["Sample Tech A", "Sample Tech B", "Sample Manager"]     # fictional roles, not people


def _row(cols, **kv):
    return [kv.get(c) for c in cols]


def _meter_series(days: int, base: float, noise: list[float], boost: dict[int, float]) -> list[float]:
    """Cumulative register values: day i consumption = base * (1 + noise) * boost (deterministic)."""
    vals, total = [], 10_000.0
    for i in range(days):
        vals.append(round(total, 1))
        total += base * (1 + noise[i % len(noise)]) * boost.get(i, 1.0)
    return vals


NOISE = [0.02, -0.03, 0.01, 0.04, -0.02, 0.0, -0.04, 0.03, -0.01, 0.02, 0.01, -0.03, 0.03, -0.02]


def build_ops_workbook(path: Path, now: datetime) -> None:
    import openpyxl
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    day0 = (now - timedelta(days=60)).replace(hour=6, minute=0, second=0, microsecond=0, tzinfo=None)
    n = 61                                                       # readings day0 .. today 06:00
    today = day0 + timedelta(days=60)

    def ago(d: float, h: int = 9) -> datetime:
        return (today - timedelta(days=d)).replace(hour=h, minute=15)

    # --- daily meter readings + daily checklists -------------------------------------------------------------
    ws = wb.create_sheet("chỉ số điện nước")
    ws.append(METER_COLS)
    last = n - 1
    # The last 4 days: the main electricity and the switchboard both draw ~60% more than usual (abnormal load),
    # the main water meter has been rising for 3 days (still rising on the latest reading).
    load = {i: 1.6 for i in range(last - 4, last)}
    meters = {
        "P-BG.TTC076": (_meter_series(n, 38.0, NOISE, load), "EVN"),        # x100 -> ~3,800 kWh/day
        "P-BG.TTC071": (_meter_series(n, 36.5, NOISE, load), "MSB"),
        "P-BG.TTC078": (_meter_series(n, 120.0, NOISE[::-1], {}), "AC2"),
        "P-BG.TTC042": (_meter_series(n, 110.0, NOISE, {}), "AC3"),
        "P-BG.TTC226": (_meter_series(n, 21.0, NOISE[3:] + NOISE[:3], {}), "XLNT"),
        "P-BG.TTC172": (_meter_series(n, 42.0, NOISE, {i: 1.9 for i in range(last - 3, last)}), "NUOC"),
        "P-BG.TTC104": (_meter_series(n, 9.0, NOISE[5:] + NOISE[:5], {}), "SOLAR"),
    }
    for meter, (vals, sysname) in meters.items():
        for i, v in enumerate(vals):
            ts = day0 + timedelta(days=i, minutes=(i * 7) % 20)
            ws.append(_row(METER_COLS, Log_ID=f"M-{sysname}-{i:03d}", Equipment_ID=meter, Tên_Hệ_Thống=sysname,
                           Branch=PREFIX, Ngay_Kiem_Tra=ts.date(), Thời_Điểm_Kiểm_Tra=ts, Ca_Truc="Ca 1",
                           Chỉ_Số_Thiết_Bị=v))
    checks = {   # checklist -> (asset, result today, observation)
        "C-TramBienAp": ("P-BG.TTC110", "Đạt", ""),
        "C-tuPPDienTong": ("P-BG.TTC046", "Không đạt",
                           _t("Tủ MSB nóng hơn bình thường, quạt hút phòng MSB không chạy",
                              "MSB panel warmer than usual; the MSB room extract fan is not running")),
        "C-MayPhatDien": ("P-BG.TTC017", "Đạt", ""),
        "C-BinhAcQuy": ("P-BG.TTC217", "Không đạt",
                        _t("Điện áp ắc quy đề máy phát thấp (23,1 V)", "Generator starter battery voltage low (23.1 V)")),
        "C-tuBomNPCCC": ("P-BG.TTC072", "Đạt", ""),
        "C-tuQuatHK": ("P-BG.TTC005", "Đạt", ""),
        "C-tuBC": ("P-BG.TTC009", "Đạt", ""),
        "C-tuXLNT": ("P-BG.TTC028", "Đạt", ""),
    }
    for d in range(0, 14):
        ts = (today - timedelta(days=d)).replace(hour=7, minute=30)
        for log_id, (asset, result, note) in checks.items():
            res, obs = (result, note) if d <= 1 else ("Đạt", "")
            ws.append(_row(METER_COLS, Log_ID=log_id, Equipment_ID=asset, Branch=PREFIX, Ngay_Kiem_Tra=ts.date(),
                           Thời_Điểm_Kiểm_Tra=ts, Ca_Truc="Ca 1", Tình_Trạng_Thiết_Bị=res,
                           Báo_Cáo_Bất_Thường=obs or None))

    # --- asset repairs & maintenance ----------------------------------------------------------------------------
    ws = wb.create_sheet("BC hư hỏng TS")
    ws.append(ASSET_COLS)
    loc = lambda floor: f"{PREFIX}-A-{floor}-Chung-"
    assets = [
        ("R-001", "P-BG.TTC046", "B1", ago(3),
         _t("Sự cố thanh cái tủ MSB nóng bất thường khi tải cao, có mùi khét nhẹ",
            "Fault: MSB busbar abnormally hot under high load, slight burning smell"),
         _t("Đo nhiệt bằng súng hồng ngoại 78°C tại thanh cái pha B; chờ đơn vị điện kiểm tra lực siết",
            "IR gun reading 78°C on the phase-B busbar; waiting for the electrical contractor to check the torque"),
         "2. Pending Repair", ago(-2)),
        ("R-002", "P-BG.TTC046", "B1", ago(41),
         _t("Thanh cái tủ MSB nóng, lỗi lực siết bu lông đấu nối; đã siết lại",
            "MSB busbar hot, loose connection bolts (fault); re-tightened"),
         "", "4. Operational", None),
        ("R-003", "P-BG.TTC046", "B1", ago(19),
         _t("Thanh cái tủ MSB nóng lại sau 3 tuần, lỗi tiếp xúc; đã vệ sinh và siết lại",
            "MSB busbar hot again after 3 weeks, contact fault; cleaned and re-tightened"),
         "", "4. Operational", None),
        ("R-004", "P-BG.TTC217", "B1", ago(9),
         _t("Ắc quy đề máy phát hỏng 1 bình, máy phát đề chậm khi chạy thử",
            "One generator starter battery failed; slow start during the test run"),
         _t("Đề xuất thay 2 bình ắc quy", "Proposed: replace both batteries"), "3. Faulty but Operational", ago(-5)),
        ("R-005", "P-BG.TTC005", "B1", ago(6),
         _t("Quạt hút khói EAF2 không hoạt động khi chạy thử định kỳ",
            "Smoke exhaust fan EAF2 not working during the periodic test"),
         _t("Kiểm tra contactor và cuộn hút", "Check the contactor and coil"), "2. Pending Repair", ago(-1)),
        ("R-006", "P-BG.TTC167", "B1", ago(4),
         _t("Máy thổi khí AB-01A kẹt cứng, mô tơ nóng bất thường",
            "Air blower AB-01A seized; motor abnormally hot"), "", "1. Out of Order", ago(-3)),
        ("R-007", "P-BG.TTC167", "B1", ago(33),
         _t("Cháy mô tơ máy thổi khí AB-01A, đã quấn lại", "Air blower AB-01A motor burnt out; rewound"),
         "", "4. Operational", None),
        ("R-008", "P-BG.TTC102", "B1", ago(12),
         _t("Máy lạnh phòng camera chảy nước", "Camera-room air conditioner leaking water"),
         _t("Vệ sinh ống thoát nước", "Drain pipe cleaned"), "4. Operational", None),
    ]
    for log_id, eq, floor, when, problem, work, status, due in assets:
        ws.append(_row(ASSET_COLS, Log_ID=log_id, Equipment_ID=eq, Location_ID=loc(floor), **{"Service Type": "Repair"},
                       Service_Details=problem, Maintenance_Details=work or None, Current_Status=status,
                       Latest_Activity_Date=when, Requester=STAFF[0], Approving_Mgr=STAFF[2],
                       Expected_Completion_Date=due, Technician_Name=STAFF[1], Action_Type="Repair"))

    # --- incident & works log ------------------------------------------------------------------------------------
    ws = wb.create_sheet("NK thi công - sự cố")
    ws.append(INC_COLS)
    incidents = [
        ("INC-01", ago(2, 14), "B1", _t("Phòng MSB thấm nước từ trần sau mưa lớn",
                                        "Water seeping through the ceiling of the MSB room after heavy rain"),
         _t("Nước nhỏ giọt cách tủ MSB khoảng 1 m, đã che tạm bằng bạt",
            "Water dripping about 1 m from the MSB panel; temporarily covered with a tarpaulin"),
         "3. Đang tìm PA"),
        ("INC-02", ago(38, 10), "B1", _t("Phòng MBA thấm nước sau mưa", "Water seepage in the transformer room after rain"),
         _t("Đã chống thấm tạm khe tường", "Wall joint temporarily sealed"), "6. Hoàn tất"),
        ("INC-03", ago(5, 22), "B1", _t("Module giám sát báo cháy tầng hầm báo lỗi đường dây",
                                        "Basement fire-alarm monitor module reports a loop fault"),
         _t("Tủ báo cháy hiển thị lỗi zone B1-03, chưa xác định vị trí đứt",
            "Fire alarm panel shows a fault on zone B1-03; break location not found yet"), "3. Đang tìm PA"),
        ("INC-04", ago(24, 9), "B1", _t("Đầu báo nhiệt tầng hầm báo lỗi", "Basement heat detector reports a fault"),
         _t("Đã thay đầu báo", "Detector replaced"), "6. Hoàn tất"),
        ("INC-05", ago(8, 16), "F3", _t("Loa thông báo tầng 3 không hoạt động", "Floor 3 public-address speakers not working"),
         "", "3. Đang tìm PA"),
        ("INC-06", ago(50, 11), "F2", _t("Sơn lại hành lang tầng 2", "Repainting the floor 2 corridor"), "", "Hoàn tất thi công"),
    ]
    for code, when, floor, quick, detail, status in incidents:
        ws.append(_row(INC_COLS, **{"Mã sự cố/ nâng cấp": f"{PREFIX}-A-{floor}-{code}",
                                    "Loại báo cáo": "Nhật ký thi công" if code == "INC-06" else "Báo cáo sự cố",
                                    "Thời gian báo cáo": when, "Báo cáo nhanh": quick, "Mô tả chi tiết": detail or None,
                                    "Trạng thái": status, "Chi Nhánh": PREFIX, "Tầng": floor,
                                    "Người báo cáo": STAFF[0]}))

    # --- generator log ------------------------------------------------------------------------------------------
    ws = wb.create_sheet("Dầu M Phát điện")
    ws.append(GEN_COLS)
    stock = 1800
    runs = [(d, "VH định kỳ", time(8, 0), time(8, 20)) for d in (55, 48, 41, 34, 27, 20, 13, 6)]
    runs.append((17, "Mất điện lưới", time(14, 5), time(15, 40)))
    for k, (d, reason, t0, t1) in enumerate(sorted(runs, key=lambda r: -r[0])):
        used = 12 if reason == "Mất điện lưới" else 3
        stock -= used
        ws.append(_row(GEN_COLS, ID=f"G-{k + 1:02d}", Ngày_Vận_Hành=ago(d, 8), Thiết_Bị_Vận_Hành="P-BG.TTC017",
                       Branch=PREFIX, Tg_bắt_đầu_VH=t0, Tg_kết_thúc_VH=t1, Thời_lượng_VH=None, Lý_do_Vận_Hành=reason,
                       Tiêu_hao_nhiên_liệu=used, Nhiên_liệu_tồn=stock, Nhân_sự_VH=STAFF[1]))

    # --- asset register (context and display names) --------------------------------------------------------------
    ws = wb.create_sheet("Asset")
    ws.append(REG_COLS)
    reg = [("P-BG.TTC046", "Main switchboard (MSB)", "Electrical", "B1"), ("P-BG.TTC110", "Transformer station", "Electrical", "B1"),
           ("P-BG.TTC017", "Standby generator", "Electrical", "B1"), ("P-BG.TTC217", "Generator starter batteries", "Electrical", "B1"),
           ("P-BG.TTC005", "Smoke exhaust fan panel EAF1-EAF2", "Fire protection", "B1"),
           ("P-BG.TTC009", "Fire alarm control panel", "Fire protection", "B1"),
           ("P-BG.TTC072", "Fire pump panel / fire water tank", "Fire protection", "B1"),
           ("P-BG.TTC167", "Wastewater air blower AB-01A", "Mechanical", "B1")]
    for eq, name, cat, floor in reg:
        ws.append(_row(REG_COLS, Equipment_ID=eq, Branch=PREFIX, Equipment_Name=name, Main_Category=cat, Floor=floor,
                       Location_ID=loc(floor), Assets_Status="In use", Last_Maintenance_Date=ago(30),
                       Next_Due_Date=ago(-60)))
    wb.save(path)


def build_vehicle_workbook(path: Path, now: datetime) -> None:
    """Daily car / motorbike counts (activity cross-check of the meter rules): steady, no busy days."""
    import openpyxl
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    start = (now - timedelta(days=62)).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
    sheets: dict[str, list] = {}
    for i in range(63):
        d = start + timedelta(days=i)
        sheets.setdefault(f"Thang {d.month:02d}.{d.year}", []).append(d)
    for title, days in sheets.items():
        ws = wb.create_sheet(title)
        ws.append(["STT", "NGÀY", "SL XE Ô TÔ", "SL XE MÁY"])
        for k, d in enumerate(days):
            ws.append([k + 1, d, 180 + (k * 13) % 25, 950 + (k * 37) % 120])
    wb.save(path)


def build_power_links(path: Path) -> None:
    """Confirmed supply path of the emergency lights / exit signs (fictional counts, same topology as the rules
    expect: generator -> one ATS -> each floor's main panel -> floor breaker (CP) -> fittings)."""
    import openpyxl
    from .power_links import COLUMNS
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Links"
    ws.append(COLUMNS)

    def add(**k):
        base = {"confirmed": "Y", "source": "SAMPLE (fictional)", "basis": "sample data"}
        base.update(k)
        ws.append([base.get(c, "") for c in COLUMNS])
    for floor, el, ex in (("B1", 10, 6), ("F1", 14, 12), ("F2", 9, 6), ("F3", 9, 6), ("F4", 11, 14), ("Roof", 5, 4)):
        add(floor=floor, panel_label=f"MAIN-{floor}", feeds="sub_panel", fed_panel_label=f"CP-{floor}", panel_kind="floor_main_panel")
        add(floor=floor, panel_label="ATS", feeds="sub_panel", fed_panel_label=f"MAIN-{floor}", panel_kind="ats")
        add(floor=floor, panel_label=f"CP-{floor}", feeds="emergency_light", count=el, panel_kind="floor_breaker")
        add(floor=floor, panel_label=f"CP-{floor}", feeds="exit_sign", count=ex, panel_kind="floor_breaker")
    add(floor="B1", panel_label="GEN", asset_id="P-BG.TTC017", feeds="sub_panel", fed_panel_label="ATS", supply="backup",
        panel_kind="generator")
    wb.save(path)


def build_sample(base: Path = SAMPLE_DIR, now: datetime | None = None) -> Path:
    """(Re)create the fictional building's files. The database is kept unless the data changed day."""
    now = now or datetime.now(TZ)
    snap = base / "snapshot"
    if snap.exists():
        shutil.rmtree(snap)
    snap.mkdir(parents=True, exist_ok=True)
    build_ops_workbook(snap / "ops.xlsx", now)
    build_vehicle_workbook(snap / "vehicles.xlsx", now)
    stamp = now.isoformat(timespec="seconds")
    (snap / "manifest.json").write_text(json.dumps({"created_by": "SAMPLE MODE (fictional building)", "files": {
        "ops_data": {"title": "Operations Data (SAMPLE)", "local_file": "ops.xlsx", "downloaded_at": stamp},
        "vehicles": {"title": "Vehicle counts (SAMPLE)", "local_file": "vehicles.xlsx", "downloaded_at": stamp}}},
        indent=1), encoding="utf-8")
    build_power_links(base / "power_links.xlsx")
    (base / "site_config.json").write_text(json.dumps({
        "building_name": BUILDING, "branch_prefix": PREFIX, "ops_source_title": "Operations Data (SAMPLE)",
        "vehicle_source_title": "Vehicle counts (SAMPLE)"}, indent=1), encoding="utf-8")
    (base / "translations.json").write_text(json.dumps(EN, ensure_ascii=False, indent=1), encoding="utf-8")
    (base / "README.txt").write_text("FICTIONAL SAMPLE BUILDING generated by firerisk/sample.py. Not real data. "
                                     "Safe to delete; re-created on every start.\n", encoding="utf-8")
    return base


def main() -> None:
    # Paths must be set BEFORE any module that reads them (config, api, ...) is imported.
    os.environ.update(sample_env())
    if "--fresh" in sys.argv and SAMPLE_DIR.exists():
        shutil.rmtree(SAMPLE_DIR)
    build_sample()
    db = Path(os.environ["FIRERISK_DB"])
    if db.exists():          # a database from an earlier day would mark today's re-created records as late arrivals
        day = datetime.fromtimestamp(db.stat().st_mtime, TZ).date()
        if day != datetime.now(TZ).date():
            db.unlink()
    print(f"SAMPLE MODE - fictional building '{BUILDING}'. Files: {SAMPLE_DIR}")
    from .ai.muse import MuseConfig
    if MuseConfig.load().configured:
        print("Meta Model API key found: Meta Muse Spark will analyse the fictional records live.")
    else:
        print("No Meta Model API key: rule engine only. Run setup_api_key.bat (or set MODEL_API_KEY in .env) "
              "to add the live Meta Muse Spark analysis.")
    from .serve import main as serve
    serve()


if __name__ == "__main__":
    main()
