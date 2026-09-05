"""Source-linked adversarial checks for the V0 runtime assurance boundary."""

from decimal import Decimal, localcontext
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.atlas import normalize_file
from app.atlas.fixtures import generate_synthetic_pack
from app.runtime.analyst import FixtureAnalyst
from app.runtime.assurance import calculate_fee, red_team, verify
from app.runtime.evidence import EvidenceCatalog
from app.runtime.evidence import build_context


class RuntimeAssuranceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = TemporaryDirectory()
        path = Path(cls.directory.name)
        manifest = generate_synthetic_pack(path)
        cls.documents = [normalize_file(path / item["filename"], role=item["role"]) for item in manifest["files"]]
        cls.catalog = EvidenceCatalog(cls.documents)
        cls.baseline = FixtureAnalyst().analyse("Check management fees and recommend Excel", cls.documents)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        self.analysis = self.baseline.model_copy(deep=True)

    def finding(self, investor_id):
        return next(finding for finding in self.analysis.findings if finding.investor_id == investor_id)

    def verification(self, investor_id):
        return next(result for result in verify(self.analysis, self.catalog) if result.investor_id == investor_id)

    def challenges(self, investor_id):
        return {item.code for item in red_team(self.analysis, self.catalog).challenges if item.investor_id == investor_id}

    def test_actual_fixture_source_arithmetic_and_missing_case(self):
        results = {result.investor_id: result for result in verify(self.analysis, self.catalog)}
        self.assertEqual(results["LP03"].expected, Decimal("37500.00"))
        self.assertEqual(results["LP03"].difference, Decimal("12500.00"))
        self.assertEqual(results["LP03"].status, "FAILED")
        self.assertEqual(results["LP01"].status, "PASSED")
        self.assertEqual(results["LP05"].status, "PASSED")
        self.assertEqual(results["LP06"].status, "CANNOT_VERIFY")
        self.assertIsNone(results["LP06"].expected)
        self.assertIsNone(results["LP06"].difference)

    def test_wrong_primary_rate_cannot_override_side_letter(self):
        self.finding("LP03").calculation.annual_rate = Decimal("0.02")
        self.assertIn("WRONG_APPLICABLE_RATE", self.challenges("LP03"))
        result = self.verification("LP03")
        self.assertFalse(result.checks["proposal_supported"])
        self.assertEqual(result.expected, Decimal("37500.00"))

    def test_future_side_letter_is_not_applied(self):
        self.finding("LP05").calculation.annual_rate = Decimal("0.015")
        self.assertIn("WRONG_APPLICABLE_RATE", self.challenges("LP05"))
        result = self.verification("LP05")
        self.assertEqual(result.expected, Decimal("50000.00"))
        self.assertEqual(result.status, "FAILED")

    def test_incorrect_claimed_arithmetic_never_becomes_trusted(self):
        calculation = self.finding("LP01").calculation
        calculation.claimed_expected = Decimal("1.00")
        calculation.claimed_difference = Decimal("49999.00")
        result = self.verification("LP01")
        self.assertEqual(result.expected, Decimal("50000.00"))
        self.assertEqual(result.difference, Decimal("0.00"))
        self.assertFalse(result.checks["claimed_expected_correct"])
        self.assertFalse(result.checks["claimed_difference_correct"])
        self.assertEqual(result.status, "FAILED")

    def test_correct_value_with_another_investors_source_is_rejected(self):
        first = next(claim for claim in self.finding("LP01").claims if claim.field == "fee_base")
        second = next(claim for claim in self.finding("LP02").claims if claim.field == "fee_base")
        self.assertEqual(first.value, second.value)
        first.evidence_ids = list(second.evidence_ids)
        self.assertIn("CLAIM_EVIDENCE_MISMATCH", self.challenges("LP01"))
        self.assertEqual(self.verification("LP01").status, "FAILED")

    def test_unknown_evidence_is_not_returned_as_a_real_reference(self):
        self.finding("LP01").evidence_ids.append("invented_source_id")
        result = red_team(self.analysis, self.catalog)
        self.assertIn("UNKNOWN_EVIDENCE", self.challenges("LP01"))
        self.assertTrue(all("invented_source_id" not in item.evidence_ids for item in result.challenges))
        self.assertNotIn("invented_source_id", self.verification("LP01").evidence_ids)

    def test_missing_side_letter_cannot_be_fixed_with_a_guessed_calculation(self):
        self.finding("LP06").calculation = self.finding("LP02").calculation.model_copy(deep=True)
        self.assertEqual(self.verification("LP06").status, "CANNOT_VERIFY")
        self.assertIn("MISSING_SOURCE", self.challenges("LP06"))

    def test_wrong_fund_and_invented_investor_are_challenged(self):
        self.finding("LP01").fund_name = "Wrong Fund"
        self.finding("LP02").investor_id = "LP99"
        self.assertIn("WRONG_FUND", self.challenges("LP01"))
        self.assertIn("UNKNOWN_INVESTOR", self.challenges("LP99"))
        self.assertEqual(self.verification("LP99").status, "CANNOT_VERIFY")
        self.assertIn("OMITTED_INVESTOR", self.challenges("LP02"))

    def test_duplicate_and_omitted_investors_do_not_disappear_from_checks(self):
        self.analysis.findings.append(self.finding("LP01").model_copy(deep=True))
        self.analysis.findings = [item for item in self.analysis.findings if item.investor_id != "LP02"]
        self.assertIn("DUPLICATE_FINDING", self.challenges("LP01"))
        self.assertIn("OMITTED_INVESTOR", self.challenges("LP02"))
        self.assertEqual(self.verification("LP01").status, "FAILED")
        self.assertEqual(self.verification("LP02").status, "FAILED")

    def test_checkers_do_not_mutate_primary(self):
        before = self.analysis.model_dump_json()
        red_team(self.analysis, self.catalog)
        verify(self.analysis, self.catalog)
        self.assertEqual(self.analysis.model_dump_json(), before)

    def test_hash_quote_and_locator_tampering_are_rejected(self):
        reference = self.catalog.resolve(self.finding("LP01").evidence_ids[:1])[0]
        self.assertTrue(self.catalog.validate_ref(reference))
        changed_hash = reference.model_copy(deep=True)
        changed_hash.document_hash = "f" * 64
        self.assertFalse(self.catalog.validate_ref(changed_hash))
        changed_quote = reference.model_copy(deep=True)
        changed_quote.quote = "A fabricated rate with the same evidence ID"
        self.assertFalse(self.catalog.validate_ref(changed_quote))
        changed_locator = reference.model_copy(deep=True)
        changed_locator.page = 100
        self.assertFalse(self.catalog.validate_ref(changed_locator))

    def test_agent_document_copy_cannot_mutate_catalog(self):
        original = self.catalog.documents[0].model_dump_json()
        documents = self.catalog.documents
        documents[0].document.document_hash = "f" * 64
        documents[0].evidence[0].quote = "Injected source change"
        self.assertEqual(self.catalog.documents[0].model_dump_json(), original)
        self.assertEqual(self.verification("LP01").status, "PASSED")

    def test_decimal_calculation_round_half_up_is_exact(self):
        self.assertEqual(calculate_fee(Decimal("0.05"), Decimal("0.10"), Decimal("1")), Decimal("0.01"))
        self.assertEqual(calculate_fee(Decimal("10000000"), Decimal("0.015"), Decimal("0.25")), Decimal("37500.00"))
        self.assertEqual(calculate_fee(Decimal("999999999999.99"), Decimal("0.12345678"), Decimal("0.25")), Decimal("30864195000.00"))

    def test_binary_floats_and_nonfinite_values_are_rejected(self):
        for invalid in (0.1, True, Decimal("NaN"), Decimal("Infinity")):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                calculate_fee(invalid, Decimal("0.1"), Decimal("0.25"))

    def test_unrecognized_extra_lpa_financial_clause_fails_closed(self):
        for clause in (
            "Notwithstanding Section 8.1, the management fee for LP01 is waived for Q3 2026.",
            "The applicable investor Fee Base means committed capital less all distributions; the investor register requires this adjustment.",
        ):
            with self.subTest(clause=clause):
                documents = self.catalog.documents
                lpa = next(document for document in documents if document.document.role == "LPA")
                # Treat these as the supplied source facts, not as analyst claims:
                # even a narrow interpreter must not certify an ignored amendment.
                lpa.evidence[-1].quote += " " + clause
                catalog = EvidenceCatalog(documents)
                analysis = FixtureAnalyst().analyse("Verify fees", documents)
                result = next(item for item in verify(analysis, catalog) if item.investor_id == "LP01")
                self.assertEqual(result.status, "CANNOT_VERIFY")
                self.assertIsNone(result.expected)

    def test_unrecognized_side_letter_fee_adjustment_fails_closed(self):
        documents = self.catalog.documents
        letter = next(document for document in documents if document.document.filename == "LP01_Side_Letter.pdf")
        letter.evidence[-1].quote += " The management fee is reduced by GBP 1000 for Q3 2026."
        catalog = EvidenceCatalog(documents)
        analysis = FixtureAnalyst().analyse("Verify fees", documents)
        result = next(item for item in verify(analysis, catalog) if item.investor_id == "LP01")
        self.assertEqual(result.status, "CANNOT_VERIFY")

    def test_percentage_interpretation_ignores_ambient_decimal_precision(self):
        documents = self.catalog.documents
        letter = next(document for document in documents if document.document.filename == "LP02_Side_Letter.pdf")
        for reference in letter.evidence:
            if "1.5%" in (reference.quote or ""):
                reference.quote = reference.quote.replace("1.5%", "12.345678%")
        with localcontext() as context:
            context.prec = 4
            terms = next(item for item in build_context(EvidenceCatalog(documents)) if item.investor_id == "LP02")
        self.assertEqual(terms.annual_rate, Decimal("0.12345678"))

    def test_oversized_source_money_fails_closed_without_runtime_exception(self):
        documents = self.catalog.documents
        register = next(document for document in documents if document.document.role == "INVESTOR_REGISTER")
        base = next(reference for reference in register.evidence if reference.csv_row == 2 and reference.csv_column == "fee_base")
        base.original_value = "1" + "0" * 47
        catalog = EvidenceCatalog(documents)
        analysis = FixtureAnalyst().analyse("Verify fees", documents)
        result = next(item for item in verify(analysis, catalog) if item.investor_id == "LP01")
        self.assertEqual(result.status, "CANNOT_VERIFY")

    def test_duplicate_workbook_reported_fee_columns_are_not_silently_selected(self):
        from openpyxl import load_workbook

        with TemporaryDirectory() as directory:
            path = Path(directory)
            manifest = generate_synthetic_pack(path)
            nav_path = path / "Administrator_NAV_Q3_2026.xlsx"
            workbook = load_workbook(nav_path)
            sheet = workbook["Investor Fees"]
            sheet["F4"] = 1
            sheet["I3"] = "Reported Fee"
            sheet["I4"] = 50000
            workbook.save(nav_path)
            workbook.close()
            documents = [normalize_file(path / item["filename"], role=item["role"]) for item in manifest["files"]]
            catalog = EvidenceCatalog(documents)
            analysis = FixtureAnalyst().analyse("Verify fees", documents)
            result = next(item for item in verify(analysis, catalog) if item.investor_id == "LP01")
            self.assertEqual(result.status, "CANNOT_VERIFY")

    def test_period_fraction_for_another_reporting_period_is_not_applied(self):
        documents = self.catalog.documents
        lpa = next(document for document in documents if document.document.role == "LPA")
        for reference in lpa.evidence:
            if "For Q3 2026" in (reference.quote or ""):
                reference.quote = reference.quote.replace("For Q3 2026", "For Q4 2026")
        catalog = EvidenceCatalog(documents)
        analysis = FixtureAnalyst().analyse("Verify fees", documents)
        result = next(item for item in verify(analysis, catalog) if item.investor_id == "LP01")
        self.assertEqual(result.status, "CANNOT_VERIFY")

    def test_derived_difference_overflow_fails_closed_without_runtime_exception(self):
        documents = self.catalog.documents
        register = next(document for document in documents if document.document.role == "INVESTOR_REGISTER")
        nav = next(document for document in documents if document.document.role == "NAV_WORKBOOK")
        base = next(reference for reference in register.evidence if reference.csv_row == 2 and reference.csv_column == "fee_base")
        base.original_value = "9" * 24
        reported = next(reference for reference in nav.evidence if reference.cell == "F4")
        reported.original_value = "-" + "9" * 24
        catalog = EvidenceCatalog(documents)
        analysis = FixtureAnalyst().analyse("Verify fees", documents)
        result = next(item for item in verify(analysis, catalog) if item.investor_id == "LP01")
        self.assertEqual(result.status, "CANNOT_VERIFY")
        self.assertIsNone(result.difference)

    def test_conflicting_investor_names_cannot_pass_on_id_match_alone(self):
        documents = self.catalog.documents
        nav = next(document for document in documents if document.document.role == "NAV_WORKBOOK")
        name = next(reference for reference in nav.evidence if reference.cell == "B4")
        name.original_value = "A Different Investor Foundation"
        catalog = EvidenceCatalog(documents)
        analysis = FixtureAnalyst().analyse("Verify fees", documents)
        result = next(item for item in verify(analysis, catalog) if item.investor_id == "LP01")
        self.assertEqual(result.status, "CANNOT_VERIFY")


if __name__ == "__main__":
    unittest.main()
