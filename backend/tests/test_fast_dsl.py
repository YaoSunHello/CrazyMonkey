"""Source-backed operation and failure-boundary tests for the finite fast DSL."""
from __future__ import annotations

import unittest
from decimal import Decimal
from unittest.mock import patch

from pydantic import ValidationError

from app.atlas.models import NormalizedDocument, SourceDocument, SourceRef
from app.runtime.contracts import NumericInput
from app.runtime.fast_dsl import FastCheck, FastPlanBatch, execute_check, parse_fast_checks
from app.runtime.investigation_evidence import EvidenceStore


class FastDslTests(unittest.TestCase):
    def sources(self, *values, pdf=False):
        document = SourceDocument(document_id="test-document", filename="source.pdf" if pdf else "source.csv",
                                  document_hash="a" * 64, role="SUPPORTING", mime_type="application/pdf" if pdf else "text/csv",
                                  size_bytes=1, extraction_status="COMPLETE", original_storage_key="unused-test-path")
        refs = [SourceRef(evidence_id=f"ev_{index}", document_id=document.document_id,
                          document_hash=document.document_hash, kind="PDF_TEXT" if pdf else "CSV_CELL",
                          page=1 if pdf else None, csv_row=None if pdf else index + 1,
                          csv_column=None if pdf else "value",
                          quote=str(value) if pdf else None, original_value=None if pdf else str(value))
                for index, value in enumerate(values)]
        return EvidenceStore([NormalizedDocument(document=document, evidence=refs)])

    def spec(self, index, unit="number", token=None):
        return NumericInput(evidence_id=f"ev_{index}", unit=unit, token=token)

    def check(self, operation, count=2, comparator=True, **kwargs):
        return FastCheck(check_id="check-1", title="Source calculation", entity_id="account-A",
                         operation=operation, inputs=[self.spec(index, "rate" if operation == "PERCENT_OF" and index == 1 else "number") for index in range(count)],
                         compare_to=self.spec(count) if comparator else None,
                         rationale="Compare the evidence-backed source values.", **kwargs)

    def test_all_numeric_operations(self):
        cases = [
            ("ADD", (4, 7, 11), "11"), ("SUBTRACT", (13, 8, 5), "5"),
            ("MULTIPLY", (6, 7, 42), "42"), ("DIVIDE", (15, 4, "3.75"), "3.75"),
            ("SUM", (3, 4, 5, 12), "12"),
        ]
        for operation, values, expected in cases:
            with self.subTest(operation=operation):
                result = execute_check(self.check(operation, count=len(values) - 1), self.sources(*values))
                self.assertEqual(result["status"], "MATCH")
                self.assertEqual(result["expected"], expected)
                self.assertEqual(Decimal(result["difference"]), 0)
                self.assertFalse(result["metadata"]["semantic_approval"])

    def test_single_value_sum_is_permitted(self):
        result = execute_check(self.check("SUM", count=1), self.sources("7.125", "7.125"))
        self.assertEqual(result["expected"], "7.125")
        self.assertEqual(result["status"], "MATCH")

    def test_percent_tokens_and_fractional_rates(self):
        for rate in ("1.5%", "0.015"):
            with self.subTest(rate=rate):
                check = self.check("PERCENT_OF", currency="GBP")
                check.inputs = [self.spec(0, "money"), self.spec(1, "rate")]
                result = execute_check(check, self.sources("10000000", rate, "150000"))
                self.assertEqual(result["expected"], "150000.00")
                self.assertEqual(result["status"], "MATCH")

    def test_exact_management_fee_discrepancy(self):
        check = self.check("MULTIPLY", count=3, currency="GBP", check_type="annual_charge")
        check.inputs = [self.spec(0, "money"), self.spec(1, "rate"), self.spec(2, "factor")]
        check.compare_to = self.spec(3, "money")
        result = execute_check(check, self.sources("10000000", "1.5%", "0.25", "50000"))
        self.assertEqual(result["status"], "DISCREPANCY")
        self.assertEqual(result["expected"], "37500.00")
        self.assertEqual(result["reported"], "50000")
        self.assertEqual(result["difference"], "12500.00")

    def test_money_rounding_is_half_up_and_tolerance_is_inclusive(self):
        check = self.check("MULTIPLY", currency="USD")
        result = execute_check(check, self.sources("1.005", "1", "1.02"))
        self.assertEqual(result["expected"], "1.01")
        self.assertEqual(result["status"], "MATCH")

    def test_decimal_addition_is_exact(self):
        result = execute_check(self.check("ADD", currency="GBP"), self.sources("0.1", "0.2", "0.30"))
        self.assertEqual(result["expected"], "0.30")
        self.assertEqual(result["difference"], "0.00")

    def test_predicates_compare_decimals_or_exact_text(self):
        for operation, values, expected_status in [
            ("EQUAL", ("1.00", "1"), "MATCH"), ("EQUAL", ("alpha", "Alpha"), "DISCREPANCY"),
            ("NOT_EQUAL", ("alpha", "beta"), "MATCH"), ("NOT_EQUAL", ("0.10", "0.1"), "DISCREPANCY"),
            ("EQUAL", ("USD", "USD"), "MATCH"),
        ]:
            with self.subTest(operation=operation, values=values):
                result = execute_check(self.check(operation, comparator=False), self.sources(*values))
                self.assertEqual(result["status"], expected_status)
                self.assertEqual(result["expected"], "true")

    def test_dates_use_explicit_iso_or_named_month_sources(self):
        for operation, values, status in [
            ("DATE_BEFORE", ("2028-01-01", "30 June 2028"), "MATCH"),
            ("DATE_AFTER", ("July 1, 2028", "2028-06-30"), "MATCH"),
            ("DATE_BEFORE", ("2028-06-30", "2028-06-30"), "DISCREPANCY"),
            ("DATE_AFTER", ("2028-01-01T13:00:00Z", "2028-01-01T12:00:00+00:00"), "MATCH"),
            ("DATE_BEFORE", ("2028-01-01 10:00:00", "2028-01-01 11:00:00"), "MATCH"),
        ]:
            with self.subTest(operation=operation, values=values):
                result = execute_check(self.check(operation, comparator=False), self.sources(*values))
                self.assertEqual(result["status"], status, result["reasons"])

    def test_ambiguous_invalid_mixed_or_unzoned_dates_abstain(self):
        for left, right in [("01/02/2028", "2028-03-01"), ("2028-02-30", "2028-03-01"),
                            ("2028-01-01", "2028-01-01T12:00:00"),
                            ("2028-01-01T12:00:00", "2028-01-01T13:00:00Z")]:
            with self.subTest(left=left, right=right):
                self.assertEqual(execute_check(self.check("DATE_BEFORE", comparator=False),
                                              self.sources(left, right))["status"], "CANNOT_VERIFY")

    def test_pdf_date_tokens_are_exactly_source_backed(self):
        check = self.check("DATE_BEFORE", comparator=False)
        check.inputs = [self.spec(0, token="1 January 2028"), self.spec(1, token="30 June 2028")]
        store = self.sources("Effective on 1 January 2028.", "Expires on 30 June 2028.", pdf=True)
        self.assertEqual(execute_check(check, store)["status"], "MATCH")
        check.inputs[0].token = "1 January 2027"
        self.assertEqual(execute_check(check, store)["status"], "CANNOT_VERIFY")

    def test_unknown_input_comparator_and_context_all_fail_before_calculation(self):
        for location in ("input", "comparator", "context"):
            with self.subTest(location=location):
                check = self.check("ADD")
                if location == "input":
                    check.inputs[0].evidence_id = "nonexistent"
                elif location == "comparator":
                    check.compare_to.evidence_id = "nonexistent"
                else:
                    check.context_evidence_ids = ["nonexistent"]
                store = self.sources(1, 2, 3)
                with patch.object(store, "number", wraps=store.number) as number:
                    result = execute_check(check, store)
                self.assertEqual(result["status"], "CANNOT_VERIFY")
                self.assertEqual(number.call_count, 0)
                self.assertEqual(result["evidence_ids"], [])

    def test_numeric_check_without_comparator_cannot_assert_a_finding(self):
        result = execute_check(self.check("ADD", comparator=False), self.sources(1, 2))
        self.assertEqual(result["status"], "CANNOT_VERIFY")
        self.assertIn("comparator", result["reasons"][0])

    def test_division_by_zero_and_missing_number_abstain(self):
        for operation, values in [("DIVIDE", (1, 0, 1)), ("ADD", ("unavailable", 2, 3))]:
            with self.subTest(operation=operation):
                self.assertEqual(execute_check(self.check(operation), self.sources(*values))["status"], "CANNOT_VERIFY")

    def test_source_hash_mutation_is_rejected(self):
        store = self.sources(1, 2, 3)
        store.refs["ev_0"].document_hash = "b" * 64
        result = execute_check(self.check("ADD"), store)
        self.assertEqual(result["status"], "CANNOT_VERIFY")
        self.assertIn("hash", result["reasons"][0])

    def test_mutated_evidence_identity_is_rejected(self):
        store = self.sources(1, 2, 3)
        store.refs["ev_0"].evidence_id = "ev_foreign"
        self.assertEqual(execute_check(self.check("ADD"), store)["status"], "CANNOT_VERIFY")

    def test_equality_cannot_strip_percentage_marker_from_pdf(self):
        check = self.check("EQUAL", comparator=False)
        check.inputs[0].token = "1.5"
        store = self.sources("The annual rate is 1.5%.", "1.5", pdf=True)
        self.assertEqual(execute_check(check, store)["status"], "CANNOT_VERIFY")

    def test_source_comparator_alias_and_partial_cell_tokens_rejected(self):
        check = self.check("ADD")
        check.compare_to = self.spec(0)
        self.assertEqual(execute_check(check, self.sources(1, 2))["status"], "CANNOT_VERIFY")
        check = self.check("ADD")
        check.inputs[0].token = "1"
        self.assertEqual(execute_check(check, self.sources(12, 2, 14))["status"], "CANNOT_VERIFY")

    def test_formula_boolean_and_missing_values_rejected(self):
        for change in ({"formula": "=1"}, {"cache_status": "PRESENT_UNVERIFIED"},
                       {"data_type": "boolean"}, {"original_value": " "}):
            with self.subTest(change=change):
                store = self.sources(1, 2, 3)
                for name, value in change.items():
                    setattr(store.refs["ev_0"], name, value)
                self.assertEqual(execute_check(self.check("ADD"), store)["status"], "CANNOT_VERIFY")

    def test_currency_conflicts_rejected(self):
        for values in [("GBP 1", "USD 2", "GBP 3"), ("EUR 1", "EUR 2", "EUR 3")]:
            with self.subTest(values=values):
                result = execute_check(self.check("ADD", currency="GBP"), self.sources(*values))
                self.assertEqual(result["status"], "CANNOT_VERIFY")

    def test_rate_and_calculation_bounds_are_enforced(self):
        check = self.check("PERCENT_OF")
        check.inputs[1].unit = "rate"
        for rate in ("1.5", "150%", "-1%"):
            with self.subTest(rate=rate):
                self.assertEqual(execute_check(check, self.sources(100, rate, 150))["status"], "CANNOT_VERIFY")
        self.assertEqual(execute_check(self.check("MULTIPLY"), self.sources("1000000000000000000000000", "1000000000000000000000000", 1))["status"], "CANNOT_VERIFY")

    def test_invalid_tolerance_is_rejected(self):
        for tolerance in (0.01, Decimal("NaN"), Decimal("-0.01"), Decimal("Infinity")):
            with self.subTest(tolerance=tolerance):
                self.assertEqual(execute_check(self.check("ADD"), self.sources(1, 2, 3), tolerance)["status"], "CANNOT_VERIFY")

    def test_plan_schema_rejects_code_wrong_arity_and_answer_fields(self):
        valid = self.check("ADD").model_dump()
        for mutation in ({"operation": "eval"}, {"inputs": [valid["inputs"][0]]},
                         {"expected": 3}, {"operation": "DIVIDE", "inputs": valid["inputs"] * 2}):
            with self.subTest(mutation=mutation), self.assertRaises(ValidationError):
                parse_fast_checks({"checks": [{**valid, **mutation}]})
        result = execute_check({**valid, "expected": "3"}, self.sources(1, 2, 3))
        self.assertEqual(result["status"], "CANNOT_VERIFY")

    def test_batch_bounds_unique_ids_and_supported_metadata(self):
        valid = self.check("ADD", source="relationship", check_type="model_proposed").model_dump()
        parsed = parse_fast_checks({"checks": [valid], "cannot_verify": ["Missing statement"]})
        self.assertEqual(parsed[0].source, "relationship")
        self.assertEqual(parsed[0].check_type, "model_proposed")
        with self.assertRaises(ValidationError):
            FastPlanBatch.model_validate({"checks": [valid, valid]})
        with self.assertRaises(ValidationError):
            parse_fast_checks({"checks": [{**valid, "check_id": f"check-{index}"} for index in range(41)]})
        with self.assertRaises(ValidationError):
            parse_fast_checks({"checks": [valid], "answer": "known"})

    def test_predicate_cannot_ignore_a_comparator(self):
        with self.assertRaises(ValidationError):
            self.check("EQUAL")


if __name__ == "__main__":
    unittest.main()
