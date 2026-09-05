"""Runnable originals -> ATLAS -> verified runtime -> review -> RELAY demo.

Only ATLAS generates/extracts original documents. No expected-answer snapshot is
read. The review step is explicitly simulated, and no email transport is called.
"""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from app.atlas import normalize_file
from app.atlas.fixtures import generate_synthetic_pack
from app.relay.export_service import ExportService, default_export_service

from .service import ReviewService


def run_demo(output_root: Path) -> dict:
    # A unique directory makes repeated demos additive and preserves prior artifacts.
    directory = output_root.resolve() / f"demo-{uuid4().hex[:12]}"
    originals = directory / "originals"
    generate_synthetic_pack(originals)
    documents = [normalize_file(path) for path in sorted(originals.iterdir())
                 if path.suffix.lower() in {".pdf", ".xlsx", ".csv"}]
    exports = ExportService(directory / "relay", default_export_service().schema_path)
    service = ReviewService(export_service=exports)
    record = service.create("fee-review-demo", "Review management fees and prepare a review deliverable.", documents, synthetic=True)
    (directory / "normalized_documents.json").write_text(
        json.dumps([document.model_dump(mode="json") for document in documents], indent=2) + "\n")
    (directory / "runtime_result.json").write_text(record.result.model_dump_json(indent=2) + "\n")
    lp03 = next(finding for finding in record.snapshot.findings if finding.investor_id == "LP03")
    reviewed = service.review(
        record.result.run_id, lp03.finding_id, "REVIEWED", "SIMULATED_DEMO_REVIEWER",
        "Simulated review step for the demo, not actual user approval. LP03 discrepancy remains unresolved.",
    )
    (directory / "review_snapshot.json").write_text(reviewed.snapshot.model_dump_json(indent=2) + "\n")
    frozen = exports.snapshot_store.get(reviewed.snapshot.run_id, reviewed.snapshot.version)
    bundle = exports.generate_all(frozen)
    summary = {
        "status": "RUNNABLE_INTEGRATED_DEMO", "mode": record.result.mode,
        "source_files_normalized": len(documents), "repair_count": record.result.repair_count,
        "findings": [{"investor": finding.investor_id, "status": finding.status,
                      "reported": str(finding.reported) if finding.reported is not None else None,
                      "expected": str(finding.expected) if finding.expected is not None else None,
                      "difference": str(finding.difference) if finding.difference is not None else None}
                     for finding in record.result.findings],
        "human_review": "SIMULATED_DEMO_REVIEWER; LP03 stays DISCREPANCY in version 2",
        "email": "DRAFT_NOT_SENT", "directory": str(directory),
        "artifacts": {artifact.artifact_type: str(bundle.directory / artifact.filename) for artifact in bundle.artifacts},
        "snapshot_sha256": bundle.snapshot_sha256,
    }
    (directory / "demo_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("outputs/v0-demo"))
    args = parser.parse_args()
    print(json.dumps(run_demo(args.output), indent=2))


if __name__ == "__main__":
    main()
