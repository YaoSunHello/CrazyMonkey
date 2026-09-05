"""BEACON facade tests: real ATLAS uploads, faithful mapping, no email bypass."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.atlas import normalize_file
from app.atlas.fixtures import generate_synthetic_pack
from app.atlas.models import ReviewSnapshot
from app.runtime import beacon


class BeaconFacadeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="beacon-facade-test-")
        cls.source_root = Path(cls.temporary.name)
        generate_synthetic_pack(cls.source_root)
        cls.register_path = cls.source_root / "investor_input_register.csv"
        cls.document = normalize_file(cls.register_path)
        ref = next(item for item in cls.document.evidence if item.original_value == "LP06")
        cls.snapshot = ReviewSnapshot.model_validate({
            "run_id": "test-beacon-run", "version": 1, "mode": "SYNTHETIC_DEMO",
            "fund_name": "Example Growth Fund III", "reporting_period": "Q3 2026",
            "created_at": "2026-09-05T12:00:00Z", "frozen_at": "2026-09-05T12:00:00Z",
            "source_documents": [cls.document.document.model_dump(mode="json")],
            "rules": [], "calculations": [], "challenger_concerns": [],
            "verifier_results": [{
                "verifier_result_id": "verification-lp06", "investor_id": "LP06",
                "status": "CANNOT_VERIFY", "checks": [{
                    "code": "MISSING_SIDE_LETTER", "passed": False,
                    "explanation": "Required source document was not supplied.",
                }], "explanation": "LP06 cannot be verified without the expected side letter.",
            }],
            "findings": [{
                "finding_id": "finding-lp06", "investor_id": "LP06",
                "reported_value": "37500.00", "currency": "GBP",
                "status": "CANNOT_VERIFY", "human_review_state": "UNREVIEWED",
                "evidence_ids": [ref.evidence_id], "source_refs": [ref.model_dump(mode="json")],
                "challenger_concern_ids": [], "verifier_result_id": "verification-lp06",
                "explanation": "LP06 side letter is missing.",
                "actionable_next_step": "Supply the LP06 side letter and rerun.",
                "unresolved_questions": ["Expected side letter for LP06 was not supplied."],
            }],
            "limitations": ["Synthetic source pack for adapter tests only."],
        })

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(beacon.router)
        self.client = TestClient(self.app)
        self.record = SimpleNamespace(
            snapshot=self.snapshot.model_copy(deep=True),
            result=SimpleNamespace(mode="DEMO_FIXTURE", case_id="test-case", trace=[]),
            documents=[self.document.model_copy(deep=True)],
            user_instruction="Preserve the original user instruction.",
        )

        class FakeStore:
            def __init__(fake, record):
                fake.record = record
                fake.calls = []

            def get(fake, identifier):
                if identifier == "missing":
                    raise KeyError(identifier)
                return fake.record

            def create(fake, case_id, instruction, documents, *, synthetic=False):
                fake.calls.append((case_id, instruction, documents, synthetic))
                return fake.record

            def review(fake, run_id, finding_id, action, reviewer_label, note):
                if finding_id != "finding-lp06":
                    raise KeyError(finding_id)
                payload = fake.record.snapshot.model_dump(mode="json")
                payload["version"] += 1
                payload["findings"][0]["human_review_state"] = action
                payload["findings"][0]["reviewer_label"] = reviewer_label
                payload["findings"][0]["reviewer_note"] = note
                payload["summary"] = None
                fake.record.snapshot = ReviewSnapshot.model_validate(payload)
                return fake.record

        self.store = FakeStore(self.record)
        self.store_patch = patch.object(beacon, "_store", return_value=self.store)
        self.store_patch.start()
        self.addCleanup(self.store_patch.stop)
        self.addCleanup(self.client.close)

    def test_mapper_preserves_missing_source_status_and_real_evidence(self):
        output = beacon.to_beacon(self.snapshot, analyst_mode="DEMO_FIXTURE")
        finding = output["findings"][0]
        self.assertEqual(finding["status"], "CANNOT_VERIFY")
        self.assertNotIn("expectedValue", finding)
        self.assertNotIn("difference", finding)
        self.assertEqual(finding["administratorValue"], {"amount": 37500.0, "currency": "GBP"})
        self.assertEqual(finding["evidence"][0]["id"], self.snapshot.findings[0].evidence_ids[0])
        self.assertEqual(finding["evidence"][0]["value"], "LP06")
        self.assertEqual(finding["checksPerformed"][0]["state"], "UNRESOLVED")
        self.assertFalse(output["outputCapabilities"]["emailSend"])
        self.assertFalse(output["outputCapabilities"]["termCorrection"])
        self.assertEqual(finding["severity"], "NONE")
        self.assertEqual(finding["confidence"]["label"], "NOT_SCORED")
        self.assertEqual(finding["requiredAction"]["documentRole"], "SIDE_LETTER")
        self.assertNotIn("investorName", finding)
        self.assertIn("not a model call", output["sourceNotice"])

    def test_investor_name_is_exposed_only_for_unique_linked_csv_evidence(self):
        raw = self.snapshot.model_dump(mode="json")
        name = next(item for item in self.document.evidence if item.original_value == "Westgate Charitable Trust")
        raw["findings"][0]["evidence_ids"].append(name.evidence_id)
        raw["findings"][0]["source_refs"].append(name.model_dump(mode="json"))
        snapshot = ReviewSnapshot.model_validate(raw)
        finding = beacon.to_beacon(snapshot, analyst_mode="DEMO_FIXTURE")["findings"][0]
        self.assertEqual(finding["investorName"], "Westgate Charitable Trust")
        other = next(item for item in self.document.evidence if item.original_value == "Cedar Grove Foundation")
        raw["findings"][0]["evidence_ids"].append(other.evidence_id)
        raw["findings"][0]["source_refs"].append(other.model_dump(mode="json"))
        snapshot = ReviewSnapshot.model_validate(raw)
        self.assertNotIn("investorName", beacon.to_beacon(snapshot, analyst_mode="DEMO_FIXTURE")["findings"][0])

    def test_missing_upload_role_is_not_inferred_from_ambiguous_questions(self):
        raw = self.snapshot.model_dump(mode="json")
        raw["findings"][0]["unresolved_questions"] = ["Side-letter applicability is ambiguous."]
        finding = beacon.to_beacon(ReviewSnapshot.model_validate(raw), analyst_mode="DEMO_FIXTURE")["findings"][0]
        self.assertNotIn("documentRole", finding["requiredAction"])

    def test_role_detection_preserves_client_identifier(self):
        response = self.client.post(
            "/api/v1/documents/detect", data={"client_file_ids": "client-one"},
            files={"files": (self.register_path.name, self.register_path.read_bytes(), "text/csv")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [{
            "id": "client-one", "clientFileId": "client-one",
            "filename": self.register_path.name, "role": "INVESTOR_REGISTER",
            "recognition": "RECOGNISED",
        }])

    def test_duplicate_client_identifiers_are_rejected(self):
        response = self.client.post(
            "/api/v1/documents/detect", data={"client_file_ids": ["same", "same"]},
            files=[("files", ("one.csv", b"a,b\n1,2\n")), ("files", ("two.csv", b"a,b\n1,2\n"))],
        )
        self.assertEqual(response.status_code, 422)

    def test_real_file_upload_is_normalized_by_atlas_before_runtime(self):
        manifest = [{
            "id": "client-one", "clientFileId": "client-one", "filename": self.register_path.name,
            "role": "INVESTOR_REGISTER", "recognition": "RECOGNISED",
        }]
        response = self.client.post(
            "/api/v1/reviews", data={"manifest": json.dumps(manifest)},
            files={"files": (self.register_path.name, self.register_path.read_bytes(), "text/csv")},
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json(), {"reviewId": "test-beacon-run"})
        _, _, documents, synthetic = self.store.calls[0]
        self.assertFalse(synthetic)
        self.assertEqual(documents[0].model_dump(mode="json"), self.document.model_dump(mode="json"))

    def test_upload_rejects_manifest_filename_mismatch(self):
        manifest = [{"id": "one", "filename": "wrong.csv", "role": "INVESTOR_REGISTER", "recognition": "RECOGNISED"}]
        response = self.client.post(
            "/api/v1/reviews", data={"manifest": json.dumps(manifest)},
            files={"files": ("actual.csv", b"a,b\n1,2\n", "text/csv")},
        )
        self.assertEqual(response.status_code, 422)
        self.assertFalse(self.store.calls)

    def test_upload_rejects_path_traversal_filename(self):
        response = self.client.post(
            "/api/v1/documents/detect", data={"client_file_ids": "one"},
            files={"files": ("../investor_register.csv", b"a,b\n1,2\n", "text/csv")},
        )
        self.assertEqual(response.status_code, 422)

    def test_demo_uses_generated_atlas_originals_not_answer_fixture(self):
        response = self.client.post("/api/v1/demo/reviews")
        self.assertEqual(response.status_code, 201, response.text)
        _, _, documents, synthetic = self.store.calls[0]
        self.assertTrue(synthetic)
        self.assertEqual(len(documents), 8)
        self.assertEqual({item.document.role for item in documents}, {"LPA", "NAV_WORKBOOK", "INVESTOR_REGISTER", "SIDE_LETTER"})
        self.assertTrue(all(item.evidence for item in documents))

    def test_human_review_does_not_change_computational_status(self):
        response = self.client.patch(
            "/api/v1/reviews/test-beacon-run/findings/finding-lp06/review",
            json={"state": "REVIEWED", "reviewerName": "Demo reviewer", "note": "Request the missing side letter."},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["humanReviewState"], "REVIEWED")
        self.assertEqual(response.json()["status"], "CANNOT_VERIFY")
        self.assertEqual(response.json()["versions"][0]["version"], 2)

    def test_term_correction_cannot_silently_override_source_math(self):
        response = self.client.post(
            "/api/v1/reviews/test-beacon-run/findings/finding-lp06/corrections",
            json={"annualRate": 1.5, "note": "User assumption", "reviewerName": "Demo reviewer"},
        )
        self.assertEqual(response.status_code, 501)
        self.assertIn("Upload source evidence", response.json()["detail"])

    def test_missing_review_does_not_fall_back_to_synthetic_fixture(self):
        response = self.client.get("/api/v1/reviews/missing")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.store.calls)

    def test_retry_preserves_the_original_instruction(self):
        response = self.client.post("/api/v1/reviews/test-beacon-run/retry")
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.store.calls[0][1], self.record.user_instruction)


if __name__ == "__main__":
    unittest.main()
