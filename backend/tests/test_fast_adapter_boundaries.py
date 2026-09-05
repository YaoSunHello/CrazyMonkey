"""Regression tests for the Turbo/legacy boundary and diagnostic identity."""
from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from openpyxl import Workbook

from app.atlas.ingestion import normalize_file
from app.fast_audit import _deduplicate, _verify, run_audit, to_plan
from app.runtime.contracts import NumericInput, VerificationPlan
from app.runtime.fast_discovery import consistency_checks
from app.runtime.fast_dsl import FastCheck
from app.runtime.investigation_evidence import EvidenceStore
from app.runtime.semantics import discover_rows


class FastAdapterBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.input_dir = self.root / "input"
        self.input_dir.mkdir()

    def workbook(self, rows):
        path = self.input_dir / "schedule.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Schedule"
        for row in rows:
            sheet.append(row)
        workbook.save(path)
        return path

    def test_sixteen_sum_operands_bridge_to_seventeen_legacy_inputs(self):
        path = self.workbook([
            ["Investor ID", "Reported Fee", "Currency"],
            *[[f"Account-{index}", index, "GBP"] for index in range(1, 17)],
            ["Total", 137, "GBP"],
        ])
        store = EvidenceStore([normalize_file(path, original_storage_key=str(path))])
        checks, notes = consistency_checks(store, discover_rows(store))
        self.assertFalse(notes)
        self.assertEqual(len(checks), 1)
        check = checks[0]
        self.assertEqual(check.operation, "SUM")
        self.assertEqual(len(check.inputs), 16)

        plan = to_plan(check)
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.inputs), 17)
        self.assertEqual(len(plan.operation.operands), 16)
        # The 17th input remains solely the reported comparator, never an operand.
        self.assertNotIn(plan.reported_input, plan.operation.operands)
        self.assertEqual(plan.inputs[plan.reported_input].evidence_id, check.compare_to.evidence_id)
        VerificationPlan.model_validate_json(plan.model_dump_json())

        verified = _verify(check, store, Decimal("0.01"))
        self.assertTrue(verified["execution_valid"])
        self.assertEqual(verified["calculation"]["status"], "DISCREPANCY")
        self.assertEqual(Decimal(verified["calculation"]["expected"]), Decimal("136"))
        self.assertEqual(Decimal(verified["calculation"]["difference"]), Decimal("1"))
        for field in ("expected", "reported", "difference", "status"):
            self.assertEqual(verified["calculation"][field], verified["legacy"][field])

    def test_equivalent_percentage_and_multiplication_deduplicate_without_conflicts(self):
        # The base sorts after the rate by evidence ID, which reproduced the bug:
        # MULTIPLY sorted its operands while PERCENT_OF retained source order.
        base = NumericInput(evidence_id="z-base", unit="money")
        rate = NumericInput(evidence_id="a-rate", unit="rate")
        reported = NumericInput(evidence_id="reported", unit="money")
        percentage = FastCheck(
            check_id="percentage", title="Source percentage", entity_id="Account-A",
            operation="PERCENT_OF", inputs=[base, rate], compare_to=reported,
            currency="GBP", rationale="Apply the directly supported percentage to its base.",
            context_evidence_ids=["percentage-context"], source="contract",
        )
        multiplication = percentage.model_copy(update={
            "check_id": "multiplication", "operation": "MULTIPLY",
            "context_evidence_ids": ["multiplication-context"], "source": "relationship",
        })
        for candidates in ([percentage, multiplication], [multiplication, percentage]):
            with self.subTest(first=candidates[0].operation):
                checks, conflicts = _deduplicate(candidates)
                self.assertEqual(len(checks), 1)
                self.assertFalse(conflicts)
                self.assertEqual(set(checks[0].context_evidence_ids), {"percentage-context", "multiplication-context"})
                self.assertEqual(checks[0].compare_to.evidence_id, "reported")

    def test_anomaly_diagnostic_ids_resolve_after_real_synthetic_run_deduplication(self):
        path = self.workbook([
            ["Investor ID", "Reported Fee", "Currency"],
            ["Repeated-ID", 11, "GBP"],
            ["Repeated-ID", 12, "GBP"],
            ["Account-A", 50, "GBP"],
            ["Account-B", 50, "GBP"],
            ["Account-C", 50, "GBP"],
        ])
        before = path.read_bytes()
        with patch("app.runtime.model_client.GeminiClient.from_environment", side_effect=AssertionError("Synthetic mode must not construct a model")):
            result, store = asyncio.run(run_audit(
                self.input_dir, "Check table consistency and anomalies.",
                output_dir=self.root / "output", mode="SYNTHETIC_DEMO",
                apply_verified_fixes=False,
            ))
        self.assertEqual(result["mode"], "SYNTHETIC_DEMO")
        self.assertEqual(result["gemini_call_count"], 0)
        self.assertEqual(result["patches"], [])
        findings = {finding["check_id"]: finding for finding in result["findings"]}
        diagnostics = [note for note in result["diagnostics"] if "check_id" in note]
        self.assertEqual({note["code"] for note in diagnostics}, {"DUPLICATE_IDENTIFIER", "REPEATED_MONETARY_VALUE"})
        self.assertEqual(len(diagnostics), 2)
        for note in diagnostics:
            self.assertIn(note["check_id"], findings)
            finding = findings[note["check_id"]]
            self.assertEqual(note["status"], "REVIEW_REQUIRED")
            self.assertEqual(finding["status"], "REVIEW_REQUIRED")
            self.assertEqual(finding["check"]["source"], "anomaly")
            self.assertIsNone(finding["patch_proposal"])
            self.assertTrue(set(note["evidence_ids"]).issubset(finding["calculation"]["evidence_ids"]))
            for evidence_id in note["evidence_ids"]:
                store.get(evidence_id)
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
