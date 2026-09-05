"""Small, bounded model transport. Returned JSON still requires plan validation.

Only the named provider's official HTTPS endpoint is used. Configuration comes
from process environment; this module does not load, write, or log credentials.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


MAX_REQUEST_BYTES = 512 * 1024
MAX_RESPONSE_BYTES = 512 * 1024
MAX_OUTPUT_TOKENS = 4096
TIMEOUT_SECONDS = 30


class RuntimeModelError(RuntimeError):
    """A sanitized transport, configuration, or JSON-validation failure."""


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward authorization or financial context to another location.
        raise RuntimeModelError("Model provider returned an unexpected redirect.")


def urlopen(request: Request, *, timeout: float):
    """Local seam for tests; avoid urllib's global opener and redirects."""
    return build_opener(_RejectRedirects()).open(request, timeout=timeout)


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError("Non-finite JSON number")


def _finite_float(value):
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("Non-finite JSON number")
    return parsed


def _json_object(raw: str | bytes) -> dict[str, Any]:
    try:
        result = json.loads(
            raw,
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise RuntimeModelError("Model provider returned invalid JSON.") from None
    if not isinstance(result, dict):
        raise RuntimeModelError("Model provider must return a JSON object.")
    return result


@dataclass(frozen=True)
class RuntimeModel:
    provider: str
    model: str
    api_key: str = field(repr=False)

    def __post_init__(self) -> None:
        if self.provider not in {"openai", "anthropic"}:
            raise RuntimeModelError("Unsupported model provider.")
        if not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", self.model):
            raise RuntimeModelError("Invalid configured model identifier.")
        if not self.api_key or any(char.isspace() for char in self.api_key):
            raise RuntimeModelError("Invalid model credential configuration.")

    @property
    def name(self) -> str:
        return f"{self.provider}/{self.model}"

    def complete_json(self, system: str, payload: dict) -> dict:
        """Request one JSON object; never execute or trust model-provided code.

        Each socket operation has a 30-second timeout. Chunked reads also check
        the elapsed deadline so a slowly trickled body cannot run indefinitely.
        No automatic retries, fallback providers, or source-content logging.
        """
        if not isinstance(system, str) or not system.strip() or not isinstance(payload, dict):
            raise RuntimeModelError("Model input requires a system prompt and JSON object.")
        try:
            user_text = json.dumps(payload, ensure_ascii=True, allow_nan=False)
            prompt = system + "\nReturn exactly one JSON object, without Markdown fences."
            messages = [{"role": "user", "content": user_text}]
            body: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "stream": False,
            }
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            if self.provider == "openai":
                endpoint = "https://api.openai.com/v1/chat/completions"
                headers["Authorization"] = "Bearer " + self.api_key
                body.update(
                    messages=[{"role": "system", "content": prompt}, *messages],
                    response_format={"type": "json_object"},
                    max_completion_tokens=MAX_OUTPUT_TOKENS,
                    store=False,
                )
            else:
                endpoint = "https://api.anthropic.com/v1/messages"
                headers.update({"x-api-key": self.api_key, "anthropic-version": "2023-06-01"})
                body.update(system=prompt, max_tokens=MAX_OUTPUT_TOKENS)
            encoded = json.dumps(body, ensure_ascii=True, allow_nan=False).encode("utf-8")
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise RuntimeModelError("Model input is not valid JSON.") from None
        if len(encoded) > MAX_REQUEST_BYTES:
            raise RuntimeModelError("Model request exceeds the byte limit.")
        request = Request(endpoint, data=encoded, headers=headers, method="POST")
        started = time.monotonic()
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                if response.status != 200:
                    raise RuntimeModelError("Model provider returned an unsuccessful response.")
                raw = bytearray()
                while True:
                    if time.monotonic() - started >= TIMEOUT_SECONDS:
                        raise RuntimeModelError("Model provider exceeded the response deadline.")
                    chunk = response.read1(min(65536, MAX_RESPONSE_BYTES + 1 - len(raw)))
                    if not chunk:
                        break
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise RuntimeModelError("Model response exceeds the byte limit.")
        except HTTPError as error:
            # Do not read the provider's body: it can contain source text or keys.
            error.close()
            raise RuntimeModelError(f"Model provider request failed (HTTP {error.code}).") from None
        except (URLError, OSError, ValueError):
            raise RuntimeModelError("Model provider connection failed or timed out.") from None
        envelope = _json_object(bytes(raw))
        content = self._content(envelope)
        return _json_object(content)

    def _content(self, envelope: dict) -> str:
        try:
            if self.provider == "openai":
                choices = envelope["choices"]
                if not isinstance(choices, list) or len(choices) != 1:
                    raise ValueError
                choice = choices[0]
                message = choice["message"]
                if choice["finish_reason"] != "stop" or message.get("refusal"):
                    raise ValueError
                if message.get("tool_calls") or message.get("function_call"):
                    raise ValueError
                content = message["content"]
            else:
                if envelope["stop_reason"] != "end_turn":
                    raise ValueError
                blocks = envelope["content"]
                if not isinstance(blocks, list) or not blocks:
                    raise ValueError
                texts = []
                for block in blocks:
                    if block["type"] != "text" or not isinstance(block["text"], str):
                        raise ValueError
                    texts.append(block["text"])
                content = "".join(texts)
            if not isinstance(content, str) or not content.strip():
                raise ValueError
            return content
        except (KeyError, IndexError, TypeError, AttributeError, ValueError):
            raise RuntimeModelError("Model provider returned an incomplete or unsupported response.") from None


def from_environment() -> RuntimeModel | None:
    """Prefer OpenAI, then Anthropic; return None when neither is configured.

    Set OPENAI_MODEL or ANTHROPIC_MODEL to override the documented defaults.
    OPENAI_BASE_URL is deliberately unsupported: credentials and document data
    are sent only to the official fixed endpoints above.
    """
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if openai_key:
        base = os.environ.get("OPENAI_BASE_URL", "").strip().rstrip("/")
        if base and base != "https://api.openai.com/v1":
            raise RuntimeModelError("Custom OPENAI_BASE_URL is not supported by this runtime.")
        model = os.environ.get("OPENAI_MODEL", "").strip() or "gpt-4.1-mini"
        return RuntimeModel("openai", model, openai_key)
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if anthropic_key:
        model = os.environ.get("ANTHROPIC_MODEL", "").strip() or "claude-haiku-4-5-20251001"
        return RuntimeModel("anthropic", model, anthropic_key)
    return None
