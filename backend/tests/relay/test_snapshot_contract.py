from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from app.relay.contracts import SnapshotContractError, adapt_review_snapshot
from app.relay.models import FindingStatus, ReviewMode
from app.relay.snapshot_store import (
    FileSnapshotStore,
    FrozenSnapshot,
    SnapshotConflictError,
)


ATLAS_SYNTHETIC_EXPECTED = (
    Path(__file__).resolve().parents[1]
    / "atlas"
    / "expected"
    / "synthetic_expected.json"
)


def _set_fund_name(payload: dict[str, Any], value: str) -> None:
    if "fundName" in payload:
        payload["fundName"] = value
    else:
        payload["fund_name"] = value


def test_synthetic_fixture_adapts_to_one_valid_output_snapshot(
    fixture_payload: dict[str, Any],
) -> None:
    snapshot = adapt_review_snapshot(fixture_payload)

    assert snapshot.mode == ReviewMode.SYNTHETIC_DEMO
    assert snapshot.coverage.scope == "Management-fee checks only"
    assert snapshot.coverage.checks_completed == 6
    assert snapshot.summary_counts() == {
        "checks_completed": 6,
        "matches": 3,
        "discrepancies": 2,
        "cannot_verify": 1,
        "unsupported": 0,
        "unreviewed": 6,
    }

    by_investor = {finding.investor_id: finding for finding in snapshot.findings}
    assert by_investor["LP03"].computational_status == FindingStatus.DISCREPANCY
    assert by_investor["LP03"].administrator_value == 50_000
    assert by_investor["LP03"].expected_value == 37_500
    assert by_investor["LP03"].difference == 12_500
    assert by_investor["LP04"].administrator_value == 50_000
    assert by_investor["LP04"].expected_value == 40_000
    assert by_investor["LP04"].difference == 10_000
    assert by_investor["LP06"].computational_status == FindingStatus.CANNOT_VERIFY
    assert by_investor["LP06"].expected_value is None


def test_relay_demo_values_match_atlas_synthetic_expectations(
    fixture_payload: dict[str, Any],
) -> None:
    expected = json.loads(ATLAS_SYNTHETIC_EXPECTED.read_text(encoding="utf-8"))
    snapshot = adapt_review_snapshot(fixture_payload)
    actual = {finding.investor_id: finding for finding in snapshot.findings}

    assert snapshot.reporting_period == expected["reporting_period"]
    assert snapshot.summary_counts() | {"unreviewed": 0} == expected["summary"] | {
        "unreviewed": 0
    }
    for investor_id, record in expected["findings"].items():
        finding = actual[investor_id]
        assert finding.administrator_value == (
            float(record["reported"]) if record["reported"] is not None else None
        )
        assert finding.expected_value == (
            float(record["expected"]) if record["expected"] is not None else None
        )
        assert finding.difference == (
            float(record["difference"]) if record["difference"] is not None else None
        )
        assert finding.computational_status.value == record["status"]


def test_freeze_persists_canonical_digest_and_isolated_snapshot(
    fixture_payload: dict[str, Any],
    snapshot_store: FileSnapshotStore,
) -> None:
    original_payload = copy.deepcopy(fixture_payload)
    frozen = snapshot_store.freeze(fixture_payload)

    assert frozen.path.is_file()
    assert hashlib.sha256(frozen.path.read_bytes()).hexdigest() == frozen.snapshot_sha256
    assert frozen.identity == (
        frozen.snapshot.run_id,
        frozen.snapshot.version,
        frozen.snapshot_sha256,
    )

    _set_fund_name(fixture_payload, "MUTATED AFTER FREEZE")
    loaded = snapshot_store.get(frozen.snapshot.run_id, frozen.snapshot.version)
    repeated = snapshot_store.freeze(original_payload)

    assert loaded.identity == frozen.identity
    assert repeated.identity == frozen.identity
    assert loaded.snapshot.fund_name != "MUTATED AFTER FREEZE"


def test_frozen_models_cannot_be_mutated(frozen_snapshot: FrozenSnapshot) -> None:
    with pytest.raises(Exception):
        frozen_snapshot.snapshot.reporting_period = "changed"  # type: ignore[misc]
    with pytest.raises(Exception):
        frozen_snapshot.snapshot.findings[0].explanation = "changed"  # type: ignore[misc]


def test_same_run_and_version_cannot_be_replaced(
    fixture_payload: dict[str, Any],
    snapshot_store: FileSnapshotStore,
) -> None:
    snapshot_store.freeze(fixture_payload)
    conflicting = copy.deepcopy(fixture_payload)
    _set_fund_name(conflicting, "Different bytes for the same frozen version")

    with pytest.raises(SnapshotConflictError, match="already frozen|concurrent freeze conflict"):
        snapshot_store.freeze(conflicting)


def test_route_run_id_must_match_payload(fixture_payload: dict[str, Any]) -> None:
    with pytest.raises(SnapshotContractError, match="run_id mismatch"):
        adapt_review_snapshot(fixture_payload, route_run_id="different-run")


@pytest.mark.parametrize(
    "unsafe_run_id",
    ["../escape", "/absolute", "nested/path", "", "space is unsafe"],
)
def test_snapshot_store_rejects_unsafe_run_ids(
    snapshot_store: FileSnapshotStore,
    unsafe_run_id: str,
) -> None:
    with pytest.raises(SnapshotContractError, match="unsafe run_id"):
        snapshot_store.get(unsafe_run_id)


@pytest.mark.parametrize(
    "private_key",
    ["chain_of_thought", "private-reasoning", "system prompt", "raw_prompt"],
)
def test_contract_rejects_private_reasoning_anywhere(
    fixture_payload: dict[str, Any],
    private_key: str,
) -> None:
    payload = copy.deepcopy(fixture_payload)
    payload.setdefault("metadata", {})[private_key] = "must never be exported"

    with pytest.raises(SnapshotContractError, match="private field is not exportable"):
        adapt_review_snapshot(payload)


def test_canonical_boundary_drops_unrecognised_upstream_internals(
    fixture_payload: dict[str, Any],
) -> None:
    canonical = adapt_review_snapshot(fixture_payload).to_jsonable()
    canonical["raw_model_response"] = {"completion": "internal model output"}
    canonical["messages"] = [{"role": "system", "content": "internal"}]
    canonical["id"] = canonical["run_id"]  # upstream alias, not an exported duplicate
    canonical["findings"][0]["internal_notes"] = "not part of the output contract"

    exported = adapt_review_snapshot(canonical).to_jsonable()
    exported_text = json.dumps(exported, sort_keys=True)

    assert "raw_model_response" not in exported
    assert "messages" not in exported
    assert "id" not in exported
    assert "internal_notes" not in exported["findings"][0]
    assert "internal model output" not in exported_text


def test_conflicting_duplicate_run_id_alias_is_rejected(
    fixture_payload: dict[str, Any],
) -> None:
    canonical = adapt_review_snapshot(fixture_payload).to_jsonable()
    canonical["id"] = "a-different-run-id"

    with pytest.raises(SnapshotContractError, match="run_id|alias|conflict"):
        adapt_review_snapshot(canonical)


def test_missing_timestamp_is_rejected_instead_of_using_wall_clock_time(
    fixture_payload: dict[str, Any],
) -> None:
    canonical = adapt_review_snapshot(fixture_payload).to_jsonable()
    canonical.pop("timestamp")

    with pytest.raises(SnapshotContractError, match="timestamp"):
        adapt_review_snapshot(canonical)


def test_duplicate_evidence_ids_are_rejected(fixture_payload: dict[str, Any]) -> None:
    canonical = adapt_review_snapshot(fixture_payload).to_jsonable()
    assert canonical["evidence_references"]
    canonical["evidence_references"].append(
        copy.deepcopy(canonical["evidence_references"][0])
    )

    with pytest.raises(SnapshotContractError, match="duplicate evidence"):
        adapt_review_snapshot(canonical)


@pytest.mark.parametrize("invalid_number", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_are_rejected(
    fixture_payload: dict[str, Any],
    invalid_number: float,
) -> None:
    canonical = adapt_review_snapshot(fixture_payload).to_jsonable()
    canonical["findings"][0]["administrator_value"] = invalid_number

    with pytest.raises(SnapshotContractError, match="finite number"):
        adapt_review_snapshot(canonical)


@pytest.mark.parametrize(
    ("identity_field", "tampered_value"),
    [("run_id", "other-valid-run"), ("version", 99)],
)
def test_store_get_rejects_snapshot_with_tampered_embedded_identity(
    fixture_payload: dict[str, Any],
    snapshot_store: FileSnapshotStore,
    identity_field: str,
    tampered_value: Any,
) -> None:
    frozen = snapshot_store.freeze(fixture_payload)
    on_disk = json.loads(frozen.path.read_text(encoding="utf-8"))
    on_disk[identity_field] = tampered_value
    frozen.path.write_text(json.dumps(on_disk), encoding="utf-8")

    with pytest.raises((SnapshotConflictError, SnapshotContractError)):
        snapshot_store.get(frozen.snapshot.run_id, frozen.snapshot.version)
