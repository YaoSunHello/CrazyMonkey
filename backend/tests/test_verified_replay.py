"""Replay tests use explicit mocked-live metadata, never real Gemini credentials."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import chdir, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook

from app.atlas.fixtures import generate_synthetic_pack
from app.atlas.ingestion import normalize_file
from app.fast_audit import from_plan, main, run_audit, to_plan
from app.runtime.challenger import challenge
from app.runtime.executor import execute
from app.runtime.fast_dsl import execute_check
from app.runtime.investigation_evidence import EvidenceStore
from app.runtime.patches import propose_patch
from app.runtime.planner import offline_plan
from app.runtime.replay import CASE_FILES, list_cases, replay_case, save_case


class VerifiedReplayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mocked-live-replay-test-")
        self.root = Path(self.temporary.name)
        self.sources = self.root / "input"
        self.cases = self.root / "cases"
        self.output = self.root / "replayed"
        generate_synthetic_pack(self.sources)
        documents = [normalize_file(path, original_storage_key=str(path))
                     for path in sorted(self.sources.iterdir()) if path.suffix in {".pdf", ".xlsx", ".csv"}]
        self.store = EvidenceStore(documents)
        self.plans = {plan.entity_id: plan for plan in offline_plan(self.store).checks}
        self.result = self.mocked_live_result()

    def tearDown(self):
        self.temporary.cleanup()

    def finding(self, entity="LP03"):
        check = from_plan(self.plans[entity])
        plan = to_plan(check)
        calculation = execute_check(check, self.store)
        verified = execute(plan, self.store)
        review = challenge(plan, verified, self.store)
        status = calculation["status"] if review.status == "PASS" else "CANNOT_VERIFY"
        proposal = propose_patch(plan, verified, self.store, review) if status == "DISCREPANCY" else None
        return {"check_id": check.check_id, "title": check.title, "entity_id": entity,
                "status": status, "currency": check.currency, "check": check.model_dump(mode="json"),
                "calculation": calculation, "verified_calculation": verified,
                "red_team": review.model_dump(mode="json"),
                "model_review": {"status": "PASS", "reasons": ["Mocked semantic review fixture, not a live call."],
                                 "evidence_ids": check.context_evidence_ids, "suggested_correction": None}
                                 if review.status == "PASS" else None,
                "sources": [self.store.citation(e) for e in calculation["evidence_ids"]],
                "patch_proposal": proposal.model_dump(mode="json") if proposal else None}

    def mocked_live_result(self):
        """Fixture-only provenance; production acceptance evidence is never fabricated."""
        return {"schema_version": 1, "mode": "LIVE_MODEL", "runtime_model": "gemini:mocked-fixture-only",
                "created_at": datetime.now(timezone.utc).isoformat(), "instruction": "Find material discrepancies.",
                "file_count": 8, "normalized_count": len(self.store.documents), "evidence_count": len(self.store.refs),
                "findings": [self.finding()], "cannot_verify": [], "diagnostics": [],
                "ingestion_errors": [], "originals_unchanged": True, "repair_attempted": False,
                "model_calls": [{"provider": "gemini", "stage": stage, "model": "mocked-fixture-only",
                                 "status": "success", "response_id": "fixture-not-live", "duration_ms": 1}
                                for stage in ("contract_discovery", "relationship_discovery", "red_team")],
                "gemini_call_count": 3, "timings": {"total_seconds": 1}, "task_trace": [],
                "peak_concurrency": {"verification": 1}, "limitations": ["Explicit mocked-live unit test fixture."]}

    def save(self):
        return save_case(self.result, self.store, "lp03-test-fixture", self.cases)

    def rewrite(self, case, filename, transform, *, refresh_digest=True):
        path = case / filename
        payload = json.loads(path.read_text())
        transform(payload)
        data = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()
        path.write_bytes(data)
        if refresh_digest and filename != "manifest.json":
            manifest = json.loads((case / "manifest.json").read_text())
            manifest["files"][filename] = hashlib.sha256(data).hexdigest()
            (case / "manifest.json").write_text(json.dumps(manifest))

    def test_exact_case_files_and_verified_listing(self):
        self.result["findings"].append(self.finding("LP02"))
        case = self.save()
        self.assertEqual({path.name for path in case.iterdir()}, set(CASE_FILES))
        manifest = json.loads((case / "manifest.json").read_text())
        self.assertEqual(manifest["accepted_count"], 2)
        self.assertEqual(manifest["finding_count"], 1)
        entry = list_cases(self.cases)[0]
        self.assertEqual(entry["case_id"], "lp03-test-fixture")
        self.assertEqual(entry["status"], "VERIFIED")
        self.assertEqual(entry["findings"], 1)
        self.assertEqual(entry["created_at"], self.result["created_at"])

    def test_replay_reexecutes_both_verifiers_and_never_constructs_gemini(self):
        case = self.save()
        messages = []
        with (patch("app.runtime.model_client.GeminiClient", side_effect=AssertionError("No model in replay")) as model,
              patch("app.runtime.replay.execute_check", wraps=execute_check) as fast,
              patch("app.runtime.replay.execute", wraps=execute) as independent):
            result = replay_case(case, output_dir=self.output, progress=messages.append)
        model.assert_not_called()
        self.assertEqual(fast.call_count, 1)
        self.assertEqual(independent.call_count, 1)
        self.assertEqual(result["mode"], "VERIFIED_REPLAY")
        self.assertEqual(result["gemini_call_count"], 0)
        self.assertEqual(result["model_calls"], [])
        self.assertEqual(result["evidence_integrity"], "PASS")
        self.assertEqual(result["deterministic_verification"], "PASS")
        self.assertEqual(result["findings"][0]["verified_calculation"]["expected"], "37500.00")
        self.assertEqual(result["findings"][0]["verified_calculation"]["reported"], "50000")
        self.assertEqual(result["findings"][0]["verified_calculation"]["difference"], "12500.00")
        self.assertEqual(result["findings"][0]["model_review_origin"], "SAVED_PRIOR_REVIEW_NO_FRESH_MODEL")
        self.assertFalse(self.output.exists())
        self.assertIn("Gemini calls: 0", messages)

    def test_replay_optional_corrections_mint_new_authority_and_preserve_originals(self):
        case = self.save()
        workbook_path = self.sources / "Administrator_NAV_Q3_2026.xlsx"
        before = workbook_path.read_bytes()
        with patch("app.runtime.replay.propose_patch", wraps=propose_patch) as mint:
            result = replay_case(case, output_dir=self.output, apply_verified_fixes=True)
        mint.assert_called_once()
        self.assertEqual(workbook_path.read_bytes(), before)
        path = Path(result["patches"][0]["output_file"])
        self.assertEqual(path.name, "Administrator_NAV_Q3_2026_FIXED.xlsx")
        workbook = load_workbook(path)
        try:
            self.assertEqual(workbook["Investor Fees"]["F6"].value, 37500)
            self.assertEqual(workbook["Audit Trail"]["C2"].value, "F6")
        finally:
            workbook.close()
        with self.assertRaisesRegex(ValueError, "new or empty"):
            replay_case(case, output_dir=self.output, apply_verified_fixes=True)

    def test_save_filters_unaccepted_checks_but_retains_historical_context(self):
        unresolved = self.finding("LP04")
        unresolved["check"]["inputs"][0]["evidence_id"] = "ev_nonexistent_unaccepted"
        unresolved["calculation"]["metadata"] = {}
        self.result["findings"].append(unresolved)
        case = self.save()
        saved = json.loads((case / "verification_plan.json").read_text())
        self.assertEqual(len(saved["checks"]), 1)
        result = replay_case(case, output_dir=self.output)
        self.assertEqual(len(result["findings"]), 1)
        self.assertEqual(len(result["prior_unverified_findings"]), 1)
        self.assertEqual(result["prior_unverified_findings"][0]["status"], "CANNOT_VERIFY")

    def test_synthetic_mode_cannot_be_saved_as_verified(self):
        self.result["mode"] = "SYNTHETIC_DEMO"
        with self.assertRaisesRegex(ValueError, "LIVE_MODEL"):
            self.save()
        self.assertFalse(self.cases.exists())

    def test_missing_live_discovery_or_semantic_review_trace_is_rejected(self):
        for stages in (("red_team",), ("contract_discovery",)):
            with self.subTest(stages=stages):
                self.result = self.mocked_live_result()
                self.result["model_calls"] = [call for call in self.result["model_calls"] if call["stage"] in stages]
                self.result["gemini_call_count"] = len(self.result["model_calls"])
                with self.assertRaises(ValueError):
                    self.save()

    def test_incomplete_source_audit_and_no_accepted_findings_are_rejected(self):
        self.result["ingestion_errors"] = [{"filename": "missing.pdf", "error": "INCOMPLETE"}]
        with self.assertRaisesRegex(ValueError, "INCOMPLETE_SOURCE_AUDIT"):
            self.save()
        self.result = self.mocked_live_result()
        self.result["findings"] = [self.finding("LP04")]
        with self.assertRaisesRegex(ValueError, "NO_ACCEPTED_REPLAY"):
            self.save()

    def test_modified_original_requires_fresh_audit_exact_error(self):
        case = self.save()
        source = self.sources / "LP03_Side_Letter.pdf"
        source.write_bytes(source.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "^SOURCE_CHANGED_REQUIRES_FRESH_AUDIT$"):
            replay_case(case, output_dir=self.output, apply_verified_fixes=True)
        self.assertFalse(self.output.exists())
        self.assertEqual(list_cases(self.cases)[0]["status"], "SOURCE_CHANGED_REQUIRES_FRESH_AUDIT")

    def test_missing_original_is_named_and_cannot_replay(self):
        case = self.save()
        (self.sources / "LP03_Side_Letter.pdf").unlink()
        with self.assertRaisesRegex(ValueError, "SOURCE_MISSING_REQUIRES_FRESH_AUDIT: LP03_Side_Letter.pdf"):
            replay_case(case, output_dir=self.output)

    def test_saved_file_corruption_and_missing_files_fail_closed(self):
        case = self.save()
        self.rewrite(case, "verifier_result.json", lambda value: value.update(untrusted="new"), refresh_digest=False)
        with self.assertRaisesRegex(ValueError, "digest"):
            replay_case(case, output_dir=self.output)
        (case / "trace.json").unlink()
        with self.assertRaisesRegex(ValueError, "eight required files"):
            replay_case(case, output_dir=self.output)

    def test_altered_final_values_rehashed_in_manifest_still_require_recalculation(self):
        case = self.save()
        self.rewrite(case, "verifier_result.json",
                     lambda value: value["findings"][0]["calculation"].update(expected="1.00"))
        with self.assertRaisesRegex(ValueError, "DETERMINISTIC_REPLAY_MISMATCH"):
            replay_case(case, output_dir=self.output)

    def test_altered_plan_hash_binding_is_rejected(self):
        case = self.save()
        self.rewrite(case, "verification_plan.json",
                     lambda value: value["checks"][0]["inputs"][0].update(evidence_id="ev_missing"))
        with self.assertRaisesRegex(ValueError, "plan bindings"):
            replay_case(case, output_dir=self.output)

    def test_deleted_normalized_evidence_cannot_supply_cached_answer(self):
        case = self.save()
        target = self.result["findings"][0]["check"]["compare_to"]["evidence_id"]
        def remove_reference(value):
            for document in value["documents"]:
                document["evidence"] = [ref for ref in document["evidence"] if ref["evidence_id"] != target]
        self.rewrite(case, "normalized_evidence.json", remove_reference)
        with self.assertRaises(ValueError):
            replay_case(case, output_dir=self.output)

    def test_cached_patch_amount_is_rechecked_not_deserialized_as_authority(self):
        case = self.save()
        self.rewrite(case, "patch_proposal.json",
                     lambda value: value["proposals"][0]["patch_proposal"].update(new_value="1.00"))
        with self.assertRaisesRegex(ValueError, "patch is not bound"):
            replay_case(case, output_dir=self.output, apply_verified_fixes=True)
        self.assertFalse(self.output.exists())

    def test_source_hashes_must_match_normalized_document_hashes(self):
        case = self.save()
        self.rewrite(case, "source_hashes.json", lambda value: value["sources"][0].update(document_hash="0" * 64))
        with self.assertRaisesRegex(ValueError, "source hash bindings"):
            replay_case(case, output_dir=self.output)

    def test_independent_executor_disagreement_cannot_be_accepted(self):
        case = self.save()
        def disagree(*args, **kwargs):
            result = execute(*args, **kwargs)
            result["expected"] = "1.00"
            return result
        with patch("app.runtime.replay.execute", side_effect=disagree):
            with self.assertRaisesRegex(ValueError, "DETERMINISTIC_REPLAY_MISMATCH"):
                replay_case(case, output_dir=self.output, apply_verified_fixes=True)

    def test_anomalies_cannot_be_promoted_by_relabeling_source(self):
        self.result["findings"][0]["check"]["check_type"] = "anomaly"
        self.result["findings"][0]["check"]["source"] = "relationship"
        with self.assertRaisesRegex(ValueError, "NO_ACCEPTED_REPLAY"):
            self.save()

    def test_money_without_currency_cannot_be_saved_as_accepted(self):
        self.result["findings"][0]["check"]["currency"] = None
        check = type(from_plan(self.plans["LP03"])).model_validate(self.result["findings"][0]["check"])
        self.result["findings"][0]["calculation"] = execute_check(check, self.store)
        with self.assertRaisesRegex(ValueError, "lacks currency"):
            self.save()

    def test_case_ids_and_existing_case_are_not_overwritten(self):
        for case_id in ("../outside", "/absolute", "..", "invalid/id"):
            with self.subTest(case_id=case_id), self.assertRaises(ValueError):
                save_case(self.result, self.store, case_id, self.cases)
        case = self.save()
        before = (case / "manifest.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.save()
        self.assertEqual((case / "manifest.json").read_bytes(), before)

    def test_oversized_saved_file_is_bounded(self):
        case = self.save()
        with patch("app.runtime.replay.MAX_CASE_FILE_BYTES", 32):
            with self.assertRaisesRegex(ValueError, "size bound"):
                replay_case(case, output_dir=self.output)

    def test_cli_replay_and_list_use_temporary_mocked_case_without_gemini(self):
        self.cases = self.root / "outputs" / "cases"
        case = self.save()
        captured = io.StringIO()
        with (patch("app.runtime.model_client.GeminiClient", side_effect=AssertionError("No Gemini in replay")) as model,
              redirect_stdout(captured)):
            code = main(["replay", "--case", str(case), "--output", str(self.output), "--apply-verified-fixes"])
        self.assertEqual(code, 0, captured.getvalue())
        model.assert_not_called()
        for text in ("MODE: VERIFIED_REPLAY", "Gemini calls: 0", "Evidence integrity: PASS", "Deterministic verification: PASS"):
            self.assertIn(text, captured.getvalue())
        result = json.loads((self.output / "result.json").read_text())
        self.assertEqual(result["findings"][0]["status"], "DISCREPANCY")
        self.assertEqual(result["gemini_call_count"], 0)
        self.assertTrue(Path(result["patches"][0]["output_file"]).is_file())
        captured = io.StringIO()
        with chdir(self.root), redirect_stdout(captured):
            self.assertEqual(main(["list"]), 0)
        for text in ("CASE ID", "STATUS", "FINDINGS", "CREATED", "lp03-test-fixture", "VERIFIED"):
            self.assertIn(text, captured.getvalue())

    def test_cli_changed_source_fails_visibly_without_output(self):
        case = self.save()
        source = self.sources / "LP03_Side_Letter.pdf"
        source.write_bytes(source.read_bytes() + b"changed")
        captured = io.StringIO()
        with redirect_stdout(captured):
            code = main(["replay", "--case", str(case), "--output", str(self.output), "--apply-verified-fixes"])
        self.assertEqual(code, 1)
        self.assertIn("SOURCE_CHANGED_REQUIRES_FRESH_AUDIT", captured.getvalue())
        self.assertNotIn("Deterministic verification: PASS", captured.getvalue())
        self.assertFalse(self.output.exists())

    def test_actual_parallel_audit_result_roundtrips_with_prior_abstentions(self):
        from test_fast_audit import ParallelModel

        plans = [from_plan(plan).model_dump(mode="json") for plan in self.plans.values()]
        model = ParallelModel(plans)
        result, store = asyncio.run(run_audit(
            self.sources, "Find material discrepancies.", output_dir=self.root / "mocked-live-run",
            model=model, mode="LIVE_MODEL", apply_verified_fixes=False,
        ))
        for entity in ("LP04", "LP06"):
            self.assertTrue(any(finding["entity_id"] == entity and finding["status"] == "CANNOT_VERIFY"
                                for finding in result["findings"]))
        self.assertTrue(any(finding["check"]["source"] == "anomaly" for finding in result["findings"]))
        case = save_case(result, store, "actual-parallel-mocked-fixture", self.cases)
        before_calls = len(model.calls)
        with patch("app.runtime.model_client.GeminiClient", side_effect=AssertionError("No Gemini in replay")):
            replayed = replay_case(case, output_dir=self.output, apply_verified_fixes=True)
        self.assertEqual(len(model.calls), before_calls)
        self.assertEqual(replayed["gemini_call_count"], 0)
        lp03 = next(finding for finding in replayed["findings"]
                    if finding["entity_id"] == "LP03" and finding["check"]["check_type"] == "annual_charge")
        self.assertEqual(lp03["status"], "DISCREPANCY")
        self.assertEqual(lp03["verified_calculation"]["expected"], "37500.00")
        self.assertEqual(lp03["verified_calculation"]["difference"], "12500.00")
        prior = replayed["prior_unverified_findings"]
        self.assertTrue(any(finding["entity_id"] == "LP04" for finding in prior))
        self.assertTrue(any(finding["entity_id"] == "LP06" for finding in prior))
        self.assertEqual(sum(output["patch_count"] for output in replayed["patches"]), 1)


if __name__ == "__main__":
    unittest.main()
