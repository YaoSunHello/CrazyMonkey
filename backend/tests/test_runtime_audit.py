"""End-to-end discovery and failure boundaries using fresh source documents."""
import csv
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook
from pydantic import ValidationError

from app.atlas.fixtures import generate_synthetic_pack, _write_pdf
from app.atlas.ingestion import normalize_file
from app.runtime.audit import investigate
from app.runtime.contracts import NumericInput, Operation, VerificationPlan
from app.runtime.investigation_evidence import EvidenceStore
from app.runtime.executor import execute
from app.runtime.planner import offline_plan


class RuntimeAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        generate_synthetic_pack(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def run_audit(self, **kwargs):
        return investigate(self.root, "Find material financial discrepancies.", **kwargs)

    def test_full_pack_recalculates_and_challenges(self):
        result, store = self.run_audit()
        findings = {f["entity_id"]: f for f in result["findings"]}
        self.assertEqual(result["checks_generated"], 6)
        lp03 = findings["LP03"]
        self.assertEqual(lp03["calculation"]["expected"], "37500.00")
        self.assertEqual(lp03["calculation"]["difference"], "12500.00")
        self.assertEqual(lp03["status"], "DISCREPANCY")
        self.assertEqual(lp03["red_team"]["status"], "PASS")
        self.assertEqual(findings["LP04"]["status"], "CANNOT_VERIFY")
        self.assertEqual(findings["LP06"]["status"], "CANNOT_VERIFY")
        self.assertEqual(findings["LP05"]["status"], "MATCH")
        for finding in result["findings"]:
            for source in finding["sources"]:
                self.assertEqual(source["original_value"], store.get(source["evidence_id"]).original_value)
                self.assertEqual(source["quote"], store.get(source["evidence_id"]).quote)

    def test_runtime_uses_changed_source_rate_not_fixture_answer(self):
        _write_pdf(self.root / "LP03_Side_Letter.pdf", title="LP03 Side Letter",
                   subtitle="Synthetic test", sections=[("Investor identity", [
                       "Investor ID: LP03. This letter supplements the Example Growth Fund III LPA for LP03 only.",
                       "The annual management fee applicable to LP03 is 1.7% of the Fee Base.",
                       "Effective from 1 January 2026; no end date is specified."])])
        # Deliberately false sidecars are not part of the supported input set.
        (self.root / "expected.json").write_text(json.dumps({"LP03": {"expected": "37500"}}))
        result, _ = self.run_audit()
        lp03 = next(f for f in result["findings"] if f["entity_id"] == "LP03")
        self.assertEqual(lp03["status"], "DISCREPANCY")
        self.assertEqual(lp03["calculation"]["expected"], "42500.00")
        self.assertEqual(lp03["calculation"]["difference"], "7500.00")

    def test_failed_input_prevents_partial_pack_certification(self):
        (self.root / "more_terms.pdf").write_bytes(b"not a PDF")
        result, _ = self.run_audit()
        self.assertTrue(result["ingestion_errors"])
        self.assertTrue(all(f["status"] == "CANNOT_VERIFY" for f in result["findings"]))

    def test_formula_cache_cannot_supply_reported_amount(self):
        path = self.root / "Administrator_NAV_Q3_2026.xlsx"
        workbook = load_workbook(path)
        workbook["Investor Fees"]["F6"] = "=50000"
        workbook.save(path)
        result, _ = self.run_audit()
        finding = next(f for f in result["findings"] if f["entity_id"] == "LP03")
        self.assertEqual(finding["status"], "CANNOT_VERIFY")

    def test_unrecognized_input_is_cannot_verify(self):
        other = self.root / "unrecognized"
        other.mkdir()
        (other / "data.csv").write_text("identifier,mystery\nW-9,123\n")
        result, _ = investigate(other, "Find discrepancies")
        self.assertFalse(result["findings"])
        self.assertTrue(result["cannot_verify"])

    def test_non_fee_relationship_is_discovered(self):
        other = self.root / "transactions"
        other.mkdir()
        with (other / "unfamiliar.csv").open("w") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Account ID", "Fund", "Currency", "Quantity", "Unit Price", "Line Total"])
            writer.writerow(["TR-908", "Synthetic Systems Fund", "GBP", "13", "17.25", "250"])
        result, _ = investigate(other, "Find discrepancies")
        finding = result["findings"][0]
        self.assertEqual(finding["plan"]["check_type"], "quantity_price")
        self.assertEqual(finding["status"], "DISCREPANCY")
        self.assertEqual(finding["calculation"]["expected"], "224.25")

    def test_source_change_detected_after_normalization(self):
        _, store = self.run_audit()
        (self.root / "LP03_Side_Letter.pdf").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            store.verify_originals()

    def test_evidence_store_owns_validated_document_copies(self):
        path = self.root / "LP03_Side_Letter.pdf"
        document = normalize_file(path, original_storage_key=str(path))
        store = EvidenceStore([document])
        document.evidence.clear()
        self.assertTrue(store.documents[0].evidence)
        self.assertIs(store.documents[0], store.docs[store.documents[0].document.document_id])

    def test_original_verification_reads_only_to_size_limit(self):
        from unittest.mock import patch
        path = self.root / "LP03_Side_Letter.pdf"
        store = EvidenceStore([normalize_file(path, original_storage_key=str(path))])
        with patch("app.runtime.investigation_evidence.MAX_FILE_BYTES", 8), patch.object(Path, "open") as opened:
            opened.return_value.__enter__.return_value.read.return_value = b"123456789"
            with self.assertRaisesRegex(ValueError, "changed"):
                store.verify_originals()
            opened.return_value.__enter__.return_value.read.assert_called_once_with(9)

    def test_fake_model_answers_and_bad_ids_are_never_accepted(self):
        class FakeModel:
            name = "fake-test-provider"
            def complete_json(self, system, payload):
                return {"checks": [], "cannot_verify": [], "expected_answer": 37500}
        result, _ = self.run_audit(model=FakeModel())
        self.assertFalse(result["findings"])
        self.assertIn("Planning failed closed", result["cannot_verify"][0])

    def test_one_bounded_model_repair_attempt(self):
        documents = [normalize_file(p, original_storage_key=str(p)) for p in sorted(self.root.iterdir()) if p.suffix in (".pdf", ".xlsx", ".csv")]
        plan = next(p for p in offline_plan(EvidenceStore(documents)).checks if p.entity_id == "LP03")
        bad = plan.model_dump(mode="json")
        bad["inputs"]["base"]["evidence_id"] = "ev_nonexistent"
        class FakeModel:
            name = "test-only-repair-model"
            calls = 0
            def complete_json(self, system, payload):
                self.calls += 1
                if self.calls == 1:
                    return {"checks": [bad], "cannot_verify": []}
                if self.calls == 2:
                    return {"checks": [plan.model_dump(mode="json")], "cannot_verify": []}
                return {"status": "PASS", "reasons": [], "evidence_ids": plan.context_evidence_ids}
        model = FakeModel()
        result, _ = self.run_audit(model=model)
        self.assertEqual(model.calls, 3)
        self.assertTrue(result["repair_attempted"])
        self.assertEqual(len(result["attempts"]), 2)
        self.assertEqual(result["findings"][0]["status"], "DISCREPANCY")

    def test_model_can_propose_an_addition_outside_offline_templates(self):
        other = self.root / "bespoke"
        other.mkdir()
        path = other / "schedule.csv"
        path.write_text("Account ID,Fund,Currency,Gross Amount,Adjustment,Reported Amount\nA-42,Demo Fund,GBP,900,17,950\n")
        document = normalize_file(path, original_storage_key=str(path))
        refs = {r.csv_column: r for r in document.evidence}
        plan = VerificationPlan(
            check_id="bespoke", title="Gross plus adjustment", check_type="model_proposed",
            entity_id="A-42", fund_name="Demo Fund", currency="GBP", rationale="Test-only independent semantic review of a source addition.",
            inputs={key: NumericInput(evidence_id=refs[label].evidence_id, unit="money")
                    for key, label in (("gross", "Gross Amount"), ("adjustment", "Adjustment"), ("reported", "Reported Amount"))},
            reported_input="reported", operation=Operation(operation="add", operands=["gross", "adjustment"]),
            context_evidence_ids=[r.evidence_id for r in document.evidence])
        class FakeModel:
            name = "test-only-semantic-model"
            calls = 0
            def complete_json(self, system, payload):
                self.calls += 1
                if self.calls == 1:
                    return {"checks": [plan.model_dump(mode="json")], "cannot_verify": []}
                return {"status": "PASS", "reasons": [], "evidence_ids": plan.context_evidence_ids}
        model = FakeModel()
        result, _ = investigate(other, "Reconcile adjusted charges.", model=model)
        self.assertEqual(model.calls, 2)
        self.assertEqual(result["findings"][0]["status"], "DISCREPANCY")
        self.assertEqual(result["findings"][0]["calculation"]["expected"], "917.00")
        self.assertEqual(result["findings"][0]["calculation"]["difference"], "33.00")


class DslBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name) / "numbers.csv"
        path.write_text("label,value\na,0.1\nb,0.2\nc,0.30\n")
        self.store = EvidenceStore([normalize_file(path, original_storage_key=str(path))])
        refs = [r for r in self.store.refs.values() if r.csv_column == "value"]
        self.plan = VerificationPlan(check_id="t", title="test", check_type="model_proposed", entity_id="a",
                    fund_name="test", currency="GBP", rationale="test-only DSL boundary",
                    inputs={key: NumericInput(evidence_id=ref.evidence_id) for key, ref in zip(("a", "b", "reported"), refs)},
                    reported_input="reported", operation=Operation(operation="add", operands=["a", "b"]),
                    context_evidence_ids=[refs[0].evidence_id])

    def tearDown(self):
        self.temp.cleanup()

    def test_decimal_arithmetic(self):
        self.assertEqual(execute(self.plan, self.store)["expected"], "0.30")

    def test_expected_cannot_reuse_reported(self):
        payload = self.plan.model_dump()
        payload["operation"]["operands"] = ["reported", "a", "b"]
        with self.assertRaises(ValidationError):
            VerificationPlan.model_validate(payload)

    def test_code_is_not_an_operation(self):
        with self.assertRaises(ValidationError):
            Operation(operation="__import__('os').system('true')", operands=["a", "b"])

    def test_deep_expression_rejected(self):
        payload = self.plan.model_dump()
        node = {"operation": "add", "operands": ["a", "b"]}
        for _ in range(8):
            node = {"operation": "add", "operands": ["a", node]}
        payload["operation"] = node
        with self.assertRaises(ValidationError):
            VerificationPlan.model_validate(payload)

    def test_partial_cell_token_rejected(self):
        spec = self.plan.inputs["a"].model_copy(update={"token": "1"})
        with self.assertRaises(ValueError):
            self.store.number(spec)

    def test_complete_pdf_rate_can_end_with_sentence_punctuation(self):
        path = Path(self.temp.name) / "rate.pdf"
        _write_pdf(path, title="Rate", subtitle="Synthetic numeric boundary test",
                   sections=[("Terms", ["The annual fee is 1.5%. A later proposal lists 11.5%."])])
        store = EvidenceStore([normalize_file(path, original_storage_key=str(path))])
        ref = next(r for r in store.refs.values() if "1.5%" in (r.quote or ""))
        self.assertEqual(store.number(NumericInput(evidence_id=ref.evidence_id, token="1.5%", unit="rate")), Decimal("0.015"))
        with self.assertRaises(ValueError):
            store.number(NumericInput(evidence_id=ref.evidence_id, token="5%", unit="rate"))

    def test_pdf_numeric_token_cannot_drop_decimal_or_group_digits(self):
        path = Path(self.temp.name) / "number.pdf"
        _write_pdf(path, title="Number", subtitle="Synthetic numeric boundary test",
                   sections=[("Terms", ["The amount is 1,500.25."])])
        store = EvidenceStore([normalize_file(path, original_storage_key=str(path))])
        ref = next(r for r in store.refs.values() if "1,500.25" in (r.quote or ""))
        for token in ("1", "1,500", "500.25", "25"):
            with self.subTest(token=token), self.assertRaises(ValueError):
                store.number(NumericInput(evidence_id=ref.evidence_id, token=token, unit="money"))
        self.assertEqual(store.number(NumericInput(evidence_id=ref.evidence_id, token="1,500.25", unit="money")), Decimal("1500.25"))


if __name__ == "__main__":
    unittest.main()
