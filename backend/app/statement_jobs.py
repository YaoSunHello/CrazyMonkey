"""HTTP bridge from uploaded Calder statements to the existing bank engine.

This module owns transport, persistence and job state only.  It deliberately
does not parse statements, implement accounting checks, prompt a model, or
build journal output.  Those remain respectively in ``ingestion.statements``,
``verification.checks``, ``agent`` and ``emit``.

Two workflows are exposed:

* ``statement-validation`` runs the deterministic parser and arithmetic
  verifier over the uploaded PDFs.  It needs no model and no workbook.
* ``journal-entries`` and ``pipeline-validation`` invoke the existing model
  pipeline.  They require an uploaded reference workbook, model credentials
  and Daytona.  There is no sample-workbook, local-execution, fixture or replay
  fallback at this HTTP boundary.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import os
import re
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import Annotated, Any, Literal
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.atlas import IngestionError, normalize_file
from app.atlas.ingestion import MAX_FILE_BYTES
from app.atlas.models import DocumentRole
from app.config import Settings
from app.emit import build as build_output
from app.ingestion.statements import parse_statement
from app.profiles import load as load_profile
from app.reference.tables import load_tables
from app.verification.checks import run_parse_checks


router = APIRouter(prefix="/api/v1/statement-jobs", tags=["statement-jobs"])

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_JOB_ROOT = ROOT / "outputs" / "statement-jobs"
MAX_DOCUMENTS = 40
MAX_BATCH_BYTES = 100 * 1024 * 1024
MAX_RELATIVE_PATH = 1024

WorkflowId = Literal["statement-validation", "journal-entries", "pipeline-validation"]
InputRole = Literal["BANK_STATEMENT", "REFERENCE_WORKBOOK"]
JobState = Literal[
    "QUEUED",
    "PROCESSING",
    "COMPLETED",
    "COMPLETED_WITH_ISSUES",
    "FAILED",
]

MODEL_WORKFLOWS = {"journal-entries", "pipeline-validation"}
TERMINAL_STATES = {"COMPLETED", "COMPLETED_WITH_ISSUES", "FAILED"}
ISSUE_CHECK_STATES = {"FAIL", "UNRESOLVED", "CANNOT_VERIFY"}


class UploadManifestItem(BaseModel):
    """One browser selection, bound to a stable client identifier."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    client_file_id: str = Field(alias="clientFileId", min_length=1, max_length=128)
    # ``files`` is the authority for the filename and extension-derived role.
    # Accepting these two values in the manifest remains useful for clients
    # that want an extra consistency check, but does not make them trusted.
    filename: str | None = Field(default=None, min_length=1, max_length=255)
    relative_path: str = Field(alias="relativePath", min_length=1, max_length=MAX_RELATIVE_PATH)
    role: InputRole | None = None


class PreparedUpload(BaseModel):
    """Validated upload data retained only until it is written to the job."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    client_file_id: str
    filename: str
    relative_path: str
    role: InputRole
    content: bytes
    source_sha256: str
    atlas_document_id: str
    size_bytes: int
    page_count: int | None = None
    sheet_count: int | None = None
    warnings: list[str] = Field(default_factory=list)


class RequestConflict(ValueError):
    pass


class StatementInputError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _settings() -> Settings:
    """Load backend-only configuration without resolving or calling a model."""

    return Settings(_env_file=str(ROOT / ".env"))


def _model_configuration(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or _settings()
    configured = bool(settings.llm_base_url.strip() and settings.llm_api_key.strip())
    host = (urlparse(settings.llm_base_url).hostname or "").lower()
    provider = None
    if configured:
        provider = settings.llm_provider.strip() or (
            "google-openai-compatible" if "googleapis.com" in host else "openai-compatible"
        )
    return {
        "configured": configured,
        "provider": provider,
        # Do not call Settings.resolved_model here: configuration inspection
        # must never make a paid or remote request.
        "model": settings.llm_model.strip() or None,
    }


def configuration_payload() -> dict[str, Any]:
    settings = _settings()
    model = _model_configuration(settings)
    daytona_configured = bool(settings.daytona_api_key.strip())
    profile_summaries = [load_profile(item).summary() for item in sorted(MODEL_WORKFLOWS)]
    return {
        "backendReachable": True,
        "llmConfigured": model["configured"],
        "daytonaConfigured": daytona_configured,
        "model": model,
        "profiles": profile_summaries,
        "workflows": [
            {
                "id": "statement-validation",
                "label": "Bank statement validation",
                "description": (
                    "Parse supported Calder statement PDFs and verify their running-balance "
                    "arithmetic without a model."
                ),
                "mode": "DETERMINISTIC",
                "acceptedInputs": ["BANK_STATEMENT"],
                "requiredInputs": [
                    {"role": "BANK_STATEMENT", "minimum": 1, "extensions": [".pdf"]}
                ],
                "requiresModel": False,
                "requiresDaytona": False,
                "requiresWorkbook": False,
            },
            {
                "id": "journal-entries",
                "label": "Bank statements to journal entries",
                "description": load_profile("journal-entries").description,
                "mode": "LIVE_MODEL",
                "acceptedInputs": ["BANK_STATEMENT", "REFERENCE_WORKBOOK"],
                "requiredInputs": [
                    {"role": "BANK_STATEMENT", "minimum": 1, "extensions": [".pdf"]},
                    {"role": "REFERENCE_WORKBOOK", "minimum": 1, "maximum": 1, "extensions": [".xlsx"]},
                ],
                "requiresModel": True,
                "requiresDaytona": True,
                "requiresWorkbook": True,
            },
            {
                "id": "pipeline-validation",
                "label": "Model and pipeline validation",
                "description": load_profile("pipeline-validation").description,
                "mode": "LIVE_MODEL",
                "acceptedInputs": ["BANK_STATEMENT", "REFERENCE_WORKBOOK"],
                "requiredInputs": [
                    {"role": "BANK_STATEMENT", "minimum": 1, "extensions": [".pdf"]},
                    {"role": "REFERENCE_WORKBOOK", "minimum": 1, "maximum": 1, "extensions": [".xlsx"]},
                ],
                "requiresModel": True,
                "requiresDaytona": True,
                "requiresWorkbook": True,
            },
        ],
    }


def _plain_filename(upload: UploadFile) -> str:
    name = upload.filename or ""
    if (
        not name
        or len(name) > 255
        or Path(name).name != name
        or any(character in name for character in ("/", "\\", "\x00"))
        or name in {".", ".."}
    ):
        raise HTTPException(422, "Each upload needs a plain filename without directory components")
    return name


def _safe_client_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value):
        raise HTTPException(422, "Invalid client file identifier")
    return value


def _safe_request_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value):
        raise HTTPException(422, "Invalid client request identifier")
    return value


def _safe_instruction(value: str) -> str:
    instruction = value.strip()
    if len(instruction) > 10_000:
        raise HTTPException(422, "Instruction must be 10,000 characters or fewer")
    return instruction


def _safe_relative_path(value: str, filename: str) -> str:
    if "\\" in value or "\x00" in value or len(value) > MAX_RELATIVE_PATH:
        raise HTTPException(422, "Invalid relative upload path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise HTTPException(422, "Invalid relative upload path")
    if path.name != filename:
        raise HTTPException(422, "Relative upload path must end with the uploaded filename")
    return path.as_posix()


def _expected_role(filename: str) -> InputRole:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return "BANK_STATEMENT"
    if suffix == ".xlsx":
        return "REFERENCE_WORKBOOK"
    raise HTTPException(422, "Statement jobs accept only PDF statements and XLSX reference workbooks")


def _validate_workflow_inputs(workflow: WorkflowId, roles: list[InputRole]) -> None:
    statements = roles.count("BANK_STATEMENT")
    workbooks = roles.count("REFERENCE_WORKBOOK")
    if statements < 1:
        raise HTTPException(422, "Select at least one bank statement PDF")
    if workflow == "statement-validation":
        if workbooks:
            raise HTTPException(422, "Bank statement validation does not use a reference workbook")
        return
    if workbooks != 1:
        raise HTTPException(
            422,
            "This workflow requires exactly one uploaded reference workbook; no bundled sample will be used",
        )


def _require_live_configuration() -> None:
    settings = _settings()
    model = _model_configuration(settings)
    missing = []
    if not model["configured"]:
        missing.append("LLM_BASE_URL and LLM_API_KEY")
    if not settings.daytona_api_key.strip():
        missing.append("DAYTONA_API_KEY")
    if missing:
        raise HTTPException(
            503,
            "Live journal processing is not configured. Set "
            + " and ".join(missing)
            + "; no local, fixture, replay, or sample-data fallback was started.",
        )


async def _prepare_uploads(
    files: list[UploadFile],
    file_ids: list[str],
    manifest_text: str,
    workflow: WorkflowId,
) -> list[PreparedUpload]:
    if not 1 <= len(files) <= MAX_DOCUMENTS:
        raise HTTPException(422, f"Select between 1 and {MAX_DOCUMENTS} files")
    if len(file_ids) != len(files) or len(set(file_ids)) != len(files):
        raise HTTPException(422, "File identifiers must uniquely match the selected files")
    try:
        raw_manifest = json.loads(manifest_text)
        if not isinstance(raw_manifest, list) or len(raw_manifest) != len(files):
            raise ValueError("manifest length")
        items = [UploadManifestItem.model_validate(item) for item in raw_manifest]
    except (json.JSONDecodeError, TypeError, ValueError, ValidationError) as exc:
        raise HTTPException(422, "Upload manifest does not match the selected files") from exc
    if len({item.client_file_id for item in items}) != len(items):
        raise HTTPException(422, "Manifest client file identifiers must be unique")
    item_by_id = {item.client_file_id: item for item in items}
    if set(file_ids) != set(item_by_id):
        raise HTTPException(422, "Manifest file identifiers do not match the uploaded files")
    validated: list[
        tuple[UploadFile, str, UploadManifestItem, str, str, InputRole]
    ] = []
    for upload, raw_file_id in zip(files, file_ids, strict=True):
        file_id = _safe_client_id(raw_file_id)
        item = item_by_id[file_id]
        filename = _plain_filename(upload)
        if item.filename is not None and filename != item.filename:
            raise HTTPException(422, "Upload filename does not match its manifest entry")
        relative_path = _safe_relative_path(item.relative_path, filename)
        role = _expected_role(filename)
        if item.role is not None and item.role != role:
            raise HTTPException(
                422,
                f"{filename} must be selected as {role}; roles are assigned by file type, not upload order",
            )
        validated.append((upload, file_id, item, filename, relative_path, role))
    _validate_workflow_inputs(workflow, [entry[-1] for entry in validated])

    prepared: list[PreparedUpload] = []
    total = 0
    with tempfile.TemporaryDirectory(prefix="crazymonkey-statement-upload-") as directory:
        for index, (upload, file_id, _item, filename, relative_path, role) in enumerate(validated):
            content = await upload.read(MAX_FILE_BYTES + 1)
            total += len(content)
            if len(content) > MAX_FILE_BYTES or total > MAX_BATCH_BYTES:
                raise HTTPException(413, "Upload exceeds the 25 MiB per-file or 100 MiB batch limit")
            path = Path(directory) / str(index) / filename
            path.parent.mkdir()
            path.write_bytes(content)
            try:
                normalized = await run_in_threadpool(
                    normalize_file,
                    path,
                    DocumentRole.SUPPORTING,
                    original_storage_key=f"pending/{file_id}/{filename}",
                )
            except IngestionError as exc:
                raise HTTPException(422, f"{exc.code}: {exc.message}") from exc
            prepared.append(
                PreparedUpload(
                    client_file_id=file_id,
                    filename=filename,
                    relative_path=relative_path,
                    role=role,
                    content=content,
                    source_sha256=normalized.document.document_hash,
                    atlas_document_id=normalized.document.document_id,
                    size_bytes=len(content),
                    page_count=(
                        int(normalized.layout["page_count"])
                        if "page_count" in normalized.layout
                        else None
                    ),
                    sheet_count=(
                        int(normalized.layout["sheet_count"])
                        if "sheet_count" in normalized.layout
                        else None
                    ),
                    warnings=list(normalized.document.warnings),
                )
            )
    return prepared


def _job_file_id(item: PreparedUpload) -> str:
    digest = hashlib.sha256(
        f"{item.client_file_id}\0{item.relative_path}\0{item.source_sha256}".encode()
    ).hexdigest()[:24]
    return f"file-{digest}"


def _request_fingerprint(
    workflow: WorkflowId,
    uploads: list[PreparedUpload],
    instruction: str,
) -> str:
    payload = {
        "workflowId": workflow,
        "instruction": instruction,
        "files": sorted(
            [
                {
                    "clientFileId": item.client_file_id,
                    "relativePath": item.relative_path,
                    "role": item.role,
                    "sha256": item.source_sha256,
                }
                for item in uploads
            ],
            key=lambda item: item["clientFileId"],
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _public_check(check: Any, file_item: dict[str, Any]) -> dict[str, Any]:
    raw = check.model_dump(mode="json") if hasattr(check, "model_dump") else dict(check)
    return {
        "name": raw.get("name", "unknown"),
        "status": raw.get("status", "CANNOT_VERIFY"),
        "message": raw.get("detail", ""),
        "evidence": raw.get("evidence") or None,
        "sourceFileId": file_item["fileId"],
        "sourceFilename": file_item["filename"],
    }


def _public_rows(statement: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in statement.rows:
        raw = row.model_dump(mode="json")
        item = {
            "accountNumber": raw.get("account_number"),
            "currency": raw.get("currency"),
            "bankReference": raw.get("bank_reference"),
            "customerReference": raw.get("customer_reference"),
            "transactionType": raw.get("trn_type"),
            "valueDate": raw.get("value_date"),
            "postDate": raw.get("post_date"),
            "time": raw.get("time"),
            "credit": raw.get("credit"),
            "debit": raw.get("debit"),
            "balance": raw.get("balance"),
            "narrative": raw.get("narrative"),
            "provenance": raw.get("provenance"),
            "narrativeProvenance": raw.get("narrative_provenance"),
            "page": row.provenance.page,
            "citation": row.provenance.as_citation(),
        }
        rows.append(item)
    return rows


def _public_recorded_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate model-pipeline rows to the same stable browser contract."""

    aliases = {
        "account_number": "accountNumber",
        "bank_reference": "bankReference",
        "customer_reference": "customerReference",
        "trn_type": "transactionType",
        "value_date": "valueDate",
        "post_date": "postDate",
        "narrative_provenance": "narrativeProvenance",
    }
    public: list[dict[str, Any]] = []
    for raw_row in rows:
        row = {aliases.get(key, key): value for key, value in raw_row.items()}
        provenance = row.get("provenance")
        if isinstance(provenance, dict):
            row.setdefault("page", provenance.get("page"))
            if not row.get("citation") and provenance.get("page") is not None:
                row["citation"] = (
                    f"p{provenance['page']} "
                    f"bbox({provenance.get('x0')},{provenance.get('top')},"
                    f"{provenance.get('x1')},{provenance.get('bottom')})"
                )
        public.append(row)
    return public


def _ensure_supported_statement(statement: Any, filename: str) -> None:
    """Reject PDFs that Atlas can read but the Calder parser cannot support."""

    if (
        not statement.rows
        or not statement.account_number.strip()
        or not statement.currency.strip()
        or statement.closing_balance is None
    ):
        raise StatementInputError(
            f"{filename} is a readable PDF but not a supported Calder bank-statement layout"
        )


class StatementJobService:
    """Small persisted, single-worker job registry for the local V0."""

    def __init__(self, root: Path | None = None) -> None:
        configured = os.getenv("CRAZYMONKEY_STATEMENT_JOB_DIR", "").strip()
        self.root = Path(root or configured or DEFAULT_JOB_ROOT)
        self._lock = RLock()

    def _job_dir(self, job_id: str) -> Path:
        if not re.fullmatch(r"statement-[a-f0-9]{32}", job_id):
            raise KeyError(job_id)
        return self.root / job_id

    def _job_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "job.json"

    def _read(self, job_id: str) -> dict[str, Any]:
        path = self._job_path(job_id)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise KeyError(job_id) from exc

    def _write(self, job: dict[str, Any]) -> None:
        directory = self._job_dir(job["jobId"])
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "job.json"
        temporary = directory / "job.json.tmp"
        temporary.write_text(
            json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(target)

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            return self._public(self._read(job_id))

    @staticmethod
    def _public(job: dict[str, Any]) -> dict[str, Any]:
        public = deepcopy(job)
        public.pop("requestFingerprint", None)
        return public

    def _existing_for_request(self, request_id: str) -> dict[str, Any] | None:
        if not self.root.exists():
            return None
        for path in self.root.glob("statement-*/job.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if job.get("clientRequestId") == request_id:
                return job
        return None

    def create(
        self,
        workflow: WorkflowId,
        client_request_id: str,
        uploads: list[PreparedUpload],
        instruction: str = "",
    ) -> tuple[dict[str, Any], bool]:
        fingerprint = _request_fingerprint(workflow, uploads, instruction)
        with self._lock:
            existing = self._existing_for_request(client_request_id)
            if existing is not None:
                if existing.get("requestFingerprint") != fingerprint:
                    raise RequestConflict(
                        "clientRequestId was already used for different files or a different workflow"
                    )
                return self._public(existing), False

            job_id = f"statement-{uuid4().hex}"
            now = _utc_now()
            job_files = []
            for upload in uploads:
                file_id = _job_file_id(upload)
                source_directory = self._job_dir(job_id) / "sources" / file_id
                source_directory.mkdir(parents=True, exist_ok=False)
                (source_directory / upload.filename).write_bytes(upload.content)
                job_files.append(
                    {
                        "fileId": file_id,
                        "clientFileId": upload.client_file_id,
                        "filename": upload.filename,
                        "relativePath": upload.relative_path,
                        "role": upload.role,
                        "sourceSha256": upload.source_sha256,
                        "atlasDocumentId": upload.atlas_document_id,
                        "sizeBytes": upload.size_bytes,
                        "sourceUrl": f"/api/v1/statement-jobs/{job_id}/sources/{file_id}",
                        "status": "UPLOADED",
                        "summary": "Uploaded and source-linked by ATLAS.",
                        "account": None,
                        "accountNumber": None,
                        "currency": None,
                        "closingBalance": None,
                        "rowCount": None,
                        "pageCount": upload.page_count,
                        "sheetCount": upload.sheet_count,
                        "checks": [],
                        "rows": [],
                        "warnings": upload.warnings,
                        "error": None,
                    }
                )
            job = {
                "jobId": job_id,
                "clientRequestId": client_request_id,
                "instruction": instruction,
                "requestFingerprint": fingerprint,
                "workflowId": workflow,
                "state": "QUEUED",
                "createdAt": now,
                "updatedAt": now,
                "completedAt": None,
                "timeline": [{"state": "QUEUED", "at": now}],
                "fileCount": len(job_files),
                "processedFiles": 0,
                "modelCallCount": 0,
                "modelCallAttempted": False,
                "modelCallSucceeded": None,
                "modelRequested": workflow in MODEL_WORKFLOWS,
                "modelSucceeded": None,
                "modelError": None,
                "runIds": [],
                "manifest": [
                    {
                        key: deepcopy(item[key])
                        for key in (
                            "fileId",
                            "clientFileId",
                            "filename",
                            "relativePath",
                            "role",
                            "sourceSha256",
                            "atlasDocumentId",
                            "sizeBytes",
                            "sourceUrl",
                        )
                    }
                    for item in job_files
                ],
                "files": job_files,
                "summary": None,
                "artifacts": [],
                "error": None,
            }
            self._write(job)
            return self._public(job), True

    def _source_path(self, job_id: str, file_item: dict[str, Any]) -> Path:
        target = self._job_dir(job_id) / "sources" / file_item["fileId"] / file_item["filename"]
        resolved = target.resolve()
        root = self._job_dir(job_id).resolve()
        if root not in resolved.parents or not resolved.is_file():
            raise KeyError(file_item["fileId"])
        return resolved

    def source(self, job_id: str, file_id: str) -> tuple[Path, dict[str, Any]]:
        job = self.get(job_id)
        item = next((item for item in job["files"] if item["fileId"] == file_id), None)
        if item is None:
            raise KeyError(file_id)
        return self._source_path(job_id, item), item

    def artifact(self, job_id: str, artifact_id: str) -> tuple[Path, dict[str, Any]]:
        job = self.get(job_id)
        item = next((item for item in job["artifacts"] if item["id"] == artifact_id), None)
        if item is None:
            raise KeyError(artifact_id)
        target = (self._job_dir(job_id) / "artifacts" / item["filename"]).resolve()
        if self._job_dir(job_id).resolve() not in target.parents or not target.is_file():
            raise KeyError(artifact_id)
        return target, item

    def _update(self, job: dict[str, Any]) -> None:
        job["updatedAt"] = _utc_now()
        with self._lock:
            self._write(job)

    async def process(self, job_id: str) -> None:
        with self._lock:
            job = deepcopy(self._read(job_id))
        if job["state"] != "QUEUED":
            return
        job["state"] = "PROCESSING"
        job.setdefault("timeline", []).append({"state": "PROCESSING", "at": _utc_now()})
        for item in job["files"]:
            item["status"] = "PROCESSING"
        self._update(job)

        try:
            if job["workflowId"] == "statement-validation":
                await self._process_validation(job)
            else:
                await self._process_model_workflow(job)
            self._finish(job)
        except Exception as exc:  # one safe terminal state; never a fallback run
            job["state"] = "FAILED"
            job["error"] = self._safe_error(exc)
            if job["modelRequested"]:
                job["modelSucceeded"] = False
                job["modelCallSucceeded"] = False
                job["modelError"] = (
                    "Live model or Daytona execution failed; no fallback result was used."
                )
            for item in job["files"]:
                if item["status"] not in TERMINAL_STATES:
                    item["status"] = "FAILED"
                    item["error"] = job["error"]
            job["completedAt"] = _utc_now()
            job.setdefault("timeline", []).append(
                {"state": "FAILED", "at": job["completedAt"]}
            )
            self._update(job)

    async def _process_validation(self, job: dict[str, Any]) -> None:
        for item in job["files"]:
            path = self._source_path(job["jobId"], item)
            try:
                statement = await run_in_threadpool(parse_statement, path)
                _ensure_supported_statement(statement, item["filename"])
                checks = await run_in_threadpool(run_parse_checks, statement)
                public_checks = [_public_check(check, item) for check in checks]
                item.update(
                    account=statement.account_short_code,
                    accountNumber=statement.account_number,
                    currency=statement.currency,
                    closingBalance=str(statement.closing_balance),
                    rowCount=len(statement.rows),
                    checks=public_checks,
                    rows=_public_rows(statement),
                    summary=(
                        f"Parsed {len(statement.rows)} rows; "
                        f"{sum(check.status == 'PASS' for check in checks)} of {len(checks)} checks passed."
                    ),
                    status=(
                        "COMPLETED_WITH_ISSUES"
                        if any(check.status in ISSUE_CHECK_STATES for check in checks)
                        else "COMPLETED"
                    ),
                    error=None,
                )
            except Exception as exc:
                item["status"] = "FAILED"
                item["error"] = self._safe_error(exc)
            job["processedFiles"] += 1
            self._update(job)

    async def _process_model_workflow(self, job: dict[str, Any]) -> None:
        # Re-check at execution time so a queued job cannot silently downgrade
        # when configuration changes between upload and processing.
        settings = _settings()
        model = _model_configuration(settings)
        if not model["configured"] or not settings.daytona_api_key.strip():
            raise RuntimeError("Live model and Daytona configuration are required")

        workbook_item = next(
            item for item in job["files"] if item["role"] == "REFERENCE_WORKBOOK"
        )
        workbook_path = self._source_path(job["jobId"], workbook_item)
        profile = load_profile(job["workflowId"])
        try:
            tables = await run_in_threadpool(
                load_tables, profile.inputs, workbook_path=workbook_path
            )
        except Exception as exc:
            raise StatementInputError(
                "The uploaded reference workbook does not contain the sheets and columns required by this workflow"
            ) from exc
        workbook_item.update(
            status="COMPLETED",
            summary=f"Validated {len(tables)} required reference tables from this uploaded workbook.",
            error=None,
        )
        job["processedFiles"] += 1
        self._update(job)

        statement_items = [item for item in job["files"] if item["role"] == "BANK_STATEMENT"]
        parsed = []
        accounts = set()
        for item in statement_items:
            path = self._source_path(job["jobId"], item)
            statement = await run_in_threadpool(parse_statement, path)
            _ensure_supported_statement(statement, item["filename"])
            if statement.account_short_code in accounts:
                raise StatementInputError(
                    "A job cannot contain two statements for the same account short code"
                )
            accounts.add(statement.account_short_code)
            parsed.append((item, path, statement))

        from app.agent import run_agent

        gate = asyncio.Semaphore(5)

        async def run_one(item: dict[str, Any], path: Path, statement: Any) -> None:
            async with gate:
                try:
                    job["modelCallAttempted"] = True
                    self._update(job)
                    result = await run_agent(
                        path,
                        settings,
                        allow_local=False,
                        quiet=True,
                        batch=job["jobId"],
                        profile=job["workflowId"],
                        reference_workbook=workbook_path,
                        instruction=job.get("instruction", ""),
                    )
                    outcome = result["outcome"]
                    job["modelCallCount"] += int(outcome.get("attempts", 0))
                    rows_path = Path(outcome["output_file"])
                    recorded = json.loads(rows_path.read_text(encoding="utf-8"))
                    public_rows = _public_recorded_rows(recorded.get("rows", []))
                    checks = [
                        _public_check(check, item) for check in recorded.get("checks", [])
                    ]
                    input_documents = [
                        {
                            "fileId": source["fileId"],
                            "filename": source["filename"],
                            "relativePath": source["relativePath"],
                            "role": source["role"],
                            "sha256": source["sourceSha256"],
                            "bytes": source["sizeBytes"],
                        }
                        for source in job["files"]
                    ]
                    envelope = build_output(
                        profile,
                        {
                            "run_id": outcome["run_id"],
                            "profile": profile.id,
                            "model": settings.llm_model or None,
                            "account": outcome["account"],
                            "source_file": item["filename"],
                            "input_documents": input_documents,
                            "rows": recorded.get("rows", []),
                            "checks": recorded.get("checks", []),
                        },
                    )
                    has_issues = (not outcome.get("passed")) or any(
                        check["status"] in ISSUE_CHECK_STATES for check in checks
                    )
                    item.update(
                        account=outcome["account"],
                        accountNumber=statement.account_number,
                        currency=statement.currency,
                        closingBalance=str(statement.closing_balance),
                        rowCount=len(public_rows),
                        checks=checks,
                        rows=public_rows,
                        result=envelope,
                        runId=outcome["run_id"],
                        summary=outcome.get("summary", "Model processing completed."),
                        status="COMPLETED_WITH_ISSUES" if has_issues else "COMPLETED",
                        error=None,
                    )
                    job["runIds"].append(outcome["run_id"])
                except Exception:
                    # Provider exceptions can contain endpoints or headers.
                    # Keep the public record actionable without persisting
                    # credentials or arbitrary remote response text.
                    item["status"] = "FAILED"
                    item["error"] = (
                        "Live model or Daytona execution failed for this statement; "
                        "no fallback result was used."
                    )
                finally:
                    job["processedFiles"] += 1
                    self._update(job)

        await asyncio.gather(*(run_one(*entry) for entry in parsed))
        job["modelSucceeded"] = all(
            item["status"] != "FAILED" for item in statement_items
        )
        job["modelCallSucceeded"] = job["modelSucceeded"]
        if not job["modelSucceeded"]:
            job["modelError"] = (
                "At least one live model or Daytona run failed; no fallback result was used."
            )

    def _finish(self, job: dict[str, Any]) -> None:
        statuses = [item["status"] for item in job["files"]]
        bank_statuses = [
            item["status"]
            for item in job["files"]
            if item["role"] == "BANK_STATEMENT"
        ]
        if all(status == "FAILED" for status in statuses) or (
            job["modelRequested"]
            and bank_statuses
            and all(status == "FAILED" for status in bank_statuses)
        ):
            state: JobState = "FAILED"
        elif any(status in {"FAILED", "COMPLETED_WITH_ISSUES"} for status in statuses):
            state = "COMPLETED_WITH_ISSUES"
        else:
            state = "COMPLETED"
        checks = [check for item in job["files"] for check in item.get("checks", [])]
        job["state"] = state
        job["summary"] = {
            "files": len(job["files"]),
            "bankStatements": sum(item["role"] == "BANK_STATEMENT" for item in job["files"]),
            "rows": sum(item.get("rowCount") or 0 for item in job["files"]),
            "checks": {
                status: sum(check["status"] == status for check in checks)
                for status in ("PASS", "FAIL", "UNRESOLVED", "CANNOT_VERIFY")
            },
        }
        job["completedAt"] = _utc_now()
        job.setdefault("timeline", []).append(
            {"state": state, "at": job["completedAt"]}
        )
        self._write_result_artifact(job)
        self._update(job)

    def _write_result_artifact(self, job: dict[str, Any]) -> None:
        directory = self._job_dir(job["jobId"]) / "artifacts"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "result.json"
        payload = {
            key: deepcopy(value)
            for key, value in job.items()
            if key not in {"requestFingerprint", "artifacts"}
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        content = path.read_bytes()
        job["artifacts"] = [
            {
                "id": "result-json",
                "filename": path.name,
                "kind": "RAW_JOB_RECORD",
                "contentType": "application/json",
                "sizeBytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "downloadUrl": (
                    f"/api/v1/statement-jobs/{job['jobId']}/artifacts/result-json"
                ),
            }
        ]

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        if isinstance(exc, StatementInputError):
            return str(exc)
        if isinstance(exc, (FileNotFoundError, json.JSONDecodeError)):
            return "A persisted job input or result could not be read."
        return "Statement processing failed; no fallback result was used."


service = StatementJobService()


@router.get("/config")
def get_configuration() -> dict[str, Any]:
    return configuration_payload()


@router.post("", status_code=202)
async def create_job(
    background_tasks: BackgroundTasks,
    files: Annotated[list[UploadFile], File()],
    fileIds: Annotated[list[str], Form()],
    manifest: Annotated[str, Form()],
    workflowId: Annotated[WorkflowId, Form()],
    clientRequestId: Annotated[str, Form()],
    instruction: Annotated[str, Form()] = "",
) -> dict[str, Any]:
    request_id = _safe_request_id(clientRequestId)
    requested_instruction = _safe_instruction(instruction)
    prepared = await _prepare_uploads(files, fileIds, manifest, workflowId)
    if workflowId in MODEL_WORKFLOWS:
        _require_live_configuration()
    try:
        job, created = service.create(
            workflowId,
            request_id,
            prepared,
            requested_instruction,
        )
    except RequestConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    if created:
        background_tasks.add_task(service.process, job["jobId"])
    return job


@router.get("/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    try:
        return service.get(job_id)
    except KeyError as exc:
        raise HTTPException(404, "Statement job not found") from exc


@router.get("/{job_id}/sources/{file_id}")
def download_source(job_id: str, file_id: str) -> FileResponse:
    try:
        path, item = service.source(job_id, file_id)
    except KeyError as exc:
        raise HTTPException(404, "Statement job source not found") from exc
    media_type = mimetypes.guess_type(item["filename"])[0] or "application/octet-stream"
    return FileResponse(
        path,
        media_type=media_type,
        filename=item["filename"],
        content_disposition_type="inline",
        headers={"ETag": f'"{item["sourceSha256"]}"', "Cache-Control": "private"},
    )


@router.get("/{job_id}/artifacts/{artifact_id}")
def download_artifact(job_id: str, artifact_id: str) -> FileResponse:
    try:
        path, item = service.artifact(job_id, artifact_id)
    except KeyError as exc:
        raise HTTPException(404, "Statement job artifact not found") from exc
    return FileResponse(
        path,
        media_type=item["contentType"],
        filename=item["filename"],
        headers={"ETag": f'"{item["sha256"]}"', "Cache-Control": "private"},
    )


@router.get("/{job_id}/artifact")
def download_result_artifact(job_id: str) -> FileResponse:
    """Convenience alias for the V0 browser's single result artifact."""

    return download_artifact(job_id, "result-json")
