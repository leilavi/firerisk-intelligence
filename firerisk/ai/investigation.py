"""Muse Spark root-cause investigation of a zone alert.

ORIGIN: NEW.
Flow: deterministic alert (rules) -> redacted evidence package -> Muse Spark (structured JSON) ->
validation against the package (every cited evidence ID must exist) -> stored result.
The rule-based severity stays authoritative; the model's priority is shown next to it.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from ..config import ASSETS, METERS, SEVERITY_ORDER
from ..hazards.pathways import PATHWAYS
from .muse import MuseClient, MuseError
from .redact import Redactor

PROMPT_VERSION = "investigation-v5"  # v5: per-risk plain-English briefing; v4: English-only output  # v2: opaque evidence-ID aliases; v3: situation, scenarios, limitations,
                                     #     related equipment alerts in the package

SYSTEM_PROMPT = """You are the reasoning engine of FireRisk Intelligence, a decision-support tool for building
fire and explosion risk. You receive an evidence package assembled by deterministic rules from real
building records (Vietnamese text from inspection logs, incident reports, asset repair logs, generator
logs and meter analysis). Your job is a careful root-cause investigation.

Rules you must follow:
1. Use ONLY the evidence in the package. Cite evidence IDs exactly as given in every list field.
2. Separate observed facts (what a record states) from hypotheses (your inference). Never present a
   correlation or a time coincidence as proof of causation.
3. Do not invent numeric probabilities, accuracy figures or time-to-fire estimates.
4. State what is unknown and what information would confirm or reject each hypothesis.
5. Consider contradicting (weakening) evidence, e.g. daily checklists that report "Đạt" (passed) or scheduled
   generator runs that succeeded, and alternative benign explanations (e.g. metering/data-entry issues).
6. Recommendations must be proportionate, specific and verifiable. Never recommend disabling alarms or
   operating fire-suppression systems automatically; for confirmed emergencies refer to the building's
   approved emergency procedure.
7. This is decision support. It does not replace certified fire systems or qualified professionals.
8. Never state that a fire has happened unless a record says so; never change the official level - the
   rule-based level is authoritative, you only give your own priority with a rationale.
9. Related equipment alerts are separate maintenance findings; use them as context only where the package
   states a reason for the link.
10. Survey video observations (if any) were produced by an AI model from a video recorded on the stated date.
   They show what was visible THEN, not the current state; they do not prove equipment works and do not confirm
   a hazard. Mention them by their video alias (V01...) in text only; never put them in evidence_ids.
11. risk_briefings: one entry per signal (use the signal alias S01, S02 ... exactly as given), written for a building
   operator who is not a fire engineer. observed = only what the records state. why_it_matters = why this kind of
   condition is a fire-safety concern. potential_consequence = what COULD happen if it stays unresolved, in
   conditional wording ("may", "could"); never say a fire, short circuit or failure has happened unless a record
   says so. certainty: "supported" if the records clearly show the condition, "partly_supported" if they show it only
   in part or it may already be fixed, "insufficient_evidence" if the records cannot support a consequence - then set
   potential_consequence to "Insufficient evidence to determine the potential consequence. Further inspection is
   required." uncertainty = what the records do not establish. first_action = the single first check or action.
   Each text field: one or two short sentences.
Be concise: short sentences, no repetition between fields.
Write in clear, plain English only (the dashboard is English). Translate Vietnamese record wording; keep equipment
codes as written."""

_ID_LIST = {"type": "array", "items": {"type": "string"}}
CERTAINTY = ["supported", "partly_supported", "insufficient_evidence"]
INSUFFICIENT_TEXT = "Insufficient evidence to determine the potential consequence. Further inspection is required."


def signal_aliases(alert, signals) -> dict:
    """Opaque signal aliases sent to the model (S01 ...) -> real signal IDs, in the alert's signal order."""
    known = {s.signal_id for s in signals}
    return {f"S{n + 1:02d}": sid for n, sid in enumerate(i for i in alert.signal_ids if i in known)}
SCHEMA = {
    "name": "FireRiskInvestigation",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "situation", "observed_facts", "hypotheses", "scenarios", "escalation_pathway",
                     "risk_assessment", "missing_information", "recommended_actions", "limitations", "uncertainty",
                     "risk_briefings"],
        "properties": {
            "risk_briefings": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["signal", "observed", "why_it_matters", "potential_consequence", "certainty",
                             "uncertainty", "first_action", "evidence_ids"],
                "properties": {
                    "signal": {"type": "string"}, "observed": {"type": "string"},
                    "why_it_matters": {"type": "string"}, "potential_consequence": {"type": "string"},
                    "certainty": {"type": "string", "enum": CERTAINTY},
                    "uncertainty": {"type": "string"}, "first_action": {"type": "string"},
                    "evidence_ids": _ID_LIST}}},
            "summary": {"type": "string"},
            "situation": {"type": "string"},
            "scenarios": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["scenario", "how_it_could_develop", "plausibility", "supporting_evidence_ids",
                             "weakening_evidence_ids", "what_would_confirm"],
                "properties": {
                    "scenario": {"type": "string"},
                    "how_it_could_develop": {"type": "string"},
                    "plausibility": {"type": "string", "enum": ["plausible", "possible", "unlikely"]},
                    "supporting_evidence_ids": _ID_LIST,
                    "weakening_evidence_ids": _ID_LIST,
                    "what_would_confirm": {"type": "string"}}}},
            "limitations": {"type": "array", "items": {"type": "string"}},
            "observed_facts": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["statement", "evidence_ids"],
                "properties": {"statement": {"type": "string"}, "evidence_ids": _ID_LIST}}},
            "hypotheses": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["cause", "category", "plausibility", "reasoning", "supporting_evidence_ids",
                             "contradicting_evidence_ids", "how_to_verify"],
                "properties": {
                    "cause": {"type": "string"},
                    "category": {"type": "string", "enum": ["electrical", "water_ingress", "mechanical",
                                                            "detection_system", "power_supply", "maintenance",
                                                            "data_quality", "other"]},
                    "plausibility": {"type": "string", "enum": ["high", "medium", "low"]},
                    "reasoning": {"type": "string"},
                    "supporting_evidence_ids": _ID_LIST,
                    "contradicting_evidence_ids": _ID_LIST,
                    "how_to_verify": {"type": "string"}}}},
            "escalation_pathway": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["step", "condition", "evidence_ids"],
                "properties": {"step": {"type": "string"}, "condition": {"type": "string"}, "evidence_ids": _ID_LIST}}},
            "risk_assessment": {
                "type": "object", "additionalProperties": False,
                "required": ["ai_priority", "agrees_with_rule_severity", "rationale"],
                "properties": {"ai_priority": {"type": "string", "enum": SEVERITY_ORDER},
                               "agrees_with_rule_severity": {"type": "boolean"},
                               "rationale": {"type": "string"}}},
            "missing_information": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["item", "why_it_matters"],
                "properties": {"item": {"type": "string"}, "why_it_matters": {"type": "string"}}}},
            "recommended_actions": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["action", "urgency", "reason", "evidence_ids", "responsible_role"],
                "properties": {"action": {"type": "string"},
                               "urgency": {"type": "string", "enum": ["immediate", "within_24h", "within_7_days", "routine"]},
                               "reason": {"type": "string"}, "evidence_ids": _ID_LIST,
                               "responsible_role": {"type": "string"}}}},
            "uncertainty": {"type": "string"},
        },
    },
}


def _clip(s: str, n: int = 600) -> str:
    s = s or ""
    return s if len(s) <= n else s[:n] + " …"


def related_evidence_ids(alert, equipment_alerts) -> list[str]:
    by_id = {e.alert_id: e for e in equipment_alerts or []}
    out: list[str] = []
    for r in getattr(alert, "related_equipment", []) or []:
        ea = by_id.get(r["equipment_alert_id"])
        if ea:
            out.extend(i for i in ea.evidence_ids if i not in out)
    return out


def build_package(alert, signals, evidence_index, now: datetime, equipment_alerts=None) -> tuple[dict, Redactor, dict]:
    """Returns (package, redactor, alias_to_real_id). Source record IDs can embed staff user names
    (e.g. 'Repair-<user>-059'), so evidence IDs are replaced by opaque aliases E01, E02 ... before sending."""
    red = Redactor()
    rel_ids = [i for i in related_evidence_ids(alert, equipment_alerts)
               if i not in alert.evidence_ids and i not in alert.context_ids]
    ids = list(alert.evidence_ids) + [c for c in alert.context_ids if c not in alert.evidence_ids] + rel_ids
    items = [evidence_index[i] for i in ids if i in evidence_index]
    items.sort(key=lambda e: e.timestamp.isoformat() if e.timestamp else "")
    real_to_alias = {e.evidence_id: f"E{n:02d}" for n, e in enumerate(items, start=1)}
    alias = lambda i: real_to_alias.get(i, i)
    for e in items:
        red.add_known(e.persons)

    def asset_name(a):
        return (ASSETS.get(a) or METERS.get(a) or {}).get("name") if a else None

    def item(e, role):
        return {
            "evidence_id": alias(e.evidence_id), "role": role, "kind": e.kind,
            "time": e.timestamp.isoformat() if e.timestamp else None,
            "asset_id": e.asset_id, "asset_name": asset_name(e.asset_id), "zone": e.zone,
            "title": red.text(_clip(e.title, 200)), "text": red.text(_clip(e.text)),
            "status": e.status, "unresolved": e.is_open,
            "hazard_tags": [t["tag"] for t in e.tags],
            "key_values": {k: v for k, v in e.values.items() if k in (
                "reason", "minutes", "result", "direction", "days", "peak", "median", "pct", "label", "note",
                "action_type", "urgency", "report_type", "fuel_stock_l")},
            "source": f"{e.source.source_title} / {e.source.sheet} / row {e.source.row}" if e.source and e.source.row else
                      (e.source.source_title if e.source else None),
            "same_asset_as_records": None,
        }

    sig_by_id = {s.signal_id: s for s in signals}
    package = {
        "analysis_time": now.isoformat(),
        "building": "Commercial building (shopping centre with offices), Vietnam",
        "zone": {"code": alert.zone, "label": alert.zone_label},
        "rule_based_alert": {"severity": alert.severity, "severity_basis": alert.severity_basis,
                             "note": "Severity from documented preliminary rules; you may disagree in risk_assessment."},
        "signals": [{"signal": f"S{n + 1:02d}", "rule": s.rule_id, "pathway": s.pathway, "mechanism": PATHWAYS[s.pathway]["mechanism"],
                     "severity": s.severity, "basis": s.basis, "unresolved": s.is_open,
                     "evidence_ids": [alias(i) for i in s.evidence_ids],
                     "context_evidence_ids": [alias(i) for i in s.context_ids]}
                    for n, s in enumerate(sig_by_id[i] for i in alert.signal_ids if i in sig_by_id)],
        "evidence": [item(e, "related_equipment" if e.evidence_id in rel_ids else
                          "context" if e.evidence_id in alert.context_ids and e.evidence_id not in alert.evidence_ids
                          else "finding") for e in items],
        "related_equipment_alerts": [
            {"equipment_alert_id": f"EQ{n + 1:02d}",   # opaque: real IDs can contain site codes
             "level": r["severity"], "link_reasons": r["reasons"],
             "title": red.text(next((ea.title for ea in equipment_alerts or [] if ea.alert_id == r["equipment_alert_id"]), "")),
             "evidence_ids": [alias(i) for i in next((ea.evidence_ids for ea in equipment_alerts or []
                                                      if ea.alert_id == r["equipment_alert_id"]), [])]}
            for n, r in enumerate(getattr(alert, "related_equipment", []) or [])],
        "survey_video_observations": [
            {"video": f"V{n + 1:02d}", "recorded_at": (v.get("recorded_at") or "unknown")[:10],
             "age_days": v.get("age_days"), "place": red.text(v.get("place") or ""),
             "origin": "AI vision model, recording-time only",
             "observations": [{**o, "observation": red.text(o["observation"])} for o in v["observations"]]}
            for n, v in enumerate(getattr(alert, "video_context", []) or [])],
        "links": [{"a": alias(l["a"]), "b": alias(l["b"]), "types": l["types"], "reasons": l["reasons"]}
                  for l in alert.links if not (l["types"] == ["same_zone_time_window"])][:80],
        "known_data_limits": [
            "Daily checklists keep only the latest result per checklist (no history in the source).",
            "The list of loads connected to the standby generator is not recorded.",
            "No temperature, smoke or gas sensor telemetry is available; only manual logs and meters.",
            "Photos referenced by the logs are not yet accessible to this system.",
        ],
    }
    for ev in package["evidence"]:
        ev.pop("same_asset_as_records", None)
    return package, red, {v: k for k, v in real_to_alias.items()}


def map_back(result: dict, alias_to_real: dict, signal_map: dict | None = None) -> dict:
    """Replace aliases (E01...) in every evidence-ID list with the real evidence IDs. Unknown aliases are kept
    as-is so validation reports them."""
    def m(lst):
        return [alias_to_real.get(i, i) for i in lst or []]
    for f in result.get("observed_facts", []):
        f["evidence_ids"] = m(f.get("evidence_ids"))
    for h in result.get("hypotheses", []):
        h["supporting_evidence_ids"] = m(h.get("supporting_evidence_ids"))
        h["contradicting_evidence_ids"] = m(h.get("contradicting_evidence_ids"))
    for x in result.get("escalation_pathway", []):
        x["evidence_ids"] = m(x.get("evidence_ids"))
    for a in result.get("recommended_actions", []):
        a["evidence_ids"] = m(a.get("evidence_ids"))
    for sc in result.get("scenarios", []):
        sc["supporting_evidence_ids"] = m(sc.get("supporting_evidence_ids"))
        sc["weakening_evidence_ids"] = m(sc.get("weakening_evidence_ids"))
    for b in result.get("risk_briefings", []):
        b["evidence_ids"] = m(b.get("evidence_ids"))
        b["signal_id"] = (signal_map or {}).get(b.get("signal"))      # None: the model named an unknown signal
    return result


def validate(result: dict, valid_ids) -> dict:
    """Drop citations to evidence IDs that are not in the package and report them."""
    valid = set(valid_ids)
    invalid: list[str] = []

    def clean(lst):
        out = []
        for i in lst or []:
            (out if i in valid else invalid).append(i)
        return out

    for f in result.get("observed_facts", []):
        f["evidence_ids"] = clean(f.get("evidence_ids"))
        f["supported"] = bool(f["evidence_ids"])
    for h in result.get("hypotheses", []):
        h["supporting_evidence_ids"] = clean(h.get("supporting_evidence_ids"))
        h["contradicting_evidence_ids"] = clean(h.get("contradicting_evidence_ids"))
    for s in result.get("escalation_pathway", []):
        s["evidence_ids"] = clean(s.get("evidence_ids"))
    for a in result.get("recommended_actions", []):
        a["evidence_ids"] = clean(a.get("evidence_ids"))
    for sc in result.get("scenarios", []):
        sc["supporting_evidence_ids"] = clean(sc.get("supporting_evidence_ids"))
        sc["weakening_evidence_ids"] = clean(sc.get("weakening_evidence_ids"))
    briefs, unknown_signals = [], []
    for b in result.get("risk_briefings", []):
        b["evidence_ids"] = clean(b.get("evidence_ids"))
        if not b.get("signal_id"):
            unknown_signals.append(b.get("signal"))
            continue
        if b.get("certainty") == "insufficient_evidence":
            b["potential_consequence"] = INSUFFICIENT_TEXT
        briefs.append(b)
    if "risk_briefings" in result:
        result["risk_briefings"] = briefs
    unsupported = [f["statement"] for f in result.get("observed_facts", []) if not f.get("supported")]
    return {"invalid_evidence_ids": sorted(set(invalid)), "unsupported_facts": unsupported,
            "unknown_signals": unknown_signals,
            "ok": not invalid and not unsupported and not unknown_signals}


def fingerprint(alert, evidence_index, equipment_alerts=None) -> str:
    """Identifies the evidence an analysis was based on. Changes when records are added/removed, a status or
    resolution changes, the rule level changes, related equipment alerts change, or the prompt version changes.
    Re-running the analysis on unchanged data gives the same fingerprint, so no duplicate AI call is made."""
    def ev(i):
        e = evidence_index.get(i)
        if not e:
            return [i, None]
        return [i, e.status, e.is_open, e.timestamp.isoformat() if e.timestamp else None,
                e.values.get("label"), bool(e.values.get("ongoing"))]
    def ctx(i):
        # Context records (e.g. the latest daily checklist) get a new record every day. Only what they SAY counts,
        # so a new "passed" checklist on the same equipment does not trigger a new AI call.
        e = evidence_index.get(i)
        if not e:
            return [i]
        tags = sorted({t["tag"] for t in e.tags} & {"checklist_pass", "fault", "grid_outage"})
        return [e.kind, e.asset_id, e.status, e.is_open, tags]
    rel = sorted((r["equipment_alert_id"], r["severity"]) for r in getattr(alert, "related_equipment", []) or [])
    payload = {"v": PROMPT_VERSION, "level": alert.severity,
               "evidence": [ev(i) for i in sorted(set(alert.evidence_ids))],
               "context": sorted({json.dumps(ctx(i), default=str) for i in set(alert.context_ids)}),
               "related": rel, "related_evidence": [ev(i) for i in sorted(set(related_evidence_ids(alert, equipment_alerts)))],
               "video": sorted((v["video_id"], v.get("analysis_created_at")) for v in getattr(alert, "video_context", []) or [])}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:20]


def investigate(alert, signals, evidence_index, now: datetime, client: MuseClient | None = None,
                equipment_alerts=None) -> dict:
    client = client or MuseClient()
    package, _, alias_to_real = build_package(alert, signals, evidence_index, now, equipment_alerts)
    user = ("Investigate this zone alert. Evidence package (JSON):\n" + json.dumps(package, ensure_ascii=False))
    request_hash = hashlib.sha256(user.encode("utf-8")).hexdigest()[:16]
    record = {"alert_id": alert.alert_id, "created_at": now.isoformat(), "prompt_version": PROMPT_VERSION,
              "fingerprint": fingerprint(alert, evidence_index, equipment_alerts), "rule_level": alert.severity,
              "model_requested": client.config.model, "request_hash": request_hash,
              "package_evidence_count": len(package["evidence"]), "redacted": True}
    try:
        res = client.chat_json(SYSTEM_PROMPT, user, SCHEMA)
    except MuseError as err:
        record.update({"status": "failed", "error_kind": err.kind, "error": str(err)})
        return record
    result = map_back(res.data, alias_to_real, signal_aliases(alert, signals))
    record.update({"status": "ok", "model": res.model, "usage": res.usage, "seconds": res.seconds,
                   "result": result, "validation": validate(result, alias_to_real.values()),
                   "evidence_ids_pseudonymised": True})
    return record
