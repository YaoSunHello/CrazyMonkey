from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from app.atlas import normalize_file
from app.atlas.fixtures import generate_synthetic_pack
from app.relay.snapshot_store import FileSnapshotStore, FrozenSnapshot
from app.runtime.pipeline import run_case
from app.runtime.snapshot import to_snapshot


BACKEND_ROOT = Path(__file__).resolve().parents[2]
EXPORT_SCHEMA_PATH = BACKEND_ROOT / "app" / "schemas" / "review_export.schema.json"


@pytest.fixture(scope="session")
def generated_payload(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Build the export snapshot from generated original files, never expected JSON."""

    source_dir = tmp_path_factory.mktemp("relay-original-sources")
    generate_synthetic_pack(source_dir)
    source_paths = sorted(
        path
        for path in source_dir.iterdir()
        if path.suffix.casefold() in {".pdf", ".xlsx", ".csv"}
    )
    documents = [normalize_file(path) for path in source_paths]
    result = run_case(
        "relay-generated-source-pack",
        "Review management fees and prepare source-linked outputs.",
        documents,
    )
    snapshot = to_snapshot(result, documents, synthetic=True)
    return snapshot.model_dump(mode="json")


@pytest.fixture
def fixture_payload(generated_payload: dict[str, Any]) -> dict[str, Any]:
    # Several contract tests deliberately mutate their input.
    return copy.deepcopy(generated_payload)


@pytest.fixture
def export_schema_path() -> Path:
    assert EXPORT_SCHEMA_PATH.is_file(), "public JSON export schema is missing"
    return EXPORT_SCHEMA_PATH


@pytest.fixture
def snapshot_store(tmp_path: Path) -> FileSnapshotStore:
    return FileSnapshotStore(tmp_path / "snapshots")


@pytest.fixture
def frozen_snapshot(
    fixture_payload: dict[str, Any],
    snapshot_store: FileSnapshotStore,
) -> FrozenSnapshot:
    return snapshot_store.freeze(fixture_payload)
