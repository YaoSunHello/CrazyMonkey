"""Gemini orchestration tests with scripted transport and real ATLAS evidence.

Normal tests never contact the provider; the separate live smoke owns that.
"""
from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.atlas.fixtures import generate_synthetic_pack
from app.atlas.ingestion import normalize_file
from app.runtime.audit import CHALLENGER_SYSTEM, investigate, main
from app.runtime.investigation_evidence import EvidenceStore
from app.runtime.model import RuntimeModelError
from app.runtime.planner import PLANNER_SYSTEM, offline_plan


class ScriptedGemini:
    name = "gemini/scripted-unit-test"

    def __init__(self, responses):
        self.responses = list(responses)
        self.stage = "unspecified"
        self.calls = []
        self.requests = []

    def complete_json(self, system, payload):
        self.requests.append({"system": system, "payload": copy.deepcopy(payload)})
        self.calls.append({"stage": self.stage, "provider": "gemini", "status": "success"})
        if not self.responses:
            raise AssertionError("unexpected additional model call")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            self.calls[-1]["status"] = "error"
            raise response
        return copy.deepcopy(response)


class GeminiAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="gemini-audit-tests-")
        cls.root = Path(cls.temporary.name) / "input"
        generate_synthetic_pack(cls.root)
        documents = [normalize_file(path, original_storage_key=str(path))
                     for path in sorted(cls.root.iterdir()) if path.suffix in (".xlsx", ".csv", ".pdf")]
        cls.store = EvidenceStore(documents)
        cls.plan = next(plan for plan in offline_plan(cls.store).checks if plan.entity_id == "LP03")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def batch(self, plan=None):
        return {"checks": [(plan or self.plan).model_dump(mode="json")], "cannot_verify": []}

    def review(self, status="PASS"):
        return {"status": status, "reasons": [] if status == "PASS" else ["Reconsider this plan against the original evidence."],
                "evidence_ids": self.plan.context_evidence_ids, "suggested_correction": None}

    def run_model(self, responses):
        model = ScriptedGemini(responses)
        result, store = investigate(self.root, "Find material financial discrepancies.", model=model, mode="LIVE_MODEL")
        return result, store, model

    def test_live_mode_constructs_gemini_and_uses_independent_source_review(self):
        model = ScriptedGemini([self.batch(), self.review()])
        with (patch("app.runtime.model_client.GeminiClient.from_environment", return_value=model) as factory,
              patch("app.runtime.planner.offline_plan") as offline):
            result, store = investigate(self.root, "Find discrepancies.", mode="LIVE_MODEL")
        factory.assert_called_once_with()
        offline.assert_not_called()
        self.assertEqual(result["mode"], "LIVE_MODEL")
        self.assertEqual([call["stage"] for call in model.calls], ["investigator", "red_team"])
        finding = result["findings"][0]
        self.assertEqual(finding["status"], "DISCREPANCY")
        self.assertEqual(finding["calculation"]["expected"], "37500.00")
        self.assertEqual(finding["calculation"]["difference"], "12500.00")
        self.assertEqual(finding["model_review"]["status"], "PASS")
        self.assertEqual(model.requests[0]["system"], PLANNER_SYSTEM)
        self.assertEqual(model.requests[1]["system"], CHALLENGER_SYSTEM)
        review_payload = model.requests[1]["payload"]
        all_ids = {ref["evidence_id"] for doc in review_payload["documents"] for ref in doc["evidence"]}
        self.assertEqual(all_ids, set(store.refs))
        self.assertEqual(review_payload["calculation"]["expected"], "37500.00")
        self.assertNotIn("repair", review_payload)

    def test_live_transport_error_never_falls_back_or_repairs(self):
        model = ScriptedGemini([RuntimeModelError("Gemini transport failed safely.")])
        with patch("app.runtime.planner.offline_plan") as offline:
            with self.assertRaisesRegex(RuntimeModelError, "transport failed"):
                investigate(self.root, "Find discrepancies.", mode="LIVE_MODEL", model=model)
        offline.assert_not_called()
        self.assertEqual(len(model.calls), 1)

    def test_red_team_transport_failure_cannot_return_an_accepted_result(self):
        model = ScriptedGemini([self.batch(), RuntimeModelError("Gemini reviewer unavailable.")])
        with self.assertRaisesRegex(RuntimeModelError, "reviewer unavailable"):
            investigate(self.root, "Find discrepancies.", mode="LIVE_MODEL", model=model)
        self.assertEqual([call["stage"] for call in model.calls], ["investigator", "red_team"])

    def test_initial_schema_failure_allows_one_repair_and_review(self):
        result, _, model = self.run_model([{"checks": [{"invented_field": "invalid"}]}, self.batch(), self.review()])
        self.assertTrue(result["repair_attempted"])
        self.assertEqual(result["findings"][0]["status"], "DISCREPANCY")
        self.assertEqual([call["stage"] for call in model.calls], ["investigator", "repair", "red_team_after_repair"])
        self.assertIn("repair", model.requests[1]["payload"])
        self.assertEqual(len(result["attempts"]), 2)

    def test_two_invalid_schemas_stop_without_a_third_attempt(self):
        invalid = {"checks": [{"invented_field": "invalid"}]}
        result, _, model = self.run_model([invalid, invalid])
        self.assertTrue(result["repair_attempted"])
        self.assertEqual(result["run_status"], "CANNOT_VERIFY")
        self.assertEqual(result["findings"], [])
        self.assertEqual(len(model.calls), 2)
        self.assertTrue(any("Repair failed closed" in reason for reason in result["cannot_verify"]))

    def test_nonexistent_evidence_is_repaired_before_review(self):
        invalid = self.batch()
        invalid["checks"][0]["inputs"]["base"]["evidence_id"] = "ev_not_in_atlas"
        result, _, model = self.run_model([invalid, self.batch(), self.review()])
        self.assertEqual(result["findings"][0]["status"], "DISCREPANCY")
        self.assertEqual([call["stage"] for call in model.calls], ["investigator", "repair", "red_team_after_repair"])

    def test_repeated_unresolved_evidence_abstains_after_one_repair(self):
        invalid = self.batch()
        invalid["checks"][0]["inputs"]["base"]["evidence_id"] = "ev_not_in_atlas"
        result, _, model = self.run_model([invalid, invalid])
        self.assertEqual(result["findings"][0]["status"], "CANNOT_VERIFY")
        self.assertIsNone(result["findings"][0]["calculation"])
        self.assertEqual(len(model.calls), 2)

    def test_review_challenge_repairs_once_then_requests_fresh_review(self):
        result, _, model = self.run_model([self.batch(), self.review("CHALLENGE"), self.batch(), self.review()])
        self.assertEqual(result["findings"][0]["status"], "DISCREPANCY")
        self.assertEqual([call["stage"] for call in model.calls],
                         ["investigator", "red_team", "repair", "red_team_after_repair"])
        self.assertEqual(len(result["attempts"]), 2)

    def test_second_review_challenge_stops_without_another_repair(self):
        result, _, model = self.run_model([self.batch(), self.review("CHALLENGE"), self.batch(), self.review("CHALLENGE")])
        self.assertEqual(result["findings"][0]["status"], "CANNOT_VERIFY")
        self.assertIsNone(result["findings"][0]["calculation"])
        self.assertEqual([call["stage"] for call in model.calls].count("repair"), 1)
        self.assertEqual(len(model.calls), 4)

    def test_schema_repair_consumes_budget_before_later_review_challenge(self):
        result, _, model = self.run_model([{"checks": [{"bad": True}]}, self.batch(), self.review("CHALLENGE")])
        self.assertEqual(result["findings"][0]["status"], "CANNOT_VERIFY")
        self.assertEqual(len(model.calls), 3)
        self.assertEqual([call["stage"] for call in model.calls].count("repair"), 1)

    def test_review_insufficient_evidence_abstains_without_repair(self):
        result, _, model = self.run_model([self.batch(), self.review("INSUFFICIENT_EVIDENCE")])
        self.assertEqual(result["findings"][0]["status"], "CANNOT_VERIFY")
        self.assertFalse(result["repair_attempted"])
        self.assertEqual(len(model.calls), 2)

    def test_model_pass_cannot_override_deterministic_source_contradiction(self):
        contradictory = next(plan for plan in offline_plan(self.store).checks if plan.entity_id == "LP04")
        review = {**self.review(), "evidence_ids": contradictory.context_evidence_ids,
                  "suggested_correction": "This model text must never replace the verifier result."}
        result, _, model = self.run_model([self.batch(contradictory), review, {"checks": [], "cannot_verify": []}])
        finding = result["findings"][0]
        self.assertEqual(finding["model_review"]["status"], "PASS")
        self.assertEqual(finding["deterministic_review"]["status"], "CHALLENGE")
        self.assertEqual(finding["status"], "CANNOT_VERIFY")
        self.assertIsNone(finding["calculation"])
        self.assertEqual(len(model.calls), 3)

    def test_repair_cannot_switch_investor_or_reported_source(self):
        for field in ("entity_id", "reported_source"):
            with self.subTest(field=field):
                replacement = self.batch()
                if field == "entity_id":
                    replacement["checks"][0]["entity_id"] = "different-account"
                else:
                    replacement["checks"][0]["inputs"]["reported"]["evidence_id"] = "ev_different_reported"
                result, _, model = self.run_model([self.batch(), self.review("CHALLENGE"), replacement])
                self.assertEqual(result["findings"][0]["status"], "CANNOT_VERIFY")
                self.assertEqual(result["findings"][0]["entity_id"], "LP03")
                self.assertEqual(len(model.calls), 3)

    def test_invalid_red_team_evidence_or_unrequested_answers_fail_closed(self):
        invalid_reviews = [
            {**self.review(), "evidence_ids": []},
            {**self.review(), "evidence_ids": ["ev_invented"]},
            {**self.review(), "expected_amount": "1"},
        ]
        for review in invalid_reviews:
            with self.subTest(review=review):
                model = ScriptedGemini([self.batch(), review])
                with self.assertRaises(RuntimeModelError):
                    investigate(self.root, "Find discrepancies.", mode="LIVE_MODEL", model=model)
                self.assertEqual(len(model.calls), 2)

    def test_mode_validation_and_synthetic_mode_never_construct_provider(self):
        with patch("app.runtime.model_client.GeminiClient.from_environment") as factory:
            with self.assertRaisesRegex(ValueError, "mode"):
                investigate(self.root, "Find discrepancies.", mode="UNKNOWN")
            with self.assertRaisesRegex(ValueError, "cannot use a model"):
                investigate(self.root, "Find discrepancies.", mode="SYNTHETIC_DEMO", model=ScriptedGemini([]))
            result, _ = investigate(self.root, "Find discrepancies.", mode="SYNTHETIC_DEMO")
        factory.assert_not_called()
        self.assertEqual(result["mode"], "SYNTHETIC_DEMO")
        self.assertEqual(result["model_calls"], [])

    def test_cli_live_failure_is_visible_and_saves_no_fallback_result(self):
        with tempfile.TemporaryDirectory(prefix="gemini-error-output-") as temporary:
            output = Path(temporary) / "result"
            error = io.StringIO()
            argv = ["audit", "--input", str(self.root), "--output", str(output), "--mode", "LIVE_MODEL"]
            with (patch("sys.argv", argv), patch("sys.stderr", error),
                  patch("app.runtime.model_client.GeminiClient.from_environment", side_effect=RuntimeModelError("Gemini unavailable."))):
                exit_code = main()
            self.assertEqual(exit_code, 1)
            self.assertIn("LIVE_MODEL ERROR", error.getvalue())
            record = json.loads((output / "error.json").read_text())
            self.assertEqual(record["mode"], "LIVE_MODEL")
            self.assertFalse(record["synthetic_fallback"])
            self.assertFalse((output / "result.json").exists())


if __name__ == "__main__":
    unittest.main()
