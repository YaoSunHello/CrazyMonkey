"""The two-route structured pipeline API for trusted normalized-document callers."""

from fastapi import APIRouter, HTTPException
from pydantic import Field

from app.atlas.models import NormalizedDocument
from .models import Contract, Mode, PipelineResult
from .service import reviews


router = APIRouter(prefix="/api/cases", tags=["verified-runtime"])


class RunRequest(Contract):
    user_instruction: str = Field(min_length=1, max_length=10000)
    normalized_documents: list[NormalizedDocument] = Field(max_length=40)
    mode: Mode = "DEMO_FIXTURE"


@router.post("/{case_id}/run", response_model=PipelineResult)
def run(case_id: str, request: RunRequest):
    configured_mode = reviews.analyst.mode if reviews.analyst is not None else "DEMO_FIXTURE"
    if request.mode != configured_mode:
        raise HTTPException(503, "The requested analyst mode is not configured; no fallback model call was made")
    try:
        return reviews.create(case_id, request.user_instruction, request.normalized_documents).result
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/{case_id}/result", response_model=PipelineResult)
def result(case_id: str):
    try:
        return reviews.get(case_id).result
    except KeyError as exc:
        raise HTTPException(404, "Case result not found in this demo server process") from exc
