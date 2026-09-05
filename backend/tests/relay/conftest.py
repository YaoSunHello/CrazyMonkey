from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.relay.snapshot_store import FileSnapshotStore, FrozenSnapshot


BACKEND_ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_FIXTURE_PATH = BACKEND_ROOT / "fixtures" / "synthetic_review_snapshot.json"
EXPORT_SCHEMA_PATH = BACKEND_ROOT / "app" / "schemas" / "review_export.schema.json"


@pytest.fixture
def fixture_path() -> Path:
    assert SYNTHETIC_FIXTURE_PATH.is_file(), "synthetic RELAY fixture is missing"
    return SYNTHETIC_FIXTURE_PATH


@pytest.fixture
def fixture_payload(fixture_path: Path) -> dict[str, Any]:
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


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
