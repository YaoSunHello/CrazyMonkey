"""Local pack API. Source copies and credentials remain in the local backend."""
from __future__ import annotations

import os
import sqlite3
import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .local_config import load_local_config
from .pack_service import MAX_FILE_BYTES, MAX_PACK_BYTES, packs, safe_relative_path


router = APIRouter(prefix="/api/pack", tags=["local-pack"])


@router.get("/config")
def configuration():
    status = load_local_config(environ=dict(os.environ))
    return {**status, "configured": status["ready"]}


@router.get("/runs")
def list_runs():
    return {"runs": packs.list_runs()}


@router.post("/runs", status_code=202)
async def create_run(files: Annotated[list[UploadFile], File()],
                     relative_paths: Annotated[list[str], Form()],
                     instruction: Annotated[str, Form()] = "Review the full supplied financial pack. Identify source-supported mapping gaps, reconciliation questions and useful next checks."):
    if len(files) != len(relative_paths):
        raise HTTPException(422, "Relative paths must match the uploaded files")
    if not configuration().get("configured"):
        raise HTTPException(503, "Gemini is not configured in this local system; no fallback model will be used")
    try:
        paths = [safe_relative_path(value) for value in relative_paths]
        run_id, sources = packs.reserve(paths, instruction)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    total = 0
    try:
        for upload, relative in zip(files, paths, strict=True):
            path = sources / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            size = 0
            with path.open("xb") as handle:
                while content := await upload.read(1024 * 1024):
                    size += len(content)
                    total += len(content)
                    if size > MAX_FILE_BYTES or total > MAX_PACK_BYTES:
                        raise HTTPException(413, "Pack exceeds 25 MiB per file or 100 MiB total")
                    handle.write(content)
        packs.launch(run_id)
        return {"run_id": run_id}
    except Exception:
        packs.abort_upload(run_id)
        raise


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    try:
        return packs.get(run_id)
    except KeyError:
        raise HTTPException(404, "Pack run not found") from None


@router.get("/runs/{run_id}/evidence/{evidence_id}")
def get_evidence(run_id: str, evidence_id: str):
    get_run(run_id)
    database = packs.root / run_id / "evidence.sqlite3"
    if not database.exists():
        raise HTTPException(404, "Evidence import is not ready")
    try:
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
            row = connection.execute("SELECT document_id, locator, content_json FROM evidence WHERE evidence_id = ?", (evidence_id,)).fetchone()
            if row is None:
                raise HTTPException(404, "Evidence reference not found")
            source = connection.execute("SELECT relative_path FROM documents WHERE document_id = ?", (row[0],)).fetchone()
    except sqlite3.OperationalError:
        raise HTTPException(503, "Evidence import is still in progress") from None
    return {"evidence_id": evidence_id, "relative_path": source[0], "locator": row[1], "content": json.loads(row[2])}
