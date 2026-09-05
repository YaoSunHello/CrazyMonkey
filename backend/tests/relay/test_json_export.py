from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.relay.json_export import validate_json_export, write_json_export
from app.relay.snapshot_store import FrozenSnapshot


GENERATED_AT = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


def test_json_export_validates_and_contains_complete_review_contract(
    tmp_path: Path,
    frozen_snapshot: FrozenSnapshot,
    export_schema_path: Path,
) -> None:
    path = tmp_path / "review.json"

    returned_payload = write_json_export(
        path,
        frozen_snapshot,
        GENERATED_AT,
        export_schema_path,
    )
    parsed_payload = json.loads(path.read_text(encoding="utf-8"))

    assert parsed_payload == returned_payload
    validate_json_export(parsed_payload, export_schema_path)
    assert parsed_payload["export_metadata"] == {
        "run_id": frozen_snapshot.snapshot.run_id,
        "version": frozen_snapshot.snapshot.version,
        "snapshot_sha256": frozen_snapshot.snapshot_sha256,
        "generated_at": "2026-09-05T12:00:00Z",
        "reporting_period": frozen_snapshot.snapshot.reporting_period,
        "mode": "SYNTHETIC_DEMO",
        "mode_label": "Synthetic Demo",
    }
    assert parsed_payload["summary"] == {
        "checks_completed": 6,
        "matches": 3,
        "discrepancies": 2,
        "cannot_verify": 1,
        "unsupported": 0,
        "unreviewed": 6,
    }

    by_investor = {
        finding["investor_id"]: finding for finding in parsed_payload["findings"]
    }
    assert by_investor["LP03"]["administrator_value"] == 50_000
    assert by_investor["LP03"]["expected_value"] == 37_500
    assert by_investor["LP03"]["difference"] == 12_500
    assert by_investor["LP04"]["administrator_value"] == 50_000
    assert by_investor["LP04"]["expected_value"] == 40_000
    assert by_investor["LP04"]["difference"] == 10_000
    assert by_investor["LP06"]["computational_status"] == "CANNOT_VERIFY"
    assert by_investor["LP06"]["expected_value"] is None

    assert parsed_payload["source_documents"]
    assert parsed_payload["evidence_references"]
    assert parsed_payload["calculations"]
    assert parsed_payload["challenger_concerns"]
    assert parsed_payload["verifier_results"]
    assert parsed_payload["human_review_decisions"]
    assert parsed_payload["unresolved_issues"]
    assert parsed_payload["audit_trail"][-1]["action"] == "OUTPUT_SNAPSHOT_FROZEN"


def test_json_export_is_byte_deterministic_for_frozen_snapshot_and_timestamp(
    tmp_path: Path,
    frozen_snapshot: FrozenSnapshot,
    export_schema_path: Path,
) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    write_json_export(first, frozen_snapshot, GENERATED_AT, export_schema_path)
    write_json_export(second, frozen_snapshot, GENERATED_AT, export_schema_path)

    assert first.read_bytes() == second.read_bytes()
