"""Explicit, bounded loading of this checkout's ignored local API configuration.

Loading changes process memory only. Values are never interpolated, evaluated,
printed or persisted, and existing process variables (including empty ones)
always retain their exact values.
"""
from __future__ import annotations

import io
import os
from pathlib import Path
import re
from typing import MutableMapping


GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
MAX_ENV_BYTES = 64 * 1024
_NAMES = (
    "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL",
    "API_KEY_AI", "API_KEY_OPENAI", "API_URL_OPENAI",
)
_KEY_NAMES = ("LLM_API_KEY", "API_KEY_AI", "API_KEY_OPENAI")
_GEMINI_MODEL = re.compile(r"(?:models/)?gemini-[A-Za-z0-9_.:/-]{1,110}\Z")


class LocalConfigError(RuntimeError):
    """Sanitized local configuration failure without source values or paths."""


def _gemini_model(environ: MutableMapping[str, str]) -> str | None:
    model = environ.get("LLM_MODEL", "")
    if not isinstance(model, str) or not _GEMINI_MODEL.fullmatch(model):
        return None
    if any(environ.get(name) and environ[name] in model for name in _KEY_NAMES):
        return None
    return model


def config_status(environ: MutableMapping[str, str] | None = None) -> dict:
    """Return only presence flags and a validated Gemini model identifier."""
    target = os.environ if environ is None else environ
    model = _gemini_model(target)
    key = target.get("LLM_API_KEY", "")
    valid_key = bool(key and len(key) <= 4096 and key.isascii() and not any(char.isspace() for char in key))
    endpoint = target.get("LLM_BASE_URL", "") in {GEMINI_BASE_URL, GEMINI_BASE_URL.rstrip("/")}
    return {
        "present": {name: bool(target.get(name, "")) for name in _NAMES},
        "provider": "gemini" if model else None,
        "model": model,
        "gemini_endpoint": endpoint,
        "ready": bool(model and valid_key and endpoint),
    }


def _read_local_env(path: Path) -> dict[str, str]:
    try:
        # An explicitly supplied file is required; no upward directory search.
        if path.is_symlink():
            raise LocalConfigError("Local API configuration must be a regular file.")
        with path.open("rb") as handle:
            raw = handle.read(MAX_ENV_BYTES + 1)
        if len(raw) > MAX_ENV_BYTES:
            raise LocalConfigError("Local API configuration exceeds the byte limit.")
        text = raw.decode("utf-8-sig")
    except LocalConfigError:
        raise
    except (OSError, UnicodeError):
        raise LocalConfigError("Local API configuration could not be read.") from None
    try:
        from dotenv.parser import parse_stream
    except ImportError:
        raise LocalConfigError("The local API configuration dependency is unavailable.") from None
    try:
        values = {}
        # parse_stream handles dotenv quoting/comments but neither interpolation
        # nor environment mutation, and emits no malformed-line warnings.
        for binding in parse_stream(io.StringIO(text)):
            if binding.error:
                raise LocalConfigError("Local API configuration contains an invalid entry.")
            if binding.key in _NAMES and binding.value is not None:
                values[binding.key] = binding.value
        return values
    except LocalConfigError:
        raise
    except Exception:
        raise LocalConfigError("Local API configuration could not be parsed.") from None


def load_local_config(env_file: Path | None = None, *, environ: MutableMapping[str, str] | None = None) -> dict:
    """Load supported local names, map the Gemini alias, and return safe status.

    Explicit LLM_API_KEY and LLM_BASE_URL are never replaced. API_KEY_AI is a
    Gemini-only alias. API_URL_OPENAI and API_KEY_OPENAI are never used to route
    or authenticate a Gemini request.
    """
    target = os.environ if environ is None else environ
    path = Path(env_file) if env_file is not None else Path(__file__).resolve().parents[2] / ".env"
    exists = path.exists() or path.is_symlink()
    values = _read_local_env(path) if exists else {}
    for name, value in values.items():
        if name not in target:
            target[name] = value
    if _gemini_model(target):
        if "LLM_API_KEY" not in target and target.get("API_KEY_AI"):
            target["LLM_API_KEY"] = target["API_KEY_AI"]
        if "LLM_BASE_URL" not in target:
            target["LLM_BASE_URL"] = GEMINI_BASE_URL
    return {**config_status(target), "local_env_loaded": exists}
