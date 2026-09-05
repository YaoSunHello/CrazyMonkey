"""The PDF must distinguish expected fee from difference-convention prose."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
from pypdf import PdfReader

from app.relay.pdf_export import write_pdf_report
from app.relay.snapshot_store import FileSnapshotStore


@pytest.mark.parametrize(
    ("investor", "fee_base", "rate", "expected", "difference"),
    [
        ("LP03", "10000000", "0.015", "£37,500.00", "£12,500.00"),
        ("LP04", "8000000", "0.020", "£40,000.00", "£10,000.00"),
    ],
)
def test_pdf_labels_expected_fee_after_runtime_calculation_description(
    tmp_path: Path, investor: str, fee_base: str, rate: str,
    expected: str, difference: str,
) -> None:
    fixture = Path(__file__).resolve().parents[1] / "fixtures/synthetic_review_snapshot.json"
    payload = json.loads(fixture.read_text())
    expression = (
        f"{fee_base} × {rate} × 0.25; ROUND_HALF_UP to 0.01; "
        "difference = reported minus expected"
    )
    calculation = next(item for item in payload["calculations"] if item["investor_id"] == investor)
    calculation["expression"] = expression
    frozen = FileSnapshotStore(tmp_path / "snapshots").freeze(payload)
    report = tmp_path / "review.pdf"
    write_pdf_report(report, frozen, datetime(2026, 9, 5, 12, tzinfo=timezone.utc))
    reader = PdfReader(report)
    text = " ".join(" ".join(page.extract_text() or "" for page in reader.pages).split())

    assert f"Calculation: {expression} Expected fee: {expected}" in text
    assert f"difference = reported minus expected = {expected}" not in text
    assert f"Expected {expected}" in text
    assert f"Difference {difference}" in text
    assert expected != difference
