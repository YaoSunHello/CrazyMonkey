"""Validation and deterministic processing behind the UI bridge routes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from fastapi import HTTPException, UploadFile
from pydantic import ValidationError

from app.emit import build as build_profile_projection
from app.ingestion.statements import parse_statement
from app.profiles import PROFILES, available, load, load_all
from app.reference.tables import from_workbook, normalise
from app.ui_bridge.schemas import (
    MAX_BATCH_BYTES,
    MAX_EVENTS,
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_PATH_DEPTH,
    PDF_CONTENT_TYPE,
    XLSX_CONTENT_TYPE,
    JobManifest,
)
from app.ui_bridge.store import (
    JOB_ROOT,
    STORE,
    IdempotencyConflict,
    Job,
    StoreFull,
    StoredInput,
    now,
    safe_remove_job_dir,
)
from app.verification.checks import balance_chain_links, run_parse_checks

EXECUTION_LABEL = "LOCAL_DETERMINISTIC"
MAX_REFERENCE_FILES = 1
MAX_WORKERS = 4
MAX_QUEUED_AND_RUNNING = 16

_EXECUTOR = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="ui-bridge")
_SUBMISSION_SLOTS = threading.BoundedSemaphore(MAX_QUEUED_AND_RUNNING)

_FORBIDDEN_SEGMENTS = {
    ".git",
    ".hg",
    ".svn",
    ".env",
    ".credentials",
    "credentials",
    "node_modules",
    "bower_components",
    "jspm_packages",
    ".pnpm-store",
    "dependencies",
    "deps",
    "vendor",
    ".venv",
    "venv",
    "env",
    "site-packages",
    "__pycache__",
    ".tox",
    ".nox",
    ".mypy_cache",
    ".pytest_cache",
}
_TEMP_SUFFIXES = {".tmp", ".temp", ".swp", ".swo", ".bak", ".part", ".crdownload"}
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def parse_manifest(raw: str) -> JobManifest:
    try:
        manifest = JobManifest.model_validate_json(raw)
    except ValidationError as exc:
        raise _error(422, "INVALID_MANIFEST", str(exc)) from exc
    if len(manifest.files) > MAX_FILES:
        raise _error(413, "TOO_MANY_FILES", f"at most {MAX_FILES} files are accepted")
    if not manifest.files:
        raise _error(422, "EMPTY_BATCH", "at least one selected source file is required")
    return manifest


def validate_idempotency_key(value: str | None) -> str:
    if value is None or not value.strip():
        raise _error(400, "IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key header is required")
    if value != value.strip() or len(value) > 200 or _CONTROL.search(value):
        raise _error(400, "INVALID_IDEMPOTENCY_KEY", "Idempotency-Key is malformed")
    return value


def _normal_content_type(value: str) -> str:
    return value.split(";", 1)[0].strip().casefold()


def _validate_path(relative_path: str, filename: str) -> str:
    if _CONTROL.search(relative_path) or _CONTROL.search(filename):
        raise _error(422, "INVALID_PATH", "paths and filenames cannot contain control characters")
    if "\\" in relative_path or "\\" in filename:
        raise _error(422, "INVALID_PATH", "use relative POSIX paths without backslashes")
    if "/" in filename or filename in {".", ".."}:
        raise _error(422, "INVALID_FILENAME", "filename must be a single path segment")
    if relative_path.startswith("/") or PurePosixPath(relative_path).is_absolute():
        raise _error(422, "ABSOLUTE_PATH", "absolute paths are not accepted")
    windows = PureWindowsPath(relative_path)
    if windows.is_absolute() or windows.drive:
        raise _error(422, "ABSOLUTE_PATH", "absolute or drive-qualified paths are not accepted")

    raw_parts = relative_path.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise _error(422, "PATH_TRAVERSAL", "path segments must be non-empty and cannot traverse")
    if len(raw_parts) - 1 > MAX_PATH_DEPTH:
        raise _error(422, "PATH_TOO_DEEP", f"maximum nesting depth is {MAX_PATH_DEPTH}")
    if raw_parts[-1] != filename:
        raise _error(422, "FILENAME_MISMATCH", "relative_path must end with filename")

    folded_parts = [unicodedata.normalize("NFC", part).casefold() for part in raw_parts]
    if any(
        part in _FORBIDDEN_SEGMENTS or part.startswith(".env.")
        for part in folded_parts[:-1]
    ):
        raise _error(422, "FORBIDDEN_PATH", "dependency, VCS, and environment directories are forbidden")
    folded_name = folded_parts[-1]
    suffix = Path(folded_name).suffix
    if (
        folded_name == ".env"
        or folded_name.startswith(".env.")
        or folded_name in {"credentials", "credentials.json", ".credentials", ".ds_store"}
        or folded_name.startswith("credentials.")
        or folded_name.startswith("~$")
        or folded_name.endswith("~")
        or suffix in _TEMP_SUFFIXES
    ):
        raise _error(422, "FORBIDDEN_FILE", "environment, credential, and temporary files are forbidden")
    return "/".join(folded_parts)


def _supported(profile, purpose: str) -> tuple[str, str]:
    if purpose == "SOURCE":
        kind = str(profile.inputs.get("documents", {}).get("kind", "")).casefold()
        if kind != "pdf":
            raise _error(422, "SOURCE_NOT_SUPPORTED", "this profile has no supported UI source format")
        return ".pdf", PDF_CONTENT_TYPE
    if not profile.inputs.get("tables"):
        raise _error(422, "REFERENCE_NOT_SUPPORTED", "this profile accepts no reference workbook")
    return ".xlsx", XLSX_CONTENT_TYPE


def _validate_manifest_files(manifest: JobManifest, uploads: list[UploadFile], profile) -> None:
    if len(uploads) != len(manifest.files):
        raise _error(422, "FILE_COUNT_MISMATCH", "ordered multipart files must match manifest files")

    client_ids: set[str] = set()
    relative_paths: set[str] = set()
    sources = 0
    references = 0
    declared_total = 0

    for entry, upload in zip(manifest.files, uploads):
        normal_client_id = unicodedata.normalize("NFC", entry.client_file_id).casefold()
        if normal_client_id in client_ids:
            raise _error(422, "DUPLICATE_CLIENT_FILE_ID", "client_file_id values must be unique")
        client_ids.add(normal_client_id)

        normal_path = _validate_path(entry.relative_path, entry.filename)
        if normal_path in relative_paths:
            raise _error(422, "DUPLICATE_RELATIVE_PATH", "relative_path values must be unique")
        relative_paths.add(normal_path)

        if entry.size_bytes <= 0:
            raise _error(422, "EMPTY_FILE", f"{entry.filename} has no declared bytes")
        if entry.size_bytes > MAX_FILE_BYTES:
            raise _error(413, "FILE_TOO_LARGE", f"{entry.filename} exceeds {MAX_FILE_BYTES} bytes")
        declared_total += entry.size_bytes
        if declared_total > MAX_BATCH_BYTES:
            raise _error(413, "BATCH_TOO_LARGE", f"batch exceeds {MAX_BATCH_BYTES} bytes")

        extension, content_type = _supported(profile, entry.purpose)
        if Path(entry.filename).suffix.casefold() != extension:
            raise _error(
                415,
                "UNSUPPORTED_FORMAT",
                f"{entry.filename} is not a supported {entry.purpose} file",
            )
        if _normal_content_type(entry.content_type) != content_type:
            raise _error(415, "UNSUPPORTED_CONTENT_TYPE", f"unsupported declared type for {entry.filename}")
        if upload.filename != entry.filename:
            raise _error(422, "UPLOAD_FILENAME_MISMATCH", "multipart filenames must match the manifest")
        if _normal_content_type(upload.content_type or "") != content_type:
            raise _error(415, "UNSUPPORTED_CONTENT_TYPE", f"unsupported multipart type for {entry.filename}")

        if entry.purpose == "SOURCE":
            sources += 1
        else:
            references += 1

    if sources == 0:
        raise _error(422, "SOURCE_REQUIRED", "at least one SOURCE PDF is required")
    if references > MAX_REFERENCE_FILES:
        raise _error(422, "TOO_MANY_REFERENCES", "at most one REFERENCE workbook is accepted")


def _request_fingerprint(manifest: JobManifest, stored: list[StoredInput]) -> str:
    digest = hashlib.sha256()
    canonical = json.dumps(
        manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    digest.update(canonical)
    for item in stored:
        digest.update(item.client_file_id.encode("utf-8"))
        digest.update(bytes.fromhex(item.sha256))
    return digest.hexdigest()


def create_job(raw_manifest: str, uploads: list[UploadFile], idempotency_key: str | None) -> tuple[Job, bool]:
    key = validate_idempotency_key(idempotency_key)
    manifest = parse_manifest(raw_manifest)
    if manifest.profile_id not in available():
        raise _error(422, "UNKNOWN_PROFILE", "profile_id is not one of the advertised profiles")
    try:
        profile = load(manifest.profile_id)
    except FileNotFoundError as exc:
        raise _error(422, "UNKNOWN_PROFILE", str(exc)) from exc
    except ValueError as exc:
        raise _error(500, "PROFILE_UNAVAILABLE", str(exc)) from exc
    _validate_manifest_files(manifest, uploads, profile)

    job_id = f"job_{uuid.uuid4().hex}"
    directory = JOB_ROOT / job_id
    directory.mkdir(mode=0o700)
    stored: list[StoredInput] = []
    actual_batch_bytes = 0

    try:
        for entry, upload in zip(manifest.files, uploads):
            source_id = f"src_{uuid.uuid4().hex}"
            target_dir = directory / source_id
            target_dir.mkdir(mode=0o700)
            target = target_dir / entry.filename
            file_hash = hashlib.sha256()
            actual = 0
            first = b""
            with target.open("xb") as output:
                while True:
                    chunk = upload.file.read(1024 * 1024)
                    if not chunk:
                        break
                    if not first:
                        first = chunk[:8]
                    actual += len(chunk)
                    actual_batch_bytes += len(chunk)
                    if actual > MAX_FILE_BYTES or actual > entry.size_bytes:
                        raise _error(
                            413,
                            "FILE_SIZE_MISMATCH",
                            f"actual size exceeds declaration for {entry.filename}",
                        )
                    if actual_batch_bytes > MAX_BATCH_BYTES:
                        raise _error(413, "BATCH_TOO_LARGE", f"batch exceeds {MAX_BATCH_BYTES} bytes")
                    output.write(chunk)
                    file_hash.update(chunk)

            if actual == 0 or actual != entry.size_bytes:
                raise _error(
                    422,
                    "FILE_SIZE_MISMATCH",
                    f"actual size does not match declaration for {entry.filename}",
                )
            if entry.purpose == "SOURCE" and not first.startswith(b"%PDF-"):
                raise _error(415, "INVALID_FILE_SIGNATURE", f"{entry.filename} is not a PDF")
            if entry.purpose == "REFERENCE" and not first.startswith(b"PK"):
                raise _error(415, "INVALID_FILE_SIGNATURE", f"{entry.filename} is not an XLSX workbook")

            stored.append(
                StoredInput(
                    source_id=source_id,
                    client_file_id=entry.client_file_id,
                    relative_path=entry.relative_path,
                    filename=entry.filename,
                    size_bytes=actual,
                    content_type=entry.content_type,
                    purpose=entry.purpose,
                    sha256=file_hash.hexdigest(),
                    path=target,
                )
            )

        fingerprint = _request_fingerprint(manifest, stored)
        candidate = Job(
            job_id=job_id,
            idempotency_key=key,
            request_fingerprint=fingerprint,
            profile_id=manifest.profile_id,
            case_name=manifest.case_name,
            directory=directory,
            files=stored,
        )
        candidate.add_event("JOB_QUEUED", "Job accepted for deterministic processing")

        if not _SUBMISSION_SLOTS.acquire(blocking=False):
            raise _error(503, "JOB_QUEUE_FULL", "the bounded local worker queue is full")
        reserved = True
        try:
            job, reused = STORE.add_or_reuse(candidate)
        except IdempotencyConflict as exc:
            raise _error(
                409,
                "IDEMPOTENCY_CONFLICT",
                "Idempotency-Key was already used for a different request",
            ) from exc
        except StoreFull as exc:
            raise _error(503, "JOB_STORE_FULL", "all bounded job slots are currently active") from exc

        if reused:
            _SUBMISSION_SLOTS.release()
            reserved = False
            safe_remove_job_dir(candidate.directory)
            return job, True

        try:
            _EXECUTOR.submit(_run_job_releasing_slot, job)
        except Exception:
            STORE.discard(job.job_id)
            raise
        reserved = False  # worker owns and releases the reservation
        return job, False
    except Exception:
        if "reserved" in locals() and reserved:
            _SUBMISSION_SLOTS.release()
        safe_remove_job_dir(directory)
        raise


def _run_job_releasing_slot(job: Job) -> None:
    try:
        process_job(job)
    finally:
        _SUBMISSION_SLOTS.release()


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _citation(item: StoredInput, provenance) -> dict[str, Any]:
    return {
        "source_id": item.source_id,
        "filename": item.filename,
        "page": provenance.page,
        "bbox": {
            "x0": provenance.x0,
            "top": provenance.top,
            "x1": provenance.x1,
            "bottom": provenance.bottom,
        },
    }


def _finding_id() -> str:
    return f"fnd_{uuid.uuid4().hex}"


def _row_id(item: StoredInput, index: int) -> str:
    return f"{item.source_id}_row_{index:04d}"


def _register_finding(job: Job, *locations: dict[str, Any]) -> None:
    finding_id = locations[0]["finding_id"]
    job.finding_locations.setdefault(finding_id, []).extend(locations)


def _source_result(job: Job, item: StoredInput, profile) -> tuple[dict[str, Any], dict[str, Any] | None]:
    item.processing_state = "PROCESSING"
    job.add_event("SOURCE_STARTED", f"Parsing {item.filename}", item.source_id)
    try:
        statement = parse_statement(item.path)
        checks = run_parse_checks(statement)
    except Exception as exc:  # one malformed source must not sink the batch
        item.processing_state = "FAILED"
        item.error = f"{type(exc).__name__}: {exc}"
        job.add_event(
            "SOURCE_FAILED",
            f"Could not process {item.filename}: {type(exc).__name__}",
            item.source_id,
        )
        return {
            **item.public_status(),
            "sha256": item.sha256,
            "rows": [],
            "transaction_links": [],
            "checks": [],
        }, None

    statuses = [check.status for check in checks]
    outcome = "FAIL" if "FAIL" in statuses else "UNRESOLVED" if "UNRESOLVED" in statuses else "PASS"
    item.processing_state = "SUCCEEDED"
    item.computational_outcome = outcome

    rows: list[dict[str, Any]] = []
    projection_rows: list[dict[str, Any]] = []
    for index, row in enumerate(statement.rows):
        row_id = _row_id(item, index)
        row_data = {
            "row_id": row_id,
            "index": index,
            "bank_reference": row.bank_reference,
            "customer_reference": row.customer_reference,
            "trn_type": row.trn_type,
            "value_date": row.value_date,
            "post_date": row.post_date,
            "time": row.time,
            "narrative": row.narrative,
            "account_number": row.account_number,
            "currency": row.currency,
            "credit": _decimal(row.credit),
            "debit": _decimal(row.debit),
            "balance": _decimal(row.balance),
            "citation": _citation(item, row.provenance),
            "narrative_citation": (
                _citation(item, row.narrative_provenance) if row.narrative_provenance else None
            ),
        }
        rows.append(row_data)
        projection_row = {
            "bank_reference": row.bank_reference,
            "customer_reference": row.customer_reference,
            "trn_type": row.trn_type,
            "value_date": row.value_date,
            "post_date": row.post_date,
            "time": row.time,
            "narrative": row.narrative,
            "account_number": row.account_number,
            "currency": row.currency,
            "credit": _decimal(row.credit),
            "debit": _decimal(row.debit),
            "balance": _decimal(row.balance),
            "page": row.provenance.page,
        }
        # These fields are deliberately explicit rather than absent.  The
        # existing pipeline projection maps an absent resolution to
        # CANNOT_VERIFY, which would be misleading here: this bridge did not
        # run the resolution pass at all.
        for required in profile.output.get("requires") or []:
            projection_row[required] = {"status": "NOT_RUN"}
        projection_rows.append(projection_row)

    links: list[dict[str, Any]] = []
    for checked_link in balance_chain_links(statement):
        index = checked_link.index
        current = statement.rows[index]
        older = statement.rows[index + 1]
        finding_id = _finding_id()
        link = {
            "finding_id": finding_id,
            "link_id": f"{item.source_id}_link_{index:04d}",
            "newer_row_id": _row_id(item, index),
            "older_row_id": _row_id(item, index + 1),
            "status": checked_link.status,
            "balance": _decimal(checked_link.balance),
            "signed_movement": _decimal(checked_link.signed_movement),
            "derived_balance": _decimal(checked_link.derived_balance),
            "comparison_balance": _decimal(checked_link.comparison_balance),
            "difference": _decimal(checked_link.difference),
            "citations": {
                "balance": _citation(item, current.provenance),
                "comparison_balance": _citation(item, older.provenance),
            },
            "review_status": "UNREVIEWED",
            "updated_at": None,
        }
        finding = {
            "finding_id": finding_id,
            "kind": "TRANSACTION_LINK",
            "source_id": item.source_id,
            "status": checked_link.status,
            "review_status": "UNREVIEWED",
            "title": f"Balance link {index + 1}",
            "detail": (
                f"{link['balance']} - ({link['signed_movement']}) = "
                f"{link['derived_balance']}; compared with {link['comparison_balance']}"
            ),
            "evidence": link["citations"],
            "updated_at": None,
        }
        links.append(link)
        _register_finding(job, link, finding)
        job.result_findings.append(finding)  # installed by process_job before this call

    check_results: list[dict[str, Any]] = []
    check_payloads: list[dict[str, Any]] = []
    for check in checks:
        finding_id = _finding_id()
        check_data = {
            "finding_id": finding_id,
            "name": check.name,
            "scope": check.scope,
            "status": check.status,
            "detail": check.detail,
            "evidence": check.evidence,
            "review_status": "UNREVIEWED",
            "updated_at": None,
        }
        finding = {
            "finding_id": finding_id,
            "kind": "CHECK",
            "source_id": item.source_id,
            "status": check.status,
            "review_status": "UNREVIEWED",
            "title": check.name,
            "detail": check.detail,
            "evidence": check.evidence,
            "updated_at": None,
        }
        check_results.append(check_data)
        check_payloads.append(check.model_dump(mode="json"))
        _register_finding(job, check_data, finding)
        job.result_findings.append(finding)

    try:
        projection = build_profile_projection(
            profile,
            {
                "run_id": f"{job.job_id}-{item.source_id}",
                "profile": profile.id,
                "model": None,
                "account": statement.account_short_code,
                "source_file": item.filename,
                "input_documents": [
                    {"filename": item.filename, "sha256": item.sha256, "bytes": item.size_bytes}
                ],
                "rows": projection_rows,
                "checks": check_payloads,
                "rows_in": len(projection_rows),
            },
        )
    except Exception as exc:  # projection is optional; verified extraction is not
        projection = None
        job.projection_errors.append(f"{item.source_id}: {type(exc).__name__}")
        job.add_event(
            "PROJECTION_OMITTED",
            f"Profile projection omitted for {item.filename}: {type(exc).__name__}",
            item.source_id,
        )

    result = {
        **item.public_status(),
        "sha256": item.sha256,
        "statement": {
            "account_short_code": statement.account_short_code,
            "account_name": statement.account_name,
            "account_number": statement.account_number,
            "currency": statement.currency,
            "bank_name": statement.bank_name,
            "date_range": statement.date_range,
            "closing_balance": _decimal(statement.closing_balance),
            "row_count": len(statement.rows),
        },
        "rows": rows,
        "transaction_links": links,
        "checks": check_results,
    }
    job.add_event("SOURCE_COMPLETED", f"Processed {item.filename}: {outcome}", item.source_id)
    return result, (
        {
            "source_id": item.source_id,
            "account": statement.account_short_code,
            "envelope": projection,
        }
        if projection is not None
        else None
    )


def _reference_result(job: Job, item: StoredInput, profile) -> tuple[dict[str, Any], dict[str, Any]]:
    item.processing_state = "PROCESSING"
    job.add_event("REFERENCE_STARTED", f"Validating {item.filename}", item.source_id)
    try:
        table_spec = profile.inputs.get("tables") or {}
        tables = from_workbook(item.path, table_spec)
        for name, spec in table_spec.items():
            actual = {normalise(column).casefold() for column in tables[name].columns}
            expected = {normalise(column).casefold() for column in spec.get("columns") or []}
            missing = expected - actual
            if missing:
                raise ValueError(
                    f"table {name!r} is missing required columns: "
                    f"{', '.join(sorted(missing))}"
                )
        table_summary = [
            {"name": name, "columns": table.columns, "row_count": len(table.rows)}
            for name, table in tables.items()
        ]
        item.processing_state = "SUCCEEDED"
        item.computational_outcome = "PASS"
        job.add_event("REFERENCE_VALID", f"Validated {item.filename}", item.source_id)
        return (
            {
                **item.public_status(),
                "sha256": item.sha256,
                "reference_tables": table_summary,
                "rows": [],
                "transaction_links": [],
                "checks": [],
            },
            {"status": "VALID", "source_id": item.source_id, "tables": table_summary},
        )
    except Exception as exc:  # source PDFs still run if a workbook is bad
        item.processing_state = "FAILED"
        item.error = f"{type(exc).__name__}: {exc}"
        job.add_event(
            "REFERENCE_INVALID",
            f"Could not validate {item.filename}: {type(exc).__name__}",
            item.source_id,
        )
        return (
            {
                **item.public_status(),
                "sha256": item.sha256,
                "reference_tables": [],
                "rows": [],
                "transaction_links": [],
                "checks": [],
            },
            {"status": "INVALID", "source_id": item.source_id, "tables": [], "error": item.error},
        )


def process_job(job: Job) -> None:
    with job.lock:
        job.processing_state = "PROCESSING"
        job.started_at = now()
        job.result_findings.clear()
        job.projection_errors.clear()
        job.finding_locations.clear()
    job.add_event("JOB_STARTED", "Deterministic processing started")

    try:
        profile = load(job.profile_id)
        documents: list[dict[str, Any]] = []
        projections: list[dict[str, Any]] = []
        reference_validation: dict[str, Any] = {"status": "NOT_PROVIDED", "tables": []}

        # Validate reference metadata first, but never use it to invent a resolution.
        for item in job.files:
            if item.purpose == "REFERENCE":
                result, reference_validation = _reference_result(job, item, profile)
                documents.append(result)
        for item in job.files:
            if item.purpose == "SOURCE":
                result, projection = _source_result(job, item, profile)
                documents.append(result)
                if projection is not None:
                    projections.append(projection)

        # Restore the browser's manifest order after reference-first processing.
        order = {item.source_id: index for index, item in enumerate(job.files)}
        documents.sort(key=lambda item: order[item["source_id"]])

        check_tally = {"PASS": 0, "FAIL": 0, "UNRESOLVED": 0}
        link_tally = {"PASS": 0, "FAIL": 0}
        checks_flat: list[dict[str, Any]] = []
        for document in documents:
            for check in document.get("checks", []):
                check_tally.setdefault(check["status"], 0)
                check_tally[check["status"]] += 1
                global_check = {"source_id": document["source_id"], **check}
                checks_flat.append(global_check)
                job.finding_locations[check["finding_id"]].append(global_check)
            for link in document.get("transaction_links", []):
                link_tally[link["status"]] += 1

        succeeded = sum(d["processing_state"] == "SUCCEEDED" for d in documents)
        failed = sum(d["processing_state"] == "FAILED" for d in documents)
        final_state = "SUCCEEDED" if failed == 0 else "PARTIAL" if succeeded else "FAILED"

        projection_payload: dict[str, Any]
        if projections and not job.projection_errors:
            projection_payload = {
                "status": "AVAILABLE",
                "reason": (
                    "Existing profile projection over deterministic extraction; "
                    "agent resolution fields remain NOT_RUN."
                ),
                "data": {"accounts": projections},
            }
        elif job.projection_errors:
            projection_payload = {
                "status": "OMITTED",
                "reason": (
                    "The optional existing profile projection could not be built; "
                    "deterministic rows and checks remain available."
                ),
            }
        else:
            projection_payload = {
                "status": "OMITTED",
                "reason": "No source document completed parsing, so no profile projection could be built.",
            }

        artifact_id = f"art_{uuid.uuid4().hex}"
        artifact_filename = f"{job.job_id}-result.json"
        artifact_path = job.directory / artifact_filename
        result = {
            "job_id": job.job_id,
            "profile_id": job.profile_id,
            "case_name": job.case_name,
            "execution_label": EXECUTION_LABEL,
            "processing_state": final_state,
            "summary": {
                "documents_total": len(documents),
                "documents_succeeded": succeeded,
                "documents_failed": failed,
                "checks": check_tally,
                "transaction_links": link_tally,
            },
            "reference_validation": reference_validation,
            "agent_resolution": {
                "status": "NOT_RUN",
                "reason": (
                    "This local deterministic bridge does not run the agent resolution "
                    "or classification pass."
                ),
            },
            "documents": documents,
            "checks": checks_flat,
            "findings": job.result_findings,
            "profile_projection": projection_payload,
            "artifacts": [
                {
                    "artifact_id": artifact_id,
                    "kind": "RESULT_JSON",
                    "filename": artifact_filename,
                    "content_type": "application/json",
                    "url": f"/api/ui/v1/jobs/{job.job_id}/artifacts/{artifact_id}",
                }
            ],
        }
        with job.lock:
            job.processing_state = final_state
            job.completed_at = now()
            job.result = result
            job.artifact_id = artifact_id
            job.artifact_path = artifact_path
            _write_artifact_locked(job)
            job.add_event("JOB_COMPLETED", f"Deterministic processing completed: {final_state}")
    except Exception as exc:  # a server-side fault still yields a terminal, inspectable job
        with job.lock:
            job.processing_state = "FAILED"
            job.completed_at = now()
            job.result = {
                "job_id": job.job_id,
                "profile_id": job.profile_id,
                "case_name": job.case_name,
                "execution_label": EXECUTION_LABEL,
                "processing_state": "FAILED",
                "summary": {
                    "documents_total": len(job.files),
                    "documents_succeeded": 0,
                    "documents_failed": len(job.files),
                    "checks": {"PASS": 0, "FAIL": 0, "UNRESOLVED": 0},
                    "transaction_links": {"PASS": 0, "FAIL": 0},
                },
                "reference_validation": {"status": "NOT_PROVIDED", "tables": []},
                "agent_resolution": {
                    "status": "NOT_RUN",
                    "reason": (
                        "This local deterministic bridge does not run the agent "
                        "resolution or classification pass."
                    ),
                },
                "documents": [],
                "checks": [],
                "findings": [],
                "profile_projection": {"status": "OMITTED", "reason": "Job processing failed."},
                "artifacts": [],
                "error": f"{type(exc).__name__}: {exc}",
            }
            job.add_event("JOB_FAILED", f"Job processing failed: {type(exc).__name__}")


def _write_artifact_locked(job: Job) -> None:
    if job.artifact_path is None or job.result is None:
        return
    payload = {
        "schema_version": "ui.v1",
        "artifact_kind": "RESULT_JSON",
        "result": job.result,
    }
    temporary = job.artifact_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, job.artifact_path)


def job_status(job: Job) -> dict[str, Any]:
    with job.lock:
        return {
            "job_id": job.job_id,
            "profile_id": job.profile_id,
            "case_name": job.case_name,
            "execution_label": EXECUTION_LABEL,
            "processing_state": job.processing_state,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "documents": [item.public_status() for item in job.files],
            "events": list(job.events),
            "event_trace": {
                "bounded": True,
                "max_events": MAX_EVENTS,
                "truncated": job.events_truncated,
            },
            "links": {"result": f"/api/ui/v1/jobs/{job.job_id}/result"},
        }


def patch_review(job: Job, finding_id: str, review_status: str) -> dict[str, Any]:
    with job.lock:
        if job.result is None:
            raise _error(409, "RESULT_NOT_READY", "review state is available only after processing completes")
        locations = job.finding_locations.get(finding_id)
        if not locations:
            raise _error(404, "FINDING_NOT_FOUND", "no such finding belongs to this job")
        computed = locations[0]["status"]
        if any(location["status"] != computed for location in locations):
            raise RuntimeError("computational finding outcome diverged")
        updated = now()
        for location in locations:
            location["review_status"] = review_status
            location["updated_at"] = updated
        _write_artifact_locked(job)
        return {
            "job_id": job.job_id,
            "finding_id": finding_id,
            "status": computed,
            "review_status": review_status,
            "updated_at": updated,
        }


def capabilities() -> dict[str, Any]:
    profiles = []
    for profile in load_all():
        if not profile.passes:
            continue
        source_kind = str(profile.inputs.get("documents", {}).get("kind", "")).casefold()
        # The UI bridge is a deterministic statement-review surface. Profiles
        # without PDF documents (for example, an agent-only screening profile)
        # remain discoverable through /api/profiles but must not be advertised
        # here as a workflow the bridge can actually start.
        if source_kind != "pdf":
            continue
        source_formats = [{"extension": ".pdf", "content_types": [PDF_CONTENT_TYPE]}]
        reference_formats = (
            [{"extension": ".xlsx", "content_types": [XLSX_CONTENT_TYPE]}]
            if profile.inputs.get("tables")
            else []
        )
        tables = [
            {
                "name": name,
                "sheet": spec.get("sheet"),
                "columns": spec.get("columns") or [],
            }
            for name, spec in (profile.inputs.get("tables") or {}).items()
        ]
        profiles.append(
            {
                "profile_id": profile.id,
                "label": profile.label,
                "description": profile.description,
                "source": {"purpose": "SOURCE", "required": True, "formats": source_formats},
                "reference": {
                    "purpose": "REFERENCE",
                    "required": False,
                    "max_files": MAX_REFERENCE_FILES,
                    "formats": reference_formats,
                    "tables": tables,
                },
            }
        )

    return {
        "api_version": "ui.v1",
        "execution": {
            "label": EXECUTION_LABEL,
            "model_calls": 0,
            "browser_commands_executed": False,
        },
        "limits": {
            "max_files": MAX_FILES,
            "max_file_bytes": MAX_FILE_BYTES,
            "max_batch_bytes": MAX_BATCH_BYTES,
            "max_path_depth": MAX_PATH_DEPTH,
            "max_events_per_job": MAX_EVENTS,
        },
        "profiles": profiles,
        "artifacts": {
            "json": {"available": True, "content_type": "application/json"},
            "report": {
                "available": False,
                "reason": "No deterministic PDF/report exporter is implemented in the UI bridge.",
            },
            "workbook": {
                "available": False,
                "reason": "No deterministic XLSX exporter is implemented in the UI bridge.",
            },
        },
        "review_statuses": ["UNREVIEWED", "REVIEWED", "NEEDS_FOLLOW_UP"],
    }


def replay_summaries() -> list[dict[str, Any]]:
    summaries = []
    examples = PROFILES.parent / "examples"
    for path in sorted(examples.glob("batch-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        accounts = payload.get("accounts") or []
        replay_id = path.stem
        summaries.append(
            {
                "replay_id": replay_id,
                "kind": "RECORDED_REPLAY",
                "original_batch_id": payload.get("batch"),
                "profile_id": payload.get("profile"),
                "original_run_ids": [a.get("run_id") for a in accounts if a.get("run_id")],
                "recorded_seconds": sum(float(a.get("seconds") or 0) for a in accounts),
                "model_calls": 0,
                "model_calls_scope": "REPLAY_READ",
                "event_trace_available": False,
                "links": {"self": f"/api/ui/v1/replays/{replay_id}"},
            }
        )
    return summaries


def replay_detail(replay_id: str) -> dict[str, Any] | None:
    summary = next((item for item in replay_summaries() if item["replay_id"] == replay_id), None)
    if summary is None:
        return None
    path = PROFILES.parent / "examples" / f"{replay_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        **summary,
        "accounts": payload.get("accounts") or [],
        "timing": {"mode": "RECORDED_SECONDS", "compression_performed": False},
        "note": (
            "Committed examples contain recorded results but no event trace; no timing "
            "compression is performed and this replay makes zero model calls."
        ),
    }
