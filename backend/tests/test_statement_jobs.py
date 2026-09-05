"""The upload bridge must use selected files and fail closed around live runs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app import statement_jobs


ROOT = Path(__file__).resolve().parents[2]
STATEMENTS = ROOT / "samples" / "01-bank-statements-to-journal-entries" / "statements"
WORKBOOK = (
    ROOT
    / "samples"
    / "01-bank-statements-to-journal-entries"
    / "workbook"
    / "Bank statement to journal entries - working file (anonymised).xlsx"
)
PDFS = [
    STATEMENTS / "20260331_NI_ABF_I_SCSP_CALDER_EUR_0894.pdf",
    STATEMENTS / "20260331_NI_A_B__FUND_II_CALDER_EUR_8102.pdf",
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    job_service = statement_jobs.StatementJobService(tmp_path / "statement-jobs")
    monkeypatch.setattr(statement_jobs, "service", job_service)
    with TestClient(app) as test_client:
        yield test_client, job_service


def _selection(paths: list[Path]):
    selected = []
    for index, path in enumerate(paths):
        role = "BANK_STATEMENT" if path.suffix.lower() == ".pdf" else "REFERENCE_WORKBOOK"
        selected.append(
            {
                "path": path,
                "clientFileId": f"client-{index}",
                "relativePath": f"Selected/{path.name}",
                "role": role,
            }
        )
    return selected


def _post(client: TestClient, paths: list[Path], *, workflow="statement-validation", request_id="request-1"):
    selected = _selection(paths)
    manifest = [
        {
            "clientFileId": item["clientFileId"],
            "relativePath": item["relativePath"],
        }
        for item in selected
    ]
    return client.post(
        "/api/v1/statement-jobs",
        data={
            "fileIds": [item["clientFileId"] for item in selected],
            "manifest": json.dumps(manifest),
            "workflowId": workflow,
            "clientRequestId": request_id,
            "instruction": "Validate only these selected original files.",
        },
        files=[
            (
                "files",
                (
                    item["path"].name,
                    item["path"].read_bytes(),
                    (
                        "application/pdf"
                        if item["path"].suffix.lower() == ".pdf"
                        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    ),
                ),
            )
            for item in selected
        ],
    )


@pytest.mark.skipif(not all(path.exists() for path in PDFS), reason="statement samples absent")
def test_reversing_pdf_order_keeps_results_bound_to_file_ids(client):
    test_client, _ = client
    first = _post(test_client, PDFS, request_id="forward")
    reverse = _post(test_client, list(reversed(PDFS)), request_id="reverse")
    assert first.status_code == reverse.status_code == 202

    first_job = test_client.get(f"/api/v1/statement-jobs/{first.json()['jobId']}").json()
    reverse_job = test_client.get(f"/api/v1/statement-jobs/{reverse.json()['jobId']}").json()
    assert first_job["state"] == reverse_job["state"] == "COMPLETED_WITH_ISSUES"
    assert first_job["processedFiles"] == reverse_job["processedFiles"] == 2
    assert [event["state"] for event in first_job["timeline"]] == [
        "QUEUED",
        "PROCESSING",
        "COMPLETED_WITH_ISSUES",
    ]

    def by_filename(job):
        return {
            item["filename"]: {
                "account": item["account"],
                "currency": item["currency"],
                "rows": item["rowCount"],
                "checks": [(check["name"], check["status"]) for check in item["checks"]],
            }
            for item in job["files"]
        }

    assert by_filename(first_job) == by_filename(reverse_job)
    assert {item["account"] for item in first_job["files"]} == {"EUR_0894", "EUR_8102"}
    assert all(item["rowCount"] == 16 for item in first_job["files"])
    assert {item["closingBalance"] for item in first_job["files"]} == {
        "13217773.59",
        "20088.32",
    }
    assert all(item["accountNumber"] for item in first_job["files"])
    assert all(item["rows"][0]["bankReference"] for item in first_job["files"])
    assert all("bank_reference" not in item["rows"][0] for item in first_job["files"])
    assert all(item["sourceSha256"] for item in first_job["manifest"])
    assert all(item["clientFileId"] for item in first_job["manifest"])


@pytest.mark.skipif(not PDFS[0].exists(), reason="statement sample absent")
def test_journal_workflow_requires_an_uploaded_reference_workbook(client):
    test_client, _ = client
    response = _post(
        test_client,
        [PDFS[0]],
        workflow="journal-entries",
        request_id="missing-workbook",
    )
    assert response.status_code == 422
    assert "exactly one uploaded reference workbook" in response.json()["detail"]
    assert "sample" in response.json()["detail"]


def test_invalid_pdf_is_rejected_before_a_job_is_created(client, tmp_path):
    test_client, job_service = client
    invalid = tmp_path / "not-a-statement.pdf"
    invalid.write_bytes(b"not a pdf")
    response = _post(test_client, [invalid], request_id="invalid-pdf")
    assert response.status_code == 422
    assert "INVALID_PDF" in response.json()["detail"]
    assert not job_service.root.exists() or not list(job_service.root.glob("statement-*"))


@pytest.mark.skipif(not PDFS[0].exists(), reason="statement sample absent")
def test_duplicate_client_request_does_not_launch_a_second_job(client):
    test_client, job_service = client
    first = _post(test_client, [PDFS[0]], request_id="same-request")
    second = _post(test_client, [PDFS[0]], request_id="same-request")
    assert first.status_code == second.status_code == 202
    assert first.json()["jobId"] == second.json()["jobId"]
    assert len(list(job_service.root.glob("statement-*/job.json"))) == 1


@pytest.mark.skipif(
    not PDFS[0].exists() or not WORKBOOK.exists(), reason="statement samples absent"
)
def test_live_workflow_never_falls_back_without_credentials(client, monkeypatch):
    test_client, job_service = client
    monkeypatch.setattr(
        statement_jobs,
        "_settings",
        lambda: Settings(
            llm_base_url="",
            llm_api_key="",
            llm_model="",
            daytona_api_key="",
        ),
    )
    response = _post(
        test_client,
        [PDFS[0], WORKBOOK],
        workflow="journal-entries",
        request_id="no-live-configuration",
    )
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "LLM_BASE_URL and LLM_API_KEY" in detail
    assert "DAYTONA_API_KEY" in detail
    assert "no local, fixture, replay, or sample-data fallback" in detail
    assert not job_service.root.exists() or not list(job_service.root.glob("statement-*"))


@pytest.mark.skipif(not PDFS[0].exists(), reason="statement sample absent")
def test_sources_and_result_artifact_are_allowlisted_downloads(client):
    test_client, _ = client
    created = _post(test_client, [PDFS[0]], request_id="downloads")
    job = test_client.get(f"/api/v1/statement-jobs/{created.json()['jobId']}").json()
    source = test_client.get(job["manifest"][0]["sourceUrl"])
    artifact = test_client.get(job["artifacts"][0]["downloadUrl"])
    assert job["artifacts"][0]["kind"] == "RAW_JOB_RECORD"
    assert source.status_code == 200
    assert source.content == PDFS[0].read_bytes()
    assert source.headers["etag"].strip('"') == job["manifest"][0]["sourceSha256"]
    assert source.headers["content-disposition"].startswith("inline;")
    assert artifact.status_code == 200
    assert artifact.json()["jobId"] == job["jobId"]
    alias = test_client.get(f"/api/v1/statement-jobs/{job['jobId']}/artifact")
    assert alias.status_code == 200
    assert alias.json()["jobId"] == job["jobId"]
    assert test_client.get(
        f"/api/v1/statement-jobs/{job['jobId']}/artifacts/not-allowed"
    ).status_code == 404


def test_configuration_describes_real_workflow_requirements(client, monkeypatch):
    test_client, _ = client
    monkeypatch.setattr(
        statement_jobs,
        "_settings",
        lambda: Settings(
            llm_base_url="",
            llm_api_key="",
            llm_model="",
            daytona_api_key="",
        ),
    )
    response = test_client.get("/api/v1/statement-jobs/config")
    assert response.status_code == 200
    payload = response.json()
    assert payload["backendReachable"] is True
    assert payload["llmConfigured"] is False
    assert payload["daytonaConfigured"] is False
    workflows = {item["id"]: item for item in payload["workflows"]}
    assert workflows["statement-validation"]["requiresWorkbook"] is False
    assert workflows["journal-entries"]["requiresWorkbook"] is True
    assert workflows["journal-entries"]["requiresModel"] is True
