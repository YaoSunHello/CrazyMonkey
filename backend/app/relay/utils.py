from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


_CURRENCY_SYMBOLS = {"GBP": "£", "USD": "$", "EUR": "€"}
_DANGEROUS_SPREADSHEET_PREFIXES = ("=", "+", "-", "@")
_MAX_SAFE_JSON_INTEGER = Decimal("9007199254740991")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def decimal_text(value: Decimal) -> str:
    return format(value, "f")


def decimal_json_value(value: Decimal | None) -> int | str | None:
    """Use a JSON integer only when JavaScript can represent it exactly."""

    if value is None:
        return None
    if value == value.to_integral_value() and abs(value) <= _MAX_SAFE_JSON_INTEGER:
        return int(value)
    return decimal_text(value)


def spreadsheet_number(value: Decimal | None) -> float | None:
    """Return a spreadsheet number only when its decimal text round-trips exactly."""

    if value is None:
        return None
    converted = float(value)
    if Decimal(str(converted)) != value:
        return None
    return converted


def money_text(value: Decimal | None, currency: str = "GBP") -> str:
    if value is None:
        return "Not available"
    symbol = _CURRENCY_SYMBOLS.get(currency.upper(), f"{currency.upper()} ")
    sign = "-" if value < 0 else ""
    return f"{sign}{symbol}{abs(value):,.2f}"


def rate_text(value: Decimal | None) -> str:
    if value is None:
        return "Not established"
    return f"{value:.2%}"


def mode_label(value: str) -> str:
    return "Synthetic Demo" if value == "SYNTHETIC_DEMO" else "Live"


def period_slug(period: str) -> str:
    match = re.search(r"\bQ([1-4])\s+(20\d{2})\b", period, flags=re.IGNORECASE)
    if match:
        return f"Q{match.group(1)}_{match.group(2)}"
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", period).strip("_")
    return (cleaned or "Reporting_Period")[:80]


def spreadsheet_literal(value: Any) -> str:
    """Return untrusted text that cannot be interpreted as an Excel formula.

    Numeric values should bypass this function and be written with numeric writers.
    """

    text = "" if value is None else str(value)
    inspected = text.lstrip(" \t\r\n\ufeff")
    if inspected.startswith(_DANGEROUS_SPREADSHEET_PREFIXES):
        return "'" + text
    return text


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bounded_text(value: str | None, limit: int = 20_000) -> str:
    text = "" if value is None else str(value)
    if len(text) <= limit:
        return text
    return text[: limit - 15] + " [truncated]"


def bounded_optional(value: str | None, limit: int = 20_000) -> str | None:
    if value is None:
        return None
    return bounded_text(value, limit)
