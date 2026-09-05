from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from .contracts import SnapshotContractError
from .email_delivery import (
    ConfirmationError,
    EmailDeliveryDisabledError,
    EmailDeliveryError,
    EmailDeliveryService,
    IdempotencyConflictError,
)
from .export_service import ExportError, ExportService, default_export_service
from .snapshot_store import SnapshotConflictError, SnapshotNotFoundError


router = APIRouter(prefix="/api", tags=["relay-outputs"])
service: ExportService = default_export_service()
delivery = EmailDeliveryService.from_environment(service.output_root / "email" / "send-log.jsonl")
fixture_path = Path(__file__).resolve().parents[2] / "fixtures" / "synthetic_review_snapshot.json"


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VersionRequest(StrictRequest):
    version: int = Field(ge=1)


class EmailPreviewRequest(VersionRequest):
    recipient: str = Field(min_length=3, max_length=254)


class EmailSendRequest(EmailPreviewRequest):
    confirmation_token: str = Field(min_length=20, max_length=4096)
    idempotency_key: str = Field(min_length=1, max_length=128)
    confirmed: bool
    action: Literal["SEND"]


@router.get("/relay/health")
def relay_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "component": "relay-outputs",
        "email_send_configured": delivery.configured,
        "email_default": "DRAFT_NOT_SENT",
    }


@router.post("/demo/load")
def load_synthetic_demo() -> dict[str, Any]:
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    try:
        frozen = service.snapshot_store.freeze(payload, route_run_id=payload["run_id"])
        bundle = service.generate_all(frozen)
    except Exception as exc:
        _raise_http(exc)
    return {
        "status": "SYNTHETIC_DEMO_READY",
        "mode": "SYNTHETIC_DEMO",
        "scope": "Management-fee checks only",
        **bundle.response(),
    }


@router.post("/runs/{run_id}/snapshots", status_code=201)
def freeze_snapshot(run_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        frozen = service.snapshot_store.freeze(payload, route_run_id=run_id)
    except Exception as exc:
        _raise_http(exc)
    return {
        "status": "SNAPSHOT_FROZEN",
        "run_id": frozen.snapshot.run_id,
        "version": frozen.snapshot.version,
        "snapshot_sha256": frozen.snapshot_sha256,
        "mode": frozen.snapshot.mode.value,
        "scope": frozen.snapshot.coverage.scope,
    }


@router.post("/runs/{run_id}/exports")
def create_exports(run_id: str, request: VersionRequest) -> dict[str, Any]:
    try:
        bundle = service.get_or_generate(run_id, request.version)
    except Exception as exc:
        _raise_http(exc)
    return {"status": "ARTIFACT_BUNDLE_COMPLETE", **bundle.response()}


@router.get("/runs/{run_id}/versions/{version}/exports/{artifact_type}")
def download_versioned_export(
    run_id: str,
    version: int,
    artifact_type: Literal["pdf", "xlsx", "excel", "json", "eml"],
    snapshot_sha256: str | None = Query(default=None, min_length=64, max_length=64),
) -> FileResponse:
    return _artifact_response(run_id, version, artifact_type, snapshot_sha256)


@router.get("/runs/{run_id}/exports/{artifact_type}")
def download_compatibility_export(
    run_id: str,
    artifact_type: Literal["pdf", "xlsx", "excel", "json", "eml"],
    version: int = Query(..., ge=1),
    snapshot_sha256: str | None = Query(default=None, min_length=64, max_length=64),
) -> FileResponse:
    """Compatibility route that still requires an explicit immutable version."""

    return _artifact_response(run_id, version, artifact_type, snapshot_sha256)


@router.get("/v1/reviews/{run_id}/exports/{artifact_type}")
def download_beacon_compatible_export(
    run_id: str,
    artifact_type: Literal["pdf", "excel", "json"],
) -> FileResponse:
    """Bridge Beacon's current download route to the latest frozen review version.

    The response exposes the resolved immutable version and hash in headers. New clients
    should retain and use the fully versioned `/api/runs/...` contract.
    """

    try:
        frozen = service.snapshot_store.get(run_id)
    except Exception as exc:
        _raise_http(exc)
    return _artifact_response(run_id, frozen.snapshot.version, artifact_type, None)


@router.post("/runs/{run_id}/email/draft")
def prepare_email_draft(run_id: str, request: VersionRequest) -> dict[str, Any]:
    try:
        bundle = service.get_or_generate(run_id, request.version)
        descriptor = bundle.artifact("eml")
    except Exception as exc:
        _raise_http(exc)
    return {
        **bundle.email_draft,
        "draft_artifact": {
            "filename": descriptor.filename,
            "sha256": descriptor.sha256,
            "download_url": descriptor.download_url,
        },
    }


@router.post("/v1/reviews/{run_id}/email/prepare")
def prepare_beacon_compatible_email_draft(run_id: str) -> dict[str, Any]:
    """Return Beacon's display-only draft shape without inventing a recipient."""

    try:
        frozen = service.snapshot_store.get(run_id)
        bundle = service.generate_all(frozen)
    except Exception as exc:
        _raise_http(exc)
    return {
        "id": f"{bundle.run_id}:v{bundle.version}:{bundle.snapshot_sha256}:draft",
        "status": "DRAFT",
        "recipient": "",
        "subject": bundle.email_draft["subject"],
        "body": bundle.email_draft["body"],
        "attachments": bundle.email_draft["attachments"],
        "review_version": bundle.version,
        "snapshot_sha256": bundle.snapshot_sha256,
        "send_available": False,
        "send_instructions": (
            "Enter a recipient through the versioned preview endpoint, then use the signed "
            "explicit-confirmation send contract."
        ),
    }


@router.post("/v1/reviews/{run_id}/email/send")
def reject_beacon_legacy_email_send(run_id: str) -> None:
    del run_id
    raise HTTPException(
        status_code=422,
        detail=(
            "This legacy request does not carry a user-entered recipient, immutable review "
            "version, signed preview token, or idempotency key. Use /api/runs/{run_id}/email/"
            "preview followed by /api/runs/{run_id}/email/send."
        ),
    )


@router.post("/runs/{run_id}/email/preview")
def preview_email(run_id: str, request: EmailPreviewRequest) -> dict[str, Any]:
    try:
        bundle = service.get_or_generate(run_id, request.version)
        return delivery.preview(bundle, request.recipient)
    except Exception as exc:
        _raise_http(exc)


@router.post("/runs/{run_id}/email/send")
def send_email(run_id: str, request: EmailSendRequest) -> dict[str, Any]:
    """Deliberate human-confirmed boundary; no model tool calls this route."""

    try:
        frozen = service.snapshot_store.get(run_id, request.version)
        claims = delivery.verify_confirmation_token(request.confirmation_token)
        if (
            claims.get("run_id") != frozen.snapshot.run_id
            or claims.get("version") != frozen.snapshot.version
            or claims.get("snapshot_sha256") != frozen.snapshot_sha256
        ):
            raise ConfirmationError("confirmation token does not match the requested snapshot")
        return delivery.send(
            confirmation_token=request.confirmation_token,
            recipient=request.recipient,
            idempotency_key=request.idempotency_key,
            confirmed=request.confirmed,
            action=request.action,
        )
    except Exception as exc:
        _raise_http(exc)


def _artifact_response(
    run_id: str,
    version: int,
    artifact_type: str,
    expected_sha256: str | None,
) -> FileResponse:
    try:
        bundle = service.get_or_generate(run_id, version)
        if expected_sha256 and bundle.snapshot_sha256 != expected_sha256:
            raise SnapshotConflictError("requested snapshot hash does not match the frozen version")
        artifact = bundle.artifact(artifact_type)
        path = bundle.directory / artifact.filename
    except Exception as exc:
        _raise_http(exc)
    return FileResponse(
        path,
        media_type=artifact.content_type,
        filename=artifact.filename,
        headers={
            "ETag": f'"{artifact.sha256}"',
            "X-Review-Version": str(bundle.version),
            "X-Snapshot-SHA256": bundle.snapshot_sha256,
            "Cache-Control": "private, immutable",
        },
    )


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, SnapshotNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, (SnapshotConflictError, IdempotencyConflictError)):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, (SnapshotContractError, ConfirmationError)):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if isinstance(exc, EmailDeliveryDisabledError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, (EmailDeliveryError, ExportError)):
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    raise exc
