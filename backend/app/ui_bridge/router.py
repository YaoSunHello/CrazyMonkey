"""FastAPI routes for the namespaced deterministic UI bridge."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from app.ui_bridge.csv_export import CSV_CONTENT_TYPE, build_transactions_csv
from app.ui_bridge.schemas import ReviewPatch
from app.ui_bridge.service import (
    EXECUTION_LABEL,
    capabilities,
    create_job,
    job_status,
    patch_review,
    replay_detail,
    replay_summaries,
)
from app.ui_bridge.store import STORE

router = APIRouter(prefix="/api/ui/v1", tags=["ui-bridge"])


def _job_or_404(job_id: str):
    job = STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"code": "JOB_NOT_FOUND", "message": "no such job"})
    return job


@router.get("/capabilities")
def get_capabilities() -> dict:
    return capabilities()


@router.post("/jobs", status_code=202)
def post_job(
    manifest: str = Form(...),
    files: list[UploadFile] = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    job, reused = create_job(manifest, files, idempotency_key)
    return {
        "job_id": job.job_id,
        "profile_id": job.profile_id,
        "case_name": job.case_name,
        "execution_label": EXECUTION_LABEL,
        "processing_state": job.processing_state,
        "idempotency_reused": reused,
        "links": {
            "status": f"/api/ui/v1/jobs/{job.job_id}",
            "result": f"/api/ui/v1/jobs/{job.job_id}/result",
        },
    }


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    return job_status(_job_or_404(job_id))


@router.get("/jobs/{job_id}/result")
def get_result(job_id: str) -> dict:
    job = _job_or_404(job_id)
    with job.lock:
        if job.result is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "RESULT_NOT_READY",
                    "message": "job has not reached a terminal processing state",
                    "processing_state": job.processing_state,
                },
            )
        return job.result


@router.get("/jobs/{job_id}/transactions.csv")
def get_transactions_csv(job_id: str):
    job = _job_or_404(job_id)
    with job.lock:
        if job.result is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "RESULT_NOT_READY", "message": "transaction rows are available only after processing completes"},
            )
        export = build_transactions_csv(job.result)
        if not export.row_count:
            raise HTTPException(
                status_code=409,
                detail={"code": "NO_TRANSACTION_ROWS", "message": "no source document produced transaction rows"},
            )
        descriptor = export.descriptor()
        return Response(
            content=export.content,
            media_type=CSV_CONTENT_TYPE,
            headers={
                "Content-Disposition": f'attachment; filename="{export.filename}"',
                "ETag": f'"{descriptor["sha256"]}"',
            },
        )


@router.get("/jobs/{job_id}/sources/{source_id}")
def get_source(job_id: str, source_id: str):
    job = _job_or_404(job_id)
    item = next((candidate for candidate in job.files if candidate.source_id == source_id), None)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "SOURCE_NOT_FOUND", "message": "no such uploaded source"},
        )
    return FileResponse(
        item.path,
        media_type=item.content_type,
        filename=item.filename,
        content_disposition_type="inline",
    )


@router.get("/jobs/{job_id}/artifacts/{artifact_id}")
def get_artifact(job_id: str, artifact_id: str):
    job = _job_or_404(job_id)
    with job.lock:
        if job.artifact_id != artifact_id or job.artifact_path is None or not job.artifact_path.is_file():
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "ARTIFACT_NOT_FOUND",
                    "message": "no such generated artifact",
                },
            )
        return FileResponse(
            job.artifact_path,
            media_type="application/json",
            filename=job.artifact_path.name,
            content_disposition_type="attachment",
        )


@router.patch("/jobs/{job_id}/findings/{finding_id}/review")
def review_finding(job_id: str, finding_id: str, update: ReviewPatch) -> dict:
    return patch_review(_job_or_404(job_id), finding_id, update.review_status)


@router.get("/replays")
def get_replays() -> dict:
    return {
        "replays": replay_summaries(),
        "note": (
            "These are committed RECORDED_REPLAY results. They contain no event "
            "trace, so no timing compression is performed; reading them makes zero "
            "model calls."
        ),
    }


@router.get("/replays/{replay_id}")
def get_replay(replay_id: str) -> dict:
    replay = replay_detail(replay_id)
    if replay is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "REPLAY_NOT_FOUND", "message": "no such committed replay"},
        )
    return replay
