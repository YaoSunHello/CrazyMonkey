"""Regression checks for RELAY's input normalization boundary and Beacon modes."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.relay.contracts import SnapshotContractError, adapt_review_snapshot


BACKEND = Path(__file__).resolve().parents[1]


def _canonical_payload() -> dict:
    return json.loads((BACKEND / "fixtures/synthetic_review_snapshot.json").read_text())


def _beacon_payload() -> dict:
    """Minimal valid current Beacon ReviewResult shape; no runtime claims."""
    canonical = _canonical_payload()
    finding = canonical["findings"][0]
    return {
        "id": canonical["run_id"],
        "version": canonical["version"],
        "mode": "SYNTHETIC_DEMO",
        "source": "DEVELOPMENT_FIXTURE",
        "fundName": canonical["fund_name"],
        "periodLabel": canonical["reporting_period"],
        "createdAt": canonical["timestamp"],
        "documents": [],
        "findings": [{
            "id": finding["finding_id"],
            "investorId": finding["investor_id"],
            "checkName": finding["check_type"],
            "status": finding["computational_status"],
            "administratorValue": {"amount": finding["administrator_value"], "currency": "GBP"},
            "expectedValue": {"amount": finding["expected_value"], "currency": "GBP"},
            "difference": {"amount": finding["difference"], "currency": "GBP"},
            "explanation": finding["explanation"],
            "evidence": [],
            "notes": [],
        }],
    }


def _post_snapshot_in_isolated_app(payload: dict, output_dir: Path) -> dict:
    # Fresh process per request prevents module-level services leaking between tests.
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(BACKEND),
        "PYTHONDONTWRITEBYTECODE": "1",
        "CRAZYMONKEY_ENABLE_EMAIL_SEND": "false",
        "CRAZYMONKEY_RELAY_OUTPUT_DIR": str(output_dir),
    })
    for key in ("SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM"):
        env.pop(key, None)
    code = '''
import json, sys
from app.relay.email_delivery import SMTPTransport

def forbid_send(*args, **kwargs):
    raise AssertionError("SMTP network sending is prohibited in QA")
SMTPTransport.send = forbid_send
from app.main import app
from fastapi.testclient import TestClient
payload = json.load(sys.stdin)
with TestClient(app, raise_server_exceptions=False) as client:
    response = client.post("/api/runs/review-demo-q3-2026/snapshots", json=payload)
body = response.json() if "application/json" in response.headers.get("content-type", "") else response.text
print(json.dumps({"status": response.status_code, "body": body}))
'''
    completed = subprocess.run(
        [sys.executable, "-c", code], input=json.dumps(payload), text=True,
        capture_output=True, env=env, cwd=BACKEND, check=False, timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.mark.parametrize("case", ["null_findings", "invalid_version", "missing_finding_id"])
def test_malformed_snapshot_api_returns_controlled_422(case: str, tmp_path: Path) -> None:
    if case == "null_findings":
        payload = _canonical_payload()
        payload["findings"] = None
    else:
        payload = _beacon_payload()
        if case == "invalid_version":
            payload["version"] = "oops"
        else:
            payload["findings"] = [{}]
    result = _post_snapshot_in_isolated_app(payload, tmp_path / "outputs")
    assert result["status"] == 422
    assert "malformed review snapshot" in result["body"]["detail"]
    assert not list(tmp_path.rglob("snapshot.json"))


@pytest.mark.parametrize("mode", ["LIVE_OFFLINE", "LIVE_MODEL"])
@pytest.mark.parametrize("notice", [None, "Upstream source notice retained."])
def test_beacon_live_modes_preserve_upstream_provenance(mode: str, notice: str | None) -> None:
    payload = _beacon_payload()
    payload.update(mode=mode, source="ATLAS")
    if notice is not None:
        payload["sourceNotice"] = notice
    snapshot = adapt_review_snapshot(payload)
    assert snapshot.mode.value == "LIVE"
    assert snapshot.source == "ATLAS"
    assert snapshot.source_notice == (
        f"{notice} Upstream Beacon mode: {mode}." if notice else f"Upstream Beacon mode: {mode}."
    )
    assert snapshot.findings[0].administrator_value == payload["findings"][0]["administratorValue"]["amount"]
    assert snapshot.version == payload["version"]


def test_development_fixture_cannot_be_promoted_to_live_by_mode_field() -> None:
    payload = _beacon_payload()
    payload.update(mode="LIVE_MODEL", sourceNotice="Explicit development fixture.")
    snapshot = adapt_review_snapshot(payload)
    assert snapshot.mode.value == "SYNTHETIC_DEMO"
    assert snapshot.source_notice == "Explicit development fixture."


def test_unknown_beacon_mode_is_still_rejected() -> None:
    payload = _beacon_payload()
    payload.update(mode="UNKNOWN", source="ATLAS")
    with pytest.raises(SnapshotContractError, match="mode"):
        adapt_review_snapshot(payload)


def test_existing_unsupported_contract_error_is_preserved() -> None:
    with pytest.raises(SnapshotContractError, match="^unsupported snapshot schema_version"):
        adapt_review_snapshot({"schema_version": "crazymonkey.pipeline-review.v1"})
