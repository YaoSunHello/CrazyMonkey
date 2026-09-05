"""Keep ingestion QA scope distinct from downstream availability and success."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from app.atlas.models import NormalizedDocument
if __package__:
    from . import run_qa_demo
else:
    import run_qa_demo


class QaDemoRunnerTests(unittest.TestCase):
    def test_present_downstream_paths_do_not_certify_or_hide_ingestion_scenarios(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkout = root / "checkout"
            for relative_path in run_qa_demo.INVENTORY_PATHS:
                path = checkout / relative_path
                if path.suffix:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("raise RuntimeError('must not import inventory paths')\n")
                else:
                    path.mkdir(parents=True)
                    (path / "__init__.py").write_text(
                        "raise RuntimeError('must not import inventory paths')\n"
                    )
            output = root / "output"
            with patch.object(run_qa_demo, "CHECKOUT_ROOT", checkout):
                report = run_qa_demo.run(output)

            self.assertEqual(report["scope"], "INGESTION_ONLY")
            self.assertEqual(report["qa_ingestion_status"], "PASS")
            self.assertEqual(report["full_demo_status"], "NOT_TESTED")
            self.assertIsNone(report["full_demo_duration_seconds"])
            self.assertNotIn("missing_stages", report)
            self.assertEqual(set(report["downstream_stages"].values()), {"NOT_TESTED"})
            self.assertIn("output_generation", report["downstream_stages"])
            self.assertIn("deterministic_verifier", report["downstream_stages"])
            self.assertEqual(set(report["checkout_path_inventory"]["paths"].values()), {"PRESENT"})
            self.assertEqual(report["checkout_path_inventory"]["scope"], "PATH_PRESENCE_ONLY")
            self.assertEqual(report["case_count"], 4)
            self.assertEqual(report["source_file_count"], 17)
            self.assertEqual(
                [(case["case_id"], len(case["documents"])) for case in report["cases"]],
                [("standard_fixture", 8), ("sterling_thousands", 3),
                 ("dollar_vertical", 3), ("euro_reordered", 3)],
            )
            artifact_paths = []
            for case in report["cases"]:
                self.assertEqual(case["financial_result"], "NOT_TESTED")
                self.assertEqual(case["last_completed_stage"], "source_normalization")
                for document in case["documents"]:
                    path = output / document["normalized_artifact"]
                    artifact_paths.append(path)
                    parsed = NormalizedDocument.model_validate_json(path.read_text())
                    self.assertEqual(parsed.document.filename, document["filename"])
                    self.assertEqual(len(parsed.evidence), document["evidence_count"])
            self.assertEqual(len(set(artifact_paths)), 17)
            self.assertEqual(report["product_output_files"], [])
            self.assertIsNone(report["email_package"])
            self.assertIsNone(report["lp03_runtime_verdict"])
            self.assertEqual(json.loads((output / "qa_demo_result.json").read_text()), report)

    def test_existing_output_directory_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            sentinel = output / "other-agent-work.txt"
            sentinel.write_bytes(b"preserve exactly\n")
            with self.assertRaises(FileExistsError):
                run_qa_demo.run(output)
            self.assertEqual(sentinel.read_bytes(), b"preserve exactly\n")
            self.assertEqual(list(output.iterdir()), [sentinel])

    def test_cli_exits_nonzero_when_ingestion_passes_but_full_flow_is_not_tested(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            environment = dict(os.environ)
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            # Match the active test import paths without assuming a particular venv or cwd.
            environment["PYTHONPATH"] = os.pathsep.join(str(path) for path in sys.path if path)
            result = subprocess.run(
                [sys.executable, str(Path(run_qa_demo.__file__).resolve()), "--output",
                 str(Path(temporary) / "output")],
                env=environment, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["qa_ingestion_status"], "PASS")
            self.assertEqual(report["full_demo_status"], "NOT_TESTED")


if __name__ == "__main__":
    unittest.main()
