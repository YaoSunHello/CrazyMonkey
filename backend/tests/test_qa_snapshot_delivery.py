"""Draft preparation must retain the exact version displayed for review."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.relay import api as relay_api
from app.relay.export_service import ExportService


def test_email_draft_uses_requested_immutable_version_and_rejects_missing_version(
    tmp_path, monkeypatch,
) -> None:
    backend = Path(__file__).resolve().parents[1]
    service = ExportService(tmp_path / "exports", backend / "app/schemas/review_export.schema.json")
    monkeypatch.setattr(relay_api, "service", service)
    # Draft generation must never invoke any configured delivery service.
    class ForbiddenDelivery:
        def __getattr__(self, name):
            raise AssertionError(f"Draft preparation used delivery: {name}")
    monkeypatch.setattr(relay_api, "delivery", ForbiddenDelivery())
    payload = json.loads((backend / "fixtures/synthetic_review_snapshot.json").read_text())
    first = service.snapshot_store.freeze(payload)
    payload["version"] = 2
    for event in payload["audit_trail"]:
        event["run_version"] = 2
    payload["fund_name"] = "Synthetic version two"
    second = service.snapshot_store.freeze(payload)
    route = f"/api/v1/reviews/{first.snapshot.run_id}/email/prepare"
    with TestClient(app) as client:
        response = client.post(route, params={"version": 1})
        assert response.status_code == 200
        draft = response.json()
        assert draft["review_version"] == 1
        assert draft["snapshot_sha256"] == first.snapshot_sha256
        assert draft["recipient"] == ""
        assert draft["send_available"] is False
        assert len(draft["attachments"]) == 3
        assert client.post(route, params={"version": 999}).status_code == 404
        assert client.post(route, params={"version": 0}).status_code == 422
        # Keep legacy callers compatible while BEACON binds its explicit version.
        latest = client.post(route).json()
        assert latest["review_version"] == 2
        assert latest["snapshot_sha256"] == second.snapshot_sha256
