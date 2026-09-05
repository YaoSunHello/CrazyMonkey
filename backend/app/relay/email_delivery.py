from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import smtplib
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import formatdate, make_msgid, parseaddr
from pathlib import Path
from typing import Any, Protocol, TYPE_CHECKING

from .snapshot_store import FrozenSnapshot
from .utils import file_sha256, iso_z

if TYPE_CHECKING:
    from .export_service import ExportBundle


class EmailDeliveryError(RuntimeError):
    pass


class EmailDeliveryDisabledError(EmailDeliveryError):
    pass


class ConfirmationError(EmailDeliveryError):
    pass


class IdempotencyConflictError(EmailDeliveryError):
    pass


@dataclass(frozen=True)
class ProviderAcceptance:
    provider_result: str
    message_id: str


class EmailTransport(Protocol):
    def send(self, message: EmailMessage) -> ProviderAcceptance: ...


@dataclass(frozen=True)
class SMTPSettings:
    host: str
    port: int
    username: str
    password: str
    from_address: str
    starttls: bool = True

    @classmethod
    def from_environment(cls) -> "SMTPSettings | None":
        values = {
            "host": os.getenv("SMTP_HOST", "").strip(),
            "port": os.getenv("SMTP_PORT", "").strip(),
            "username": os.getenv("SMTP_USERNAME", "").strip(),
            "password": os.getenv("SMTP_PASSWORD", "").strip(),
            "from_address": os.getenv("SMTP_FROM", "").strip(),
        }
        if not all(values.values()):
            return None
        return cls(
            host=values["host"],
            port=int(values["port"]),
            username=values["username"],
            password=values["password"],
            from_address=values["from_address"],
            starttls=os.getenv("SMTP_STARTTLS", "true").lower() not in {"0", "false", "no"},
        )


class SMTPTransport:
    def __init__(self, settings: SMTPSettings):
        self.settings = settings

    def send(self, message: EmailMessage) -> ProviderAcceptance:
        connection_class = smtplib.SMTP_SSL if self.settings.port == 465 else smtplib.SMTP
        with connection_class(self.settings.host, self.settings.port, timeout=20) as client:
            if self.settings.starttls and self.settings.port != 465:
                client.starttls()
            client.login(self.settings.username, self.settings.password)
            refused = client.send_message(message)
        if refused:
            raise EmailDeliveryError(f"provider refused one or more recipients: {sorted(refused)}")
        return ProviderAcceptance(
            provider_result="SMTP accepted the message for transport; inbox delivery is not confirmed.",
            message_id=str(message["Message-ID"]),
        )


def draft_subject(snapshot) -> str:  # type: ignore[no-untyped-def]
    counts = snapshot.summary_counts()
    discrepancy_word = "discrepancy" if counts["discrepancies"] == 1 else "discrepancies"
    return (
        f"CrazyMonkey NAV Review - {snapshot.reporting_period} - "
        f"{counts['discrepancies']} {discrepancy_word} require review"
    )


def draft_body(snapshot) -> str:  # type: ignore[no-untyped-def]
    counts = snapshot.summary_counts()
    return (
        "Hi,\n\n"
        f"CrazyMonkey completed the management-fee review for {snapshot.reporting_period}.\n\n"
        f"{counts['checks_completed']} checks completed:\n"
        f"- {counts['matches']} matched\n"
        f"- {counts['discrepancies']} discrepancies\n"
        f"- {counts['cannot_verify']} could not be verified\n"
        f"- {counts['unsupported']} unsupported\n\n"
        "The attached PDF, Excel and JSON reports contain the calculations and source "
        "references used for each finding.\n\n"
        "This review remains subject to human review and does not constitute legal or "
        "regulatory sign-off.\n\n"
        "Regards,\nCrazyMonkey\n"
    )


def write_eml_draft(
    path: Path,
    frozen: FrozenSnapshot,
    generated_at: datetime,
    attachments: list[Path],
) -> dict[str, Any]:
    message = EmailMessage(policy=policy.default)
    message["Subject"] = draft_subject(frozen.snapshot)
    message["Date"] = formatdate(generated_at.timestamp(), localtime=False, usegmt=True)
    message["X-CrazyMonkey-Status"] = "DRAFT_NOT_SENT"
    message["X-CrazyMonkey-Run-ID"] = frozen.snapshot.run_id
    message["X-CrazyMonkey-Review-Version"] = str(frozen.snapshot.version)
    message["X-CrazyMonkey-Snapshot-SHA256"] = frozen.snapshot_sha256
    message.set_content(draft_body(frozen.snapshot))
    for attachment in attachments:
        maintype, subtype = _attachment_content_type(attachment.suffix.lower())
        message.add_attachment(
            attachment.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=attachment.name,
        )
    path.write_bytes(message.as_bytes(policy=policy.default))
    return {
        "status": "DRAFT_NOT_SENT",
        "to": [],
        "subject": str(message["Subject"]),
        "body": draft_body(frozen.snapshot),
        "attachments": [attachment.name for attachment in attachments],
        "run_id": frozen.snapshot.run_id,
        "version": frozen.snapshot.version,
        "snapshot_sha256": frozen.snapshot_sha256,
        "generated_at": iso_z(generated_at),
    }


@dataclass(frozen=True)
class PreviewContext:
    recipient: str
    run_id: str
    version: int
    snapshot_sha256: str
    draft_path: Path
    draft_sha256: str
    attachment_sha256: tuple[tuple[str, str], ...]
    expires_at: datetime


class EmailDeliveryService:
    """Two-step, preview-bound email delivery boundary.

    A model or uploaded document cannot manufacture a valid send: the recipient is accepted
    only from the preview request, then bound into a signed short-lived token. Sending also
    requires the literal action SEND and a separate idempotency key.
    """

    def __init__(
        self,
        transport: EmailTransport | None,
        from_address: str | None,
        audit_log: Path,
        secret: bytes | None = None,
        token_ttl_seconds: int = 600,
    ):
        self.transport = transport
        self.from_address = from_address
        self.audit_log = audit_log
        self.secret = secret or secrets.token_bytes(32)
        self.token_ttl_seconds = token_ttl_seconds
        self._previews: dict[str, PreviewContext] = {}
        self._used_tokens: set[str] = set()
        self._idempotency: dict[str, tuple[str, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_environment(cls, audit_log: Path) -> "EmailDeliveryService":
        send_enabled = os.getenv("CRAZYMONKEY_ENABLE_EMAIL_SEND", "").lower() in {
            "1",
            "true",
            "yes",
        }
        # Disabled delivery must not make review/export startup depend on SMTP.
        settings = SMTPSettings.from_environment() if send_enabled else None
        secret_value = os.getenv("CRAZYMONKEY_CONFIRMATION_SECRET", "")
        return cls(
            transport=SMTPTransport(settings) if settings and send_enabled else None,
            from_address=settings.from_address if settings and send_enabled else None,
            audit_log=audit_log,
            secret=secret_value.encode("utf-8") if secret_value else None,
        )

    @property
    def configured(self) -> bool:
        return self.transport is not None and bool(self.from_address)

    def preview(self, bundle: "ExportBundle", recipient: str) -> dict[str, Any]:
        recipient = validate_recipient(recipient)
        draft_path = bundle.artifact_path("eml")
        attachment_digests = tuple(
            sorted(
                (artifact.filename, artifact.sha256)
                for artifact in bundle.artifacts
                if artifact.artifact_type in {"pdf", "xlsx", "json"}
            )
        )
        draft_digest = file_sha256(draft_path)
        draft = _parse_email(draft_path)
        if _email_attachment_digests(draft) != attachment_digests:
            raise EmailDeliveryError("draft attachments do not match the generated artifact bundle")
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.token_ttl_seconds)
        nonce = secrets.token_urlsafe(18)
        claims = {
            "recipient": recipient,
            "run_id": bundle.run_id,
            "version": bundle.version,
            "snapshot_sha256": bundle.snapshot_sha256,
            "draft_sha256": draft_digest,
            "attachments": attachment_digests,
            "expires_at": int(expires_at.timestamp()),
            "nonce": nonce,
        }
        token = self._sign_claims(claims)
        context = PreviewContext(
            recipient=recipient,
            run_id=bundle.run_id,
            version=bundle.version,
            snapshot_sha256=bundle.snapshot_sha256,
            draft_path=draft_path,
            draft_sha256=draft_digest,
            attachment_sha256=attachment_digests,
            expires_at=expires_at,
        )
        with self._lock:
            self._previews[token] = context
        return {
            "status": "PREVIEW_NOT_SENT",
            "to": [recipient],
            "subject": str(draft["Subject"]),
            "body": draft.get_body(preferencelist=("plain",)).get_content(),
            "attachments": [
                {"filename": name, "sha256": digest} for name, digest in attachment_digests
            ],
            "run_id": bundle.run_id,
            "version": bundle.version,
            "snapshot_sha256": bundle.snapshot_sha256,
            "confirmation_token": token,
            "expires_at": iso_z(expires_at),
            "send_configured": self.configured,
        }

    def send(
        self,
        *,
        confirmation_token: str,
        recipient: str,
        idempotency_key: str,
        confirmed: bool,
        action: str,
    ) -> dict[str, Any]:
        if not confirmed or action != "SEND":
            raise ConfirmationError("explicit confirmed=true and action=SEND are required")
        if not idempotency_key or len(idempotency_key) > 128:
            raise ConfirmationError("a bounded idempotency key is required")
        recipient = validate_recipient(recipient)
        claims = self.verify_confirmation_token(confirmation_token)
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "token": confirmation_token,
                    "recipient": recipient,
                    "run_id": claims["run_id"],
                    "version": claims["version"],
                    "snapshot_sha256": claims["snapshot_sha256"],
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

        with self._lock:
            prior = self._idempotency.get(idempotency_key)
            if prior:
                prior_fingerprint, response = prior
                if prior_fingerprint != fingerprint:
                    raise IdempotencyConflictError("idempotency key was already used for another send")
                return dict(response)
            if confirmation_token in self._used_tokens:
                raise ConfirmationError("confirmation token has already been used")
            context = self._previews.get(confirmation_token)
            if context is None:
                raise ConfirmationError("confirmation token was not issued by this process")
            if context.expires_at < datetime.now(timezone.utc):
                raise ConfirmationError("confirmation token has expired")
            if context.recipient != recipient or claims["recipient"] != recipient:
                raise ConfirmationError("recipient does not match the email preview")
            if claims.get("draft_sha256") != context.draft_sha256:
                raise ConfirmationError("confirmation token does not match the previewed draft")
            if not self.configured:
                raise EmailDeliveryDisabledError(
                    "real email is disabled until CRAZYMONKEY_ENABLE_EMAIL_SEND=true "
                    "and SMTP settings are configured"
                )

            if file_sha256(context.draft_path) != context.draft_sha256:
                raise ConfirmationError("email draft changed after preview")
            message = _parse_email(context.draft_path)
            if _email_attachment_digests(message) != context.attachment_sha256:
                raise ConfirmationError("email attachments changed after preview")
            if message.get("To"):
                del message["To"]
            if message.get("From"):
                del message["From"]
            message["To"] = recipient
            message["From"] = self.from_address
            message["Message-ID"] = make_msgid(domain=self.from_address.split("@")[-1])
            assert self.transport is not None
            try:
                acceptance = self.transport.send(message)
            except Exception as exc:
                self._append_audit(
                    {
                        "status": "PROVIDER_SEND_FAILED",
                        "recipient": recipient,
                        "run_id": context.run_id,
                        "version": context.version,
                        "snapshot_sha256": context.snapshot_sha256,
                        "provider_result": f"{type(exc).__name__}: {exc}",
                    },
                    idempotency_key,
                    context,
                )
                raise
            response = {
                "status": "ACCEPTED_BY_PROVIDER",
                "message_id": acceptance.message_id,
                "provider_result": acceptance.provider_result,
                "recipient": recipient,
                "run_id": context.run_id,
                "version": context.version,
                "snapshot_sha256": context.snapshot_sha256,
            }
            self._used_tokens.add(confirmation_token)
            self._idempotency[idempotency_key] = (fingerprint, response)
            self._append_audit(response, idempotency_key, context)
            return dict(response)

    def verify_confirmation_token(self, token: str) -> dict[str, Any]:
        """Validate a preview token without exposing signing internals to the API layer."""

        return self._verify_token(token)

    def _sign_claims(self, claims: dict[str, Any]) -> str:
        payload = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")
        encoded = base64.urlsafe_b64encode(payload).rstrip(b"=")
        signature = hmac.new(self.secret, encoded, hashlib.sha256).digest()
        return (encoded + b"." + base64.urlsafe_b64encode(signature).rstrip(b"=")).decode("ascii")

    def _verify_token(self, token: str) -> dict[str, Any]:
        try:
            encoded, signature = token.encode("ascii").split(b".", 1)
            expected = hmac.new(self.secret, encoded, hashlib.sha256).digest()
            supplied = base64.urlsafe_b64decode(signature + b"=" * (-len(signature) % 4))
            if not hmac.compare_digest(expected, supplied):
                raise ConfirmationError("invalid confirmation token")
            payload = base64.urlsafe_b64decode(encoded + b"=" * (-len(encoded) % 4))
            claims = json.loads(payload)
        except ConfirmationError:
            raise
        except Exception as exc:
            raise ConfirmationError("invalid confirmation token") from exc
        if int(claims.get("expires_at", 0)) < int(datetime.now(timezone.utc).timestamp()):
            raise ConfirmationError("confirmation token has expired")
        return claims

    def _append_audit(
        self,
        response: dict[str, Any],
        idempotency_key: str,
        context: PreviewContext,
    ) -> None:
        self.audit_log.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "requested_at": iso_z(datetime.now(timezone.utc)),
            "recipient": response["recipient"],
            "run_id": response["run_id"],
            "version": response["version"],
            "snapshot_sha256": response["snapshot_sha256"],
            "status": response["status"],
            "message_id": response.get("message_id"),
            "provider_result": response.get("provider_result"),
            "attachments": [
                {"filename": filename, "sha256": digest}
                for filename, digest in context.attachment_sha256
            ],
            "idempotency_key_sha256": hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest(),
        }
        with self.audit_log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")


def _email_attachment_digests(message: EmailMessage) -> tuple[tuple[str, str], ...]:
    digests = []
    for part in message.iter_attachments():
        filename = part.get_filename()
        payload = part.get_payload(decode=True)
        if not filename or payload is None:
            raise EmailDeliveryError("draft contains an attachment without a filename or payload")
        digests.append((filename, hashlib.sha256(payload).hexdigest()))
    return tuple(sorted(digests))


def validate_recipient(value: str) -> str:
    if not isinstance(value, str) or len(value) > 254 or any(char in value for char in "\r\n,;"):
        raise ConfirmationError("enter exactly one valid recipient address")
    display_name, address = parseaddr(value)
    if display_name or address != value or address.count("@") != 1:
        raise ConfirmationError("enter exactly one valid recipient address")
    local, domain = address.rsplit("@", 1)
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ConfirmationError("enter exactly one valid recipient address")
    return address


def _parse_email(path: Path) -> EmailMessage:
    parsed = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    if not isinstance(parsed, EmailMessage):
        raise EmailDeliveryError("draft is not a valid EmailMessage")
    return parsed


def _attachment_content_type(suffix: str) -> tuple[str, str]:
    return {
        ".pdf": ("application", "pdf"),
        ".xlsx": ("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ".json": ("application", "json"),
    }.get(suffix, ("application", "octet-stream"))
