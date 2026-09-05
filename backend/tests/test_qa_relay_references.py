"""Reject contradictory RELAY links without requiring invented missing evidence."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from pydantic import ValidationError

from app.relay.models import OutputSnapshotView


class RelayReferenceQaTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic_review_snapshot.json"
        self.payload = json.loads(fixture.read_text(encoding="utf-8"))

    def test_canonical_synthetic_fixture_preserves_asserted_and_unresolved_findings(self) -> None:
        snapshot = OutputSnapshotView.model_validate(self.payload)
        self.assertEqual(snapshot.summary_counts(), {
            "checks_completed": 6, "matches": 3, "discrepancies": 2,
            "cannot_verify": 1, "unsupported": 0, "unreviewed": 6,
        })
        lp06 = next(finding for finding in snapshot.findings if finding.investor_id == "LP06")
        self.assertIsNone(lp06.calculation_id)
        self.assertIsNone(lp06.expected_value)

    def test_calculation_cannot_name_another_investor(self) -> None:
        self.payload["calculations"][0]["investor_id"] = "LP_WRONG"
        with self.assertRaisesRegex(ValidationError, "investor does not match its finding"):
            OutputSnapshotView.model_validate(self.payload)

    def test_finding_cannot_reuse_another_findings_calculation(self) -> None:
        first, second = self.payload["findings"][:2]
        first["calculation_id"] = second["calculation_id"]
        with self.assertRaisesRegex(ValidationError, "linked to another finding"):
            OutputSnapshotView.model_validate(self.payload)

    def test_calculation_requires_reciprocal_finding_reference(self) -> None:
        self.payload["findings"][0]["calculation_id"] = None
        with self.assertRaisesRegex(ValidationError, "not referenced by its linked finding"):
            OutputSnapshotView.model_validate(self.payload)

    def test_investor_term_cannot_cite_unknown_evidence(self) -> None:
        self.payload["investor_terms"][0]["evidence_ids"].append("invented-term-source")
        with self.assertRaisesRegex(ValidationError, "investor term .* references unknown evidence"):
            OutputSnapshotView.model_validate(self.payload)

    def test_unresolved_term_may_have_no_available_evidence(self) -> None:
        term = next(term for term in self.payload["investor_terms"] if term["investor_id"] == "LP06")
        term["evidence_ids"] = []
        snapshot = OutputSnapshotView.model_validate(self.payload)
        unresolved = next(term for term in snapshot.investor_terms if term.investor_id == "LP06")
        self.assertEqual(unresolved.evidence_ids, ())
        self.assertEqual(unresolved.applicability_state, "MISSING_EVIDENCE")
        self.assertIsNone(unresolved.applicable_rate_fraction)
        self.assertEqual(snapshot.summary_counts()["cannot_verify"], 1)


if __name__ == "__main__":
    unittest.main()
