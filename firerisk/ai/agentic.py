"""Agentic root-cause investigation: Meta Muse Spark decides which records to look up. ORIGIN: NEW (2026-10-30).

Flow
  rule-based alert -> the same redacted evidence package as the single-call investigation ->
  Muse Spark gets READ-ONLY tools over the whole record store (asset history, record search, meter readings,
  equipment alerts, survey-video findings, asset list) and decides what to check (tool calling, official format:
  https://dev.meta.ai/docs/tool-calling) -> every call is executed locally, redacted, aliased and recorded in a trace
  -> when Muse Spark stops calling tools (or a turn / call cap is reached) the same history is asked for the final
  answer in the existing strict JSON schema -> cited IDs validated against everything Muse Spark was shown.

Safety
  * Tools only read. Nothing the model asks for can change data, levels, alarms or equipment.
  * Record IDs never leave the app: every record gets an opaque alias (E01 ...); personal names are redacted.
  * Arguments are validated; a bad call returns an error message the model can recover from, never an exception.
  * Caps: MAX_TURNS tool turns, MAX_CALLS tool calls, MAX_RESULTS records per call.
  * Fallback: any API error, an answer cut off, or a tool loop that cannot finish -> the single-call investigation
    (investigation.investigate) runs instead, and the record says why ("mode": "single_call", "agentic_fallback").
  * The rule level stays authoritative, exactly as in the single-call investigation.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import date, datetime

from ..config import ASSETS, METER_FEEDS, METERS
from . import investigation as inv
from .muse import MuseBadResponse, MuseClient, MuseError, MuseTruncated

MAX_TURNS = 6          # tool turns before the final answer is requested
MAX_CALLS = 16         # tool calls in one investigation
MAX_RESULTS = 25       # records returned by one call
TOOL_TURN_TOKENS = 8000

AGENT_ADDENDUM = """

Tools (read-only): the package above is what the deterministic rules assembled. Before you answer you may look up
more records with the tools - e.g. the full history of an asset, earlier incidents in the same room, meter readings
around a fault date, related equipment alerts, survey-video findings, which life-safety equipment an electrical panel supplies. Look up only what could change or test your
conclusion (a repeat fault, a contradicting record, a timeline gap). Records returned by tools get evidence IDs
(E..) you may cite like package evidence. Do not call a tool for something already in the package. When you have
enough, stop calling tools and say in one or two sentences what you checked and why; you will then be asked for
the final JSON."""

FINAL_PROMPT = ("Now write the investigation as JSON in the required schema. Cite evidence IDs exactly as given in "
                "the package or in the tool results; video findings by their video alias in text only.")

KINDS = ["incident", "construction", "asset_service", "inspection_check", "generator_run", "meter_reading",
         "meter_episode", "vehicle_day"]


def _fn(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "additionalProperties": False, "properties": properties, "required": required}}}


_DATE = {"type": "string", "description": "ISO date YYYY-MM-DD"}
TOOLS = [
    _fn("list_assets", "List the building's known assets and meters (code, name, floor/zone, fire-safety role, which "
        "meter measures it). Use it to find asset codes.",
        {"zone": {"type": "string", "description": "Optional floor/zone code, e.g. B1, F2, Roof, Building"}}, []),
    _fn("get_asset_history", "All records of one asset (repairs, incidents, checklists, generator runs, meter findings), "
        "newest first. Use it to see whether a fault is a repeat or whether a repair held.",
        {"asset_id": {"type": "string", "description": "Asset code, e.g. P-BG.TTC167"},
         "since": _DATE, "until": _DATE}, ["asset_id"]),
    _fn("search_records", "Search all building records by words in the title/text, zone, record kind, date range or open "
        "status, newest first. Use it for records the package may not contain (same room, same symptom, same period).",
        {"text": {"type": "string", "description": "Words to find (Vietnamese or English, case-insensitive)"},
         "zone": {"type": "string"}, "kind": {"type": "string", "enum": KINDS},
         "since": _DATE, "until": _DATE, "open_only": {"type": "boolean"}}, []),
    _fn("get_meter_readings", "Daily readings and detected consumption episodes of one meter (electricity or water) in a "
        "date range. Use it to check loading around a fault date.",
        {"meter_id": {"type": "string", "description": "Meter code, e.g. P-BG.TTC226"}, "since": _DATE, "until": _DATE},
        ["meter_id"]),
    _fn("get_equipment_alerts", "Maintenance (equipment) alerts from the rule set, with level and evidence, for a zone or "
        "one asset.", {"zone": {"type": "string"}, "asset_id": {"type": "string"}}, []),
    _fn("get_fire_safety_supply", "Which life-safety equipment (emergency lights, exit signs, fire pump, smoke control, "
        "fire alarm) an electrical asset supplies, directly or through downstream panels, per floor with counts - from "
        "the building's electrical and emergency-lighting drawings, each link checked by a person. Give asset_id to "
        "ask about one panel, or zone to list the assets supplying life-safety equipment on that floor. An empty list "
        "means no confirmed link, NOT that the asset supplies nothing.",
        {"asset_id": {"type": "string"}, "zone": {"type": "string"}}, []),
    _fn("get_video_findings", "Meta Muse Spark survey-video observations for a zone (what was visible at recording time "
        "only; not current state, not a confirmed hazard).", {"zone": {"type": "string"}}, ["zone"]),
]
TOOL_NAMES = {t["function"]["name"] for t in TOOLS}


def _day(v):
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise ValueError(f"invalid date {v!r}; use YYYY-MM-DD") from None


class EvidenceTools:
    """Executes the model's tool calls on the in-memory analysis result. Shares the package's alias map, so a record
    has the same alias whether it came from the package or from a tool."""

    def __init__(self, evidence_index: dict, real_to_alias: dict, redactor, equipment_alerts=None, video_lookup=None,
                 power_links=None):
        self.ev = evidence_index
        self.alias = dict(real_to_alias)
        self.red = redactor
        self.equipment_alerts = equipment_alerts or []
        self.video_lookup = video_lookup
        self.power_links = power_links
        self.video_alias: dict[str, str] = {}
        self.new_aliases: list[str] = []           # records first shown through a tool

    # --- helpers ----------------------------------------------------------------------------------
    def alias_of(self, real_id: str) -> str:
        if real_id not in self.alias:
            self.alias[real_id] = f"E{len(self.alias) + 1:02d}"
            self.new_aliases.append(self.alias[real_id])
            e = self.ev.get(real_id)
            if e:
                self.red.add_known(e.persons)
        return self.alias[real_id]

    def alias_to_real(self) -> dict:
        return {v: k for k, v in self.alias.items()}

    def _item(self, e) -> dict:
        name = (ASSETS.get(e.asset_id) or METERS.get(e.asset_id) or {}).get("name") if e.asset_id else None
        return {"evidence_id": self.alias_of(e.evidence_id), "kind": e.kind,
                "time": e.timestamp.isoformat() if e.timestamp else None, "asset_id": e.asset_id, "asset_name": name,
                "zone": e.zone, "title": self.red.text(inv._clip(e.title, 160)), "text": self.red.text(inv._clip(e.text, 300)),
                "status": e.status, "unresolved": e.is_open, "hazard_tags": [t["tag"] for t in e.tags]}

    @staticmethod
    def _in_range(e, since, until) -> bool:
        d = e.timestamp.date() if e.timestamp else None
        if (since or until) and d is None:
            return False
        return (not since or d >= since) and (not until or d <= until)

    def _records(self, pred, since=None, until=None):
        rows = [e for e in self.ev.values() if "test_record" not in (e.flags or []) and pred(e) and self._in_range(e, since, until)]
        rows.sort(key=lambda e: e.timestamp.isoformat() if e.timestamp else "", reverse=True)
        return rows

    def _page(self, rows) -> dict:
        return {"total_matches": len(rows), "returned": min(len(rows), MAX_RESULTS),
                "records": [self._item(e) for e in rows[:MAX_RESULTS]],
                **({"note": f"only the newest {MAX_RESULTS} shown; narrow the dates for more"} if len(rows) > MAX_RESULTS else {})}

    # --- tools ------------------------------------------------------------------------------------
    def list_assets(self, zone=None):
        feeds = {a: m for m, lst in METER_FEEDS.items() for a in lst}
        assets = [{"asset_id": k, "name": v["name"], "zone": v.get("zone"), "fire_role": v.get("fire_role"),
                   "measured_by_meter": feeds.get(k)} for k, v in ASSETS.items() if not zone or v.get("zone") == zone]
        meters = [{"meter_id": k, "name": v["name"], "zone": v.get("zone"), "unit": v.get("unit"),
                   "feeds": METER_FEEDS.get(k, [])} for k, v in METERS.items() if not zone or v.get("zone") == zone]
        return {"assets": assets, "meters": meters}

    def get_asset_history(self, asset_id, since=None, until=None):
        if asset_id not in ASSETS and asset_id not in METERS and not any(e.asset_id == asset_id for e in self.ev.values()):
            return {"error": f"unknown asset_id {asset_id!r}; call list_assets"}
        return self._page(self._records(lambda e: e.asset_id == asset_id and e.kind != "meter_reading", _day(since), _day(until)))

    def search_records(self, text=None, zone=None, kind=None, since=None, until=None, open_only=False):
        if not any((text, zone, kind, since, until, open_only)):
            return {"error": "give at least one filter (text, zone, kind, dates or open_only)"}
        if kind and kind not in KINDS:
            return {"error": f"unknown kind {kind!r}; one of {KINDS}"}
        words = [w for w in (text or "").lower().split() if w]
        def pred(e):
            hay = f"{e.title} {e.text}".lower()
            return ((not words or all(w in hay for w in words)) and (not zone or e.zone == zone)
                    and (not kind or e.kind == kind) and (not open_only or e.is_open))
        return self._page(self._records(pred, _day(since), _day(until)))

    def get_meter_readings(self, meter_id, since=None, until=None):
        if meter_id not in METERS:
            return {"error": f"unknown meter_id {meter_id!r}; call list_assets"}
        s, u = _day(since), _day(until)
        reads = self._records(lambda e: e.asset_id == meter_id and e.kind == "meter_reading", s, u)
        eps = self._records(lambda e: e.asset_id == meter_id and e.kind == "meter_episode", s, u)
        m = METERS[meter_id]
        return {"meter": {"meter_id": meter_id, "name": m["name"], "unit": m.get("unit"),
                          "unit_verified": bool(m.get("multiplier")) and m.get("multiplier_verified", True),
                          "feeds": METER_FEEDS.get(meter_id, [])},
                "readings": [{"evidence_id": self.alias_of(e.evidence_id), "date": e.timestamp.date().isoformat() if e.timestamp else None,
                              "reading": e.values.get("reading"), "daily_entered": e.values.get("daily_entered")}
                             for e in reads[:60]],
                "readings_total": len(reads),
                "episodes": [self._item(e) for e in eps[:15]]}

    def get_equipment_alerts(self, zone=None, asset_id=None):
        rows = [a for a in self.equipment_alerts if (not zone or a.zone == zone) and (not asset_id or a.asset_id == asset_id)]
        return {"equipment_alerts": [{"asset_id": a.asset_id, "asset_name": a.asset_name, "zone": a.zone,
                                      "level": a.severity, "critical_equipment": a.critical,
                                      "title": self.red.text(a.title), "open_items": a.open_items,
                                      "rules": [r.get("rule") for r in a.rules],
                                      "evidence_ids": [self.alias_of(i) for i in a.evidence_ids if i in self.ev][:15]}
                                     for a in rows[:20]], "total": len(rows)}

    def get_fire_safety_supply(self, asset_id=None, zone=None):
        """Simplified drawing links only (owner's condition 2): floor, equipment type, count, direct or not.
        No panel labels, circuits or drawing details."""
        from ..power_links import summary
        if not asset_id and not zone:
            return {"error": "give asset_id or zone"}
        pl = self.power_links
        if pl is None or not pl.links:
            return {"links": [], "note": "no confirmed drawing links are available in this run"}
        out = summary(pl, asset_id=asset_id or None, floor=zone or None)
        out["total"] = len(out["links"])
        return out

    def get_video_findings(self, zone):
        if not self.video_lookup:
            return {"error": "survey videos are not available in this run"}
        out = []
        for v in self.video_lookup(zone) or []:
            va = self.video_alias.setdefault(v["video_id"], f"V{len(self.video_alias) + 1:02d}")
            out.append({"video": va, "recorded_at": (v.get("recorded_at") or "unknown")[:10], "place": self.red.text(v.get("place") or ""),
                        "origin": "Meta Muse Spark video review, recording-time only",
                        "findings": [{**f, "title": self.red.text(f.get("title") or ""),
                                      "what_is_visible": self.red.text(f.get("what_is_visible") or "")} for f in v.get("findings", [])],
                        "observations": [{**o, "observation": self.red.text(o["observation"])} for o in v.get("observations", [])][:15]})
        return {"videos": out, "note": "Mention videos by alias in text only; never as evidence_ids."}

    def run(self, name: str, raw_args: str | None) -> tuple[dict, dict]:
        """Returns (result for the model, trace entry). Never raises."""
        try:
            args = json.loads(raw_args or "{}")
            if not isinstance(args, dict):
                raise ValueError("arguments must be a JSON object")
        except (json.JSONDecodeError, ValueError) as err:
            return {"error": f"arguments are not valid JSON: {err}"}, {"error": "invalid_arguments"}
        if name not in TOOL_NAMES:
            return {"error": f"unknown tool {name!r}"}, {"error": "unknown_tool"}
        allowed = set(next(t for t in TOOLS if t["function"]["name"] == name)["function"]["parameters"]["properties"])
        clean = {k: v for k, v in args.items() if k in allowed and v not in (None, "")}
        before = set(self.alias.values())
        try:
            result = getattr(self, name)(**clean)
        except (ValueError, TypeError) as err:
            result = {"error": str(err)}
        shown = sorted(set(self.alias.values()) - before)
        entry = {"args": clean, "error": result.get("error"),
                 "returned": result.get("returned", len(result.get("readings", [])) or len(result.get("equipment_alerts", []))
                                        or len(result.get("videos", [])) or len(result.get("assets", []))
                                        or len(result.get("links", []))),
                 "total_matches": result.get("total_matches"), "new_evidence_aliases": shown}
        return result, entry


def investigate_agentic(alert, signals, evidence_index, now: datetime, client: MuseClient | None = None,
                        equipment_alerts=None, video_lookup=None, power_links=None) -> dict:
    """Agentic investigation with automatic fallback to the single-call investigation."""
    client = client or MuseClient()
    t_start = time.monotonic()
    package, red, alias_to_real = inv.build_package(alert, signals, evidence_index, now, equipment_alerts)
    tools = EvidenceTools(evidence_index, {v: k for k, v in alias_to_real.items()}, red, equipment_alerts, video_lookup,
                          power_links)
    user = "Investigate this zone alert. Evidence package (JSON):\n" + json.dumps(package, ensure_ascii=False)
    messages = [{"role": "system", "content": inv.SYSTEM_PROMPT + AGENT_ADDENDUM}, {"role": "user", "content": user}]
    trace: list[dict] = []
    usage_total: dict = {}
    calls = 0
    stop = "model_finished"

    def add_usage(u):
        for k, v in (u or {}).items():
            if isinstance(v, (int, float)):
                usage_total[k] = usage_total.get(k, 0) + v

    try:
        for turn in range(1, MAX_TURNS + 1):
            t = client.chat_tools(messages, TOOLS, max_completion_tokens=TOOL_TURN_TOKENS)
            add_usage(t.usage)
            if not t.tool_calls:
                if t.message.get("content"):
                    messages.append({"role": "assistant", "content": t.message["content"]})
                    trace.append({"turn": turn, "type": "note", "text": red.text(inv._clip(t.message["content"], 600)),
                                  "seconds": t.seconds})
                break
            messages.append(t.message)                     # assistant message with tool_calls, unchanged
            if (t.message.get("content") or "").strip():  # live 2026-10-30: Muse Spark states its intent with the calls
                trace.append({"turn": turn, "type": "intent", "text": red.text(inv._clip(t.message["content"], 400)),
                              "seconds": t.seconds})
            for tc in t.tool_calls:
                fn = (tc.get("function") or {})
                calls += 1
                if calls > MAX_CALLS:
                    result, entry = {"error": f"tool call limit ({MAX_CALLS}) reached; answer with what you have"}, {"error": "call_limit"}
                else:
                    result, entry = tools.run(fn.get("name"), fn.get("arguments"))
                messages.append({"role": "tool", "tool_call_id": tc.get("id"), "content": json.dumps(result, ensure_ascii=False, default=str)})
                trace.append({"turn": turn, "type": "tool", "tool": fn.get("name"), "seconds": t.seconds, **entry})
            if calls >= MAX_CALLS:
                stop = "call_limit"
                break
        else:
            stop = "turn_limit"
        final = client.chat_json_messages(messages + [{"role": "user", "content": FINAL_PROMPT}], inv.SCHEMA,
                                          max_completion_tokens=inv.INVESTIGATION_MAX_TOKENS)
        add_usage(final.usage)
    except MuseError as err:
        if not _tool_problem(err):
            # API unreachable, auth, rate limit, server error: one call would fail the same way - record the failure
            return {"alert_id": alert.alert_id, "created_at": now.isoformat(), "prompt_version": inv.PROMPT_VERSION,
                    "fingerprint": inv.fingerprint(alert, evidence_index, equipment_alerts), "rule_level": alert.severity,
                    "model_requested": client.config.model, "status": "failed", "mode": "agentic",
                    "error_kind": err.kind, "error": str(err), "agent": {"trace": trace, "tool_calls": calls}}
        rec = inv.investigate(alert, signals, evidence_index, now, client, equipment_alerts)
        rec.update({"mode": "single_call", "agentic_fallback": {"reason": err.kind, "error": str(err)[:300],
                                                                "trace_before_failure": trace}})
        return rec
    a2r = tools.alias_to_real()
    result = inv.map_back(final.data, a2r, inv.signal_aliases(alert, signals))
    validation = inv.validate(result, a2r.values())            # drops IDs Muse Spark was never shown
    beyond = sorted(set(_cited(result)) - set(alias_to_real.values()))
    record = {"alert_id": alert.alert_id, "created_at": now.isoformat(), "prompt_version": inv.PROMPT_VERSION,
              "fingerprint": inv.fingerprint(alert, evidence_index, equipment_alerts), "rule_level": alert.severity,
              "model_requested": client.config.model,
              "request_hash": hashlib.sha256(user.encode("utf-8")).hexdigest()[:16],
              "package_evidence_count": len(package["evidence"]), "redacted": True, "evidence_ids_pseudonymised": True,
              "status": "ok", "mode": "agentic", "model": final.model, "usage": usage_total,
              "seconds": round(time.monotonic() - t_start, 2), "result": result,
              "validation": validation,
              "agent": {"tool_calls": calls, "turns": len({s["turn"] for s in trace}), "stop": stop, "trace": trace,
                        "records_looked_up": len(tools.new_aliases),
                        "cited_beyond_package": beyond, "limits": {"turns": MAX_TURNS, "calls": MAX_CALLS, "results": MAX_RESULTS}}}
    return record


def _tool_problem(err: MuseError) -> bool:
    """True when the failure concerns the tool-calling conversation itself (request rejected as invalid, malformed
    answer, answer cut off) - then the proven single-call investigation is the fallback."""
    if isinstance(err, MuseTruncated):
        return True
    if isinstance(err, MuseBadResponse):
        msg = str(err)
        return not msg.startswith("HTTP 5")
    return False


def _cited(result: dict) -> list[str]:
    out = []
    for f in result.get("observed_facts", []):
        out += f.get("evidence_ids", [])
    for h in result.get("hypotheses", []):
        out += h.get("supporting_evidence_ids", []) + h.get("contradicting_evidence_ids", [])
    for x in result.get("escalation_pathway", []) + result.get("recommended_actions", []):
        out += x.get("evidence_ids", [])
    for sc in result.get("scenarios", []):
        out += sc.get("supporting_evidence_ids", []) + sc.get("weakening_evidence_ids", [])
    for b in result.get("risk_briefings", []):
        out += b.get("evidence_ids", [])
        for c in b.get("claims") or []:
            out += c.get("evidence_ids", [])
    return out
