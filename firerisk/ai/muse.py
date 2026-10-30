"""Meta Model API client (Muse Spark) - standard library only.

ORIGIN: NEW. Endpoint, auth and parameters follow the official docs read on 2026-10-27:
  https://dev.meta.ai/docs/quickstart, /docs/protocols/chat-completions, /docs/structured-output
and were verified by a real call (evidence/api_check_20261027_133317.json).
"""

from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class MuseError(Exception):
    kind = "error"


class MuseNotConfigured(MuseError):
    kind = "not_configured"


class MuseAuthError(MuseError):
    kind = "auth"


class MuseRateLimited(MuseError):
    kind = "rate_limited"


class MuseTimeout(MuseError):
    kind = "timeout"


class MuseBadResponse(MuseError):
    kind = "bad_response"


class MuseTruncated(MuseBadResponse):
    """The model stopped because the completion budget (which includes reasoning tokens) ran out."""
    kind = "truncated"


@dataclass
class MuseConfig:
    api_key: str | None
    base_url: str = "https://api.meta.ai/v1"
    model: str = "muse-spark-1.3"
    timeout_s: int = 180

    @classmethod
    def load(cls) -> "MuseConfig":
        env = dict(os.environ)
        env_file = ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8-sig").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        return cls(api_key=env.get("MODEL_API_KEY") or None,
                   base_url=env.get("META_API_BASE_URL", "https://api.meta.ai/v1").rstrip("/"),
                   model=env.get("META_REASONING_MODEL", "muse-spark-1.3"))

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


@dataclass
class MuseResult:
    data: dict
    model: str | None
    usage: dict | None
    seconds: float
    raw_content: str


@dataclass
class ToolTurn:
    message: dict              # the assistant message exactly as returned (sent back in the next turn)
    tool_calls: list[dict]
    finish_reason: str | None
    model: str | None
    usage: dict | None
    seconds: float


class MuseClient:
    def __init__(self, config: MuseConfig | None = None, opener=None):
        self.config = config or MuseConfig.load()
        self._open = opener or urllib.request.urlopen

    def _post(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(
            f"{self.config.base_url}{path}", data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"})
        return self._send(req)

    def _send(self, req) -> dict:
        """Send any prepared request (JSON POST, multipart upload, DELETE) with the same error handling."""
        try:
            with self._open(req, timeout=self.config.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", errors="replace")[:500]
            if err.code in (401, 403):
                raise MuseAuthError(f"HTTP {err.code}: {body}") from None
            if err.code == 429:
                raise MuseRateLimited(f"HTTP 429: {body}") from None
            if err.code == 504:
                raise MuseTimeout(f"HTTP 504: {body}") from None
            raise MuseBadResponse(f"HTTP {err.code}: {body}") from None
        except TimeoutError as err:
            raise MuseTimeout(str(err)) from None
        except urllib.error.URLError as err:
            if isinstance(err.reason, TimeoutError):
                raise MuseTimeout(str(err)) from None
            raise MuseError(f"network error: {err.reason}") from None
        except json.JSONDecodeError as err:
            raise MuseBadResponse(f"non-JSON response: {err}") from None

    def _post_retry(self, payload: dict, retries: int) -> tuple[dict, float]:
        """POST /chat/completions; retries only rate limits and timeouts (a 400 is never resent)."""
        attempt = 0
        while True:
            start = time.monotonic()
            try:
                body = self._post("/chat/completions", payload)
                return body, time.monotonic() - start
            except (MuseRateLimited, MuseTimeout):
                if attempt >= retries:
                    raise
                time.sleep((2 ** attempt) + random.random())
                attempt += 1

    def chat_json(self, system: str, user: str, schema: dict, *, reasoning_effort: str = "medium",
                  max_completion_tokens: int = 8000, retries: int = 2) -> MuseResult:
        return self.chat_json_messages([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                       schema, reasoning_effort=reasoning_effort,
                                       max_completion_tokens=max_completion_tokens, retries=retries)

    def chat_tools(self, messages: list[dict], tools: list[dict], *, reasoning_effort: str = "medium",
                   max_completion_tokens: int = 8000, retries: int = 2) -> ToolTurn:
        """One turn of a tool-calling conversation (official format, https://dev.meta.ai/docs/tool-calling):
        function tools only, tool_choice "auto" (the only value the API accepts). Returns the assistant message
        unchanged - it must be sent back as-is, followed by one role "tool" message per call."""
        if not self.config.configured:
            raise MuseNotConfigured("MODEL_API_KEY is not set (run setup_api_key.bat)")
        payload = {"model": self.config.model, "messages": messages, "tools": tools, "tool_choice": "auto",
                   "reasoning_effort": reasoning_effort, "max_completion_tokens": max_completion_tokens}
        body, secs = self._post_retry(payload, retries)
        try:
            choice = body["choices"][0]
            msg, finish = choice["message"], choice.get("finish_reason")
        except (KeyError, IndexError, TypeError):
            raise MuseBadResponse(f"unexpected response shape: {str(body)[:300]}") from None
        if finish == "length":
            raise MuseTruncated(f"tool turn cut off at max_completion_tokens={max_completion_tokens}")
        return ToolTurn(message=msg, tool_calls=list(msg.get("tool_calls") or []), finish_reason=finish,
                        model=body.get("model"), usage=body.get("usage"), seconds=round(secs, 2))

    def chat_json_messages(self, messages: list[dict], schema: dict, *, reasoning_effort: str = "medium",
                           max_completion_tokens: int = 8000, retries: int = 2) -> MuseResult:
        if not self.config.configured:
            raise MuseNotConfigured("MODEL_API_KEY is not set (run setup_api_key.bat)")
        payload = {
            "model": self.config.model,
            "messages": messages,
            "response_format": {"type": "json_schema", "json_schema": schema},
            "reasoning_effort": reasoning_effort,
            "max_completion_tokens": max_completion_tokens,
        }
        body, secs = self._post_retry(payload, retries)
        try:
            content = body["choices"][0]["message"]["content"]
            finish = body["choices"][0].get("finish_reason")
        except (KeyError, IndexError, TypeError):
            raise MuseBadResponse(f"unexpected response shape: {str(body)[:300]}") from None
        if finish == "length":
            raise MuseTruncated(f"answer cut off at max_completion_tokens={max_completion_tokens} "
                                f"(usage {body.get('usage')})")
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            raise MuseBadResponse(f"model output is not valid JSON: {str(content)[:300]}") from None
        return MuseResult(data=data, model=body.get("model"), usage=body.get("usage"), seconds=round(secs, 2),
                          raw_content=content)
