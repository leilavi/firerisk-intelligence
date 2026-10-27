"""Meta Model API connection check for FireRisk Intelligence.

Uses only the Python standard library (no pip install needed).

What it does:
  1. Reads MODEL_API_KEY from the environment or from the project's .env file.
  2. GET  /v1/models                 -> lists the model IDs your key can use.
  3. POST /v1/chat/completions       -> one small structured-output request to
                                        muse-spark-1.3 (JSON schema).
  4. Writes a sanitized evidence file to evidence/api_check_<timestamp>.json.
     The API key is NEVER printed or saved.

API facts used here were taken from the official docs (read 2026-10-27):
  https://dev.meta.ai/docs/quickstart
  https://dev.meta.ai/docs/protocols/chat-completions
  https://dev.meta.ai/docs/structured-output
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = os.environ.get("META_API_BASE_URL", "https://api.meta.ai/v1").rstrip("/")
MODEL = os.environ.get("META_REASONING_MODEL", "muse-spark-1.3")
TIMEOUT_S = 120
ROOT = Path(__file__).resolve().parent.parent


def load_api_key() -> str | None:
    key = os.environ.get("MODEL_API_KEY")
    if key:
        return key.strip()
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line.startswith("MODEL_API_KEY="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                return value or None
    return None


def request(method: str, path: str, key: str, body: dict | None = None) -> tuple[int, dict | str, float]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8")
            status = resp.status
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")
        status = err.code
    elapsed = time.monotonic() - start
    try:
        return status, json.loads(raw), elapsed
    except json.JSONDecodeError:
        return status, raw[:2000], elapsed


def redact(obj, key: str):
    """Remove the API key from anything we save, just in case it is echoed."""
    text = json.dumps(obj, ensure_ascii=False)
    if key and key in text:
        text = text.replace(key, "<REDACTED_KEY>")
    return json.loads(text)


SCHEMA = {
    "name": "ConnectionCheck",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["ok"]},
            "model_role": {"type": "string"},
            "observation_count": {"type": "integer"},
        },
        "required": ["status", "model_role", "observation_count"],
        "additionalProperties": False,
    },
}


def main() -> int:
    print("=" * 60)
    print("FireRisk Intelligence - Meta Model API connection check")
    print(f"Endpoint: {BASE_URL}   Model: {MODEL}")
    print("=" * 60)

    key = load_api_key()
    if not key:
        print("[FAIL] MODEL_API_KEY not found. Run setup_api_key.bat first.")
        return 2
    print(f"[OK]   API key loaded ({len(key)} characters, value hidden)")

    evidence: dict = {
        "check": "meta_model_api_connection",
        "run_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base_url": BASE_URL,
        "model_requested": MODEL,
        "steps": [],
    }
    ok = True

    # Step 1: list models
    print("\n[1/2] Listing models (GET /models) ...")
    try:
        status, body, secs = request("GET", "/models", key)
    except Exception as exc:  # network errors, DNS, TLS, timeout
        print(f"[FAIL] Network error: {type(exc).__name__}: {exc}")
        evidence["steps"].append({"step": "list_models", "error": f"{type(exc).__name__}: {exc}"})
        status, body, secs = None, None, 0
    if status is not None:
        ids = []
        if isinstance(body, dict) and isinstance(body.get("data"), list):
            ids = sorted(str(m.get("id")) for m in body["data"] if isinstance(m, dict))
        print(f"       HTTP {status} in {secs:.1f}s")
        if status == 200:
            print(f"[OK]   {len(ids)} models available: {', '.join(ids) if ids else '(none listed)'}")
            if ids and MODEL not in ids:
                print(f"[WARN] {MODEL} is not in the list.")
        else:
            ok = False
            print(f"[FAIL] {str(body)[:500]}")
        evidence["steps"].append({"step": "list_models", "http_status": status,
                                  "seconds": round(secs, 2), "model_ids": ids})
    else:
        ok = False

    # Step 2: structured-output chat completion
    print("\n[2/2] Structured output test (POST /chat/completions) ...")
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are the reasoning engine of a fire-risk decision-support tool. Answer only with the requested JSON."},
            {"role": "user", "content": "Connection test. Set status to 'ok', describe your role in one short sentence, and count the observations: (1) panel temperature rising, (2) exhaust fan fault, (3) repeated breaker trips."},
        ],
        "response_format": {"type": "json_schema", "json_schema": SCHEMA},
        "reasoning_effort": "low",
        "max_completion_tokens": 2000,
    }
    try:
        status, body, secs = request("POST", "/chat/completions", key, payload)
    except Exception as exc:
        print(f"[FAIL] Network error: {type(exc).__name__}: {exc}")
        evidence["steps"].append({"step": "chat_completion", "error": f"{type(exc).__name__}: {exc}"})
        status = None
        ok = False
    if status is not None:
        print(f"       HTTP {status} in {secs:.1f}s")
        step = {"step": "chat_completion", "http_status": status, "seconds": round(secs, 2)}
        if status == 200 and isinstance(body, dict):
            content = body["choices"][0]["message"].get("content", "")
            step["model_returned"] = body.get("model")
            step["usage"] = body.get("usage")
            step["raw_content"] = content
            try:
                parsed = json.loads(content)
                valid = (parsed.get("status") == "ok"
                         and isinstance(parsed.get("observation_count"), int)
                         and set(parsed) == {"status", "model_role", "observation_count"})
                step["parsed"] = parsed
                step["schema_valid"] = valid
                print(f"[{'OK' if valid else 'FAIL'}]   Model replied: {parsed}")
                print(f"       Usage: {body.get('usage')}")
                ok = ok and valid
            except json.JSONDecodeError:
                step["schema_valid"] = False
                print(f"[FAIL] Reply was not valid JSON: {content[:300]}")
                ok = False
        else:
            ok = False
            step["error_body"] = body
            hints = {400: "bad request (parameter or schema rejected)", 401: "key invalid or not active",
                     403: "key lacks access", 429: "rate limit / no credits", 504: "timeout"}
            print(f"[FAIL] {hints.get(status, 'unexpected error')}: {str(body)[:500]}")
        evidence["steps"].append(step)

    evidence["result"] = "PASS" if ok else "FAIL"
    out_dir = ROOT / "evidence"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"api_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_file.write_text(json.dumps(redact(evidence, key), indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"RESULT: {evidence['result']}")
    print(f"Evidence saved (no key inside): {out_file}")
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
