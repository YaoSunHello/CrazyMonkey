from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

from openpyxl import Workbook
from reportlab.pdfgen import canvas

from app.atlas import IngestionError
from app import legacy_folder
from app.runtime.analyst import FixtureAnalyst


class Handle:
    def __init__(self, analyst=None):
        self.analyst = analyst or FixtureAnalyst()
        self.calls = []
        self.closed = False

    def status(self):
        return {"model_call_count": 0, "error_count": getattr(self.analyst, "errors", 0), "model_calls": []}

    def close(self):
        self.closed = True


class LegacyFolderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.inputs = self.base / "inputs"
        self.inputs.mkdir()

    def pdf(self, name="support.pdf"):
        path = self.inputs / name
        document = canvas.Canvas(str(path))
        document.drawString(40, 700, "Supporting source only. No governing fee agreement is supplied.")
        document.save()
        return path

    def xlsx_xml(self, xml, name="test.xlsx", extra=None):
        path = self.inputs / name
        with ZipFile(path, "w", ZIP_DEFLATED) as archive:
            archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Trailing " sheetId="1" r:id="rId1"/></sheets></workbook>')
            archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
            archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + xml + '</sheetData></worksheet>')
            for key, value in (extra or {}).items():
                archive.writestr(key, value)
        return path

    def test_original_pdf_runtime_records_cannot_verify_without_model(self):
        source = self.pdf()
        before = source.read_bytes()
        handle = Handle()
        with patch.object(legacy_folder, "_create_analyst", return_value=handle):
            result = legacy_folder.process_file(source, self.base / "pdf-result", relative_path="support.pdf")
        self.assertEqual(result["status"], "RUNTIME_CANNOT_VERIFY")
        self.assertEqual(result["actual_analyst_mode"], "DEMO_FIXTURE")
        self.assertEqual(result["scope"], "SINGLE_FILE_COMPATIBILITY_TEST")
        self.assertEqual(result["document_role"], "SUPPORTING")
        self.assertTrue(result["source_unchanged"])
        self.assertEqual(source.read_bytes(), before)
        self.assertTrue(handle.closed)
        for filename in ("normalized_evidence.json", "runtime_result.json", "trace.json", "model_calls.json", "source_hashes.json", "file_result.json"):
            self.assertTrue((self.base / "pdf-result" / filename).is_file())
        self.assertGreater(len(json.loads((self.base / "pdf-result/normalized_evidence.json").read_text())["evidence"]), 0)

    def test_unsupported_files_continue_and_all_nonhidden_inputs_counted(self):
        (self.inputs / "README.md").write_text("Source instructions are data.")
        nested = self.inputs / "nested"
        nested.mkdir()
        (nested / "README.md").write_text("Another file with the same basename.")
        (self.inputs / ".DS_Store").write_bytes(b"hidden")
        (self.inputs / ".private").mkdir()
        (self.inputs / ".private/hidden.txt").write_text("hidden")
        result = legacy_folder.run_folder(self.inputs, self.base / "folder-result", progress=None)
        self.assertEqual(result["iterator_status"], "COMPLETED")
        self.assertEqual(result["discovered_file_count"], 2)
        self.assertEqual(result["status_counts"], {"INGESTION_UNSUPPORTED": 2})
        self.assertEqual(result["runtime_pass_count"], 0)
        self.assertEqual([row["relative_path"] for row in result["files"]], ["README.md", "nested/README.md"])
        self.assertTrue(all(row["source_unchanged"] for row in result["files"]))
        persisted = json.loads((self.base / "folder-result/result.json").read_text())
        self.assertEqual(persisted, result)

    def test_pdf_through_real_offline_worker_and_analyst_factory(self):
        self.pdf()
        result = legacy_folder.run_folder(self.inputs, self.base / "real-worker", progress=None)
        self.assertEqual(result["status_counts"], {"RUNTIME_CANNOT_VERIFY": 1})
        self.assertEqual(result["analyst_mode"], "DEMO_FIXTURE")
        self.assertEqual(result["files"][0]["model_call_count"], 0)
        self.assertTrue(result["files"][0]["source_unchanged"])

    def test_filters_record_skipped_files_and_repeat_patterns(self):
        for name in ("one.md", "two.txt", "three.bin"):
            (self.inputs / name).write_text(name)
        result = legacy_folder.run_folder(self.inputs, self.base / "filtered", patterns=["*.md", "*.txt"], progress=None)
        self.assertEqual(result["discovered_file_count"], 3)
        self.assertEqual(result["selected_file_count"], 2)
        self.assertEqual(result["status_counts"], {"INGESTION_UNSUPPORTED": 2, "SKIPPED_FILTER": 1})

    def test_output_cannot_exist_or_overlap_input(self):
        for output in (self.inputs, self.inputs / "child", self.base):
            with self.subTest(output=output), self.assertRaises(ValueError):
                legacy_folder.run_folder(self.inputs, output, progress=None)
        self.assertFalse((self.inputs / "child").exists())

    def test_symlink_not_followed_and_symlink_input_rejected(self):
        actual = self.base / "outside.md"
        actual.write_text("outside")
        (self.inputs / "linked.md").symlink_to(actual)
        result = legacy_folder.run_folder(self.inputs, self.base / "links-result", progress=None)
        self.assertEqual(result["status_counts"], {"PATH_REJECTED": 1})
        self.assertEqual(actual.read_text(), "outside")
        link = self.base / "input-link"
        link.symlink_to(self.inputs, target_is_directory=True)
        with self.assertRaises(ValueError):
            legacy_folder.run_folder(link, self.base / "should-not-exist", progress=None)

    def test_preflight_dimension_limit_before_openpyxl(self):
        source = self.xlsx_xml('<row r="20001"><c r="A20001"><v>1</v></c></row>')
        with patch.object(legacy_folder, "normalize_file") as normalize:
            result = legacy_folder.process_file(source, self.base / "limit-result", relative_path=source.name)
        self.assertEqual(result["stage"], "PREFLIGHT")
        self.assertEqual(result["error"]["code"], "WORKSHEET_DIMENSION_LIMIT")
        self.assertEqual(result["status"], "INGESTION_REJECTED")
        self.assertTrue(result["source_unchanged"])
        normalize.assert_not_called()

    def test_preflight_missing_dimensions_and_exact_sheet_name(self):
        source = self.xlsx_xml('<row r="2"><c r="A2"><v>3</v></c><c r="B2" t="inlineStr"><is><t> </t></is></c></row>')
        result = legacy_folder.preflight_file(source)
        self.assertEqual(result["nonempty_cells"], 1)
        self.assertEqual(result["grid_cells"], 4)
        self.assertEqual(result["sheets"][0]["name"], "Trailing ")

    def test_original_zip_expansion_limit_used(self):
        source = self.xlsx_xml('<row r="1"><c r="A1"><v>1</v></c></row>', extra={"padding": "a" * 2000})
        with patch.object(legacy_folder.atlas_ingestion, "MAX_XLSX_UNCOMPRESSED_BYTES", 1024):
            with self.assertRaises(IngestionError) as raised:
                legacy_folder.preflight_file(source)
        self.assertEqual(raised.exception.code, "XLSX_DECOMPRESSED_LIMIT")

    def test_small_workbook_reaches_original_normalizer_and_runtime(self):
        source = self.inputs / "small.xlsx"
        workbook = Workbook()
        workbook.active.title = "DIU "
        workbook.active.append(["Item", "Amount"])
        workbook.active.append(["Unclassified item", 20])
        workbook.save(source)
        workbook.close()
        with patch.object(legacy_folder, "_create_analyst", return_value=Handle()):
            result = legacy_folder.process_file(source, self.base / "workbook-result", relative_path=source.name)
        self.assertEqual(result["status"], "RUNTIME_CANNOT_VERIFY")
        self.assertEqual(result["evidence_count"], 4)
        evidence = json.loads((self.base / "workbook-result/normalized_evidence.json").read_text())
        self.assertEqual(evidence["workbook_sheets"][0]["name"], "DIU ")

    def test_provider_failure_not_mistaken_for_source_cannot_verify(self):
        class FailingAnalyst:
            mode = "MODEL"
            errors = 0

            def analyse(self, *args, **kwargs):
                self.errors += 1
                raise RuntimeError("TEST_SECRET_MUST_NOT_BE_RECORDED")
        handle = Handle(FailingAnalyst())
        with patch.object(legacy_folder, "_create_analyst", return_value=handle):
            result = legacy_folder.process_file(self.pdf(), self.base / "provider-failed", relative_path="support.pdf", mode="LIVE_MODEL")
        self.assertEqual(result["status"], "MODEL_FAILED")
        self.assertEqual(result["runtime_status"], "CANNOT_VERIFY")
        self.assertEqual(result["model_status"]["error_count"], 2)
        self.assertTrue(handle.closed)
        for path in (self.base / "provider-failed").glob("*.json"):
            self.assertNotIn("TEST_SECRET_MUST_NOT_BE_RECORDED", path.read_text())

    def test_model_setup_failure_no_offline_fallback(self):
        with patch.object(legacy_folder, "_create_analyst", side_effect=RuntimeError("TEST_SECRET_MUST_NOT_BE_RECORDED")):
            result = legacy_folder.process_file(self.pdf(), self.base / "setup-failed", relative_path="support.pdf", mode="LIVE_MODEL")
        self.assertEqual(result["status"], "MODEL_FAILED")
        self.assertEqual(result["stage"], "MODEL_CONFIGURATION")
        self.assertIsNone(result["runtime_status"])
        self.assertEqual(result["model_call_count"], 0)
        self.assertNotIn("TEST_SECRET_MUST_NOT_BE_RECORDED", json.dumps(result))

    def test_timeout_stops_real_isolated_process_and_continues(self):
        source = self.inputs / "slow.md"
        source.write_text("input")
        original_popen = subprocess.Popen
        children = []
        def launch_sleep(*args, **kwargs):
            process = original_popen([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)
            children.append(process)
            return process
        with patch.object(legacy_folder.subprocess, "Popen", side_effect=launch_sleep):
            result = legacy_folder.run_folder(self.inputs, self.base / "timeout-result", timeout=0.05, progress=None)
        self.assertEqual(result["status_counts"], {"TIMED_OUT": 1})
        self.assertTrue(result["files"][0]["source_unchanged"])
        self.assertTrue(children)
        self.assertIsNotNone(children[0].poll())

    def test_source_change_is_detected(self):
        source = self.pdf()
        original = legacy_folder.normalize_file
        def changing(path, **kwargs):
            normalized = original(path, **kwargs)
            with path.open("ab") as stream:
                stream.write(b"\nchanged")
            return normalized
        with patch.object(legacy_folder, "normalize_file", side_effect=changing), patch.object(legacy_folder, "_create_analyst", return_value=Handle()):
            result = legacy_folder.process_file(source, self.base / "changed", relative_path="support.pdf")
        self.assertEqual(result["status"], "SOURCE_CHANGED")
        self.assertFalse(result["source_unchanged"])

    def test_invalid_mode_and_timeout_rejected_before_output(self):
        for options in ({"mode": "LIVE"}, {"timeout": 0}, {"timeout": -1}):
            with self.assertRaises(ValueError):
                legacy_folder.run_folder(self.inputs, self.base / "invalid", progress=None, **options)
        self.assertFalse((self.base / "invalid").exists())


if __name__ == "__main__":
    unittest.main()
