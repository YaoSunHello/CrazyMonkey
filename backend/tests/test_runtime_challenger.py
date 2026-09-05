"""The challenger must reject plausible arithmetic with incorrect source meaning."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.atlas.fixtures import generate_synthetic_pack, _write_pdf
from app.atlas.ingestion import normalize_file
from app.runtime.challenger import challenge
from app.runtime.contracts import ModelChallenge, NumericInput, Operation, VerificationPlan
from app.runtime.investigation_evidence import EvidenceStore, source_text
from app.runtime.executor import execute


class IndependentChallengerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.folder = Path(self.temp.name)
        generate_synthetic_pack(self.folder)
        documents = [normalize_file(p, original_storage_key=str(p)) for p in sorted(self.folder.iterdir())
                     if p.suffix in {".pdf", ".xlsx", ".csv"}]
        self.store = EvidenceStore(documents)

    def tearDown(self):
        self.temp.cleanup()

    def plan(self, investor="LP03", rate="1.5%", rate_document=None):
        row = int(investor[-2:]) + 3
        def cell(coord):
            return next(r for r in self.store.refs.values() if r.cell == coord and r.sheet == "Investor Fees")
        filename = rate_document or investor + "_Side_Letter.pdf"
        document = next(d for d in self.store.documents if d.document.filename == filename)
        rate_ref = next(r for r in document.evidence if rate in source_text(r) and "annual" in source_text(r))
        return VerificationPlan(
            check_id="test", title="Annual management fee", check_type="annual_charge",
            entity_id=investor, fund_name="Example Growth Fund III", currency="GBP",
            rationale="Check the independently evidenced annual term against the amount charged.",
            inputs={
                "base": NumericInput(evidence_id=cell(f"C{row}").evidence_id, unit="money"),
                "rate": NumericInput(evidence_id=rate_ref.evidence_id, token=rate, unit="rate"),
                "factor": NumericInput(evidence_id=cell(f"E{row}").evidence_id, unit="factor"),
                "reported": NumericInput(evidence_id=cell(f"F{row}").evidence_id, unit="money")},
            reported_input="reported", operation=Operation(operation="multiply", operands=["base", "rate", "factor"]),
            context_evidence_ids=[r.evidence_id for r in self.store.refs.values()])

    def test_lp03_independently_challenged_passes(self):
        plan = self.plan()
        result = execute(plan, self.store)
        self.assertEqual(result["expected"], "37500.00")
        self.assertEqual(result["difference"], "12500.00")
        reviewed = challenge(plan, result, self.store)
        self.assertEqual(reviewed.status, "PASS", reviewed.reasons)
        self.assertTrue(all(reviewed.checks.values()))

    def test_arithmetic_tampering_rejected(self):
        plan = self.plan()
        result = execute(plan, self.store)
        result["expected"] = "35000"
        self.assertEqual(challenge(plan, result, self.store).status, "CHALLENGE")

    def test_investor_swap_rejected_even_same_rate(self):
        plan = self.plan(rate_document="LP02_Side_Letter.pdf")
        self.assertEqual(challenge(plan, execute(plan, self.store), self.store).status, "CHALLENGE")

    def test_default_does_not_overrule_existing_applicable_override(self):
        plan = self.plan(rate="2.0%", rate_document="Example_Growth_Fund_III_LPA.pdf")
        self.assertEqual(challenge(plan, execute(plan, self.store), self.store).status, "CHALLENGE")

    def test_future_override_does_not_replace_default(self):
        good = self.plan("LP05", "2.0%", "Example_Growth_Fund_III_LPA.pdf")
        reviewed = challenge(good, execute(good, self.store), self.store)
        self.assertEqual(reviewed.status, "PASS", reviewed.reasons)
        bad = self.plan("LP05")
        self.assertEqual(challenge(bad, execute(bad, self.store), self.store).status, "CHALLENGE")

    def test_no_variation_uses_default(self):
        plan = self.plan("LP01", "2.0%", "Example_Growth_Fund_III_LPA.pdf")
        reviewed = challenge(plan, execute(plan, self.store), self.store)
        self.assertEqual(reviewed.status, "PASS", reviewed.reasons)

    def test_base_contradiction_rejected(self):
        plan = self.plan("LP04", "2.0%", "Example_Growth_Fund_III_LPA.pdf")
        self.assertEqual(challenge(plan, execute(plan, self.store), self.store).status, "CHALLENGE")

    def test_expected_missing_agreement_blocks_assertion(self):
        plan = self.plan("LP06", "2.0%", "Example_Growth_Fund_III_LPA.pdf")
        self.assertEqual(challenge(plan, execute(plan, self.store), self.store).status, "INSUFFICIENT_EVIDENCE")

    def test_forged_evidence_id_rejected(self):
        plan = self.plan()
        result = execute(plan, self.store)
        plan.context_evidence_ids.append("ev_not_in_atlas")
        self.assertEqual(challenge(plan, result, self.store).status, "CHALLENGE")

    def test_repeated_operand_rejected(self):
        plan = self.plan()
        plan.operation.operands.append("base")
        self.assertEqual(challenge(plan, execute(plan, self.store), self.store).status, "CHALLENGE")

    def test_nested_annual_operation_rejected_without_exception(self):
        plan = self.plan()
        plan.operation = Operation(operation="multiply", operands=["base", Operation(operation="multiply", operands=["rate", "factor"])])
        self.assertEqual(challenge(plan, execute(plan, self.store), self.store).status, "CHALLENGE")

    def test_wrong_currency_rejected(self):
        plan = self.plan()
        plan.currency = "EUR"
        self.assertEqual(challenge(plan, execute(plan, self.store), self.store).status, "CHALLENGE")

    def test_configured_tolerance_is_independently_checked(self):
        from decimal import Decimal
        plan = self.plan()
        tolerance = Decimal("15000")
        result = execute(plan, self.store, tolerance)
        self.assertEqual(challenge(plan, result, self.store, tolerance).status, "PASS")
        self.assertEqual(challenge(plan, result, self.store).status, "CHALLENGE")

    def generic_plan(self, kind):
        path = self.folder / "generic.csv"
        if kind == "quantity_price":
            path.write_text("Account,Fund,Quantity,Unit price,Line total,Currency\nACCT-9,Generic Fund,3,17,55,GBP\n")
            fields = {"quantity": "Quantity", "price": "Unit price", "reported": "Line total"}
            operation = "multiply"
        else:
            path.write_text("Account,Fund,Gross,Deductions,Net,Currency\nACCT-9,Generic Fund,500,30,460,GBP\n")
            fields = {"gross": "Gross", "deductions": "Deductions", "reported": "Net"}
            operation = "subtract"
        store = EvidenceStore([normalize_file(path, original_storage_key=str(path))])
        refs = {r.csv_column: r for r in store.refs.values()}
        plan = VerificationPlan(
            check_id="generic", title="Source row relationship", check_type=kind,
            entity_id="ACCT-9", fund_name="Generic Fund", currency="GBP", rationale="Compare independently calculated line amount.",
            inputs={key: NumericInput(evidence_id=refs[column].evidence_id, unit="number" if key == "quantity" else "money")
                    for key, column in fields.items()},
            reported_input="reported", operation=Operation(operation=operation, operands=[key for key in fields if key != "reported"]),
            context_evidence_ids=list(store.refs))
        return plan, store

    def test_quantity_price_source_labels_pass(self):
        plan, store = self.generic_plan("quantity_price")
        reviewed = challenge(plan, execute(plan, store), store)
        self.assertEqual(reviewed.status, "PASS", reviewed.reasons)

    def test_gross_less_deductions_source_labels_pass(self):
        plan, store = self.generic_plan("gross_less_deductions")
        reviewed = challenge(plan, execute(plan, store), store)
        self.assertEqual(reviewed.status, "PASS", reviewed.reasons)

    def test_reversed_subtraction_fails_semantic_proof(self):
        plan, store = self.generic_plan("gross_less_deductions")
        plan.operation.operands.reverse()
        self.assertEqual(challenge(plan, execute(plan, store), store).status, "INSUFFICIENT_EVIDENCE")

    def test_generic_duplicate_operand_does_not_pass(self):
        plan, store = self.generic_plan("quantity_price")
        plan.operation.operands.append("quantity")
        self.assertEqual(challenge(plan, execute(plan, store), store).status, "INSUFFICIENT_EVIDENCE")

    def replace_terms(self, filename, clauses):
        _write_pdf(self.folder / filename, title="Synthetic contractual terms", subtitle="Regression source",
                   sections=[("Applicable terms", clauses)])
        self.store = EvidenceStore([normalize_file(p, original_storage_key=str(p))
                                    for p in sorted(self.folder.iterdir()) if p.suffix in {".pdf", ".xlsx", ".csv"}])

    def personal_terms(self, extra=(), rate_clause=None):
        self.replace_terms("LP03_Side_Letter.pdf", [
            "Example Growth Fund III. Investor ID: LP03.",
            rate_clause or "The annual management fee is 1.5% of the Fee Base.",
            "Effective from 1 January 2026.", *extra])

    def test_contractual_factor_conflict_cannot_use_quarter_assumption(self):
        self.replace_terms("Example_Growth_Fund_III_LPA.pdf", [
            "Example Growth Fund III.", "The default annual management fee is 2.0% of Fee Base.",
            "For Q3 2026 the quarterly fee is annual rate x 0.20 x Fee Base."])
        plan = self.plan()
        reviewed = challenge(plan, execute(plan, self.store), self.store)
        self.assertEqual(reviewed.status, "CHALLENGE")
        self.assertFalse(reviewed.checks["period_interpretation"])

    def test_factor_for_different_reporting_period_is_not_support(self):
        self.replace_terms("Example_Growth_Fund_III_LPA.pdf", [
            "Example Growth Fund III.", "The default annual management fee is 2.0% of Fee Base.",
            "For Q2 2025 the quarterly fee is annual rate x 0.25 x Fee Base."])
        plan = self.plan()
        reviewed = challenge(plan, execute(plan, self.store), self.store)
        self.assertEqual(reviewed.status, "INSUFFICIENT_EVIDENCE")
        self.assertFalse(reviewed.checks["period_interpretation"])

    def test_personal_adjustment_rounding_scale_and_currency_block_simple_charge(self):
        for clause in (
            "The charge is subject to a rebate of GBP 1,000.",
            "Round all fee amounts down to the nearest pound.",
            "All fee amounts are expressed in thousands of pounds.",
            "All fee amounts are payable in USD.",
        ):
            with self.subTest(clause=clause):
                self.personal_terms([clause])
                plan = self.plan()
                reviewed = challenge(plan, execute(plan, self.store), self.store)
                self.assertEqual(reviewed.status, "INSUFFICIENT_EVIDENCE", reviewed.reasons)

    def test_model_cannot_choose_first_of_ambiguous_rates(self):
        self.personal_terms(rate_clause="The annual management fee is 1.5% or 2.0% pending confirmation.")
        plan = self.plan()
        reviewed = challenge(plan, execute(plan, self.store), self.store)
        self.assertEqual(reviewed.status, "CHALLENGE")
        self.assertFalse(reviewed.checks["rate_applicability"])

    def test_scaled_reported_amount_is_not_accepted(self):
        plan, store = self.generic_plan("quantity_price")
        path = self.folder / "generic.csv"
        path.write_text(path.read_text().replace("Line total", "Line total (GBP 000)"))
        new_store = EvidenceStore([normalize_file(path, original_storage_key=str(path))])
        new_refs = {r.csv_column: r for r in new_store.refs.values()}
        mapping = {"quantity": "Quantity", "price": "Unit price", "reported": "Line total (GBP 000)"}
        for name, column in mapping.items():
            plan.inputs[name].evidence_id = new_refs[column].evidence_id
        plan.context_evidence_ids = list(new_store.refs)
        reviewed = challenge(plan, execute(plan, new_store), new_store)
        self.assertEqual(reviewed.status, "INSUFFICIENT_EVIDENCE", reviewed.reasons)

    def test_novel_relationship_requires_separate_semantic_review(self):
        plan, store = self.generic_plan("gross_less_deductions")
        plan.check_type = "model_proposed"
        plan.operation = Operation(operation="add", operands=["gross", "deductions"])
        result = execute(plan, store)
        review = ModelChallenge(status="PASS", reasons=[], evidence_ids=list(store.refs))
        self.assertEqual(challenge(plan, result, store).status, "INSUFFICIENT_EVIDENCE")
        self.assertEqual(challenge(plan, result, store, semantic_review=review).status, "PASS")
        review.evidence_ids = ["ev_forged"]
        self.assertEqual(challenge(plan, result, store, semantic_review=review).status, "CHALLENGE")

    def test_semantic_review_cannot_override_currency_arithmetic_or_known_template(self):
        plan, store = self.generic_plan("gross_less_deductions")
        review = ModelChallenge(status="PASS", reasons=[], evidence_ids=list(store.refs))
        plan.operation.operands.reverse()
        result = execute(plan, store)
        self.assertEqual(challenge(plan, result, store, semantic_review=review).status, "INSUFFICIENT_EVIDENCE")
        plan.check_type = "model_proposed"
        result["expected"] = "123.00"
        self.assertEqual(challenge(plan, result, store, semantic_review=review).status, "CHALLENGE")
        result = execute(plan, store)
        plan.currency = "EUR"
        self.assertEqual(challenge(plan, result, store, semantic_review=review).status, "CHALLENGE")


if __name__ == "__main__":
    unittest.main()
