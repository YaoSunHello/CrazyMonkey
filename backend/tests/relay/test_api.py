from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.relay import api as relay_api
from app.relay.email_delivery import EmailDeliveryService
from app.relay.export_service import ExportService


def _isolated_client(
    monkeypatch,
    tmp_path: Path,
    export_schema_path: Path,
) -> TestClient:
    service = ExportService(tmp_path / "relay-output", export_schema_path)
    delivery = EmailDeliveryService(
        transport=None,
        from_address=None,
        audit_log=tmp_path / "email-send-log.jsonl",
        secret=b"api-test-secret-with-at-least-32-bytes",
    )
    monkeypatch.setattr(relay_api, "service", service)
    monkeypatch.setattr(relay_api, "delivery", delivery)
    return TestClient(app)


def test_real_app_mounts_relay_and_serves_versioned_and_beacon_exports(
    monkeypatch,
    tmp_path: Path,
    export_schema_path: Path,
) -> None:
    client = _isolated_client(monkeypatch, tmp_path, export_schema_path)

    health = client.get("/api/relay/health")
    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "component": "relay-outputs",
        "email_send_configured": False,
        "email_default": "DRAFT_NOT_SENT",
    }

    demo = client.post("/api/demo/load")
    assert demo.status_code == 200
    payload = demo.json()
    run_id = payload["run_id"]
    version = payload["version"]
    digest = payload["snapshot_sha256"]

    pdf = client.get(
        f"/api/runs/{run_id}/versions/{version}/exports/pdf",
        params={"snapshot_sha256": digest},
    )
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["x-review-version"] == str(version)
    assert pdf.headers["x-snapshot-sha256"] == digest
    assert pdf.headers["etag"].strip('"')

    excel = client.get(f"/api/v1/reviews/{run_id}/exports/excel")
    assert excel.status_code == 200
    assert excel.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert excel.headers["x-review-version"] == str(version)
    assert excel.headers["x-snapshot-sha256"] == digest

    draft = client.post(f"/api/v1/reviews/{run_id}/email/prepare")
    assert draft.status_code == 200
    assert draft.json()["status"] == "DRAFT"
    assert draft.json()["recipient"] == ""
    assert draft.json()["send_available"] is False
    assert len(draft.json()["attachments"]) == 3

    legacy_send = client.post(
        f"/api/v1/reviews/{run_id}/email/send",
        json={"draftId": draft.json()["id"], "confirmed": True},
    )
    assert legacy_send.status_code == 422
    assert "user-entered recipient" in legacy_send.json()["detail"]


def test_route_errors_preserve_frozen_snapshot_identity(
    monkeypatch,
    tmp_path: Path,
    export_schema_path: Path,
    fixture_payload: dict[str, object],
) -> None:
    client = _isolated_client(monkeypatch, tmp_path, export_schema_path)
    run_id = str(fixture_payload["run_id"])

    mismatch = client.post(f"/api/runs/not-{run_id}/snapshots", json=fixture_payload)
    assert mismatch.status_code == 422
    assert "run_id mismatch" in mismatch.json()["detail"]

    frozen = client.post(f"/api/runs/{run_id}/snapshots", json=fixture_payload)
    assert frozen.status_code == 201
    digest = frozen.json()["snapshot_sha256"]

    repeated = client.post(f"/api/runs/{run_id}/snapshots", json=fixture_payload)
    assert repeated.status_code == 201
    assert repeated.json()["snapshot_sha256"] == digest

    wrong_hash = client.get(
        f"/api/runs/{run_id}/versions/1/exports/json",
        params={"snapshot_sha256": "0" * 64},
    )
    assert wrong_hash.status_code == 409

    missing = client.post("/api/runs/no-such-run/exports", json={"version": 1})
    assert missing.status_code == 404

    extra_field = client.post(
        f"/api/runs/{run_id}/exports",
        json={"version": 1, "unexpected": True},
    )
    assert extra_field.status_code == 422
