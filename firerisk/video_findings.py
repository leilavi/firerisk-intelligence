"""AI video findings and survey coverage. ORIGIN: NEW (0.9).

A video finding is something Muse Captain (Meta Muse Spark, survey-video prompt v2) saw in a survey video and
recommends checking on site. It is NOT a rule-based alert:
  * it has no official risk level (the rule engine sets levels; there is no rule for video findings yet);
  * it starts as "New finding" and only a person can move it to Needs verification / Confirmed / Resolved;
  * it is LINKED to an existing alert only by a stated deterministic reason (same equipment in the asset register,
    or same floor and a matching fire-safety group); otherwise it stays a separate finding.
Coverage reports what the set of videos actually allows to say about the building - never "the whole building was
inspected" just because every file was processed.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict

from .config import ZONE_LABELS
from .video import EXT_STATUS, FINDING_CAT_LABEL, FINDING_CATS, VIDEO_PROMPT_VERSION

STATUS_LABEL = {"new": "New finding", "acknowledged": "Needs verification", "investigating": "Needs verification",
                "confirmed": "Confirmed", "resolved": "Resolved", "false_alarm": "Not confirmed on site"}
# Which rule pathways a finding group relates to (used only to propose a link, with the reason shown).
CAT_TO_PATHWAYS = {
    "ignition_source": {"motor_overheat", "water_electrical", "electrical_anomaly", "backup_power"},
    "combustibles_housekeeping": {"motor_overheat"},
    "egress_access": {"smoke_control", "pa_system"},
    "extinguishers_first_aid": {"fire_water"},
    "detection_alarm": {"detection_impairment", "pa_system"},
    "suppression_smoke_control": {"fire_water", "smoke_control"},
    "water_moisture_electrical": {"water_electrical"},
}
CAT_ORDER = ["ignition_source", "water_moisture_electrical", "combustibles_housekeeping", "egress_access",
             "extinguishers_first_aid", "detection_alarm", "suppression_smoke_control"]
EXT_LABEL = {"visible_accessible": "Visible and accessible", "visible_access_may_be_obstructed": "Visible but access may be obstructed",
             "not_visible_in_footage": "Not visible in the surveyed footage", "needs_on_site_verification": "Needs on-site verification"}
FLOORS = ["Roof", "F4", "F3", "F2", "F1", "B1"]


def finding_id(video_id: str, f: dict) -> str:
    key = f"{video_id}|{f.get('title', '').strip().lower()}|{round(float(f.get('time_start_s') or 0))}"
    return "VF-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


def _links(f: dict, v: dict, res, is_active) -> list[dict]:
    out = []
    eq_ids = {e.get("equipment_id") for e in v.get("equipment") or [] if e.get("equipment_id")}
    names = {e.get("equipment_id"): e.get("name") for e in v.get("equipment") or []}
    cat_paths = CAT_TO_PATHWAYS.get(f["category"], set())
    sig = {s.signal_id: s for s in res.signals}
    for a in res.alerts:
        if not is_active(a.alert_id):
            continue
        for c in a.fields.get("risks", []):
            s = sig.get(c["signal_id"])
            if not s:
                continue
            assets = {res.evidence[i].asset_id for i in s.evidence_ids if i in res.evidence and res.evidence[i].asset_id}
            reason = None
            if eq_ids & assets:
                reason = "The video is linked to the same equipment in the asset register"
            elif v.get("zone") and v["zone"] == a.zone and s.pathway in cat_paths:
                reason = f"Same floor (asset register) and the finding group matches this risk"
            if reason:
                out.append({"kind": "fire_risk", "alert_id": a.alert_id, "signal_id": c["signal_id"], "title": c["risk"],
                            "severity": c["severity"], "reason": reason})
    for ea in res.equipment_alerts:
        if is_active(ea.alert_id) and ea.asset_id and ea.asset_id in eq_ids:
            out.append({"kind": "equipment", "alert_id": ea.alert_id, "title": names.get(ea.asset_id) or ea.asset_id,
                        "severity": ea.severity, "reason": "The video is linked to this equipment in the asset register"})
    return out


def collect(videos, res, store, is_active) -> dict:
    """All AI video findings (latest successful v2 analysis of each video), their links, status and coverage."""
    findings, per_video = [], []
    for v in videos.list():
        latest_ok = videos.latest_analysis(v["video_id"], only_ok=True)
        latest_any = videos.latest_analysis(v["video_id"])
        v2 = latest_ok if latest_ok and latest_ok.get("prompt_version") == VIDEO_PROMPT_VERSION else None
        state = ("running" if v["analysis_status"] == "running" else
                 "reviewed" if v2 else
                 "failed" if latest_any and latest_any.get("status") == "failed" and latest_any.get("prompt_version") == VIDEO_PROMPT_VERSION else
                 "older_review_only" if latest_ok else "not_analysed")
        per_video.append({"video_id": v["video_id"], "filename": v["filename"], "zone": v.get("zone"),
                          "drive_file_id": v.get("drive_file_id"),
                          "zone_label": ZONE_LABELS.get(v.get("zone") or "", "Location not verified"),
                          "room": v.get("room"), "equipment": v.get("equipment") or [], "recorded_at": v.get("recorded_at"),
                          "size": v.get("size"), "duration_s": v.get("duration_s"), "state": state,
                          "error": (latest_any or {}).get("error") if state == "failed" else None,
                          "error_kind": (latest_any or {}).get("error_kind") if state == "failed" else None,
                          "analysed_at": (v2 or latest_ok or {}).get("created_at"), "model": (v2 or latest_ok or {}).get("model"),
                          "method": (v2 or {}).get("method"), "areas": (v2 or {}).get("areas", []),
                          "coverage": (v2 or {}).get("coverage") or {}, "findings_count": len((v2 or {}).get("findings", []))})
        for f in (v2 or {}).get("findings", []):
            fid = finding_id(v["video_id"], f)
            st = (store.current_status(fid) or {}).get("status", "new")
            links = _links(f, v, res, is_active)
            findings.append({
                "finding_id": fid, "video_id": v["video_id"], "filename": v["filename"], "zone": v.get("zone"),
                "zone_label": ZONE_LABELS.get(v.get("zone") or "", "Location not verified"),
                "area_label": f.get("area_label"), "category": f["category"], "category_label": FINDING_CAT_LABEL[f["category"]],
                "title": f["title"], "what_is_visible": f.get("what_is_visible"), "fire_safety_link": f.get("fire_safety_link"),
                "potential_consequence_if_confirmed": f.get("potential_consequence_if_confirmed"),
                "certainty": f.get("certainty"), "recommended_check": f.get("recommended_check"),
                "records_to_collect": f.get("records_to_collect"), "time_start_s": f["time_start_s"],
                "time_end_s": f.get("time_end_s"), "recorded_at": v.get("recorded_at"), "analysed_at": v2.get("created_at"),
                "status": st, "status_label": STATUS_LABEL.get(st, st), "links": links, "linked": bool(links),
                "verified": st in ("confirmed", "resolved"), "origin": "ai_vision",
                "official_level": None})
    open_ = [f for f in findings if f["status"] not in ("resolved", "false_alarm")]
    order = lambda f: (CAT_ORDER.index(f["category"]), f["certainty"] != "clearly_visible", f["linked"])
    counts = {"total": len(findings), "new": sum(1 for f in findings if f["status"] == "new"),
              "needs_verification": sum(1 for f in findings if f["status"] in ("new", "acknowledged", "investigating")),
              "linked": sum(1 for f in findings if f["linked"]), "confirmed": sum(1 for f in findings if f["status"] == "confirmed"),
              "resolved": sum(1 for f in findings if f["status"] == "resolved")}
    return {"findings": sorted(findings, key=order), "top": sorted(open_, key=order)[:3], "counts": counts,
            "videos": per_video, "coverage": coverage(per_video, res)}


def coverage(per_video: list[dict], res) -> dict:
    drive = [dict(e, drive_file_id=e.get("drive_file_id") or k) for k, e in (res.video_catalog or {}).items()]
    local_ids = {v.get("drive_file_id") for v in per_video if v.get("drive_file_id")}
    reviewed = [v for v in per_video if v["state"] == "reviewed"]
    assessed, not_assessable = Counter(), Counter()
    needs_footage, limits, areas = [], [], []
    for v in reviewed:
        cov = v["coverage"]
        assessed.update(cov.get("categories_assessed") or [])
        not_assessable.update(cov.get("categories_not_assessable") or [])
        needs_footage += [{"video": v["filename"], "need": n} for n in cov.get("needs_more_footage") or []]
        if cov.get("image_limitations"):
            limits.append({"video": v["filename"], "limitation": cov["image_limitations"]})
        for a in v["areas"]:
            areas.append({"video_id": v["video_id"], "video": v["filename"], "zone_label": v["zone_label"],
                          "area_label": a.get("area_label"), "label_basis": a.get("label_basis"),
                          "time_start_s": a.get("time_start_s"),
                          "extinguishers": a.get("extinguishers"), "extinguishers_label": EXT_LABEL.get(a.get("extinguishers")),
                          "extinguishers_visible_count": a.get("extinguishers_visible_count"),
                          "detection_devices": a.get("detection_devices"), "other_fire_equipment": a.get("other_fire_equipment")})
    groups = defaultdict(list)                 # possible overlaps: same floor + room, or same linked equipment
    for v in per_video:
        for e in v["equipment"]:
            groups[("equipment", e.get("equipment_id"))].append(v["filename"])
        if v["zone"] and v["room"]:
            groups[("room", v["zone"], v["room"])].append(v["filename"])
    overlaps = sorted({tuple(sorted(set(l))) for l in groups.values() if len(set(l)) > 1})
    floors_with_video = {v["zone"] for v in per_video if v["zone"]}
    return {
        "drive_videos": len(drive), "on_this_computer": len(per_video),
        "reviewed": len(reviewed), "older_review_only": sum(1 for v in per_video if v["state"] == "older_review_only"),
        "failed": [{"video": v["filename"], "error_kind": v["error_kind"], "error": v["error"]} for v in per_video if v["state"] == "failed"],
        "not_analysed": [v["filename"] for v in per_video if v["state"] in ("not_analysed", "running")],
        "not_downloaded": [{"title": e.get("title"), "size": e.get("size")} for e in drive if e["drive_file_id"] not in local_ids],
        "location_not_verified": [v["filename"] for v in per_video if not v["zone"]],
        "floors_with_video": [z for z in FLOORS if z in floors_with_video],
        "floors_without_video": [z for z in FLOORS if z not in floors_with_video],
        "possible_overlaps": [list(o) for o in overlaps],
        "areas": areas,
        "groups_assessed": {c: assessed.get(c, 0) for c in FINDING_CATS},
        "groups_not_assessable": {c: not_assessable.get(c, 0) for c in FINDING_CATS},
        "group_labels": FINDING_CAT_LABEL,
        "groups_never_assessed": [c for c in FINDING_CATS if not assessed.get(c)],
        "needs_more_footage": needs_footage, "image_limitations": limits,
        "note": ("Coverage of the building is judged from the locations the videos can be tied to. Processing every "
                 "uploaded file does not mean the whole building was inspected, and anything not visible in a video "
                 "(an extinguisher, a detector, a sprinkler) is not proven absent."),
    }
