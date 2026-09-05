"""Fail-closed Gemini transport using the official OpenAI Python SDK.

Only LLM_API_KEY, LLM_BASE_URL and LLM_MODEL supply provider configuration.
Credentials, prompts and raw responses never enter the transport's call ledger.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

try:
    from openai import DefaultHttpxClient, OpenAI
    from httpx2 import SyncByteStream
except ImportError:
    OpenAI = DefaultHttpxClient = None
    SyncByteStream = object

from .model import RuntimeModelError, _json_object


GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
MAX_REQUEST_BYTES = 512 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_OUTPUT_TOKENS = 16_384
TIMEOUT_SECONDS = 60
_STAGES = {
    "investigator", "contract_discovery", "relationship_discovery", "red_team",
    "repair", "red_team_after_repair", "unspecified",
}


class _BoundedStream(SyncByteStream):
    """Bound successful and error bodies before the SDK buffers either one."""

    def __init__(self, stream):
        self.stream = stream
        self.started = time.monotonic()

    def __iter__(self):
        total = 0
        for chunk in self.stream:
            if time.monotonic() - self.started >= TIMEOUT_SECONDS:
                raise RuntimeModelError("Gemini response exceeded the time limit.")
            total += len(chunk)
            if total > MAX_RESPONSE_BYTES:
                raise RuntimeModelError("Gemini response exceeds the byte limit.")
            yield chunk

    def close(self):
        self.stream.close()


def _bound_response(response) -> None:
    # Identity encoding keeps the byte bound meaningful after decoding, too.
    if response.headers.get("content-encoding", "identity").lower() not in {"", "identity"}:
        raise RuntimeModelError("Gemini returned an unsupported response encoding.")
    content_length = response.headers.get("content-length", "")
    if content_length.isdigit() and int(content_length) > MAX_RESPONSE_BYTES:
        raise RuntimeModelError("Gemini response exceeds the byte limit.")
    response.stream = _BoundedStream(response.stream)


@dataclass(repr=False)
class GeminiClient:
    model: str
    _sdk: Any = field(repr=False)
    _api_key: str = field(repr=False)
    stage: str = "unspecified"
    calls: list[dict[str, Any]] = field(default_factory=list)
    _calls_lock: Any = field(default_factory=threading.Lock, repr=False)

    def __repr__(self) -> str:
        return f"GeminiClient(model={self.model!r})"

    @property
    def name(self) -> str:
        return f"gemini/{self.model}"

    @classmethod
    def from_environment(cls) -> "GeminiClient":
        required = ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")
        missing = [name for name in required if not os.environ.get(name, "")]
        if missing:
            raise RuntimeModelError("Missing Gemini configuration: " + ", ".join(missing) + ".")
        api_key, base_url, model = (os.environ[name] for name in required)
        if base_url not in {GEMINI_BASE_URL, GEMINI_BASE_URL + "/"}:
            raise RuntimeModelError("LLM_BASE_URL must be the official Gemini OpenAI-compatible HTTPS endpoint.")
        if not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", model) or api_key in model:
            raise RuntimeModelError("Invalid configured Gemini model identifier.")
        if len(api_key) > 4096 or not api_key.isascii() or any(char.isspace() for char in api_key):
            raise RuntimeModelError("Invalid Gemini credential configuration.")
        if OpenAI is None or DefaultHttpxClient is None:
            raise RuntimeModelError("The required OpenAI Python SDK is unavailable.")
        http_client = None
        try:
            http_client = DefaultHttpxClient(
                follow_redirects=False,
                trust_env=False,
                event_hooks={"response": [_bound_response]},
            )
            sdk = OpenAI(
                api_key=api_key,
                base_url=base_url,
                max_retries=0,
                timeout=TIMEOUT_SECONDS,
                http_client=http_client,
                default_headers={"Accept-Encoding": "identity"},
            )
        except Exception:
            if http_client is not None:
                try:
                    http_client.close()
                except Exception:
                    pass
            raise RuntimeModelError("The Gemini SDK client could not be initialized.") from None
        return cls(model=model, _sdk=sdk, _api_key=api_key)

    def complete_json(self, system: str, payload: dict, *, stage: str | None = None) -> dict:
        """Make one SDK request. Every failure propagates; no retries or fallback."""
        if not isinstance(system, str) or not system.strip() or not isinstance(payload, dict):
            raise RuntimeModelError("Gemini input requires a system prompt and JSON object.")
        try:
            user_text = json.dumps(payload, ensure_ascii=True, allow_nan=False)
            body = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system + "\nReturn exactly one JSON object, without Markdown fences."},
                    {"role": "user", "content": user_text},
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": MAX_OUTPUT_TOKENS,
                "stream": False,
            }
            encoded = json.dumps(body, ensure_ascii=True, allow_nan=False).encode("utf-8")
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise RuntimeModelError("Gemini input is not valid JSON.") from None
        if len(encoded) > MAX_REQUEST_BYTES:
            raise RuntimeModelError("Gemini request exceeds the byte limit.")
        selected_stage = self.stage if stage is None else stage
        record: dict[str, Any] = {
            "stage": selected_stage if isinstance(selected_stage, str) and selected_stage in _STAGES else "unspecified",
            "provider": "gemini",
            "model": self.model,
            "response_id": None,
            "duration_ms": 0,
            "status": "error",
            "usage": {},
        }
        started = time.monotonic()
        try:
            try:
                response = self._sdk.chat.completions.create(**body)
            except Exception:
                # Even a wrapped SDK exception using our error type is untrusted.
                raise RuntimeModelError("Gemini SDK request failed; no provider details were retained.") from None
            record.update(self._safe_response_metadata(response))
            record["status"] = "invalid_response"
            content = self._content(response)
            result = _json_object(content)
            record["status"] = "success"
            return result
        except RuntimeModelError:
            raise
        except Exception:
            # SDK exceptions may include request headers, URLs or provider bodies.
            raise RuntimeModelError("Gemini SDK request failed; no provider details were retained.") from None
        finally:
            record["duration_ms"] = max(0, int((time.monotonic() - started) * 1000))
            with self._calls_lock:
                self.calls.append(record)

    def _content(self, response) -> str:
        try:
            if len(response.choices) != 1:
                raise ValueError
            choice = response.choices[0]
            message = choice.message
            if choice.finish_reason != "stop" or getattr(message, "refusal", None):
                raise ValueError
            if getattr(message, "tool_calls", None) or getattr(message, "function_call", None):
                raise ValueError
            content = message.content
            if not isinstance(content, str) or not content.strip():
                raise ValueError
            if len(content.encode("utf-8")) > MAX_RESPONSE_BYTES:
                raise RuntimeModelError("Gemini response exceeds the byte limit.")
            return content
        except RuntimeModelError:
            raise
        except (AttributeError, IndexError, TypeError, ValueError, UnicodeError):
            raise RuntimeModelError("Gemini returned an incomplete or unsupported response.") from None

    def _safe_response_metadata(self, response) -> dict[str, Any]:
        response_id = getattr(response, "id", None)
        if (
            not isinstance(response_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", response_id)
            or self._api_key in response_id
        ):
            response_id = None
        usage = getattr(response, "usage", None)
        safe_usage = {}
        for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = getattr(usage, name, None)
            if type(value) is int and 0 <= value <= 1_000_000_000:
                safe_usage[name] = value
        return {"response_id": response_id, "usage": safe_usage}

    def close(self) -> None:
        try:
            self._sdk.close()
        except Exception:
            raise RuntimeModelError("The Gemini SDK client could not be closed.") from None


def from_environment() -> GeminiClient:
    return GeminiClient.from_environment()
