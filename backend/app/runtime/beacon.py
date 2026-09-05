"""Small BEACON facade over the runtime and ATLAS's canonical source contracts.

No parsing, financial calculation, or email sending is implemented here. Uploaded
bytes go through ATLAS; computational results come from the runtime service;
RELAY's existing routes own immutable exports and confirmed email delivery.
"""

from __future__ import annotations

import json
import re
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.atlas import IngestionError, detect_document_role, normalize_file
from app.atlas.fixtures import generate_synthetic_pack
from app.atlas.ingestion import MAX_FILE_BYTES
from app.atlas.models import DocumentRole, NormalizedDocument, ReviewSnapshot


router = APIRouter(prefix="/api/v1", tags=["beacon-review"])
DEFAULT_INSTRUCTION = "Review the supplied management fees against their source-linked governing terms."
MAX_DOCUMENTS = 40
MAX_BATCH_BYTES = 100 * 1024 * 1024


class UploadManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=200)
    filename: str = Field(min_length=1, max_length=255)
    role: DocumentRole
    recognition: str
    clientFileId: str | None = None
    fileCount: int | None = None


class HumanReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    state: str = Field(pattern=r"^(UNREVIEWED|REVIEWED|NEEDS_FOLLOW_UP|TERM_CONFIRMED)$")
    reviewerName: str = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=4000)


def _store():
    # Import lazily to keep this presentation adapter independent of service setup.
    from .service import reviews

    return reviews


def _get(review_id: str):
    try:
        return _store().get(review_id)
    except KeyError as exc:
        raise HTTPException(404, "Review not found") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _create(case_id: str, instruction: str, documents: list[NormalizedDocument], *, synthetic: bool = False):
    try:
        return _store().create(case_id, instruction, documents, synthetic=synthetic)
    except (IngestionError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


def _filename(upload: UploadFile) -> str:
    name = upload.filename or ""
    if (
        not name
        or len(name) > 255
        or Path(name).name != name
        or any(character in name for character in ("/", "\\", "\x00"))
        or name in {".", ".."}
    ):
        raise HTTPException(422, "Each upload needs a plain filename without directory components")
    if Path(name).suffix.lower() not in {".pdf", ".xlsx", ".csv"}:
        raise HTTPException(422, "ATLAS supports PDF, XLSX, and CSV uploads")
    return name


def _check_count(files: list[UploadFile]) -> None:
    if not 1 <= len(files) <= MAX_DOCUMENTS:
        raise HTTPException(422, f"Select between 1 and {MAX_DOCUMENTS} files")


async def _normalize_uploads(files: list[UploadFile], roles: list[DocumentRole]) -> list[NormalizedDocument]:
    _check_count(files)
    if len(roles) != len(files):
        raise HTTPException(422, "Upload roles do not match the selected files")
    normalized: list[NormalizedDocument] = []
    total = 0
    with tempfile.TemporaryDirectory(prefix="crazymonkey-upload-") as directory:
        for index, (upload, role) in enumerate(zip(files, roles, strict=True)):
            name = _filename(upload)
            content = await upload.read(MAX_FILE_BYTES + 1)
            total += len(content)
            if len(content) > MAX_FILE_BYTES or total > MAX_BATCH_BYTES:
                raise HTTPException(413, "Upload exceeds the 25 MiB per-file or 100 MiB batch limit")
            # Separate folders retain the real filename even when names repeat.
            path = Path(directory) / str(index) / name
            path.parent.mkdir()
            path.write_bytes(content)
            try:
                normalized.append(await run_in_threadpool(normalize_file, path, role))
            except IngestionError as exc:
                raise HTTPException(422, f"{exc.code}: {exc.message}") from exc
    if len({item.document.document_id for item in normalized}) != len(normalized):
        raise HTTPException(422, "The same source document was uploaded more than once")
    return normalized


@router.post("/documents/detect")
async def detect_documents(
    files: Annotated[list[UploadFile], File()],
    client_file_ids: Annotated[list[str], Form()],
) -> list[dict[str, Any]]:
    _check_count(files)
    if len(files) != len(client_file_ids) or len(set(client_file_ids)) != len(files):
        raise HTTPException(422, "Client file identifiers must uniquely match the selected files")
    detected = []
    for upload, client_id in zip(files, client_file_ids, strict=True):
        if not client_id or len(client_id) > 128:
            raise HTTPException(422, "Invalid client file identifier")
        name = _filename(upload)
        if upload.size is not None and upload.size > MAX_FILE_BYTES:
            raise HTTPException(413, "Upload exceeds the 25 MiB per-file limit")
        guess = detect_document_role(name)
        detected.append({
            "id": client_id,
            "clientFileId": client_id,
            "filename": name,
            "role": guess.role.value,
            "recognition": "RECOGNISED" if guess.confident else "NEEDS_CONFIRMATION",
        })
    return detected


@router.post("/reviews", status_code=201)
async def start_review(
    files: Annotated[list[UploadFile], File()],
    manifest: Annotated[str, Form()],
) -> dict[str, str]:
    _check_count(files)
    try:
        raw = json.loads(manifest)
        if not isinstance(raw, list) or len(raw) != len(files):
            raise ValueError("manifest length")
        items = [UploadManifest.model_validate(item) for item in raw]
    except (ValueError, TypeError, ValidationError) as exc:
        raise HTTPException(422, "Upload manifest does not match the selected files") from exc
    for upload, item in zip(files, items, strict=True):
        if _filename(upload) != item.filename or item.recognition != "RECOGNISED":
            raise HTTPException(422, "Confirm every document role and preserve the upload filename")
    documents = await _normalize_uploads(files, [item.role for item in items])
    record = await run_in_threadpool(_create, f"upload-{uuid4().hex}", DEFAULT_INSTRUCTION, documents)
    return {"reviewId": record.snapshot.run_id}


def _synthetic_review():
    with tempfile.TemporaryDirectory(prefix="crazymonkey-demo-") as directory:
        generate_synthetic_pack(Path(directory))
        documents = [
            normalize_file(path)
            for path in sorted(Path(directory).iterdir())
            if path.suffix.lower() in {".pdf", ".xlsx", ".csv"}
        ]
    return _create(f"demo-{uuid4().hex}", DEFAULT_INSTRUCTION, documents, synthetic=True)


@router.post("/demo/reviews", status_code=201)
def start_synthetic_review() -> dict[str, str]:
    return {"reviewId": _synthetic_review().snapshot.run_id}


@router.get("/reviews/{review_id}")
def get_review(review_id: str) -> dict[str, Any]:
    record = _get(review_id)
    return to_beacon(record.snapshot, analyst_mode=record.result.mode)


@router.get("/reviews/{review_id}/progress")
def get_progress(review_id: str) -> dict[str, Any]:
    record = _get(review_id)
    stages = [
        ("READING_FILES", "Read source files with ATLAS"),
        ("EXTRACTING_TERMS", "Propose evidence-linked terms"),
        ("COMPARING_DOCUMENTS", "Compare governing documents"),
        ("CHALLENGING_ASSUMPTIONS", "Challenge proposed findings"),
        ("CHECKING_CALCULATIONS", "Verify using exact Decimal arithmetic"),
        ("PREPARING_REVIEW", "Prepare the human-review snapshot"),
    ]
    return {
        "reviewId": record.snapshot.run_id,
        "state": "COMPLETE",
        "stages": [{"code": code, "label": label, "state": "COMPLETE"} for code, label in stages],
        "messages": [
            {"id": f"trace-{index}", "text": f"{event.stage}: {event.explanation}"}
            for index, event in enumerate(record.result.trace)
        ],
    }


@router.post("/reviews/{review_id}/retry", status_code=201)
def retry_review(review_id: str) -> dict[str, str]:
    previous = _get(review_id)
    record = _create(
        previous.result.case_id,
        getattr(previous, "user_instruction", DEFAULT_INSTRUCTION),
        previous.documents,
        synthetic=previous.snapshot.mode == "SYNTHETIC_DEMO",
    )
    return {"reviewId": record.snapshot.run_id}


@router.patch("/reviews/{review_id}/findings/{finding_id}/review")
def human_review(review_id: str, finding_id: str, request: HumanReviewRequest) -> dict[str, Any]:
    _get(review_id)
    try:
        record = _store().review(
            review_id, finding_id, request.state, request.reviewerName,
            request.note or f"Human review state changed to {request.state}.",
        )
    except KeyError as exc:
        raise HTTPException(404, "Review or finding not found") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    result = to_beacon(record.snapshot, analyst_mode=record.result.mode)
    return next(item for item in result["findings"] if item["id"] == finding_id)


@router.post("/reviews/{review_id}/findings/{finding_id}/corrections")
def unsupported_term_correction(review_id: str, finding_id: str) -> None:
    record = _get(review_id)
    if finding_id not in {item.finding_id for item in record.snapshot.findings}:
        raise HTTPException(404, "Finding not found")
    raise HTTPException(
        501,
        "Unsourced term overrides are not supported. Upload source evidence and rerun; "
        "human review notes never replace the deterministic financial result.",
    )


@router.post("/reviews/{review_id}/documents", status_code=201)
async def add_supporting_document(
    review_id: str,
    file: Annotated[UploadFile, File()],
    role: Annotated[DocumentRole, Form()],
) -> dict[str, str]:
    previous = _get(review_id)
    documents = await _normalize_uploads([file], [role])
    combined = [*previous.documents, *documents]
    if len({item.document.document_id for item in combined}) != len(combined):
        raise HTTPException(422, "This source document is already present")
    if len(combined) > MAX_DOCUMENTS:
        raise HTTPException(422, f"A review supports at most {MAX_DOCUMENTS} source files")
    record = await run_in_threadpool(
        _create, previous.result.case_id,
        getattr(previous, "user_instruction", DEFAULT_INSTRUCTION), combined,
        synthetic=previous.snapshot.mode == "SYNTHETIC_DEMO",
    )
    return {"reviewId": record.snapshot.run_id}


def to_beacon(snapshot: ReviewSnapshot, *, analyst_mode: str) -> dict[str, Any]:
    """Presentation-only mapper: never infer or recompute a financial status."""
    snapshot = ReviewSnapshot.model_validate(snapshot.model_dump(mode="json"))
    documents = {item.document_id: item for item in snapshot.source_documents}
    calculations = {item.calculation_id: item for item in snapshot.calculations}
    verifiers = {item.verifier_result_id: item for item in snapshot.verifier_results}
    concerns = {item.concern_id: item for item in snapshot.challenger_concerns}
    kind_names = {"PDF_TEXT": "PDF", "WORKBOOK_CELL": "SPREADSHEET", "CSV_CELL": "CSV"}
    severity_rank = {"NONE": 0, "INFO": 1, "WARNING": 2, "CRITICAL": 3}

    def decimal_wire_value(value: Decimal) -> int | str:
        """Return JSON that cannot lose an exact decimal in a JavaScript number."""

        if value == value.to_integral_value() and abs(value) <= Decimal("9007199254740991"):
            return int(value)
        return format(value, "f")

    def money(amount, currency):
        return (
            {"amount": decimal_wire_value(amount), "currency": currency}
            if amount is not None
            else None
        )

    findings = []
    for finding in snapshot.findings:
        verifier = verifiers[finding.verifier_result_id]
        calculation = calculations.get(finding.calculation_id)
        item: dict[str, Any] = {
            "id": finding.finding_id,
            "investorId": finding.investor_id,
            "checkName": "Management fee",
            "status": finding.status,
            "humanReviewState": finding.human_review_state,
            "severity": max(
                (concerns[concern_id].severity for concern_id in finding.challenger_concern_ids),
                key=severity_rank.__getitem__, default="NONE",
            ),
            "confidence": {
                "label": "NOT_SCORED",
                "basis": "The canonical ATLAS snapshot does not provide a confidence score; rely on deterministic checks and source evidence.",
            },
            "explanation": finding.explanation,
            "evidence": [
                {
                    "id": ref.evidence_id,
                    "documentId": ref.document_id,
                    "filename": documents[ref.document_id].filename,
                    "documentRole": documents[ref.document_id].role,
                    "sourceKind": kind_names[ref.kind],
                    "locator": ref.locator,
                    **({"quote": ref.quote} if ref.quote is not None else {}),
                    **({"value": ref.original_value} if ref.original_value is not None else {}),
                }
                for ref in finding.source_refs
            ],
            "checksPerformed": [
                {
                    "id": check.code,
                    "label": f"{check.code}: {check.explanation}",
                    "state": "COMPLETE" if check.passed else (
                        "UNRESOLVED" if finding.status == "CANNOT_VERIFY" else "CONCERN"
                    ),
                }
                for check in verifier.checks
            ],
            "verifierStatement": verifier.explanation,
            "notes": [
                {
                    "id": event.event_id,
                    "author": event.reviewer_label,
                    "body": event.note,
                    "createdAt": event.timestamp.isoformat(),
                }
                for event in snapshot.audit_trail if event.finding_id == finding.finding_id
            ],
        }
        investor_names = {
            ref.original_value for ref in finding.source_refs
            if ref.kind == "CSV_CELL" and ref.csv_column == "investor_name" and ref.original_value
        }
        if len(investor_names) == 1:
            item["investorName"] = next(iter(investor_names))
        if finding.status != "MATCH":
            item["requiredAction"] = {"label": finding.actionable_next_step}
            if any(re.fullmatch(
                r"(?:The )?expected side[- ]letter(?: for [A-Za-z0-9._-]+)? (?:was |is )?(?:not supplied|not provided|missing)[.!?]?",
                question.strip(), flags=re.IGNORECASE,
            ) for question in finding.unresolved_questions):
                item["requiredAction"]["documentRole"] = "SIDE_LETTER"
        for field, amount in (
            ("administratorValue", finding.reported_value),
            ("expectedValue", finding.expected_value),
            ("difference", finding.difference),
        ):
            if amount is not None:
                item[field] = money(amount, finding.currency)
        if calculation is not None:
            item["calculation"] = {
                "inputs": [
                    {"label": "Fee base", "value": str(calculation.fee_base)},
                    {"label": "Annual rate (fraction)", "value": str(calculation.annual_rate)},
                    {"label": "Period factor", "value": str(calculation.period_factor)},
                ],
                "expression": calculation.formula_description,
                "result": money(calculation.expected_amount, calculation.currency),
            }
        financial_version = {
            **(
                {"applicableRate": decimal_wire_value(calculation.annual_rate * Decimal("100"))}
                if calculation is not None
                else {}
            ),
            **(
                {"expectedValue": money(finding.expected_value, finding.currency)}
                if finding.expected_value is not None
                else {}
            ),
        }
        versions = [{
            "version": 1,
            "createdAt": snapshot.created_at.isoformat(),
            "reason": "Initial source-linked deterministic review",
            **financial_version,
        }]
        for event in snapshot.audit_trail:
            if event.finding_id != finding.finding_id:
                continue
            versions.append({
                "version": event.run_version,
                "createdAt": event.timestamp.isoformat(),
                "reason": f"Human review: {str(event.action).replace('_', ' ').title()}",
                **financial_version,
            })
        if versions[-1]["version"] != snapshot.version:
            versions.append({
                "version": snapshot.version,
                "createdAt": snapshot.frozen_at.isoformat(),
                "reason": "Current immutable review snapshot",
                **financial_version,
            })
        item["versions"] = versions
        if finding.challenger_concern_ids:
            item["challengerConcern"] = " ".join(
                concerns[concern_id].suspected_problem
                for concern_id in finding.challenger_concern_ids
            )
        findings.append(item)

    return {
        "id": snapshot.run_id,
        "version": snapshot.version,
        "mode": snapshot.mode,
        "source": "ATLAS",
        "sourceNotice": (
            "Original files were normalized by ATLAS and processed by the runtime. "
            f"Analyst mode: {analyst_mode}. "
            + ("DEMO_FIXTURE is a bounded deterministic clause interpreter, not a model call. "
               if analyst_mode == "DEMO_FIXTURE" else "")
            + "Financial statuses are separate from human review; exports freeze this review version."
        ),
        "fundName": snapshot.fund_name,
        "periodLabel": snapshot.reporting_period,
        "createdAt": snapshot.created_at.isoformat(),
        "documents": [
            {
                "id": document.document_id,
                "filename": document.filename,
                "role": document.role,
                "recognition": "RECOGNISED" if document.extraction_status == "COMPLETE" else "NEEDS_CONFIRMATION",
            }
            for document in snapshot.source_documents
        ],
        "findings": findings,
        "outputCapabilities": {
            "pdf": True, "excel": True, "json": True, "emailPrepare": True,
            # BEACON's legacy form does not supply RELAY's safe-send contract.
            "emailSend": False,
            "termCorrection": False,
        },
    }
