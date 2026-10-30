"""Live check: does Meta Muse Spark (muse-spark-1.3) do tool calling the way FireRisk needs it?

ORIGIN: NEW (2026-10-30). Uses the production client (firerisk/ai/muse.py) and only SYNTHETIC test records - no real
building data is sent. Format from the official docs (read 2026-10-30):
  https://dev.meta.ai/docs/tool-calling   https://dev.meta.ai/docs/cookbook/tool-function-calling
  * tools = [{"type": "function", "function": {name, description, parameters}}]; tool_choice only "auto";
  * finish_reason "tool_calls"; the assistant message with its tool_calls must be sent back, followed by one
    {"role": "tool", "tool_call_id", "content"} message per call.

Steps
  A  tools offered            -> does the model call a tool, with arguments that parse as JSON?
  B  tool results sent back   -> does it continue (more calls or a plain answer)?   (loop, at most 5 turns)
  C  final structured answer  -> same history, no tools, response_format json_schema strict -> schema-valid JSON?
  D  tools + response_format in ONE request -> accepted or rejected? (decides the loop design; either is fine)
Writes evidence/tool_calling_check_<time>.json (no key, no real data). Exit code 0 = A, B and C passed.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from firerisk.ai.muse import MuseClient, MuseError  # noqa: E402

RECORDS = {   # SYNTHETIC test data, clearly not the real building
    "TEST-BLOWER-1": [
        {"id": "T1", "date": "2026-09-02", "type": "repair", "text": "TEST: blower motor burnt out, motor rewound", "status": "closed"},
        {"id": "T2", "date": "2026-10-20", "type": "incident", "text": "TEST: blower seized again, breaker tripped", "status": "open"},
    ],
    "TEST-METER-1": [
        {"id": "T3", "date": "2026-10-19", "type": "meter", "text": "TEST: daily consumption 180% of the 30-day median", "status": None},
    ],
}
TOOLS = [
    {"type": "function", "function": {
        "name": "get_asset_history",
        "description": "Return every TEST maintenance, incident and meter record of one asset, oldest first.",
        "parameters": {"type": "object", "additionalProperties": False, "required": ["asset_id"],
                       "properties": {"asset_id": {"type": "string", "description": "Asset code, e.g. TEST-BLOWER-1"}}}}},
    {"type": "function", "function": {
        "name": "get_meter_readings",
        "description": "Return the TEST meter findings for the meter that measures an asset.",
        "parameters": {"type": "object", "additionalProperties": False, "required": ["meter_id"],
                       "properties": {"meter_id": {"type": "string"}}}}},
]
SYSTEM = ("You investigate a TEST fire-risk alert for a software test. Use the tools to look up records before you "
          "answer. Use only what the tools return.")
USER = ("TEST alert: blower TEST-BLOWER-1 seized and tripped its breaker on 2026-10-20. Its power is measured by "
        "meter TEST-METER-1. Check the history you need, then say in two sentences whether this looks like a repeat fault.")
SCHEMA = {"name": "ToolCheckAnswer", "strict": True, "schema": {
    "type": "object", "additionalProperties": False, "required": ["repeat_fault", "evidence_ids", "summary"],
    "properties": {"repeat_fault": {"type": "boolean"}, "evidence_ids": {"type": "array", "items": {"type": "string"}},
                   "summary": {"type": "string"}}}}


def run_tool(name: str, args: dict):
    if name == "get_asset_history":
        return RECORDS.get(args.get("asset_id"), {"error": f"unknown asset_id {args.get('asset_id')!r}"})
    if name == "get_meter_readings":
        return RECORDS.get(args.get("meter_id"), {"error": f"unknown meter_id {args.get('meter_id')!r}"})
    return {"error": f"unknown tool {name}"}


def main() -> int:
    client = MuseClient()
    if not client.config.configured:
        print("MODEL_API_KEY is not set - run setup_api_key.bat first.")
        return 2
    model = client.config.model
    out = {"checked_at": datetime.now(timezone.utc).isoformat(), "model_requested": model, "data": "SYNTHETIC TEST records only",
           "steps": {}}
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": USER}]
    calls_made, passed = [], {"A": False, "B": False, "C": False}

    # A + B: tool loop
    try:
        for turn in range(5):
            t0 = time.monotonic()
            body = client._post("/chat/completions", {"model": model, "messages": messages, "tools": TOOLS,
                                                      "tool_choice": "auto", "max_completion_tokens": 4000})
            choice = body["choices"][0]
            msg, finish = choice["message"], choice.get("finish_reason")
            tcs = msg.get("tool_calls") or []
            step = {"turn": turn + 1, "seconds": round(time.monotonic() - t0, 2), "finish_reason": finish,
                    "tool_calls": [{"name": tc["function"]["name"], "arguments": tc["function"].get("arguments")} for tc in tcs],
                    "message_keys": sorted(msg.keys()), "usage": body.get("usage"),
                    "content": (msg.get("content") or "")[:400]}
            out["steps"].setdefault("A_B_loop", []).append(step)
            print(f"turn {turn + 1}: finish_reason={finish} tool_calls={[c['name'] for c in step['tool_calls']]}")
            if not tcs:
                passed["B"] = bool(calls_made)            # it used the tool results and answered
                break
            messages.append(msg)                          # the assistant message with its tool_calls, unchanged
            for tc in tcs:
                args = json.loads(tc["function"].get("arguments") or "{}")   # raises if not JSON -> A fails
                passed["A"] = True
                calls_made.append(tc["function"]["name"])
                messages.append({"role": "tool", "tool_call_id": tc["id"],
                                 "content": json.dumps(run_tool(tc["function"]["name"], args))})
        else:
            passed["B"] = bool(calls_made)                # still calling tools after 5 turns: loop works, cap reached
            out["steps"]["loop_note"] = "turn cap (5) reached while the model was still calling tools"
    except (MuseError, KeyError, IndexError, TypeError, json.JSONDecodeError) as err:
        out["steps"]["A_B_error"] = f"{type(err).__name__}: {err}"[:800]
        print("tool loop failed:", out["steps"]["A_B_error"])

    # C: final structured answer from the same history, tools no longer offered
    if passed["A"]:
        try:
            t0 = time.monotonic()
            final = messages + [{"role": "user", "content": "Now give the final answer as JSON."}]
            body = client._post("/chat/completions", {"model": model, "messages": final,
                                                      "response_format": {"type": "json_schema", "json_schema": SCHEMA},
                                                      "max_completion_tokens": 4000})
            content = body["choices"][0]["message"].get("content")
            data = json.loads(content)
            ok = isinstance(data.get("repeat_fault"), bool) and isinstance(data.get("evidence_ids"), list)
            passed["C"] = ok
            out["steps"]["C_final"] = {"seconds": round(time.monotonic() - t0, 2), "answer": data, "schema_ok": ok,
                                       "usage": body.get("usage")}
            print("final structured answer:", json.dumps(data, ensure_ascii=False))
        except (MuseError, KeyError, IndexError, TypeError, json.JSONDecodeError) as err:
            out["steps"]["C_error"] = f"{type(err).__name__}: {err}"[:800]
            print("final structured answer failed:", out["steps"]["C_error"])

    # D: tools and response_format together (informative only)
    try:
        body = client._post("/chat/completions", {"model": model, "messages": messages[:2], "tools": TOOLS,
                                                  "response_format": {"type": "json_schema", "json_schema": SCHEMA},
                                                  "max_completion_tokens": 2000})
        out["steps"]["D_tools_plus_schema"] = {"accepted": True, "finish_reason": body["choices"][0].get("finish_reason")}
    except MuseError as err:
        out["steps"]["D_tools_plus_schema"] = {"accepted": False, "error": str(err)[:400]}
    print("tools + response_format in one request:", out["steps"]["D_tools_plus_schema"])

    out["passed"] = passed
    out["tools_called"] = calls_made
    key = client.config.api_key or ""
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if key and key in text:
        text = text.replace(key, "[REDACTED]")
    path = ROOT / "evidence" / f"tool_calling_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text, encoding="utf-8")
    verdict = "PASS" if all(passed.values()) else "FAIL"
    print(f"\n{verdict}: A (calls a tool) {passed['A']}, B (uses results) {passed['B']}, C (final JSON) {passed['C']}")
    print(f"Evidence written to {path.relative_to(ROOT)}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
