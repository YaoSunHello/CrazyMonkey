"""Disabled delivery must not make local review/export startup depend on SMTP."""

import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

from app.relay.email_delivery import EmailDeliveryService, SMTPTransport


@pytest.mark.parametrize("flag", ["", "false", "0", "no"])
def test_disabled_email_ignores_malformed_smtp_settings(tmp_path: Path, flag: str) -> None:
    settings = {
        "CRAZYMONKEY_ENABLE_EMAIL_SEND": flag,
        "SMTP_HOST": "smtp.example.test",
        "SMTP_PORT": "not-a-port",
        "SMTP_USERNAME": "synthetic-user",
        "SMTP_PASSWORD": "synthetic-test-only",
        "SMTP_FROM": "sender@example.test",
    }
    with patch.dict(os.environ, settings), patch.object(
        SMTPTransport, "send", side_effect=AssertionError("must not contact SMTP")
    ) as send:
        delivery = EmailDeliveryService.from_environment(tmp_path / "audit.jsonl")
        assert not delivery.configured
        assert delivery.transport is None
        assert delivery.from_address is None
        send.assert_not_called()
    assert not (tmp_path / "audit.jsonl").exists()


def test_actual_app_import_and_health_survive_disabled_invalid_smtp(tmp_path: Path) -> None:
    environment = dict(os.environ)
    environment.update({
        "PYTHONDONTWRITEBYTECODE": "1",
        "CRAZYMONKEY_ENABLE_EMAIL_SEND": "false",
        "CRAZYMONKEY_RELAY_OUTPUT_DIR": str(tmp_path / "relay"),
        "SMTP_HOST": "smtp.example.test",
        "SMTP_PORT": "not-a-port",
        "SMTP_USERNAME": "synthetic-user",
        "SMTP_PASSWORD": "synthetic-test-only",
        "SMTP_FROM": "sender@example.test",
    })
    environment["PYTHONPATH"] = os.pathsep.join(str(path) for path in sys.path if path)
    script = """
import json
from unittest.mock import patch
with patch('smtplib.SMTP', side_effect=AssertionError('SMTP forbidden')), \\
     patch('smtplib.SMTP_SSL', side_effect=AssertionError('SMTP forbidden')):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        response = client.get('/api/relay/health')
        assert response.status_code == 200
        print(json.dumps(response.json()))
"""
    result = subprocess.run([sys.executable, "-c", script], env=environment,
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["email_send_configured"] is False
