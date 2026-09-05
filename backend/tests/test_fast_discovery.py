from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook

from app.atlas.ingestion import normalize_file
from app.runtime.fast_discovery import MAX_CHECKS, MAX_NOTES, anomaly_checks, consistency_checks
from app.runtime.fast_dsl import execute_check
from app.runtime.investigation_evidence import EvidenceStore
from app.runtime.semantics import discover_rows


class FastDiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.sequence = 0

    def workbook(self, sheets):
        self.sequence += 1
        path = Path(self.directory.name) / f"source-{self.sequence}.xlsx"
        workbook = Workbook()
        workbook.remove(workbook.active)
        for title, rows in sheets.items():
            sheet = workbook.create_sheet(title)
            for row in rows:
                sheet.append(row)
        workbook.save(path)
        return normalize_file(path, original_storage_key=str(path))

    def sources(self, sheets):
        store = EvidenceStore([self.workbook(sheets)])
        return store, discover_rows(store)

    def test_quantity_price_is_source_linked_and_calculates_decimal_discrepancy(self):
        store, rows = self.sources({"Orders": [
            ["Investor ID", "Quantity", "Unit Price", "Line Total", "Currency"],
            ["A-1", "3", "12.35", "38.05", "GBP"],
            ["A-2", "2", "20", "40", "GBP"],
        ]})
        checks, notes = consistency_checks(store, rows)
        self.assertFalse(notes)
        self.assertEqual(len(checks), 2)
        first = checks[0]
        self.assertEqual(first.check_type, "quantity_price")
        result = execute_check(first, store)
        self.assertEqual(result["status"], "DISCREPANCY")
        self.assertEqual(Decimal(result["expected"]), Decimal("37.05"))
        self.assertEqual(Decimal(result["difference"]), Decimal("1.00"))
        self.assertEqual([store.get(spec.evidence_id).cell for spec in first.inputs], ["B2", "C2"])
        self.assertEqual(store.get(first.compare_to.evidence_id).cell, "D2")
        self.assertTrue(all(store.get(evidence_id) for evidence_id in first.context_evidence_ids))
        self.assertEqual(execute_check(checks[1], store)["status"], "MATCH")
        store.verify_originals()

    def test_gross_deductions_and_subtotals_do_not_double_count_grand_total(self):
        store, rows = self.sources({"Payments": [
            ["Investor ID", "Gross", "Deductions", "Net", "Currency"],
            ["A", 100, 5, 95, "EUR"],
            ["B", 200, 10, 190, "EUR"],
            ["Subtotal", 300, 15, 285, "EUR"],
            ["C", 50, 2, 48, "EUR"],
            ["Grand Total", 350, 17, 334, "EUR"],
        ]})
        checks, notes = consistency_checks(store, rows)
        self.assertFalse(notes)
        row_checks = [check for check in checks if check.check_type == "gross_less_deductions"]
        self.assertEqual(len(row_checks), 3)
        self.assertTrue(all(execute_check(check, store)["status"] == "MATCH" for check in row_checks))
        grand_net = next(check for check in checks if check.entity_id == "Grand Total" and "net" in check.title)
        self.assertEqual(len(grand_net.inputs), 3)
        result = execute_check(grand_net, store)
        self.assertEqual(result["status"], "DISCREPANCY")
        self.assertEqual(Decimal(result["expected"]), Decimal("333"))
        self.assertNotIn("D4", [store.get(spec.evidence_id).cell for spec in grand_net.inputs])

    def test_percentage_and_missing_cell_diagnostics_withhold_invalid_checks(self):
        store, rows = self.sources({"Charges": [
            ["Investor ID", "Fee Base", "Annual Rate", "Period Factor", "Reported Fee", "Currency"],
            ["A", 1000, "1.5%", "0.25", "3.75", "GBP"],
            ["B", 1000, "150%", "0.25", "375", "GBP"],
            ["C", 1000, "1.5%", None, "3.75", "GBP"],
        ]})
        checks, notes = consistency_checks(store, rows)
        # A rate entered on the schedule cannot establish contractual authority.
        self.assertFalse(checks)
        self.assertEqual({note["code"] for note in notes}, {"INVALID_PERCENTAGE", "MISSING_CELL"})
        missing = next(note for note in notes if note["code"] == "MISSING_CELL")
        self.assertIn("D1", [store.get(evidence_id).cell for evidence_id in missing["evidence_ids"]])
        self.assertTrue(all(note["status"] == "CANNOT_VERIFY" for note in notes))

    def test_csv_missing_cells_use_real_row_evidence_and_declared_headers(self):
        path = Path(self.directory.name) / "missing.csv"
        path.write_text("Investor ID,Quantity,Unit Price,Line Total,Currency\nA,2,10,,GBP\n")
        store = EvidenceStore([normalize_file(path, original_storage_key=str(path))])
        checks, notes = consistency_checks(store, discover_rows(store))
        self.assertFalse(checks)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["code"], "MISSING_CELL")
        self.assertTrue(all(store.get(evidence_id).csv_row == 2 for evidence_id in notes[0]["evidence_ids"]))

    def test_date_ordering_handles_reversal_same_day_and_ambiguous_formats(self):
        store, rows = self.sources({"Periods": [
            ["Investor ID", "Period Start", "Period End"],
            ["A", "2030-03-01", "2030-03-31"],
            ["B", "2030-03-31", "2030-03-01"],
            ["C", "2030-03-01", "2030-03-01"],
            ["D", "03/04/2030", "2030-05-31"],
        ]})
        checks, notes = consistency_checks(store, rows)
        self.assertEqual([check.entity_id for check in checks], ["A", "B"])
        self.assertEqual([execute_check(check, store)["status"] for check in checks], ["MATCH", "DISCREPANCY"])
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["code"], "AMBIGUOUS_DATE")
        self.assertEqual(notes[0]["entity_id"], "D")

    def test_conflicting_and_unsupported_currencies_withhold_money_checks(self):
        store, rows = self.sources({"Orders": [
            ["Investor ID", "Quantity", "Unit Price", "Line Total", "Currency"],
            ["A", 2, "$10", "£20", "GBP"],
            ["B", 2, 10, 20, "JPY"],
            ["C", 2, "€10", "€20", "EUR"],
        ]})
        checks, notes = consistency_checks(store, rows)
        self.assertEqual([check.entity_id for check in checks], ["C"])
        self.assertEqual(checks[0].currency, "EUR")
        self.assertEqual(sum(note["code"] == "CURRENCY_CONFLICT" for note in notes), 2)

    def test_totals_require_every_detail_and_matching_currencies(self):
        store, rows = self.sources({"Mixed": [
            ["Investor ID", "Reported Fee", "Currency"],
            ["A", 10, "GBP"],
            ["B", 20, "USD"],
            ["Total", 30, "GBP"],
        ], "Incomplete": [
            ["Investor ID", "Reported Fee", "Currency"],
            ["C", 10, "GBP"],
            ["D", None, "GBP"],
            ["Total", 10, "GBP"],
        ]})
        checks, notes = consistency_checks(store, rows)
        self.assertFalse(checks)
        self.assertEqual(sum(note["code"] == "TOTAL_INCOMPLETE" for note in notes), 2)

    def test_duplicates_are_scoped_to_document_sheet_and_header(self):
        header = ["Investor ID", "Reported Fee", "Currency"]
        first = self.workbook({"First": [header, ["A", 10, "GBP"], ["A", 20, "GBP"], header, ["A", 30, "GBP"]],
                               "Second": [header, ["A", 40, "GBP"]]})
        second = self.workbook({"First": [header, ["A", 50, "GBP"]]})
        store = EvidenceStore([first, second])
        checks, notes = anomaly_checks(store, discover_rows(store))
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0].source, "anomaly")
        self.assertEqual(checks[0].check_type, "anomaly")
        self.assertEqual(execute_check(checks[0], store)["status"], "DISCREPANCY")
        self.assertEqual(notes[0]["status"], "REVIEW_REQUIRED")
        self.assertEqual(notes[0]["code"], "DUPLICATE_IDENTIFIER")
        self.assertEqual([store.get(spec.evidence_id).cell for spec in checks[0].inputs], ["A2", "A3"])
        self.assertIsNone(checks[0].compare_to)

    def test_repeated_money_requires_three_distinct_entities_and_nonzero_values(self):
        header = ["Investor ID", "Reported Fee", "Currency"]
        store, rows = self.sources({"Amounts": [
            header, ["A", "10.00", "GBP"], ["B", "10", "GBP"], ["C", "10.0", "GBP"],
            ["D", 0, "GBP"], ["E", 0, "GBP"], ["F", 0, "GBP"],
            ["G", 20, "GBP"], ["H", 20, "GBP"], ["I", 20, "USD"],
        ], "Other": [header, ["J", 20, "GBP"]]})
        checks, notes = anomaly_checks(store, rows)
        self.assertEqual(len(checks), 1)
        self.assertEqual(notes[0]["code"], "REPEATED_MONETARY_VALUE")
        self.assertEqual(notes[0]["status"], "REVIEW_REQUIRED")
        self.assertEqual(checks[0].currency, "GBP")
        self.assertIsNone(checks[0].compare_to)
        self.assertEqual(execute_check(checks[0], store)["status"], "DISCREPANCY")
        self.assertTrue(all(store.get(evidence_id) for evidence_id in notes[0]["evidence_ids"]))

    def test_formula_values_are_not_trusted_as_numeric_sources(self):
        store, rows = self.sources({"Orders": [
            ["Investor ID", "Quantity", "Unit Price", "Line Total"],
            ["A", 2, 10, "=B2*C2"],
        ]})
        checks, notes = consistency_checks(store, rows)
        self.assertFalse(checks)
        self.assertEqual(notes[0]["code"], "INVALID_NUMERIC_INPUT")

    def test_check_and_diagnostic_bounds(self):
        store, rows = self.sources({"Orders": [
            ["Investor ID", "Quantity", "Unit Price", "Line Total"],
            *[[f"A-{index}", 2, 10, 20] for index in range(70)],
            *[[f"B-{index}", "unknown", "unknown", "unknown"] for index in range(70)],
        ], "Duplicates": [
            ["Investor ID", "Reported Fee", "Currency"],
            *[["duplicate", index + 1, "GBP"] for index in range(70)],
        ]})
        checks, notes = consistency_checks(store, rows)
        self.assertEqual(len(checks), MAX_CHECKS)
        self.assertEqual(len(notes), MAX_NOTES)
        anomalies, anomaly_notes = anomaly_checks(store, rows)
        self.assertEqual(len(anomalies), MAX_CHECKS)
        self.assertLessEqual(len(anomaly_notes), MAX_NOTES)
        self.assertEqual(len({check.check_id for check in checks}), MAX_CHECKS)

    def test_totals_larger_than_dsl_operand_limit_abstain(self):
        store, rows = self.sources({"Totals": [
            ["Investor ID", "Reported Fee", "Currency"],
            *[[f"A-{index}", 1, "GBP"] for index in range(17)],
            ["Total", 17, "GBP"],
        ]})
        checks, notes = consistency_checks(store, rows)
        self.assertFalse(checks)
        self.assertEqual(notes[0]["code"], "TOTAL_OPERAND_LIMIT")


if __name__ == "__main__":
    unittest.main()
