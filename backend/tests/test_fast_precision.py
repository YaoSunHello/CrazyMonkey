"""Real rounding-boundary regression: semantic review cannot erase disagreement."""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from app.atlas.ingestion import normalize_file
from app.fast_audit import _verify, from_plan, run_audit
from app.runtime.fast_discovery import consistency_checks
from app.runtime.investigation_evidence import EvidenceStore
from app.runtime.planner import offline_plan
from app.runtime.semantics import discover_rows


class FastPrecisionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="fast-precision-")
        self.root = Path(self.temporary.name)
        self.inputs = self.root / "input"
        self.inputs.mkdir()
        self.path = self.inputs / "rounding.csv"
        # (1 - 10^-30) * (1.005 + 1.005 * 10^-30) is just BELOW 1.005.
        # Precision 50 erases the 10^-60 term; precision 80 retains it.
        self.path.write_text(
            "Account ID,Fund,Currency,Quantity,Unit Price,Line Total\n"
            "ROUND-1,Test Fund,GBP,0.999999999999999999999999999999,"
            "1.005000000000000000000000000001005,1.03\n"
        )
        self.store = EvidenceStore([normalize_file(self.path, original_storage_key=str(self.path))])
        self.plan = offline_plan(self.store).checks[0]

    def tearDown(self):
        self.temporary.cleanup()

    def test_real_decimal_executor_disagreement_is_a_hard_failure(self):
        item = _verify(from_plan(self.plan), self.store, Decimal("0.01"))
        self.assertEqual(item["calculation"]["expected"], "1.00")
        self.assertEqual(item["legacy"]["expected"], "1.01")
        self.assertFalse(item["execution_valid"])
        self.assertEqual(item["review"].status, "CHALLENGE")
        self.assertIn("independent executors disagree", item["review"].reasons)

    def test_full_run_does_not_ask_a_model_to_override_numeric_disagreement(self):
        check = from_plan(self.plan).model_dump(mode="json")
        evidence_ids = self.plan.context_evidence_ids

        class PassingReviewer:
            name = "gemini/scripted-precision-test"

            def __init__(self):
                self.calls = []

            def complete_json(self, system, payload, *, stage):
                self.calls.append({"stage": stage, "provider": "gemini", "status": "success"})
                if stage == "contract_discovery":
                    return {"checks": [check], "cannot_verify": []}
                if stage == "relationship_discovery":
                    return {"checks": [], "cannot_verify": []}
                # Even a willing reviewer must never be consulted to override
                # this deterministic disagreement.
                return {"status": "PASS", "reasons": [], "evidence_ids": evidence_ids}

        model = PassingReviewer()
        original = self.path.read_bytes()
        result, _ = asyncio.run(run_audit(
            self.inputs, "Find material financial discrepancies.",
            output_dir=self.root / "output", mode="LIVE_MODEL", model=model,
        ))
        self.assertEqual(len(result["findings"]), 1)
        finding = result["findings"][0]
        self.assertEqual(finding["status"], "CANNOT_VERIFY")
        self.assertIsNone(finding["patch_proposal"])
        self.assertIsNone(finding["model_review"])
        self.assertEqual(result["patches"], [])
        self.assertEqual(sorted(call["stage"] for call in model.calls),
                         ["contract_discovery", "relationship_discovery"])
        self.assertEqual(self.path.read_bytes(), original)

    def test_money_arithmetic_cannot_bypass_missing_currency_as_a_predicate(self):
        self.path.write_text("Account ID,Fund,Quantity,Unit Price,Line Total\nA-1,Test Fund,2,10,25\n")
        store = EvidenceStore([normalize_file(self.path, original_storage_key=str(self.path))])
        checks, _ = consistency_checks(store, discover_rows(store))
        self.assertEqual(len(checks), 1)
        self.assertIsNone(checks[0].currency)
        item = _verify(checks[0], store, Decimal("0.01"))
        self.assertFalse(item["execution_valid"])
        self.assertNotEqual(item["review"].status, "PASS")


if __name__ == "__main__":
    unittest.main()
