"""Contract and security tests for the local deterministic UI bridge."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.profiles import available
from app.ui_bridge.schemas import MAX_BATCH_BYTES, MAX_FILE_BYTES, MAX_FILES
from app.ui_bridge.store import STORE

ROOT = Path(__file__).resolve().parents[2]
STATEMENTS = ROOT / "samples" / "01-bank-statements-to-journal-entries" / "statements"
WORKBOOK = (
    ROOT
    / "samples"
    / "01-bank-statements-to-journal-entries"
    / "workbook"
    / "Bank statement to journal entries - working file (anonymised).xlsx"
)
UNRESOLVED_STATEMENT = STATEMENTS / "20260331_NI_A_B__FUND_II_CALDER_EUR_8102.pdf"


@pytest.fixture(scope="module")
def client():
    STORE.clear()
    with TestClient(app) as value:
        yield value
    STORE.clear()


def entry(
    filename: str,
    blob: bytes,
    *,
    client_file_id: str = "client-1",
    relative_path: str | None = None,
    purpose: str = "SOURCE",
    content_type: str | None = None,
    size_bytes: int | None = None,
    selection_status: str = "SELECTED",
) -> dict:
    return {
        "client_file_id": client_file_id,
        "relative_path": relative_path or filename,
        "filename": filename,
        "size_bytes": len(blob) if size_bytes is None else size_bytes,
        "content_type": content_type
        or (
            "application/pdf"
            if purpose == "SOURCE"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        "selection_status": selection_status,
        "purpose": purpose,
    }


def submit(
    client: TestClient,
    entries: list[dict],
    blobs: list[bytes],
    *,
    key: str | None = None,
    case_name: str = "Bridge contract test",
    profile_id: str = "journal-entries",
):
    headers = {} if key is None else {"Idempotency-Key": key}
    parts = [
        ("files", (item["filename"], blob, item["content_type"]))
        for item, blob in zip(entries, blobs)
    ]
    return client.post(
        "/api/ui/v1/jobs",
        data={
            "manifest": json.dumps(
                {
                    "profile_id": profile_id,
                    "case_name": case_name,
                    "files": entries,
                }
            )
        },
        files=parts,
        headers=headers,
    )


def wait_for_result(client: TestClient, job_id: str, timeout: float = 15.0) -> tuple[dict, dict]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status_response = client.get(f"/api/ui/v1/jobs/{job_id}")
        assert status_response.status_code == 200
        status = status_response.json()
        if status["processing_state"] in {"SUCCEEDED", "PARTIAL", "FAILED"}:
            result_response = client.get(f"/api/ui/v1/jobs/{job_id}/result")
            assert result_response.status_code == 200
            return status, result_response.json()
        time.sleep(0.025)
    pytest.fail(f"job {job_id} did not finish")


@pytest.fixture(scope="module")
def completed_job(client: TestClient):
    blob = UNRESOLVED_STATEMENT.read_bytes()
    item = entry(
        UNRESOLVED_STATEMENT.name,
        blob,
        relative_path=f"incoming/2026/{UNRESOLVED_STATEMENT.name}",
    )
    response = submit(client, [item], [blob], key=f"completed-{uuid.uuid4().hex}")
    assert response.status_code == 202, response.text
    accepted = response.json()
    status, result = wait_for_result(client, accepted["job_id"])
    return {"accepted": accepted, "status": status, "result": result, "bytes": blob}


def test_capabilities_are_explicit_and_profile_specific(client: TestClient):
    response = client.get("/api/ui/v1/capabilities")
    assert response.status_code == 200
    body = response.json()
    assert body["execution"] == {
        "label": "LOCAL_DETERMINISTIC",
        "model_calls": 0,
        "browser_commands_executed": False,
    }
    assert body["limits"] == {
        "max_files": 40,
        "max_file_bytes": 25 * 1024 * 1024,
        "max_batch_bytes": 100 * 1024 * 1024,
        "max_path_depth": 12,
        "max_events_per_job": 100,
    }
    assert {profile["profile_id"] for profile in body["profiles"]} == {
        "journal-entries",
        "pipeline-validation",
    }
    assert "mandate-fit" in available()
    for profile in body["profiles"]:
        assert profile["source"]["formats"] == [
            {"extension": ".pdf", "content_types": ["application/pdf"]}
        ]
        assert profile["reference"]["formats"] == [
            {
                "extension": ".xlsx",
                "content_types": [
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ],
            }
        ]
        assert profile["reference"]["tables"]
    assert body["artifacts"]["json"]["available"] is True
    assert body["artifacts"]["report"]["available"] is False
    assert body["artifacts"]["report"]["reason"]
    assert body["artifacts"]["workbook"]["available"] is False
    assert body["artifacts"]["workbook"]["reason"]


def test_idempotency_key_is_required(client: TestClient):
    blob = UNRESOLVED_STATEMENT.read_bytes()
    response = submit(client, [entry(UNRESOLVED_STATEMENT.name, blob)], [blob])
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_profile_id_cannot_escape_the_advertised_profile_registry(client: TestClient):
    blob = b"%PDF-1.4\n"
    response = submit(
        client,
        [entry("safe.pdf", blob)],
        [blob],
        key=f"profile-path-{uuid.uuid4().hex}",
        profile_id="../../examples/batch-20260905-191130-journal-entries",
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "UNKNOWN_PROFILE"


def test_more_than_one_hundred_manifest_entries_are_rejected_never_truncated(client: TestClient):
    blob = b"%PDF-1.4\n"
    entries = [
        entry(
            f"statement-{index}.pdf",
            blob,
            client_file_id=f"client-{index}",
        )
        for index in range(101)
    ]
    response = submit(client, entries, [blob] * len(entries), key=f"count-{uuid.uuid4().hex}")
    assert response.status_code == 413
    assert response.json()["detail"] == {
        "code": "TOO_MANY_FILES",
        "message": f"at most {MAX_FILES} files are accepted",
    }


def test_same_filename_in_different_nested_directories_is_accepted(client: TestClient):
    blob = UNRESOLVED_STATEMENT.read_bytes()
    name = UNRESOLVED_STATEMENT.name
    entries = [
        entry(name, blob, client_file_id="left", relative_path=f"desk/left/{name}"),
        entry(name, blob, client_file_id="right", relative_path=f"desk/right/{name}"),
    ]
    response = submit(client, entries, [blob, blob], key=f"same-name-{uuid.uuid4().hex}")
    assert response.status_code == 202, response.text
    status, result = wait_for_result(client, response.json()["job_id"])
    assert status["processing_state"] == "SUCCEEDED"
    assert result["summary"]["documents_succeeded"] == 2
    assert len({document["source_id"] for document in result["documents"]}) == 2


@pytest.mark.parametrize(
    ("relative_path", "filename", "expected_code"),
    [
        ("../safe.pdf", "safe.pdf", "PATH_TRAVERSAL"),
        ("/safe.pdf", "safe.pdf", "ABSOLUTE_PATH"),
        ("C:/safe.pdf", "safe.pdf", "ABSOLUTE_PATH"),
        ("folder\\safe.pdf", "safe.pdf", "INVALID_PATH"),
        (".git/safe.pdf", "safe.pdf", "FORBIDDEN_PATH"),
        (".env.local/safe.pdf", "safe.pdf", "FORBIDDEN_PATH"),
        ("credentials/safe.pdf", "safe.pdf", "FORBIDDEN_PATH"),
        ("node_modules/safe.pdf", "safe.pdf", "FORBIDDEN_PATH"),
        (".env", ".env", "FORBIDDEN_FILE"),
        ("credentials.json", "credentials.json", "FORBIDDEN_FILE"),
        ("folder/\x00safe.pdf", "\x00safe.pdf", "INVALID_PATH"),
        ("/".join(["deep"] * 13 + ["safe.pdf"]), "safe.pdf", "PATH_TOO_DEEP"),
    ],
)
def test_traversal_absolute_forbidden_nul_and_deep_paths_are_rejected(
    client: TestClient, relative_path: str, filename: str, expected_code: str
):
    blob = b"%PDF-1.4\n"
    response = submit(
        client,
        [entry(filename, blob, relative_path=relative_path)],
        [blob],
        key=f"bad-path-{uuid.uuid4().hex}",
    )
    assert response.status_code in {415, 422}
    assert response.json()["detail"]["code"] == expected_code


def test_duplicate_client_ids_and_paths_are_rejected(client: TestClient):
    blob = b"%PDF-1.4\n"
    first = entry("one.pdf", blob, client_file_id="duplicate")
    second = entry("two.pdf", blob, client_file_id="duplicate")
    response = submit(client, [first, second], [blob, blob], key=f"dup-id-{uuid.uuid4().hex}")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "DUPLICATE_CLIENT_FILE_ID"

    second = entry("one.pdf", blob, client_file_id="different")
    response = submit(client, [first, second], [blob, blob], key=f"dup-path-{uuid.uuid4().hex}")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "DUPLICATE_RELATIVE_PATH"


def test_unselected_files_are_rejected_not_silently_ignored(client: TestClient):
    blob = b"%PDF-1.4\n"
    response = submit(
        client,
        [entry("safe.pdf", blob, selection_status="UNSELECTED")],
        [blob],
        key=f"unselected-{uuid.uuid4().hex}",
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_MANIFEST"


def test_unknown_purpose_is_rejected_not_treated_as_a_source(client: TestClient):
    blob = b"%PDF-1.4\n"
    item = entry("safe.pdf", blob)
    item["purpose"] = "COMMAND"
    response = submit(
        client,
        [item],
        [blob],
        key=f"purpose-{uuid.uuid4().hex}",
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_MANIFEST"


@pytest.mark.parametrize(
    ("item", "blob", "status", "code"),
    [
        (entry("empty.pdf", b"", size_bytes=0), b"", 422, "EMPTY_FILE"),
        (
            entry("too-large.pdf", b"x", size_bytes=MAX_FILE_BYTES + 1),
            b"x",
            413,
            "FILE_TOO_LARGE",
        ),
        (entry("wrong-size.pdf", b"%PDF-", size_bytes=10), b"%PDF-", 422, "FILE_SIZE_MISMATCH"),
        (
            entry("unsupported.txt", b"hello", content_type="text/plain"),
            b"hello",
            415,
            "UNSUPPORTED_FORMAT",
        ),
        (entry("fake.pdf", b"not a pdf"), b"not a pdf", 415, "INVALID_FILE_SIGNATURE"),
    ],
)
def test_empty_unsupported_and_invalid_file_sizes_are_rejected(
    client: TestClient, item: dict, blob: bytes, status: int, code: str
):
    response = submit(client, [item], [blob], key=f"bad-file-{uuid.uuid4().hex}")
    assert response.status_code == status, response.text
    assert response.json()["detail"]["code"] == code


def test_declared_batch_over_one_hundred_mib_is_rejected_without_reading_or_truncating(client: TestClient):
    blob = b"%PDF-1.4\n"
    entries = [
        entry(
            f"large-{index}.pdf",
            blob,
            client_file_id=f"large-{index}",
            size_bytes=MAX_FILE_BYTES if index < 4 else 1,
        )
        for index in range(5)
    ]
    assert sum(item["size_bytes"] for item in entries) == MAX_BATCH_BYTES + 1
    response = submit(client, entries, [blob] * 5, key=f"batch-size-{uuid.uuid4().hex}")
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "BATCH_TOO_LARGE"


def test_duplicate_idempotency_reuses_the_job_and_conflicting_payload_is_409(
    client: TestClient,
):
    blob = UNRESOLVED_STATEMENT.read_bytes()
    item = entry(UNRESOLVED_STATEMENT.name, blob)
    key = f"idem-{uuid.uuid4().hex}"
    first = submit(client, [item], [blob], key=key)
    assert first.status_code == 202, first.text
    second = submit(client, [item], [blob], key=key)
    assert second.status_code == 202, second.text
    assert second.json()["job_id"] == first.json()["job_id"]
    assert second.json()["idempotency_reused"] is True

    conflict = submit(client, [item], [blob], key=key, case_name="A different request")
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"
    status, _ = wait_for_result(client, first.json()["job_id"])
    assert [event["meta"]["event_type"] for event in status["events"]].count("JOB_STARTED") == 1
    assert all(
        set(event) == {"kind", "label", "detail", "status", "body", "meta", "at"}
        for event in status["events"]
    )
    assert all(isinstance(event["at"], float) for event in status["events"])


def test_status_has_bounded_events_and_separates_processing_from_outcome(
    completed_job: dict,
):
    status = completed_job["status"]
    assert status["processing_state"] == "SUCCEEDED"
    assert status["documents"][0]["processing_state"] == "SUCCEEDED"
    assert status["documents"][0]["computational_outcome"] == "UNRESOLVED"
    assert status["event_trace"] == {
        "bounded": True,
        "max_events": 100,
        "truncated": False,
    }
    assert len(status["events"]) <= 100
    assert "percent" not in json.dumps(status).lower()


def test_exact_uploaded_bytes_are_served_inline(client: TestClient, completed_job: dict):
    accepted = completed_job["accepted"]
    source_id = completed_job["result"]["documents"][0]["source_id"]
    response = client.get(f"/api/ui/v1/jobs/{accepted['job_id']}/sources/{source_id}")
    assert response.status_code == 200
    assert response.content == completed_job["bytes"]
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["content-disposition"].startswith("inline")


def test_unresolved_checks_and_real_citation_source_identity_are_preserved(completed_job: dict):
    result = completed_job["result"]
    document = result["documents"][0]
    source_id = document["source_id"]
    assert "UNRESOLVED" in {check["status"] for check in document["checks"]}
    assert "UNRESOLVED" in {check["status"] for check in result["checks"]}
    assert result["summary"]["checks"]["UNRESOLVED"] >= 1

    row_citation = document["rows"][0]["citation"]
    assert row_citation["source_id"] == source_id
    assert row_citation["filename"] == document["filename"]
    assert row_citation["page"] >= 1
    assert set(row_citation["bbox"]) == {"x0", "top", "x1", "bottom"}

    link = document["transaction_links"][0]
    assert set(link) >= {
        "balance",
        "signed_movement",
        "derived_balance",
        "comparison_balance",
        "difference",
        "status",
    }
    assert link["status"] in {"PASS", "FAIL"}
    assert link["citations"]["balance"]["source_id"] == source_id
    assert link["citations"]["comparison_balance"]["source_id"] == source_id
    # Decimal operands cross JSON as exact strings, never binary floats.
    assert all(
        link[key] is None or isinstance(link[key], str)
        for key in (
            "balance",
            "signed_movement",
            "derived_balance",
            "comparison_balance",
            "difference",
        )
    )


def test_json_artifact_download_contains_the_real_result(client: TestClient, completed_job: dict):
    result = completed_job["result"]
    artifact = result["artifacts"][0]
    response = client.get(artifact["url"])
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    payload = response.json()
    assert payload["artifact_kind"] == "RESULT_JSON"
    assert payload["result"]["job_id"] == result["job_id"]
    assert payload["result"]["documents"][0]["rows"] == result["documents"][0]["rows"]
    assert payload["result"]["profile_projection"]["status"] == "AVAILABLE"


def test_review_action_changes_only_review_state_and_refreshes_artifact(
    client: TestClient, completed_job: dict
):
    result = client.get(
        f"/api/ui/v1/jobs/{completed_job['accepted']['job_id']}/result"
    ).json()
    finding = next(item for item in result["findings"] if item["kind"] == "CHECK")
    original_outcome = finding["status"]
    response = client.patch(
        f"/api/ui/v1/jobs/{result['job_id']}/findings/{finding['finding_id']}/review",
        json={"review_status": "NEEDS_FOLLOW_UP"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == original_outcome
    assert response.json()["review_status"] == "NEEDS_FOLLOW_UP"

    after = client.get(f"/api/ui/v1/jobs/{result['job_id']}/result").json()
    top_finding = next(item for item in after["findings"] if item["finding_id"] == finding["finding_id"])
    global_check = next(item for item in after["checks"] if item["finding_id"] == finding["finding_id"])
    document_check = next(
        item
        for item in after["documents"][0]["checks"]
        if item["finding_id"] == finding["finding_id"]
    )
    for item in (top_finding, global_check, document_check):
        assert item["status"] == original_outcome
        assert item["review_status"] == "NEEDS_FOLLOW_UP"

    artifact = client.get(after["artifacts"][0]["url"]).json()["result"]
    artifact_finding = next(
        item for item in artifact["findings"] if item["finding_id"] == finding["finding_id"]
    )
    assert artifact_finding["status"] == original_outcome
    assert artifact_finding["review_status"] == "NEEDS_FOLLOW_UP"


def test_one_failed_document_does_not_discard_the_successful_document(client: TestClient):
    good = UNRESOLVED_STATEMENT.read_bytes()
    bad = b"%PDF-1.4\nthis is deliberately not a parseable PDF\n%%EOF\n"
    entries = [
        entry(UNRESOLVED_STATEMENT.name, good, client_file_id="good"),
        entry("broken_source_USD_0001.pdf", bad, client_file_id="bad"),
    ]
    response = submit(client, entries, [good, bad], key=f"partial-{uuid.uuid4().hex}")
    assert response.status_code == 202, response.text
    status, result = wait_for_result(client, response.json()["job_id"])
    assert status["processing_state"] == "PARTIAL"
    by_client_id = {document["client_file_id"]: document for document in result["documents"]}
    assert by_client_id["good"]["processing_state"] == "SUCCEEDED"
    assert by_client_id["good"]["rows"]
    assert by_client_id["bad"]["processing_state"] == "FAILED"
    assert by_client_id["bad"]["rows"] == []
    assert result["summary"]["documents_succeeded"] == 1
    assert result["summary"]["documents_failed"] == 1


def test_reference_workbook_is_schema_validated_but_resolution_is_not_run(client: TestClient):
    source = UNRESOLVED_STATEMENT.read_bytes()
    workbook = WORKBOOK.read_bytes()
    entries = [
        entry(UNRESOLVED_STATEMENT.name, source, client_file_id="statement"),
        entry(
            WORKBOOK.name,
            workbook,
            client_file_id="reference",
            relative_path=f"references/{WORKBOOK.name}",
            purpose="REFERENCE",
        ),
    ]
    response = submit(client, entries, [source, workbook], key=f"reference-{uuid.uuid4().hex}")
    assert response.status_code == 202, response.text
    _, result = wait_for_result(client, response.json()["job_id"], timeout=30)
    assert result["reference_validation"]["status"] == "VALID"
    table_names = {table["name"] for table in result["reference_validation"]["tables"]}
    assert {"legal_entities", "project_codes", "account_map"} <= table_names
    reference_document = next(
        document for document in result["documents"] if document["purpose"] == "REFERENCE"
    )
    assert reference_document["rows"] == []
    assert reference_document["transaction_links"] == []
    assert reference_document["checks"] == []
    assert result["agent_resolution"] == {
        "status": "NOT_RUN",
        "reason": "This local deterministic bridge does not run the agent resolution or classification pass.",
    }
    assert result["profile_projection"]["reason"].endswith(
        "agent resolution fields remain NOT_RUN."
    )
    projected_row = result["profile_projection"]["data"]["accounts"][0]["envelope"][
        "statement_rows"
    ][0]
    assert projected_row["counterparty_match"] == {"status": "NOT_RUN"}
    assert projected_row["project_code_match"] == {"status": "NOT_RUN"}


def test_pipeline_validation_projection_also_exposes_not_run_not_a_fake_resolution(
    client: TestClient,
):
    source = UNRESOLVED_STATEMENT.read_bytes()
    item = entry(UNRESOLVED_STATEMENT.name, source)
    response = submit(
        client,
        [item],
        [source],
        key=f"pipeline-profile-{uuid.uuid4().hex}",
        profile_id="pipeline-validation",
    )
    assert response.status_code == 202, response.text
    _, result = wait_for_result(client, response.json()["job_id"])
    envelope = result["profile_projection"]["data"]["accounts"][0]["envelope"]
    assert envelope["extracted_rows"][0]["counterparty_status"] == "NOT_RUN"
    assert envelope["extracted_rows"][0]["project_code_status"] == "NOT_RUN"
    assert envelope["extracted_rows"][0]["classification"] is None
    assert envelope["export_candidates"] == []


def test_replays_are_clearly_recorded_and_never_claim_an_event_trace(client: TestClient):
    response = client.get("/api/ui/v1/replays")
    assert response.status_code == 200
    listing = response.json()
    assert listing["replays"]
    replay = listing["replays"][0]
    assert replay["kind"] == "RECORDED_REPLAY"
    assert replay["original_batch_id"]
    assert replay["profile_id"]
    assert replay["original_run_ids"]
    assert replay["recorded_seconds"] > 0
    assert replay["model_calls"] == 0
    assert replay["model_calls_scope"] == "REPLAY_READ"
    assert replay["event_trace_available"] is False

    detail_response = client.get(replay["links"]["self"])
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["accounts"]
    assert all(account["run_id"] and account["seconds"] for account in detail["accounts"])
    assert detail["timing"] == {
        "mode": "RECORDED_SECONDS",
        "compression_performed": False,
    }
    assert "no event trace" in detail["note"]
    assert "zero model calls" in detail["note"]
