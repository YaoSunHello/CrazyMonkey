"""Bounded in-memory job state and safely-scoped temporary storage."""

from __future__ import annotations

import atexit
import shutil
import tempfile
import threading
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.trace import Event
from app.ui_bridge.schemas import MAX_EVENTS

MAX_JOBS = 64
JOB_ROOT = Path(tempfile.gettempdir()) / "crazymonkey-ui-bridge"
JOB_ROOT.mkdir(parents=True, exist_ok=True)

_EVENT_PRESENTATION = {
    "JOB_QUEUED": ("state", "queued", "ok"),
    "JOB_STARTED": ("state", "starting", "running"),
    "SOURCE_STARTED": ("tool", "parse_statement", "running"),
    "SOURCE_FAILED": ("tool", "parse_statement", "fail"),
    "PROJECTION_OMITTED": ("tool", "profile_projection", "skip"),
    "SOURCE_COMPLETED": ("tool", "run_parse_checks", "ok"),
    "REFERENCE_STARTED": ("tool", "validate_reference", "running"),
    "REFERENCE_VALID": ("tool", "validate_reference", "ok"),
    "REFERENCE_INVALID": ("tool", "validate_reference", "fail"),
    "JOB_COMPLETED": ("state", "completed", "ok"),
    "JOB_FAILED": ("state", "failed", "fail"),
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass
class StoredInput:
    source_id: str
    client_file_id: str
    relative_path: str
    filename: str
    size_bytes: int
    content_type: str
    purpose: str
    sha256: str
    path: Path
    processing_state: str = "PENDING"
    computational_outcome: str | None = None
    error: str | None = None
    atlas: dict[str, Any] | None = None

    def public_status(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "client_file_id": self.client_file_id,
            "relative_path": self.relative_path,
            "filename": self.filename,
            "purpose": self.purpose,
            "processing_state": self.processing_state,
            "computational_outcome": self.computational_outcome,
            "error": self.error,
            "atlas": self.atlas,
        }


@dataclass
class Job:
    job_id: str
    idempotency_key: str
    request_fingerprint: str
    profile_id: str
    case_name: str
    directory: Path
    files: list[StoredInput]
    processing_state: str = "QUEUED"
    created_at: str = field(default_factory=now)
    started_at: str | None = None
    completed_at: str | None = None
    result: dict[str, Any] | None = None
    artifact_id: str | None = None
    artifact_path: Path | None = None
    events_truncated: bool = False
    event_sequence: int = 0
    events: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=MAX_EVENTS))
    finding_locations: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    result_findings: list[dict[str, Any]] = field(default_factory=list)
    projection_errors: list[str] = field(default_factory=list)
    lock: threading.RLock = field(default_factory=threading.RLock)

    def add_event(self, event_type: str, message: str, source_id: str | None = None) -> None:
        with self.lock:
            if len(self.events) == self.events.maxlen:
                self.events_truncated = True
            self.event_sequence += 1
            kind, label, status = _EVENT_PRESENTATION[event_type]
            meta: dict[str, Any] = {
                "event_type": event_type,
                "sequence": self.event_sequence,
            }
            if source_id is not None:
                meta["source_id"] = source_id
            event = Event(
                kind=kind,
                label=label,
                detail=message,
                status=status,
                meta=meta,
            )
            # Event is the repository's seven-field trace contract. Keep
            # sequencing and bridge-specific source IDs inside meta rather
            # than creating a second event shape for the browser.
            self.events.append(
                {
                    "kind": event.kind,
                    "label": event.label,
                    "detail": event.detail,
                    "status": event.status,
                    "body": event.body,
                    "meta": event.meta,
                    "at": event.at,
                }
            )


class IdempotencyConflict(Exception):
    pass


class StoreFull(Exception):
    pass


class JobStore:
    """At most ``MAX_JOBS`` live/recent jobs, oldest terminal jobs pruned first."""

    def __init__(self) -> None:
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._keys: dict[str, str] = {}
        self._lock = threading.RLock()

    def add_or_reuse(self, job: Job) -> tuple[Job, bool]:
        pruned: list[Job] = []
        with self._lock:
            previous_id = self._keys.get(job.idempotency_key)
            if previous_id is not None:
                previous = self._jobs.get(previous_id)
                if previous is not None:
                    if previous.request_fingerprint != job.request_fingerprint:
                        raise IdempotencyConflict
                    return previous, True
                self._keys.pop(job.idempotency_key, None)

            while len(self._jobs) >= MAX_JOBS:
                terminal_id = next(
                    (
                        job_id
                        for job_id, candidate in self._jobs.items()
                        if candidate.processing_state in {"SUCCEEDED", "PARTIAL", "FAILED"}
                    ),
                    None,
                )
                if terminal_id is None:
                    raise StoreFull
                old = self._jobs.pop(terminal_id)
                self._keys.pop(old.idempotency_key, None)
                pruned.append(old)

            self._jobs[job.job_id] = job
            self._keys[job.idempotency_key] = job.job_id

        for old in pruned:
            safe_remove_job_dir(old.directory)
        return job, False

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def discard(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.pop(job_id, None)
            if job is not None:
                self._keys.pop(job.idempotency_key, None)
        if job is not None:
            safe_remove_job_dir(job.directory)

    def clear(self) -> None:
        """Test/process cleanup without ever removing anything outside JOB_ROOT."""
        with self._lock:
            jobs = list(self._jobs.values())
            self._jobs.clear()
            self._keys.clear()
        for job in jobs:
            safe_remove_job_dir(job.directory)


def safe_remove_job_dir(path: Path) -> None:
    """Remove only a direct, server-generated child of our dedicated root."""
    try:
        root = JOB_ROOT.resolve()
        target = path.resolve()
    except OSError:
        return
    if target.parent != root or not target.name.startswith("job_"):
        return
    shutil.rmtree(target, ignore_errors=True)


STORE = JobStore()
atexit.register(STORE.clear)
