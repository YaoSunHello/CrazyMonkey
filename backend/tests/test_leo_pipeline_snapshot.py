from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPOSITORY_ROOT / "samples" / "leo_pipeline_snapshot.json"
METRIC_SCHEMA_PATH = (
    REPOSITORY_ROOT / "backend" / "app" / "schemas" / "extracted_metric.schema.json"
)


class PipelineSnapshotFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = _load_json(FIXTURE_PATH)
        cls.metric_schema = _load_json(METRIC_SCHEMA_PATH)

    def test_uses_fresh_crazymonkey_contract(self) -> None:
        self.assertEqual(
            self.snapshot["schema_version"],
            "crazymonkey.pipeline-review.v1",
        )
        self.assertEqual(self.snapshot["mode"], "SYNTHETIC_DEMO")
        serialized = json.dumps(self.snapshot).casefold()
        for legacy_marker in ("ylookup", "fundops", "retinapeg", "atlas", "relay"):
            self.assertNotIn(legacy_marker, serialized)

    def test_stage_order_makes_challenge_and_verification_explicit(self) -> None:
        stages = [item["stage"] for item in self.snapshot["pipeline_stages"]]
        statuses = [item["status"] for item in self.snapshot["pipeline_stages"]]
        self.assertEqual(
            stages,
            ["NORMALIZED", "ANALYSED", "CHALLENGED", "VERIFIED"],
        )
        self.assertEqual(statuses, ["COMPLETE"] * 4)

    def test_normalized_metrics_match_existing_required_interface(self) -> None:
        required = set(self.metric_schema["required"])
        documents = {
            item["filename"] for item in self.snapshot["source_documents"]
        }
        evidence_ids = {
            item["evidence_id"] for item in self.snapshot["evidence"]
        }

        for metric in self.snapshot["normalized_metrics"]:
            self.assertTrue(required.issubset(metric))
            self.assertIsInstance(metric["metric_value"], (int, float))
            self.assertIn(metric["source_document"], documents)
            self.assertIn(metric["evidence_id"], evidence_ids)
            confidence = metric["confidence_score"]
            self.assertGreaterEqual(confidence, 0)
            self.assertLessEqual(confidence, 1)

    def test_all_review_records_resolve_to_known_metrics_and_evidence(self) -> None:
        metric_ids = {
            item["metric_id"] for item in self.snapshot["normalized_metrics"]
        }
        evidence_ids = {
            item["evidence_id"] for item in self.snapshot["evidence"]
        }
        concern_ids = {
            item["concern_id"] for item in self.snapshot["red_team_concerns"]
        }

        for proposal in self.snapshot["analyst_proposals"]:
            self.assertIn(proposal["metric_id"], metric_ids)
            self.assertTrue(set(proposal["evidence_ids"]).issubset(evidence_ids))
        for concern in self.snapshot["red_team_concerns"]:
            self.assertIn(concern["metric_id"], metric_ids)
            self.assertTrue(set(concern["evidence_ids"]).issubset(evidence_ids))
        for result in self.snapshot["verifier_results"]:
            self.assertIn(result["metric_id"], metric_ids)
            self.assertTrue(
                set(result["blocking_concern_ids"]).issubset(concern_ids)
            )
            if result["status"] == "INDETERMINATE":
                self.assertTrue(result["blocking_concern_ids"])

    def test_summary_reconciles_and_delivery_remains_gated(self) -> None:
        results = self.snapshot["verifier_results"]
        summary = self.snapshot["review_summary"]
        self.assertEqual(summary["metrics"], len(self.snapshot["normalized_metrics"]))
        self.assertEqual(
            summary["verified"],
            sum(result["status"] == "PASS" for result in results),
        )
        self.assertEqual(
            summary["needs_review"],
            sum(result["status"] != "PASS" for result in results),
        )

        delivery = self.snapshot["delivery"]
        self.assertEqual(delivery["pdf"], "NOT_GENERATED")
        self.assertEqual(delivery["excel"], "NOT_GENERATED")
        self.assertEqual(delivery["email"]["recipient"], "")
        self.assertFalse(delivery["email"]["send_authorized"])


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected a JSON object in {path}")
    return value


if __name__ == "__main__":
    unittest.main()
