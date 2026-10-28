"""Static configuration for one building deployment.

Building-identifying values (name, branch prefix used in the source logs) are NOT stored in the public
repository. They are read from data/private/site_config.json (git-ignored) when present.

Every entry records where the knowledge came from:
  "skill"  - stated in the pre-existing skill v2.2 (user-confirmed facts)
  "data"   - read from the operational data itself (column values)
  "rule"   - FireRisk rule parameter chosen during the Hackathon (documented, preliminary)
"""

from __future__ import annotations

from datetime import timedelta, timezone

# Vietnam has no daylight saving time; a fixed offset avoids needing tzdata on Windows.
LOCAL_TZ = timezone(timedelta(hours=7), name="UTC+07:00")

import json as _json
from pathlib import Path as _Path

_SITE_FILE = _Path(__file__).resolve().parent.parent / "data" / "private" / "site_config.json"
_SITE = _json.loads(_SITE_FILE.read_text(encoding="utf-8")) if _SITE_FILE.exists() else {}

BUILDING_NAME = _SITE.get("building_name", "Demo building")
BRANCH_PREFIX = _SITE.get("branch_prefix", "BLD")   # skill §2.3: scope filter (prefix of Location_ID / Chi Nhánh)
OPS_SOURCE_TITLE = _SITE.get("ops_source_title", "Operations Data")
VEHICLE_SOURCE_TITLE = _SITE.get("vehicle_source_title", "Vehicle counts")
ASSET_PREFIX = "P-"          # skill §2.3: Equipment_ID prefix for this building

# --------------------------------------------------------------------------------------
# Meters (skill §2.4, user-confirmed 2026-10-07). multiplier converts the raw register to
# the physical unit where it is verified; None means the unit is NOT verified.
# --------------------------------------------------------------------------------------
METERS: dict[str, dict] = {
    "P-BG.TTC076": {"name": "Utility (EVN) main electricity meter", "unit": "kWh", "multiplier": 100,
                    "role": "electric_main", "min_delta": 200, "zone": "B1", "source": "skill"},
    # Multiplier x100 is ASSUMED (skill: MSB ~97% of EVN when x100 is applied; not verified on site)
    "P-BG.TTC071": {"name": "MSB main switchboard meter", "unit": "kWh (x100 assumed)", "multiplier": 100,
                    "multiplier_verified": False,
                    "role": "electric_msb", "min_delta": 200, "zone": "B1", "source": "skill"},
    "P-BG.TTC078": {"name": "Air-conditioning meter, floor 2", "unit": "raw", "multiplier": None,
                    "role": "electric_sub", "min_delta": 50, "zone": "F2", "source": "skill"},
    "P-BG.TTC042": {"name": "Air-conditioning meter, floor 3", "unit": "raw", "multiplier": None,
                    "role": "electric_sub", "min_delta": 50, "zone": "F3", "source": "skill"},
    "P-BG.TTC104": {"name": "Solar PV meter", "unit": "raw", "multiplier": None,
                    "role": "electric_solar", "min_delta": 3, "zone": "Roof", "source": "skill"},
    "P-BG.TTC226": {"name": "Wastewater treatment meter", "unit": "raw", "multiplier": None,
                    "role": "electric_sub", "min_delta": 4, "zone": "B1", "source": "skill"},
    "P-BG.TTC172": {"name": "Main water meter", "unit": "m³", "multiplier": 1,
                    "role": "water_main", "min_delta": 5, "zone": "Building", "source": "skill"},
}

# --------------------------------------------------------------------------------------
# Assets that appear in the data. "zone" values come from Location_ID in the asset log
# (e.g. "<BRANCH>-A-B1-Chung-") or from the skill/catalog; "fire_role" is a FireRisk
# classification of how the asset relates to fire safety (rule).
# --------------------------------------------------------------------------------------
ASSETS: dict[str, dict] = {
    "P-BG.TTC110": {"name": "Transformer station (MBA) and LV breaker", "zone": "B1", "fire_role": "electrical_room", "source": "data"},
    "P-BG.TTC054": {"name": "Transformer (MBA) room", "zone": "B1", "fire_role": "electrical_room", "source": "data"},
    "P-BG.TTC046": {"name": "Main switchboard (MSB) / main distribution panel room", "zone": "B1", "fire_role": "electrical_room", "source": "skill"},
    "P-BG.TTC210": {"name": "Lighting and fan distribution panel", "zone": "B1", "fire_role": "electrical_panel", "source": "data"},
    "P-BG.TTC014": {"name": "Booster pump panel", "zone": "B1", "fire_role": "electrical_panel", "source": "data"},
    "P-BG.TTC017": {"name": "Standby generator", "zone": "B1", "fire_role": "backup_power", "source": "skill"},
    "P-BG.TTC217": {"name": "Generator starter batteries (2 units)", "zone": "B1", "fire_role": "backup_power", "source": "skill"},
    "P-BG.TTC072": {"name": "Fire pump control panel / fire water tank", "zone": "B1", "fire_role": "fire_water", "source": "data"},
    "P-BG.TTC005": {"name": "Smoke exhaust fan panel (EAF1-EAF2)", "zone": "B1", "fire_role": "smoke_control", "source": "data"},
    "P-BG.TTC009": {"name": "Fire alarm control panel / heat-detector monitor module (basement shaft AB)", "zone": "B1", "fire_role": "fire_detection", "source": "data"},
    "P-PCCC642": {"name": "Lightning protection system", "zone": "Building", "fire_role": "lightning", "source": "data"},
    "P-BG.TTC028": {"name": "Wastewater treatment (XLNT) control panel", "zone": "B1", "fire_role": "motor_equipment", "source": "data"},
    "P-BG.TTC167": {"name": "Wastewater air blower AB-01A (XLNT)", "zone": "B1", "fire_role": "motor_equipment", "source": "data"},
    "P-BG.TTC117": {"name": "Domestic water pump panel", "zone": "B1", "fire_role": "other", "source": "data"},
    "P-BG.TTC219": {"name": "Air conditioner, floor 2", "zone": "F2", "fire_role": "hvac", "source": "data"},
    "P-BG.TTC102": {"name": "Camera room air conditioner", "zone": "B1", "fire_role": "hvac", "source": "data"},
}

# Which meter measures which equipment (system dependency used for evidence links). source: skill + data
METER_FEEDS: dict[str, list[str]] = {
    "P-BG.TTC226": ["P-BG.TTC167", "P-BG.TTC028"],          # wastewater treatment meter -> blowers / XLNT panel
    "P-BG.TTC076": ["P-BG.TTC110", "P-BG.TTC054", "P-BG.TTC046"],  # utility main -> transformer / MSB
    "P-BG.TTC071": ["P-BG.TTC046", "P-BG.TTC054"],
    "P-BG.TTC078": ["P-BG.TTC219"],                          # floor-2 AC meter -> floor-2 AC unit
}
# Asset groups that depend on each other (generator <-> batteries; MSB <-> transformer)
ASSET_DEPENDENCIES: list[tuple[str, str, str]] = [
    ("P-BG.TTC217", "P-BG.TTC017", "starter batteries of the standby generator"),
    ("P-BG.TTC046", "P-BG.TTC054", "main switchboard and transformer share the B1 electrical rooms"),
    ("P-BG.TTC046", "P-BG.TTC110", "main switchboard is fed by the transformer station"),
    ("P-BG.TTC009", "P-BG.TTC005", "fire alarm panel and smoke exhaust fans are both fire-protection systems in B1"),
]

# Daily inspection checklists (Log_ID in the meter/inspection tab -> asset). source: data
INSPECTION_CHECKLISTS: dict[str, str] = {
    "C-TramBienAp": "Transformer station", "C-MayPhatDien": "Generator", "C-BinhAcQuy": "Generator batteries",
    "C-tuPPDienTong": "Main distribution panel", "C-tuChieusangQuat": "Lighting/fan panel",
    "C-tuTangAp09": "Booster pump panel", "C-tuBomNPCCC": "Fire pump panel", "C-tuBomNSH": "Domestic water pump panel",
    "C-tuQuatHK": "Smoke exhaust fan panel", "C-tuXLNT": "Wastewater panel", "C-tuBC": "Fire alarm panel",
    "C-Ehang": "Goods lift", "C-EKhach": "Passenger lift",
    "C-ES1": "Escalator 1", "C-ES2": "Escalator 2", "C-ES3": "Escalator 3",
    "C-ES4": "Escalator 4", "C-ES5": "Escalator 5", "C-ES6": "Escalator 6",
}

# Name of the AI analyst shown in the dashboard (display only). The model actually called is Meta's
# Muse Spark, MODEL_ID below / MODEL_NAME in .env (default muse-spark-1.3); nothing about the API call changes.
AI_DISPLAY_NAME = "Muse Captain"

ZONE_LABELS: dict[str, str] = {
    "B1": "Basement B1 (technical rooms)", "F1": "Floor 1", "F2": "Floor 2", "F3": "Floor 3",
    "F4": "Floor 4", "Roof": "Roof", "Building": "Whole building",
}

# Status vocabularies observed in the data (source: data, checked 2026-10-27) -> canonical class.
# Unknown values are kept, flagged "unmapped_status" and treated as "unknown" (never silently resolved).
STATUS_CLASS: dict[str, str] = {
    "3. Đang tìm PA": "open",            # seeking a solution
    "2. Pending Repair": "open",
    "1. Out of Order": "open",
    "3. Faulty but Operational": "degraded",
    "3. Tạm dừng": "paused",
    "Đang thi công": "in_progress",       # skill §2.4: may not be updated after completion
    "6. Hoàn tất": "resolved",
    "Hoàn tất thi công": "resolved",
    "4. Operational": "resolved",
    "Đạt": "pass",                        # daily checklist passed
    "Không đạt": "fail",
}
OPEN_CLASSES = {"open", "degraded", "paused", "in_progress", "fail"}
# kept for backwards compatibility
OPEN_STATUS = {k: v in OPEN_CLASSES for k, v in STATUS_CLASS.items()}

# Severity levels (skill §7) and their rank.
SEVERITY_ORDER = ["normal", "watch", "warning", "high", "emergency"]
SEVERITY_LABEL = {"normal": "Normal", "watch": "Watch", "warning": "Warning", "high": "High risk", "emergency": "Emergency"}

# Rule parameters (rule; preliminary, not certified engineering thresholds)
LOOKBACK_DAYS = 60            # evidence window for zone correlation
RECURRENCE_WINDOW_DAYS = 30   # "recurring" = >= 2 reports on same asset/pathway within this window
STALE_DATA_DAYS = 2           # skill §2B.9 (daily meter readings)
# Expected update cadence per sheet: max age in days before the source is reported as stale.
# None = event-driven log (only written when something happens) -> never "stale".
SOURCE_CADENCE_DAYS: dict[str, float | None] = {
    "chỉ số điện nước": STALE_DATA_DAYS,
    "Dầu M Phát điện": 8,        # scheduled generator run is weekly (data)
    "BC hư hỏng TS": None,
    "NK thi công - sự cố": None,
    "vehicles": 35,              # monthly workbook (data)
}
MAD_BASELINE_DAYS = 28        # skill §5A.2
MAD_K = 3.0                   # skill §5A.3
MAD_SCALE = 1.4826            # skill §5A.3
