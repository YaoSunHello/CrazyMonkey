"""Reproduce the implemented ingestion demo and expose missing V0 stages.

Run from the repository root:
    PYTHONPATH=backend python backend/tests/run_qa_demo.py --output outputs/qa

The output directory must be new. Generated JSON is QA evidence, not a product
review or an email-ready delivery package. No model or email credentials needed.
Exit status is 1 while the complete V0 pipeline is unavailable, even if all
implemented ingestion steps pass.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from app.atlas.fixtures import generate_synthetic_pack
from app.atlas.ingestion import normalize_file
from app.atlas.models import NormalizedDocument
from test_qa_unseen import generate_unseen_cases


MISSING_STAGES = [
    "primary_agent", "red_team", "deterministic_verifier", "bounded_repair",
    "output_router", "output_generation", "email_package",
]


def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=False)
    started = perf_counter()
    source_dir = output_dir / "standard_sources"
    manifest = generate_synthetic_pack(source_dir)
    packs = [{"case_id": "standard_fixture", "paths": [source_dir / item["filename"]
              for item in manifest["files"]]}]
    packs.extend(generate_unseen_cases(output_dir / "unseen_sources"))
    results = []
    for pack in packs:
        pack_started = perf_counter()
        documents = []
        for source in pack["paths"]:
            normalized = normalize_file(source)
            artifact = output_dir / "normalized" / pack["case_id"] / f"{source.name}.json"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text(normalized.model_dump_json(indent=2) + "\n", encoding="utf-8")
            # Re-open the actual generated artifact against its strict contract.
            parsed = NormalizedDocument.model_validate_json(artifact.read_text(encoding="utf-8"))
            assert parsed == normalized
            documents.append({
                "filename": source.name, "status": normalized.document.extraction_status,
                "evidence_count": len(normalized.evidence), "warnings": normalized.document.warnings,
                "normalized_artifact": str(artifact.relative_to(output_dir)),
            })
        results.append({
            "case_id": pack["case_id"], "documents": documents,
            "duration_seconds": round(perf_counter() - pack_started, 6),
            "last_completed_stage": "source_normalization",
            "financial_result": "NOT_EXECUTABLE: verifier absent",
        })
    report = {
        "synthetic": True, "qa_ingestion_status": "PASS",
        "full_demo_status": "FAIL", "full_demo_duration_seconds": None,
        "reason": "The committed V0 ends at source normalization; downstream stages are absent.",
        "missing_stages": MISSING_STAGES,
        "generation_and_ingestion_seconds": round(perf_counter() - started, 6),
        "cases": results,
        "product_output_files": [], "email_package": None,
        "lp03_runtime_verdict": None,
        "notice": "Source fixtures and normalized QA JSON are not verified financial outputs.",
    }
    summary_path = output_dir / "qa_demo_result.json"
    summary_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    assert json.loads(summary_path.read_text(encoding="utf-8")) == report
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["full_demo_status"] == "PASS" else 1)
