from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .contracts import SnapshotContractError, adapt_review_snapshot
from .models import OutputSnapshotView


class SnapshotNotFoundError(FileNotFoundError):
    pass


class SnapshotConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class FrozenSnapshot:
    snapshot: OutputSnapshotView
    snapshot_sha256: str
    path: Path

    @property
    def identity(self) -> tuple[str, int, str]:
        return self.snapshot.run_id, self.snapshot.version, self.snapshot_sha256


class FileSnapshotStore:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def freeze(self, payload: dict[str, Any], route_run_id: str | None = None) -> FrozenSnapshot:
        snapshot = adapt_review_snapshot(payload, route_run_id=route_run_id)
        canonical = canonical_snapshot_bytes(snapshot)
        digest = hashlib.sha256(canonical).hexdigest()
        target = self._snapshot_path(snapshot.run_id, snapshot.version)
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists():
            existing_bytes = target.read_bytes()
            existing_digest = hashlib.sha256(existing_bytes).hexdigest()
            if existing_digest != digest:
                raise SnapshotConflictError(
                    f"run {snapshot.run_id!r} version {snapshot.version} is already frozen "
                    "with different content; create a new version"
                )
            existing = OutputSnapshotView.model_validate_json(existing_bytes)
            return FrozenSnapshot(existing, existing_digest, target)

        fd, temporary_name = tempfile.mkstemp(prefix="snapshot-", suffix=".json", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(canonical)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary_name, target)
            except FileExistsError:
                existing_bytes = target.read_bytes()
                existing_digest = hashlib.sha256(existing_bytes).hexdigest()
                if existing_digest != digest:
                    raise SnapshotConflictError(
                        f"concurrent freeze conflict for {snapshot.run_id!r} version {snapshot.version}"
                    )
            return FrozenSnapshot(snapshot, digest, target)
        finally:
            Path(temporary_name).unlink(missing_ok=True)

    def get(self, run_id: str, version: int | None = None) -> FrozenSnapshot:
        _validate_run_id(run_id)
        if version is None:
            run_dir = self.root / run_id
            versions = []
            if run_dir.exists():
                for candidate in run_dir.glob("v*/snapshot.json"):
                    try:
                        versions.append(int(candidate.parent.name[1:]))
                    except ValueError:
                        continue
            if not versions:
                raise SnapshotNotFoundError(f"no frozen snapshot for run {run_id!r}")
            version = max(versions)
        target = self._snapshot_path(run_id, version)
        if not target.exists():
            raise SnapshotNotFoundError(f"no frozen snapshot for run {run_id!r} version {version}")
        raw = target.read_bytes()
        try:
            snapshot = OutputSnapshotView.model_validate_json(raw)
        except ValidationError as exc:
            raise SnapshotConflictError("stored snapshot failed integrity validation") from exc
        if snapshot.run_id != run_id or snapshot.version != version:
            raise SnapshotConflictError(
                "snapshot content identity does not match its storage path"
            )
        return FrozenSnapshot(snapshot, hashlib.sha256(raw).hexdigest(), target)

    def _snapshot_path(self, run_id: str, version: int) -> Path:
        _validate_run_id(run_id)
        if version < 1:
            raise SnapshotContractError("version must be at least 1")
        return self.root / run_id / f"v{version}" / "snapshot.json"


def canonical_snapshot_bytes(snapshot: OutputSnapshotView) -> bytes:
    return (
        json.dumps(
            snapshot.to_jsonable(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _validate_run_id(run_id: str) -> None:
    if not run_id or len(run_id) > 128 or not run_id[0].isalnum() or any(
        char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
        for char in run_id
    ):
        raise SnapshotContractError("unsafe run_id")
