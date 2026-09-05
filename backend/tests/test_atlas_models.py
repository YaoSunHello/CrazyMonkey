from __future__ import annotations

import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from app.atlas.models import (
    CoverageSummary,
    EvidenceKind,
    ReviewSnapshot,
    RunMode,
    SourceRef,
)


class AtlasModelTests(unittest.TestCase):
    def test_source_reference_requires_exact_support_and_a_matching_locator(self) -> None:
        common = {
            "evidence_id": "ev_example",
            "document_id": "doc_example",
            "document_hash": "0" * 64,
            "kind": EvidenceKind.WORKBOOK_CELL,
            "sheet": "Fees",
            "cell": "C4",
        }

        with self.assertRaises(ValidationError):
            SourceRef(**common)

        reference = SourceRef(**common, original_value="50000")
        self.assertEqual(reference.locator, "Fees!C4")

    def test_snapshot_summary_is_derived_instead_of_trusted(self) -> None:
        now = datetime.now(timezone.utc)
        snapshot = ReviewSnapshot(
            run_id="run_example",
            version=1,
            mode=RunMode.SYNTHETIC_DEMO,
            fund_name="Synthetic Fund",
            reporting_period="Q3 2026",
            created_at=now,
            frozen_at=now,
            source_documents=[],
            rules=[],
            calculations=[],
            challenger_concerns=[],
            verifier_results=[],
            findings=[],
            limitations=["Management-fee scope only."],
        )

        self.assertEqual(
            snapshot.summary,
            CoverageSummary(
                checks_completed=0,
                matches=0,
                discrepancies=0,
                cannot_verify=0,
                unsupported=0,
                unreviewed=0,
            ),
        )

    def test_snapshot_rejects_a_supplied_summary_that_disagrees_with_findings(self) -> None:
        now = datetime.now(timezone.utc)

        with self.assertRaises(ValidationError):
            ReviewSnapshot(
                run_id="run_example",
                version=1,
                mode=RunMode.SYNTHETIC_DEMO,
                fund_name="Synthetic Fund",
                reporting_period="Q3 2026",
                created_at=now,
                frozen_at=now,
                source_documents=[],
                rules=[],
                calculations=[],
                challenger_concerns=[],
                verifier_results=[],
                findings=[],
                limitations=["Management-fee scope only."],
                summary=CoverageSummary(
                    checks_completed=1,
                    matches=1,
                    discrepancies=0,
                    cannot_verify=0,
                    unsupported=0,
                    unreviewed=0,
                ),
            )


if __name__ == "__main__":
    unittest.main()
