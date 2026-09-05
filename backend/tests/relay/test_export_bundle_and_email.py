from __future__ import annotations

import json
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path

import pytest

from app.relay.email_delivery import (
    ConfirmationError,
    EmailDeliveryService,
    IdempotencyConflictError,
    ProviderAcceptance,
)
from app.relay.export_service import ExportService
from app.relay.snapshot_store import FrozenSnapshot


class RecordingTransport:
    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> ProviderAcceptance:
        self.messages.append(message)
        return ProviderAcceptance(
            provider_result="Mock provider accepted; delivery not asserted.",
            message_id=str(message["Message-ID"]),
        )


@pytest.fixture
def export_service(tmp_path: Path, export_schema_path: Path) -> ExportService:
    return ExportService(tmp_path / "relay-output", export_schema_path)


def test_one_frozen_snapshot_generates_complete_idempotent_bundle(
    export_service: ExportService,
    frozen_snapshot: FrozenSnapshot,
) -> None:
    first = export_service.generate_all(frozen_snapshot)
    second = export_service.generate_all(frozen_snapshot)

    assert first.generated_at == second.generated_at
    assert first.snapshot_sha256 == frozen_snapshot.snapshot_sha256
    assert {item.artifact_type for item in first.artifacts} == {"pdf", "xlsx", "json", "eml"}
    assert [(item.filename, item.sha256) for item in first.artifacts] == [
        (item.filename, item.sha256) for item in second.artifacts
    ]
    assert all(item.download_url.startswith(f"/api/runs/{first.run_id}/versions/{first.version}/") for item in first.artifacts)

    draft = BytesParser(policy=policy.default).parsebytes(first.artifact_path("eml").read_bytes())
    assert draft["To"] is None
    assert draft["X-CrazyMonkey-Status"] == "DRAFT_NOT_SENT"
    assert draft["X-CrazyMonkey-Run-ID"] == first.run_id
    assert draft["X-CrazyMonkey-Review-Version"] == str(first.version)
    assert str(draft["X-CrazyMonkey-Snapshot-SHA256"]).strip() == first.snapshot_sha256
    assert sorted(part.get_filename() for part in draft.iter_attachments()) == sorted(
        item.filename for item in first.artifacts if item.artifact_type in {"pdf", "xlsx", "json"}
    )


def test_email_send_requires_preview_confirmation_and_is_idempotent(
    tmp_path: Path,
    export_service: ExportService,
    frozen_snapshot: FrozenSnapshot,
) -> None:
    bundle = export_service.generate_all(frozen_snapshot)
    transport = RecordingTransport()
    delivery = EmailDeliveryService(
        transport=transport,
        from_address="ylookup@example.test",
        audit_log=tmp_path / "email-log.jsonl",
        secret=b"deterministic-test-secret-32-bytes!",
    )
    preview = delivery.preview(bundle, "reviewer@example.test")
    assert preview["status"] == "PREVIEW_NOT_SENT"
    assert preview["to"] == ["reviewer@example.test"]
    assert preview["snapshot_sha256"] == bundle.snapshot_sha256

    with pytest.raises(ConfirmationError):
        delivery.send(
            confirmation_token=preview["confirmation_token"],
            recipient="reviewer@example.test",
            idempotency_key="request-1",
            confirmed=False,
            action="SEND",
        )
    with pytest.raises(ConfirmationError):
        delivery.send(
            confirmation_token=preview["confirmation_token"],
            recipient="attacker@example.test",
            idempotency_key="request-1",
            confirmed=True,
            action="SEND",
        )

    accepted = delivery.send(
        confirmation_token=preview["confirmation_token"],
        recipient="reviewer@example.test",
        idempotency_key="request-1",
        confirmed=True,
        action="SEND",
    )
    replay = delivery.send(
        confirmation_token=preview["confirmation_token"],
        recipient="reviewer@example.test",
        idempotency_key="request-1",
        confirmed=True,
        action="SEND",
    )
    assert accepted == replay
    assert accepted["status"] == "ACCEPTED_BY_PROVIDER"
    assert "delivery not asserted" in accepted["provider_result"]
    assert len(transport.messages) == 1
    assert transport.messages[0]["To"] == "reviewer@example.test"
    audit_path = tmp_path / "email-log.jsonl"
    audit = json.loads(audit_path.read_text(encoding="utf-8").splitlines()[0])
    assert audit["status"] == "ACCEPTED_BY_PROVIDER"
    assert "delivery not asserted" in audit["provider_result"]
    assert {item["filename"] for item in audit["attachments"]} == {
        item.filename
        for item in bundle.artifacts
        if item.artifact_type in {"pdf", "xlsx", "json"}
    }

    other_preview = delivery.preview(bundle, "other-reviewer@example.test")
    with pytest.raises(IdempotencyConflictError):
        delivery.send(
            confirmation_token=other_preview["confirmation_token"],
            recipient="other-reviewer@example.test",
            idempotency_key="request-1",
            confirmed=True,
            action="SEND",
        )


def test_email_send_rejects_a_draft_changed_after_preview(
    tmp_path: Path,
    export_service: ExportService,
    frozen_snapshot: FrozenSnapshot,
) -> None:
    bundle = export_service.generate_all(frozen_snapshot)
    transport = RecordingTransport()
    delivery = EmailDeliveryService(
        transport=transport,
        from_address="ylookup@example.test",
        audit_log=tmp_path / "email-log.jsonl",
        secret=b"deterministic-test-secret-32-bytes!",
    )
    preview = delivery.preview(bundle, "reviewer@example.test")
    draft_path = bundle.artifact_path("eml")
    draft_path.write_bytes(draft_path.read_bytes() + b"\n")

    with pytest.raises(ConfirmationError, match="draft changed after preview"):
        delivery.send(
            confirmation_token=preview["confirmation_token"],
            recipient="reviewer@example.test",
            idempotency_key="mutated-draft-request",
            confirmed=True,
            action="SEND",
        )

    assert transport.messages == []


@pytest.mark.parametrize(
    "recipient",
    ["uploaded@example.test,other@example.test", "Name <name@example.test>", "bad\nBcc:x@y.test", "missing-at.example"],
)
def test_email_recipient_must_be_one_user_entered_address(
    tmp_path: Path,
    export_service: ExportService,
    frozen_snapshot: FrozenSnapshot,
    recipient: str,
) -> None:
    bundle = export_service.generate_all(frozen_snapshot)
    delivery = EmailDeliveryService(
        transport=RecordingTransport(),
        from_address="ylookup@example.test",
        audit_log=tmp_path / "email-log.jsonl",
        secret=b"deterministic-test-secret-32-bytes!",
    )
    with pytest.raises(ConfirmationError):
        delivery.preview(bundle, recipient)
