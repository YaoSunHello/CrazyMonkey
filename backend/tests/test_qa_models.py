"""Adversarial checks of the implemented ATLAS contracts, not a fee verifier."""

from __future__ import annotations

import copy
import unittest
from decimal import Decimal

from pydantic import ValidationError

from app.atlas.models import (
    Calculation,
    Finding,
    InvestorRule,
    NormalizedDocument,
    ReviewSnapshot,
    SourceDocument,
    SourceRef,
    VerifierResult,
)


def source_ref() -> dict:
    return {
        "evidence_id": "ev_1",
        "document_id": "doc_1",
        "document_hash": "a" * 64,
        "kind": "WORKBOOK_CELL",
        "sheet": "Fees",
        "cell": "B3",
        "original_value": "50000",
    }


def source_document() -> dict:
    return {
        "document_id": "doc_1",
        "filename": "Fees.xlsx",
        "document_hash": "a" * 64,
        "role": "NAV_WORKBOOK",
        "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "size_bytes": 100,
        "extraction_status": "COMPLETE",
        "original_storage_key": "source/Fees.xlsx",
    }


def rule() -> dict:
    return {
        "rule_id": "rule_1",
        "rule_version": 1,
        "investor_id": "LP03",
        "identity_evidence_ids": ["ev_1"],
        "applicable_annual_rate": "0.015",
        "fee_basis": "Commitment",
        "fee_base": "10000000",
        "currency": "GBP",
        "period_start": "2026-07-01",
        "period_end": "2026-09-30",
        "period_factor": "0.25",
        "applicability_state": "APPLIES",
        "applicability_rationale": "Synthetic model validation example.",
        "input_evidence": {"reported_amount": ["ev_1"]},
        "extraction_state": "SUPPORTED",
    }


def calculation() -> dict:
    return {
        "calculation_id": "calc_1",
        "rule_id": "rule_1",
        "rule_version": 1,
        "investor_id": "LP03",
        "formula_code": "ANNUAL_RATE_X_PERIOD_FACTOR_X_FEE_BASE",
        "formula_description": "Annual rate times period factor times fee base",
        "fee_base": "10000000",
        "annual_rate": "0.015",
        "period_factor": "0.25",
        "currency": "GBP",
        "tolerance": "0.01",
        "expected_amount": "37500",
        "reported_amount": "50000",
        "difference": "12500",
        "input_evidence": {"reported_amount": ["ev_1"]},
    }


def verifier() -> dict:
    return {
        "verifier_result_id": "verifier_1",
        "investor_id": "LP03",
        "rule_id": "rule_1",
        "calculation_id": "calc_1",
        "status": "DISCREPANCY",
        "checks": [{"code": "TEST", "passed": True, "explanation": "Test contract."}],
        "explanation": "Synthetic contract example; no live verifier executed.",
    }


def finding() -> dict:
    return {
        "finding_id": "finding_1",
        "investor_id": "LP03",
        "reported_value": "50000",
        "expected_value": "37500",
        "difference": "12500",
        "currency": "GBP",
        "status": "DISCREPANCY",
        "calculation_id": "calc_1",
        "evidence_ids": ["ev_1"],
        "source_refs": [source_ref()],
        "verifier_result_id": "verifier_1",
        "explanation": "Synthetic contract example.",
        "actionable_next_step": "Review source evidence.",
    }


def snapshot() -> dict:
    return {
        "run_id": "run_1",
        "version": 1,
        "mode": "SYNTHETIC_DEMO",
        "fund_name": "Synthetic QA Fund",
        "reporting_period": "Q3 2026",
        "created_at": "2026-09-05T12:00:00Z",
        "frozen_at": "2026-09-05T12:00:00Z",
        "source_documents": [source_document()],
        "rules": [rule()],
        "calculations": [calculation()],
        "challenger_concerns": [],
        "verifier_results": [verifier()],
        "findings": [finding()],
        "limitations": ["Model contract fixture; does not execute a financial verifier."],
    }


class SourceContractQATests(unittest.TestCase):
    def test_document_filename_and_storage_key_are_preserved_exactly(self) -> None:
        result = SourceDocument(**(source_document() | {
            "filename": " Fees.csv", "original_storage_key": " source/ Fees.csv ",
        }))
        self.assertEqual(result.filename, " Fees.csv")
        self.assertEqual(result.original_storage_key, " source/ Fees.csv ")

    def test_raw_evidence_and_locator_whitespace_is_preserved(self) -> None:
        item = source_ref()
        item.update(sheet=" Fees ", original_value="  LP03\n", quote="  exact quote\n")
        result = SourceRef(**item)
        self.assertEqual(result.original_value, "  LP03\n")
        self.assertEqual(result.quote, "  exact quote\n")
        self.assertEqual(result.locator, " Fees !B3")

    def test_empty_strings_do_not_supply_support(self) -> None:
        for support in ({"original_value": ""}, {"original_value": None, "quote": ""}):
            with self.subTest(support=support), self.assertRaises(ValidationError):
                SourceRef(**(source_ref() | support))

    def test_whitespace_only_original_remains_representable(self) -> None:
        self.assertEqual(SourceRef(**(source_ref() | {"original_value": "  "})).original_value, "  ")

    def test_normalized_document_rejects_foreign_document_and_hash(self) -> None:
        for change in ({"document_id": "other"}, {"document_hash": "b" * 64}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                NormalizedDocument(document=source_document(), evidence=[source_ref() | change])

    def test_normalized_document_rejects_duplicate_evidence_ids(self) -> None:
        with self.assertRaises(ValidationError):
            NormalizedDocument(document=source_document(), evidence=[source_ref(), source_ref()])


class FinancialContractQATests(unittest.TestCase):
    def test_non_finite_financial_values_are_rejected(self) -> None:
        for field in ("fee_base", "annual_rate", "period_factor", "tolerance", "expected_amount", "reported_amount", "difference"):
            for invalid in ("NaN", "Infinity", "-Infinity"):
                with self.subTest(field=field, invalid=invalid), self.assertRaises(ValidationError):
                    Calculation(**(calculation() | {field: invalid}))

    def test_zero_tolerance_allowed_negative_tolerance_rejected(self) -> None:
        self.assertEqual(Calculation(**(calculation() | {"tolerance": "0"})).tolerance, Decimal("0"))
        with self.assertRaises(ValidationError):
            Calculation(**(calculation() | {"tolerance": "-0.01"}))

    def test_reversed_reporting_and_effective_ranges_rejected(self) -> None:
        for changes in (
            {"period_start": "2026-10-01"},
            {"effective_from": "2026-10-01", "effective_to": "2026-09-30"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                InvestorRule(**(rule() | changes))

    def test_decimal_sign_zero_and_precision_remain_representable(self) -> None:
        result = Calculation(**(calculation() | {"fee_base": "-0.000001", "reported_amount": "0"}))
        self.assertEqual(result.fee_base, Decimal("-0.000001"))
        self.assertEqual(result.reported_amount, Decimal("0"))


class ConclusionContractQATests(unittest.TestCase):
    def test_asserted_findings_require_values_calculation_and_evidence(self) -> None:
        for status in ("MATCH", "DISCREPANCY"):
            for change in (
                {"reported_value": None}, {"expected_value": None}, {"difference": None},
                {"currency": None}, {"calculation_id": None}, {"evidence_ids": [], "source_refs": []},
            ):
                with self.subTest(status=status, change=change), self.assertRaises(ValidationError):
                    Finding(**(finding() | {"status": status} | change))

    def test_finding_evidence_ids_must_resolve_to_source_refs(self) -> None:
        for changes in (
            {"evidence_ids": ["forged"]},
            {"source_refs": []},
            {"evidence_ids": []},
            {"source_refs": [source_ref(), source_ref()]},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                Finding(**(finding() | changes))

    def test_asserted_verifier_result_requires_successful_checks(self) -> None:
        for change in (
            {"checks": []},
            {"status": "MATCH", "checks": [{"code": "SOURCE", "passed": False, "explanation": "Missing source"}]},
            {"blocking_concern_ids": ["concern_1"]},
            {"calculation_id": None},
        ):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                VerifierResult(**(verifier() | change))

    def test_discrepancy_can_include_a_failed_comparison_check(self) -> None:
        result = VerifierResult(**(verifier() | {
            "checks": [{"code": "AMOUNT_COMPARISON", "passed": False, "explanation": "Reported fee differs."}],
        }))
        self.assertEqual(result.status, "DISCREPANCY")

    def test_asserted_zero_amounts_remain_valid(self) -> None:
        result = Finding(**(finding() | {
            "status": "MATCH", "reported_value": "0", "expected_value": "0", "difference": "0",
        }))
        self.assertEqual(result.expected_value, Decimal("0"))

    def test_cannot_verify_can_represent_missing_evidence_and_values(self) -> None:
        for status in ("CANNOT_VERIFY", "UNSUPPORTED"):
            unresolved = finding() | {
                "status": status, "reported_value": None, "expected_value": None,
                "difference": None, "currency": None, "calculation_id": None,
                "evidence_ids": [], "source_refs": [],
            }
            self.assertEqual(Finding(**unresolved).status, status)
            result = verifier() | {"status": status, "calculation_id": None, "checks": []}
            self.assertEqual(VerifierResult(**result).status, status)


class SnapshotIntegrityQATests(unittest.TestCase):
    def test_consistent_snapshot_round_trips_with_decimal_values(self) -> None:
        parsed = ReviewSnapshot(**snapshot())
        self.assertEqual(ReviewSnapshot.model_validate_json(parsed.model_dump_json()), parsed)
        self.assertEqual(parsed.findings[0].difference, Decimal("12500"))

    def test_snapshot_rejects_duplicate_record_ids(self) -> None:
        for collection in ("source_documents", "rules", "calculations", "verifier_results", "findings"):
            data = snapshot()
            data[collection].append(copy.deepcopy(data[collection][0]))
            with self.subTest(collection=collection), self.assertRaises(ValidationError):
                ReviewSnapshot(**data)

    def test_snapshot_rejects_missing_and_foreign_references(self) -> None:
        for collection, field, value in (
            ("calculations", "rule_id", "missing"),
            ("calculations", "rule_version", 2),
            ("calculations", "investor_id", "LP_WRONG"),
            ("verifier_results", "rule_id", "missing"),
            ("verifier_results", "calculation_id", "missing"),
            ("verifier_results", "investor_id", "LP_WRONG"),
            ("findings", "calculation_id", "missing"),
            ("findings", "verifier_result_id", "missing"),
            ("findings", "investor_id", "LP_WRONG"),
            ("findings", "currency", "USD"),
            ("findings", "reported_value", "999"),
            ("findings", "status", "MATCH"),
            ("findings", "challenger_concern_ids", ["missing"]),
        ):
            data = snapshot()
            data[collection][0][field] = value
            with self.subTest(collection=collection, field=field), self.assertRaises(ValidationError):
                ReviewSnapshot(**data)

    def test_snapshot_rejects_evidence_outside_source_documents(self) -> None:
        for change in ({"document_id": "missing"}, {"document_hash": "b" * 64}):
            data = snapshot()
            data["findings"][0]["source_refs"][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValidationError):
                ReviewSnapshot(**data)


if __name__ == "__main__":
    unittest.main()
