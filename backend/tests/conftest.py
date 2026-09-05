"""Repository-wide safety boundaries for backend tests.

The test suite may exercise RELAY's draft, preview, confirmation, and mocked
transport behavior, but it must never construct a real SMTP client.  Clear any
developer-machine email configuration before application modules are imported,
then install a fail-closed guard for both SMTP connection classes.
"""

from __future__ import annotations

import os
import smtplib
from typing import NoReturn

import pytest


_EMAIL_ENVIRONMENT_VARIABLES = (
    "CRAZYMONKEY_ENABLE_EMAIL_SEND",
    "CRAZYMONKEY_CONFIRMATION_SECRET",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "SMTP_STARTTLS",
)


def _clear_email_environment() -> None:
    for name in _EMAIL_ENVIRONMENT_VARIABLES:
        os.environ.pop(name, None)


def _block_smtp_construction(*args: object, **kwargs: object) -> NoReturn:
    del args, kwargs
    raise AssertionError("Backend tests must never construct a real SMTP client")


# Root conftest modules load before test-module collection.  Applying both
# protections here therefore also covers application objects constructed at
# import time.
_clear_email_environment()
smtplib.SMTP = _block_smtp_construction  # type: ignore[misc,assignment]
smtplib.SMTP_SSL = _block_smtp_construction  # type: ignore[misc,assignment]


@pytest.fixture(autouse=True)
def _no_network_email(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reassert the no-email invariant before every backend test."""

    for name in _EMAIL_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(smtplib, "SMTP", _block_smtp_construction)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _block_smtp_construction)
