from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader

from .artifact_assertions import compact_text, pdf_text
from app.relay.pdf_export import write_pdf_report
from app.relay.snapshot_store import FrozenSnapshot


GENERATED_AT = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


def test_pdf_report_generates_opens_and_contains_required_review_evidence(
    tmp_path: Path,
    frozen_snapshot: FrozenSnapshot,
) -> None:
    path = tmp_path / "review.pdf"

    write_pdf_report(path, frozen_snapshot, GENERATED_AT)

    assert path.read_bytes().startswith(b"%PDF-")
    assert path.stat().st_size > 5_000
    reader = PdfReader(path)
    assert len(reader.pages) >= 2
    text = compact_text(pdf_text(path))

    assert "CRAZYMONKEY NAV REVIEW" in text
    assert "Management-fee checks only" in text
    assert "Run ID " + frozen_snapshot.snapshot.run_id in text
    assert "Review version " + str(frozen_snapshot.snapshot.version) in text
    assert frozen_snapshot.snapshot_sha256 in text
    assert "Synthetic Demo" in text

    assert "KEY EXCEPTIONS" in text
    assert "LP03 - Management fee" in text
    assert "Administrator £50,000.00" in text
    assert "Expected £37,500.00" in text
    assert "Difference £12,500.00" in text
    assert "1.5%" in text or "1.50%" in text
    assert "Section 3.1" in text

    assert "LP04 - Management fee" in text
    assert "Administrator £50,000.00" in text
    assert "Expected £40,000.00" in text
    assert "Difference £10,000.00" in text

    assert "CANNOT VERIFY" in text
    assert "LP06" in text
    assert "side letter" in text.casefold()
    assert "HUMAN REVIEW" in text
    assert "UNREVIEWED" in text

    assert (
        "This review checks the management-fee calculations described above. "
        "It does not constitute legal advice, regulated approval, audit certification, "
        "or validation of the entire NAV."
    ) in text
    for prohibited_claim in (
        "CERTIFIED",
        "COMPLIANT",
        "LEGALLY CORRECT",
        "ERROR FREE",
        "APPROVED NAV",
    ):
        assert prohibited_claim not in text


def test_pdf_metadata_carries_frozen_snapshot_identity(
    tmp_path: Path,
    frozen_snapshot: FrozenSnapshot,
) -> None:
    path = tmp_path / "review.pdf"
    write_pdf_report(path, frozen_snapshot, GENERATED_AT)

    metadata = PdfReader(path).metadata
    assert metadata is not None
    assert metadata.title == "CrazyMonkey NAV Review"
    assert metadata.author == "CrazyMonkey RELAY"
    assert frozen_snapshot.snapshot.run_id in (metadata.subject or "")
    assert f"version {frozen_snapshot.snapshot.version}" in (metadata.subject or "")
    assert frozen_snapshot.snapshot_sha256 in (metadata.subject or "")
