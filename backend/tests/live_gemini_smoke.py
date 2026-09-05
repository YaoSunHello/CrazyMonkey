"""Manually invoked integration test that calls the configured Gemini service.

Run from the repository root:
    PYTHONPATH=backend python backend/tests/live_gemini_smoke.py -v

This filename deliberately does not match the normal ``test_*.py`` suite.
Without LLM_API_KEY the test skips; with it, this command performs real calls
and fails if LIVE_MODEL cannot produce the accepted, source-linked LP03 finding.
No credentials or raw provider responses are printed or written by this test.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from app.atlas.fixtures import generate_synthetic_pack
from app.runtime.audit import investigate
from app.runtime.contracts import VerificationPlan


@unittest.skipUnless(bool(os.environ.get("LLM_API_KEY", "").strip()), "LLM_API_KEY is not configured")
class LiveGeminiSmokeTests(unittest.TestCase):
    def test_live_lp03_with_independent_gemini_review(self):
        # Use the user-specified pack when available; otherwise generate the
        # current ATLAS fixture without changing its values or terminology.
        with tempfile.TemporaryDirectory(prefix="crazymonkey-live-smoke-") as temporary:
            input_dir = Path("/tmp/crazymonkey-atlas-fixtures")
            if not input_dir.is_dir():
                input_dir = Path(temporary) / "sources"
                generate_synthetic_pack(input_dir)

            result, store = investigate(
                input_dir,
                "Find material financial discrepancies in this fund pack.",
                mode="LIVE_MODEL",
            )

            self.assertEqual(result["mode"], "LIVE_MODEL")
            self.assertTrue(result["runtime_model"])
            self.assertFalse(result["ingestion_errors"])
            self.assertEqual(result["run_status"], "VERIFIED_CHECKS")

            calls = result["model_calls"]
            self.assertGreaterEqual(len(calls), 2)
            stages = {call["stage"] for call in calls if call["status"] == "success"}
            self.assertIn("investigator", stages)
            self.assertTrue({"red_team", "red_team_after_repair"} & stages)
            self.assertTrue(all(call["provider"] == "gemini" for call in calls))

            matches = [
                finding for finding in result["findings"]
                if finding["entity_id"] == "LP03" and finding["status"] == "DISCREPANCY"
            ]
            self.assertTrue(matches, "Live Gemini did not produce the accepted LP03 discrepancy")
            finding = next(
                (item for item in matches if item["calculation"]
                 and Decimal(item["calculation"]["expected"]) == Decimal("37500.00")),
                matches[0],
            )
            self.assertEqual(finding["currency"], "GBP")
            self.assertEqual(finding["red_team"]["status"], "PASS")
            self.assertEqual(finding["model_review"]["status"], "PASS")
            self.assertTrue(finding["model_review"]["evidence_ids"])
            calculation = finding["calculation"]
            self.assertIsNotNone(calculation)
            self.assertEqual(Decimal(calculation["expected"]), Decimal("37500.00"))
            self.assertEqual(Decimal(calculation["reported"]), Decimal("50000.00"))
            self.assertEqual(Decimal(calculation["difference"]), Decimal("12500.00"))

            plan = VerificationPlan.model_validate(finding["plan"])
            reported = plan.inputs[plan.reported_input]
            reported_source = store.citation(reported.evidence_id)
            self.assertEqual(reported_source["filename"], "Administrator_NAV_Q3_2026.xlsx")
            self.assertIn("Investor Fees!F6", reported_source["locator"])
            self.assertEqual(store.number(reported), Decimal("50000"))
            self.assertTrue(any(
                name != plan.reported_input and spec.unit == "money"
                and store.number(spec) == Decimal("10000000")
                for name, spec in plan.inputs.items()
            ), "The accepted fee base must resolve to source evidence")
            self.assertTrue(any(
                spec.unit == "factor" and store.number(spec) == Decimal("0.25")
                for spec in plan.inputs.values()
            ), "The accepted period factor must resolve to source evidence")

            rate_sources = [
                store.citation(spec.evidence_id)
                for spec in plan.inputs.values()
                if spec.unit == "rate" and store.number(spec) == Decimal("0.015")
            ]
            self.assertTrue(any(
                source["filename"] == "LP03_Side_Letter.pdf" and source["page"] == 1
                for source in rate_sources
            ), "The accepted 1.5% rate must resolve to the LP03 side letter")
            for evidence_id in (
                [spec.evidence_id for spec in plan.inputs.values()]
                + plan.context_evidence_ids
                + finding["model_review"]["evidence_ids"]
            ):
                store.get(evidence_id)
            store.verify_originals()

            self.assertLessEqual(len(result["attempts"]), 2)
            self.assertTrue(all(attempt["attempt"] in (0, 1) for attempt in result["attempts"]))


if __name__ == "__main__":
    unittest.main()
