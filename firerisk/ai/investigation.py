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

PROMPT_VERSION = "investigation-v2"  # v2: opaque evidence-ID aliases

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
5. Consider contradicting evidence, e.g. daily checklists that report "Đạt" (passed) or scheduled
   generator runs that succeeded, and alternative benign explanations (e.g. metering/data-entry issues).
6. Recommendations must be proportionate, specific and verifiable. Never recommend disabling alarms or
   operating fire-suppression systems automatically; for confirmed emergencies refer to the building's
   approved emergency procedure.
7. This is decision support. It does not replace certified fire systems or qualified professionals.
Write in clear English. Keep Vietnamese equipment names in parentheses where useful."""

_ID_LIST = {"type": "array", "items": {"type": "string"}}
SCHEMA = {
    "name": "FireRiskInvestigation",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "observed_facts", "hypotheses", "escalation_pathway", "risk_assessment",
                     "missing_information", "recommended_actions", "uncertainty"],
        "properties": {
            "summary": {"type": "string"},
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


def build_package(alert, signals, evidence_index, now: datetime) -> tuple[dict, Redactor, dict]:
    """Returns (package, redactor, alias_to_real_id). Source record IDs can embed staff user names
    (e.g. 'Repair-<user>-059'), so evidence IDs are replaced by opaque aliases E01, E02 ... before sending."""
    red = Redactor()
    ids = list(alert.evidence_ids) + [c for c in alert.context_ids if c not in alert.evidence_ids]
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
        "signals": [{"rule": s.rule_id, "pathway": s.pathway, "mechanism": PATHWAYS[s.pathway]["mechanism"],
                     "severity": s.severity, "basis": s.basis, "unresolved": s.is_open,
                     "evidence_ids": [alias(i) for i in s.evidence_ids],
                     "context_evidence_ids": [alias(i) for i in s.context_ids]}
                    for s in (sig_by_id[i] for i in alert.signal_ids if i in sig_by_id)],
        "evidence": [item(e, "context" if e.evidence_id in alert.context_ids and e.evidence_id not in alert.evidence_ids
                          else "finding") for e in items],
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


def map_back(result: dict, alias_to_real: dict) -> dict:
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
    unsupported = [f["statement"] for f in result.get("observed_facts", []) if not f.get("supported")]
    return {"invalid_evidence_ids": sorted(set(invalid)), "unsupported_facts": unsupported,
            "ok": not invalid and not unsupported}


def investigate(alert, signals, evidence_index, now: datetime, client: MuseClient | None = None) -> dict:
    client = client or MuseClient()
    package, _, alias_to_real = build_package(alert, signals, evidence_index, now)
    user = ("Investigate this zone alert. Evidence package (JSON):\n" + json.dumps(package, ensure_ascii=False))
    request_hash = hashlib.sha256(user.encode("utf-8")).hexdigest()[:16]
    record = {"alert_id": alert.alert_id, "created_at": now.isoformat(), "prompt_version": PROMPT_VERSION,
              "model_requested": client.config.model, "request_hash": request_hash,
              "package_evidence_count": len(package["evidence"]), "redacted": True}
    try:
        res = client.chat_json(SYSTEM_PROMPT, user, SCHEMA)
    except MuseError as err:
        record.update({"status": "failed", "error_kind": err.kind, "error": str(err)})
        return record
    result = map_back(res.data, alias_to_real)
    record.update({"status": "ok", "model": res.model, "usage": res.usage, "seconds": res.seconds,
                   "result": result, "validation": validate(result, alias_to_real.values()),
                   "evidence_ids_pseudonymised": True})
    return record
