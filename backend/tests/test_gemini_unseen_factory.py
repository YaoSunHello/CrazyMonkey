"""Validate blind-input isolation and sufficient synthetic-source evidence."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook
from pypdf import PdfReader

from gemini_unseen_factory import generate_gemini_blind_pair


class GeminiUnseenFactoryTests(unittest.TestCase):
    def test_blind_input_contains_only_source_pair_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "pack"
            manifest = generate_gemini_blind_pair(root)
            self.assertEqual(manifest, {"input_dir": str((root / "input").resolve())})
            self.assertEqual({p.suffix for p in (root / "input").iterdir()}, {".pdf", ".xlsx"})
            hashes = json.loads((root / "control/input_hashes.json").read_text())
            with self.assertRaises(FileExistsError):
                generate_gemini_blind_pair(root)
            self.assertEqual(hashes, {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in (root / "input").iterdir()})

    def test_oracle_arithmetic_identity_and_anchors_match_source_pair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "pack"
            generate_gemini_blind_pair(root)
            oracle = json.loads((root / "control/oracle.json").read_text())
            computed = Decimal(oracle["fee_base"]) * Decimal(oracle["annual_rate"]) * Decimal(oracle["period_factor"])
            self.assertEqual(computed, Decimal(oracle["expected_amount"]))
            self.assertEqual(Decimal(oracle["reported_amount"]) - computed,
                             Decimal(oracle["difference_reported_minus_expected"]))
            workbook = load_workbook(root / "input/statement_93.xlsx", data_only=True)
            try:
                sheet = workbook["Remuneration statement"]
                self.assertEqual(sheet["E9"].value, oracle["investor_id"])
                self.assertEqual(Decimal(str(sheet["E15"].value)), Decimal(oracle["fee_base"]))
                self.assertEqual(Decimal(str(sheet["E16"].value)), Decimal(oracle["period_factor"]))
                self.assertEqual(Decimal(str(sheet["E17"].value)), Decimal(oracle["reported_amount"]))
                # A runtime can discover the result only by combining source evidence.
                all_values = {str(cell.value) for row in sheet for cell in row if cell.value is not None}
                self.assertNotIn(oracle["expected_amount"], all_values)
                self.assertNotIn(oracle["difference_reported_minus_expected"], all_values)
            finally:
                workbook.close()
            reader = PdfReader(root / "input/terms_64.pdf")
            self.assertEqual(len(reader.pages), 1)
            text = reader.pages[0].extract_text()
            for fragment in (oracle["investor_id"], oracle["investor_name"], oracle["fund_name"],
                             "1.35%", "0.50", "USD 6,840,000.00", "round half up", "USD 0.01",
                             "1 January 2028", "30 June 2028", "sole operative agreement"):
                self.assertIn(fragment, text)
            self.assertNotIn(oracle["expected_amount"], text)
            self.assertNotIn(oracle["difference_reported_minus_expected"], text)


if __name__ == "__main__":
    unittest.main()
