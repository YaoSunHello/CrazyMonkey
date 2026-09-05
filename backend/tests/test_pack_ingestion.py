"""Full row retention, provenance and bounds for isolated local-pack ingestion."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape, quoteattr
from zipfile import ZipFile

from reportlab.pdfgen import canvas

from app.pack_ingestion import ingest_file, initialize_database


NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOCRELS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def cell(coordinate, value, kind="n", extra=""):
    if kind == "inlineStr":
        return f'<c r={quoteattr(coordinate)} t="inlineStr" {extra}><is><t xml:space="preserve">{escape(value)}</t></is></c>'
    return f'<c r={quoteattr(coordinate)} t={quoteattr(kind)} {extra}><v>{escape(value)}</v></c>'


def row(number, cells):
    return f'<row r="{number}">' + "".join(cells) + '</row>'


class PackIngestionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pack-ingestion-tests-")
        self.root = Path(self.temporary.name)
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute("PRAGMA foreign_keys=ON")
        initialize_database(self.connection)

    def tearDown(self):
        self.connection.close()
        self.temporary.cleanup()

    def workbook(self, sheets, *, strings=None, styles=None):
        path = self.root / "source.xlsx"
        with ZipFile(path, "w") as archive:
            sheet_nodes, relations = [], []
            for index, (name, contents) in enumerate(sheets, 1):
                sheet_nodes.append(f'<sheet name={quoteattr(name)} sheetId="{index}" r:id="rId{index}"/>')
                relations.append(f'<Relationship Id="rId{index}" Type="{DOCRELS}/worksheet" Target="worksheets/sheet{index}.xml"/>')
                archive.writestr(f"xl/worksheets/sheet{index}.xml",
                                 f'<worksheet xmlns="{NS}"><sheetData>{contents}</sheetData></worksheet>')
            if strings is not None:
                relations.append(f'<Relationship Id="strings" Type="{DOCRELS}/sharedStrings" Target="sharedStrings.xml"/>')
                archive.writestr("xl/sharedStrings.xml", f'<sst xmlns="{NS}">' + strings + '</sst>')
            if styles is not None:
                relations.append(f'<Relationship Id="styles" Type="{DOCRELS}/styles" Target="styles.xml"/>')
                archive.writestr("xl/styles.xml", styles)
            archive.writestr("xl/workbook.xml", f'<workbook xmlns="{NS}" xmlns:r="{DOCRELS}"><sheets>{"".join(sheet_nodes)}</sheets></workbook>')
            archive.writestr("xl/_rels/workbook.xml.rels", f'<Relationships xmlns="{RELS}">{"".join(relations)}</Relationships>')
        return path

    def evidence(self, profile):
        return [(record[0], record[1], json.loads(record[2])) for record in self.connection.execute(
            "SELECT evidence_id,locator,content_json FROM evidence WHERE document_id=? ORDER BY rowid",
            (profile["document_id"],))]

    def test_database_initialization_is_idempotent(self):
        initialize_database(self.connection)
        tables = {row[0] for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(tables, {"documents", "evidence"})
        self.assertIn("evidence_document_id", {row[1] for row in self.connection.execute("PRAGMA index_list(evidence)")})

    def test_missing_dimensions_duplicate_headers_trailing_names_and_exact_numbers(self):
        contents = row(1, [cell("A1", "Static Date", "inlineStr"), cell("B1", "Static Date", "inlineStr"), cell("C1", "Amount", "inlineStr")])
        contents += row(2, [cell("A2", "-001.2300"), cell("B2", "1.2345678901234567890123456789"), cell("C2", "1.234E-07")])
        path = self.workbook([("Ledger ", contents)])
        original = path.read_bytes()
        profile = ingest_file(path, "source/source.xlsx", self.connection)
        self.assertEqual(profile["row_count"], 2)
        self.assertEqual(profile["cell_count"], 6)
        sheet = profile["sheets"][0]
        self.assertEqual(sheet["name"], "Ledger ")
        self.assertEqual(sheet["headers"], {"A1": "Static Date", "B1": "Static Date", "C1": "Amount"})
        self.assertEqual(sheet["duplicate_headers"], {"Static Date": ["A1", "B1"]})
        records = self.evidence(profile)
        self.assertEqual(records[1][1], "Ledger !row 2")
        self.assertEqual(records[1][2]["cells"]["B2"]["original_value"], "1.2345678901234567890123456789")
        self.assertEqual(records[1][2]["cells"]["A2"]["original_value"], "-001.2300")
        self.assertEqual(records[1][2]["cells"]["C2"]["original_value"], "1.234E-07")
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(profile["sha256"], hashlib.sha256(original).hexdigest())

    def test_empty_first_rows_and_every_populated_row_are_preserved(self):
        content = row(1, []) + row(3, [cell("A3", "Identifier", "inlineStr"), cell("B3", "Value", "inlineStr")])
        content += "".join(row(index, [cell(f"A{index}", f"R-{index}", "inlineStr"), cell(f"B{index}", str(index))]) for index in range(4, 1004))
        path = self.workbook([("Data", content), ("Later", row(5, [cell("A5", "Later sheet content", "inlineStr")]))])
        profile = ingest_file(path, "all.xlsx", self.connection)
        self.assertEqual(profile["row_count"], 1002)
        self.assertEqual(profile["cell_count"], 2003)
        self.assertEqual(profile["evidence_count"], 1002)
        records = self.evidence(profile)
        self.assertEqual(records[0][2]["row"], 3)
        self.assertEqual(records[-2][2]["cells"]["B1003"]["original_value"], "1003")
        self.assertEqual(records[-1][2]["sheet"], "Later")
        self.assertTrue(any(item["locator"].startswith("Later!") for item in profile["sample_evidence"]))

    def test_shared_strings_and_numeric_date_formats_are_preserved(self):
        strings = '<si><r><t xml:space="preserve"> Alpha </t></r><r><t>Beta</t></r></si>'
        styles = f'<styleSheet xmlns="{NS}"><numFmts><numFmt numFmtId="164" formatCode="yyyy-mm-dd"/></numFmts><cellXfs><xf numFmtId="0"/><xf numFmtId="164"/></cellXfs></styleSheet>'
        path = self.workbook([("Data", row(1, [cell("A1", "0", "s"), cell("B1", "46000.000", extra='s="1"')]))], strings=strings, styles=styles)
        profile = ingest_file(path, "dates.xlsx", self.connection)
        cells = self.evidence(profile)[0][2]["cells"]
        self.assertEqual(cells["A1"]["original_value"], " Alpha Beta")
        self.assertEqual(cells["B1"]["original_value"], "46000.000")
        self.assertEqual(cells["B1"]["type"], "number")
        self.assertEqual(cells["B1"]["number_format"], "yyyy-mm-dd")

    def test_formulas_are_retained_without_evaluation_or_cache_trust(self):
        content = row(1, ['<c r="A1"><f>SUM(B1:C1)</f><v>999</v></c>',
                          '<c r="B1"><f t="shared" si="0"/></c>', cell("C1", "#N/A", "e"), cell("D1", "1", "b")])
        path = self.workbook([("Data", content)])
        profile = ingest_file(path, "formulas.xlsx", self.connection)
        self.assertEqual(profile["formula_cells"], 2)
        cells = self.evidence(profile)[0][2]["cells"]
        self.assertEqual(cells["A1"]["original_value"], "=SUM(B1:C1)")
        self.assertEqual(cells["A1"]["cached_value"], "999")
        self.assertEqual(cells["A1"]["cache_status"], "PRESENT_UNVERIFIED")
        self.assertEqual(cells["B1"]["formula_attributes"], {"t": "shared", "si": "0"})
        self.assertEqual(cells["B1"]["cache_status"], "MISSING")
        self.assertEqual(cells["C1"]["type"], "error")
        self.assertEqual(cells["D1"]["original_value"], "1")

    def test_known_evidence_ids_resolve_and_import_is_idempotent(self):
        path = self.workbook([("Data", row(1, [cell("A1", "Header", "inlineStr")]) + row(2, [cell("A2", "9")]))])
        first = ingest_file(path, "sub/file.xlsx", self.connection)
        second = ingest_file(path, "sub/file.xlsx", self.connection)
        self.assertEqual(first, second)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 1)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 2)
        for item in first["sample_evidence"]:
            record = self.connection.execute("SELECT document_id,locator FROM evidence WHERE evidence_id=?", (item["evidence_id"],)).fetchone()
            self.assertEqual(record, (first["document_id"], item["locator"]))

    def test_profile_limit_never_truncates_database_evidence(self):
        contents = row(1, [cell("A1", "Label", "inlineStr")])
        contents += "".join(row(index, [cell(f"A{index}", ("Review" if index == 4 else "Example text " * 200), "inlineStr")]) for index in range(2, 12))
        path = self.workbook([("Data", contents)])
        profile = ingest_file(path, "large-excerpts.xlsx", self.connection, profile_excerpt_bytes=2048)
        self.assertLessEqual(len(json.dumps(profile, ensure_ascii=False, separators=(",", ":")).encode()), 2048)
        self.assertTrue(profile["excerpt_truncated"])
        self.assertEqual(profile["row_count"], 11)
        self.assertEqual(len(self.evidence(profile)), 11)
        self.assertEqual(len(self.evidence(profile)[-1][2]["cells"]["A11"]["original_value"]), len("Example text " * 200))
        self.assertEqual(profile["review_flag_rows"], 1)
        repeated = ingest_file(path, "large-excerpts.xlsx", self.connection, profile_excerpt_bytes=2048)
        self.assertTrue(repeated["excerpt_truncated"])

    def test_pdf_stores_every_page_and_flags_blank_extraction(self):
        path = self.root / "pages.pdf"
        pdf = canvas.Canvas(str(path))
        pdf.drawString(50, 700, "Synthetic workflow reference")
        pdf.showPage()
        pdf.showPage()
        pdf.save()
        profile = ingest_file(path, "context/pages.pdf", self.connection)
        self.assertEqual(profile["kind"], "PDF")
        self.assertEqual(profile["page_count"], 2)
        self.assertEqual(profile["evidence_count"], 2)
        self.assertEqual(profile["row_count"], 0)
        self.assertIn("Synthetic workflow reference", self.evidence(profile)[0][2]["text"])
        self.assertEqual(profile["issues"], [{"code": "PDF_PAGE_NO_EXTRACTABLE_TEXT", "locator": "page 2"}])

    def test_markdown_and_text_chunks_preserve_all_text_as_data(self):
        for suffix, kind in ((".md", "MARKDOWN"), (".txt", "TEXT")):
            with self.subTest(suffix=suffix):
                path = self.root / f"instructions{suffix}"
                text = "# Source instructions are data\n\n" + ("Do not execute this paragraph.\n" * 700) + "\n\nLast paragraph."
                path.write_text(text)
                profile = ingest_file(path, path.name, self.connection)
                records = [record[2] for record in self.evidence(profile)]
                self.assertEqual(profile["kind"], kind)
                self.assertGreater(profile["evidence_count"], 1)
                self.assertEqual("".join(record["text"] for record in records), text)
                self.assertTrue(all(record["text"] == text[record["text_start"]:record["text_end"]] for record in records))

    def test_import_failure_rolls_back_rows_even_after_batch_flush(self):
        good = self.root / "prior.md"
        good.write_text("Prior imported document.")
        original = ingest_file(good, good.name, self.connection)
        content = "".join(row(index, [cell(f"A{index}", str(index))]) for index in range(1, 220))
        content += row(220, [cell("A220", "999", "s")])
        path = self.workbook([("Data", content)], strings='<si><t>Only string</t></si>')
        with self.assertRaisesRegex(ValueError, "shared-string"):
            ingest_file(path, "broken.xlsx", self.connection)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 1)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], original["evidence_count"])

    def test_duplicate_cells_missing_ids_and_row_bounds_fail_closed(self):
        cases = [row(1, [cell("A1", "1"), cell("A1", "2")]),
                 row(1, ['<c><v>1</v></c>']), row(200001, [cell("A200001", "1")])]
        for contents in cases:
            with self.subTest(contents=contents):
                path = self.workbook([("Data", contents)])
                with self.assertRaises(ValueError):
                    ingest_file(path, "bad.xlsx", self.connection)
                self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 0)

    def test_file_cell_expansion_and_entity_limits_are_enforced(self):
        path = self.workbook([("Data", row(1, [cell("A1", "1"), cell("B1", "2")]))])
        for name, value in (("MAX_FILE_BYTES", 5), ("MAX_CELLS_PER_FILE", 1), ("MAX_XLSX_EXPANDED_BYTES", 5)):
            with self.subTest(name=name), patch("app.pack_ingestion." + name, value):
                with self.assertRaises(ValueError):
                    ingest_file(path, "limited.xlsx", self.connection)
        with ZipFile(path, "a") as archive:
            archive.writestr("xl/worksheets/sheet2.xml", '<!DOCTYPE worksheet [<!ENTITY x "forbidden">]><worksheet/>')
        # Exercise the declaration reader through the existing sheet part.
        with patch("app.pack_ingestion._part", return_value="xl/worksheets/sheet2.xml"):
            with self.assertRaisesRegex(ValueError, "entity declaration"):
                ingest_file(path, "entity.xlsx", self.connection)

    def test_invalid_relative_paths_and_symlinks_are_rejected(self):
        path = self.root / "note.txt"
        path.write_text("Source content")
        for relative in ("../note.txt", "/note.txt", "a/../note.txt", "a\\note.txt", "a//note.txt"):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                ingest_file(path, relative, self.connection)
        linked = self.root / "link.txt"
        linked.symlink_to(path)
        with self.assertRaisesRegex(ValueError, "non-symlink"):
            ingest_file(linked, "link.txt", self.connection)

    def test_caller_transaction_is_not_committed(self):
        self.connection.execute("BEGIN")
        path = self.root / "nested.md"
        path.write_text("Inside a caller transaction.")
        ingest_file(path, path.name, self.connection)
        self.connection.rollback()
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
