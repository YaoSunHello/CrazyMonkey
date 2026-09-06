"""Contract and security tests for the local deterministic UI bridge."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import time
import uuid
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen.canvas import Canvas

from app.main import app
from app.profiles import available, load
from app.ui_bridge.csv_export import CSV_COLUMNS, build_transactions_csv
from app.ui_bridge.schemas import MAX_BATCH_BYTES, MAX_FILE_BYTES, MAX_FILES
from app.ui_bridge.store import STORE, Job

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


def test_registry_profile_outside_ui_capabilities_cannot_be_started(client: TestClient):
    blob = UNRESOLVED_STATEMENT.read_bytes()
    response = submit(
        client,
        [entry(UNRESOLVED_STATEMENT.name, blob)],
        [blob],
        key=f"unsupported-profile-{uuid.uuid4().hex}",
        profile_id="mandate-fit",
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "PROFILE_NOT_SUPPORTED"


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
    descriptor = result["exports"]["transactions_csv"]
    response = client.get(descriptor["url"])
    exported = list(csv.DictReader(io.StringIO(response.text, newline="")))
    assert response.status_code == 200
    assert descriptor["row_count"] == len(exported) == 32
    for document_index, document in enumerate(result["documents"]):
        block = exported[document_index * 16:(document_index + 1) * 16]
        assert {row["source_id"] for row in block} == {document["source_id"]}
        assert {row["source_relative_path"] for row in block} == {document["relative_path"]}
        assert [row["source_index"] for row in block] == [str(index) for index in range(16)]
        assert [row["chain_order"] for row in block] == [str(index) for index in reversed(range(16))]


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


def test_manifest_extra_fields_are_rejected(client: TestClient):
    blob = b"%PDF-1.4\n"
    item = entry("safe.pdf", blob)
    item["browser_command"] = "do-not-run"
    response = submit(client, [item], [blob], key=f"extra-{uuid.uuid4().hex}")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_MANIFEST"


def test_multipart_order_and_content_type_must_match_the_manifest(client: TestClient):
    blob = b"%PDF-1.4\n"
    entries = [
        entry("one.pdf", blob, client_file_id="one"),
        entry("two.pdf", blob, client_file_id="two"),
    ]
    manifest = json.dumps({
        "profile_id": "journal-entries",
        "case_name": "Multipart contract",
        "files": entries,
    })
    reversed_response = client.post(
        "/api/ui/v1/jobs",
        data={"manifest": manifest},
        files=[
            ("files", ("two.pdf", blob, "application/pdf")),
            ("files", ("one.pdf", blob, "application/pdf")),
        ],
        headers={"Idempotency-Key": f"order-{uuid.uuid4().hex}"},
    )
    assert reversed_response.status_code == 422
    assert reversed_response.json()["detail"]["code"] == "UPLOAD_FILENAME_MISMATCH"

    mime_response = client.post(
        "/api/ui/v1/jobs",
        data={"manifest": json.dumps({
            "profile_id": "journal-entries",
            "case_name": "Multipart MIME contract",
            "files": [entries[0]],
        })},
        files=[("files", ("one.pdf", blob, "text/plain"))],
        headers={"Idempotency-Key": f"mime-{uuid.uuid4().hex}"},
    )
    assert mime_response.status_code == 415
    assert mime_response.json()["detail"]["code"] == "UNSUPPORTED_CONTENT_TYPE"


def test_event_trace_is_actually_bounded_and_uses_the_shared_contract(tmp_path: Path):
    job = Job(
        job_id="job_event_contract",
        idempotency_key="event-contract-key",
        request_fingerprint="event-contract-fingerprint",
        profile_id="journal-entries",
        case_name="Event contract",
        directory=tmp_path,
        files=[],
    )
    for index in range(101):
        job.add_event("JOB_QUEUED", f"queued {index}")

    assert job.events_truncated is True
    assert len(job.events) == 100
    assert job.events[0]["meta"]["sequence"] == 2
    assert job.events[-1]["meta"]["sequence"] == 101
    assert set(job.events[-1]) == {"kind", "label", "detail", "status", "body", "meta", "at"}


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
    missing_status = next(
        check["status"]
        for check in completed_job["result"]["documents"][0]["checks"]
        if check["name"] == "printed_openings"
    )
    assert missing_status in {"UNRESOLVED", "CANNOT_VERIFY"}
    assert status["documents"][0]["computational_outcome"] == missing_status
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


def test_atlas_metadata_stays_bound_to_the_original_source(completed_job: dict):
    document = completed_job["result"]["documents"][0]
    atlas = document["atlas"]
    assert atlas["document_id"]
    assert atlas["document_id"] != document["source_id"]
    assert atlas["document_hash"] == document["sha256"] == hashlib.sha256(
        completed_job["bytes"]
    ).hexdigest()
    assert atlas["filename"] == document["filename"]
    assert atlas["role"] == "SUPPORTING"
    assert atlas["extraction_status"] == "COMPLETE"
    assert atlas["evidence_count"] > 0
    assert atlas["warnings"] == []
    assert atlas["original_storage_key"] == (
        f"{completed_job['accepted']['job_id']}/{document['source_id']}/{document['filename']}"
    )
    assert completed_job["status"]["documents"][0]["atlas"] == atlas
    assert document["rows"][0]["citation"]["source_id"] == document["source_id"]
    citations = [row["citation"] for row in document["rows"]]
    citations.extend(
        row["narrative_citation"] for row in document["rows"] if row["narrative_citation"]
    )
    for link in document["transaction_links"]:
        citations.extend(link["citations"].values())
    for citation in citations:
        assert citation["atlas_document_id"] == atlas["document_id"]
        assert citation["document_hash"] == atlas["document_hash"]
        assert citation["source_id"] == document["source_id"]
        assert citation["page"] >= 1
        assert citation["bbox"]
    aggregate_checks = document["checks"] + completed_job["result"]["checks"] + [
        finding for finding in completed_job["result"]["findings"] if finding["kind"] == "CHECK"
    ]
    for check in aggregate_checks:
        assert check["source_citation"] == {
            "source_id": document["source_id"],
            "filename": document["filename"],
            "atlas_document_id": atlas["document_id"],
            "document_hash": atlas["document_hash"],
        }


def test_renamed_statement_upload_completes_with_real_rows(client: TestClient):
    blob = UNRESOLVED_STATEMENT.read_bytes()
    response = submit(
        client, [entry("statement.pdf", blob)], [blob], key=f"renamed-{uuid.uuid4().hex}"
    )
    assert response.status_code == 202, response.text
    status, result = wait_for_result(client, response.json()["job_id"])
    assert status["processing_state"] == "SUCCEEDED"
    document = result["documents"][0]
    assert document["statement"]["account_short_code"] == "EUR_240149813030"
    assert document["statement"]["account_number"] == "240-149813-030"
    assert document["statement"]["closing_balance"] == "20088.32"
    assert len(document["rows"]) == 16
    assert document["atlas"]["document_hash"] == hashlib.sha256(blob).hexdigest()


def ordinary_pdf() -> bytes:
    output = io.BytesIO()
    canvas = Canvas(output)
    canvas.drawString(72, 720, "Meeting notes: discuss tomorrow's review.")
    canvas.save()
    return output.getvalue()


@pytest.mark.parametrize("with_good_statement", [False, True])
def test_readable_nonstatement_is_failed_without_discarding_other_sources(
    client: TestClient, with_good_statement: bool,
):
    bad = ordinary_pdf()
    entries = [entry("meeting_notes.pdf", bad, client_file_id="notes")]
    blobs = [bad]
    if with_good_statement:
        good = UNRESOLVED_STATEMENT.read_bytes()
        entries.append(entry(UNRESOLVED_STATEMENT.name, good, client_file_id="good"))
        blobs.append(good)
    response = submit(client, entries, blobs, key=f"unsupported-pdf-{uuid.uuid4().hex}")
    assert response.status_code == 202, response.text
    status, result = wait_for_result(client, response.json()["job_id"])
    assert status["processing_state"] == ("PARTIAL" if with_good_statement else "FAILED")
    documents = {item["client_file_id"]: item for item in result["documents"]}
    rejected = documents["notes"]
    assert rejected["processing_state"] == "FAILED"
    assert rejected["computational_outcome"] is None
    assert "UNSUPPORTED_STATEMENT" in rejected["error"]
    assert rejected["rows"] == rejected["checks"] == []
    assert rejected["atlas"]["extraction_status"] == "COMPLETE"
    assert rejected["atlas"]["evidence_count"] > 0
    if with_good_statement:
        assert documents["good"]["processing_state"] == "SUCCEEDED"
        assert len(documents["good"]["rows"]) == 16
    else:
        assert result["exports"] == {}
        response = client.get(f"/api/ui/v1/jobs/{result['job_id']}/transactions.csv")
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "NO_TRANSACTION_ROWS"


@pytest.mark.parametrize("kind", ["encrypted", "image-only"])
def test_atlas_rejections_are_document_failures_in_a_mixed_batch(client: TestClient, kind):
    good = UNRESOLVED_STATEMENT.read_bytes()
    writer = PdfWriter()
    if kind == "encrypted":
        writer.append_pages_from_reader(PdfReader(io.BytesIO(good)))
        writer.encrypt("test-only-password")
        code = "ENCRYPTED_PDF"
    else:
        writer.add_blank_page(width=600, height=800)
        code = "IMAGE_ONLY_OR_EMPTY_PDF"
    output = io.BytesIO()
    writer.write(output)
    writer.close()
    bad = output.getvalue()
    response = submit(
        client,
        [
            entry("unsupported.pdf", bad, client_file_id="bad"),
            entry(UNRESOLVED_STATEMENT.name, good, client_file_id="good"),
        ],
        [bad, good],
        key=f"atlas-rejection-{uuid.uuid4().hex}",
    )
    assert response.status_code == 202, response.text
    status, result = wait_for_result(client, response.json()["job_id"])
    assert status["processing_state"] == "PARTIAL"
    bad_document, good_document = result["documents"]
    assert bad_document["processing_state"] == "FAILED"
    assert code in bad_document["error"]
    assert bad_document["atlas"]["extraction_status"] == "FAILED"
    assert bad_document["atlas"]["evidence_count"] == 0
    assert bad_document["atlas"]["warnings"]
    assert good_document["processing_state"] == "SUCCEEDED"
    assert len(good_document["rows"]) == 16


def test_unverified_checks_and_real_citation_source_identity_are_preserved(completed_job: dict):
    result = completed_job["result"]
    document = result["documents"][0]
    source_id = document["source_id"]
    missing_status = next(check["status"] for check in document["checks"] if check["name"] == "printed_openings")
    assert missing_status in {"UNRESOLVED", "CANNOT_VERIFY"}
    assert missing_status in {check["status"] for check in result["checks"]}
    assert result["summary"]["checks"][missing_status] >= 1

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
    assert payload["result"]["exports"] == result["exports"]


def test_transaction_csv_schema_exact_bytes_hash_and_source_linkage(client: TestClient, completed_job: dict):
    result = completed_job["result"]
    document = result["documents"][0]
    descriptor = result["exports"]["transactions_csv"]
    response = client.get(descriptor["url"])
    assert response.status_code == 200
    assert response.headers["content-type"] == descriptor["content_type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == f'attachment; filename="{descriptor["filename"]}"'
    assert response.headers["etag"] == f'"{descriptor["sha256"]}"'
    assert descriptor == {
        "url": f"/api/ui/v1/jobs/{result['job_id']}/transactions.csv",
        "filename": f"{result['job_id']}-transactions.csv",
        "content_type": "text/csv; charset=utf-8",
        "row_count": 16,
        "sha256": hashlib.sha256(response.content).hexdigest(),
    }
    assert response.content == build_transactions_csv(result).content
    assert not response.content.startswith(b"\xef\xbb\xbf")
    assert response.content.endswith(b"\r\n")
    reader = csv.DictReader(io.StringIO(response.content.decode("utf-8"), newline=""))
    expected_columns = (
        "schema_version", "job_id", "profile_id", "case_name", "execution_label",
        "agent_resolution_status", "job_processing_state", "source_id", "source_filename",
        "source_relative_path", "document_hash", "atlas_document_id", "atlas_extraction_status",
        "document_processing_state", "computational_outcome", "account_short_code",
        "account_number", "currency", "row_id", "source_index", "chain_order",
        "value_date", "value_date_iso", "post_date", "time", "bank_reference",
        "customer_reference", "trn_type", "narrative", "credit", "debit", "signed_movement",
        "balance", "link_status", "difference", "finding_id", "older_row_id",
        "derived_balance", "comparison_balance", "citation_page", "citation_x0", "citation_top",
        "citation_x1", "citation_bottom",
    )
    assert tuple(reader.fieldnames) == CSV_COLUMNS == expected_columns
    rows = list(reader)
    assert len(rows) == descriptor["row_count"] == len(document["rows"])
    original_hash = hashlib.sha256(completed_job["bytes"]).hexdigest()
    links = {link["newer_row_id"]: link for link in document["transaction_links"]}
    for index, (exported, original) in enumerate(zip(rows, document["rows"])):
        assert exported["schema_version"] == "transactions.v1"
        assert exported["job_id"] == result["job_id"]
        assert exported["job_processing_state"] == result["processing_state"]
        assert exported["execution_label"] == "LOCAL_DETERMINISTIC"
        assert exported["agent_resolution_status"] == "NOT_RUN"
        assert exported["source_id"] == document["source_id"]
        assert exported["source_filename"] == document["filename"]
        assert exported["source_relative_path"] == document["relative_path"]
        assert exported["document_hash"] == original_hash == document["atlas"]["document_hash"]
        assert exported["atlas_document_id"] == original["citation"]["atlas_document_id"] == document["atlas"]["document_id"]
        assert exported["atlas_extraction_status"] == document["atlas"]["extraction_status"]
        assert exported["computational_outcome"] == document["computational_outcome"]
        assert exported["account_number"] == original["account_number"]
        assert exported["account_short_code"] == document["statement"]["account_short_code"]
        assert exported["currency"] == original["currency"]
        assert exported["row_id"] == original["row_id"]
        assert exported["source_index"] == str(index) == str(original["index"])
        assert exported["chain_order"] == str(len(rows) - 1 - index)
        for key in ("value_date", "post_date", "time", "bank_reference", "customer_reference", "trn_type"):
            assert exported[key] == original[key]
        for key in ("credit", "debit", "balance", "signed_movement"):
            assert exported[key] == (original[key] if original[key] is not None else "")
        assert exported["citation_page"] == str(original["citation"]["page"])
        for coordinate, value in original["citation"]["bbox"].items():
            assert exported[f"citation_{coordinate}"] == str(value)
        link = links.get(original["row_id"], {})
        for column, key in (("link_status", "status"), ("difference", "difference"), ("finding_id", "finding_id"),
                            ("older_row_id", "older_row_id"), ("derived_balance", "derived_balance"),
                            ("comparison_balance", "comparison_balance")):
            assert exported[column] == (link.get(key) if link.get(key) is not None else "")
    assert rows[0]["value_date"] == "31 Mar 2026"
    assert rows[0]["value_date_iso"] == "2026-03-31"
    assert rows[-1]["link_status"] == rows[-1]["finding_id"] == rows[-1]["difference"] == ""


def test_transaction_csv_preserves_negative_debits_and_does_not_reanalyse(
    client: TestClient, completed_job: dict, monkeypatch: pytest.MonkeyPatch
):
    def must_not_run(*args, **kwargs):
        raise AssertionError("CSV download must not rerun ingestion, parsing or verification")

    for name in ("normalize_file", "parse_statement", "run_parse_checks", "balance_chain_links"):
        monkeypatch.setattr(f"app.ui_bridge.service.{name}", must_not_run)
    result = completed_job["result"]
    descriptor = result["exports"]["transactions_csv"]
    first = client.get(descriptor["url"])
    second = client.get(descriptor["url"])
    assert first.status_code == second.status_code == 200
    assert first.content == second.content
    rows = list(csv.DictReader(io.StringIO(first.text, newline="")))
    assert rows[0]["credit"] == ""
    assert rows[0]["debit"] == rows[0]["signed_movement"] == "-0.44"
    for exported, original in zip(rows, result["documents"][0]["rows"]):
        expected = original["credit"] if original["credit"] is not None else original["debit"]
        assert exported["signed_movement"] == (expected if expected is not None else "")
    source_id = result["documents"][0]["source_id"]
    assert client.get(f"/api/ui/v1/jobs/{result['job_id']}/sources/{source_id}").content == completed_job["bytes"]


@pytest.mark.parametrize("text", ["=SUM(A1:A2)", "+CMD", "-CMD", "@SUM(A1:A2)", " \t\r\n\ufeff=1+1"])
def test_transaction_csv_escapes_untrusted_text_only(completed_job: dict, text: str):
    result = deepcopy(completed_job["result"])
    result["case_name"] = text
    document = result["documents"][0]
    document["filename"] = document["relative_path"] = text
    original = document["rows"][0]
    for key in ("narrative", "bank_reference", "customer_reference", "trn_type", "account_number"):
        original[key] = text
    original["debit"] = original["signed_movement"] = "-0.44"
    export = build_transactions_csv(result)
    first = next(csv.DictReader(io.StringIO(export.content.decode("utf-8"), newline="")))
    for key in ("case_name", "source_filename", "source_relative_path", "narrative", "bank_reference",
                "customer_reference", "trn_type", "account_number"):
        assert first[key] == "'" + text
    assert first["debit"] == first["signed_movement"] == "-0.44"


def test_transaction_csv_quotes_unicode_and_preserves_exact_decimals_and_missing_values(completed_job: dict):
    result = deepcopy(completed_job["result"])
    result["documents"][0]["computational_outcome"] = "FAIL"
    result["documents"][0]["transaction_links"][0].update(status="FAIL", difference="0.01")
    original = result["documents"][0]["rows"][0]
    original.update(
        narrative='Caf\u00e9, "supplier"\r\nsecond line',
        balance="9007199254740993.12500000000000001",
        credit="0.00",
        debit=None,
        signed_movement="0.00",
        value_date="not a valid date",
    )
    export = build_transactions_csv(result)
    first = next(csv.DictReader(io.StringIO(export.content.decode("utf-8"), newline="")))
    assert b'Caf\xc3\xa9, ""supplier""\r\nsecond line' in export.content
    assert first["narrative"] == original["narrative"]
    assert first["balance"] == original["balance"]
    assert first["credit"] == first["signed_movement"] == "0.00"
    assert first["debit"] == ""
    assert first["value_date"] == "not a valid date"
    assert first["value_date_iso"] == ""
    assert first["computational_outcome"] == first["link_status"] == "FAIL"
    assert first["difference"] == "0.01"
    original.update(credit=None, debit=None, signed_movement=None)
    missing = next(csv.DictReader(io.StringIO(build_transactions_csv(result).content.decode("utf-8"), newline="")))
    assert missing["credit"] == missing["debit"] == missing["signed_movement"] == ""


@pytest.mark.parametrize("invalid", ["=1+1", "-1+2", "Infinity", "NaN", 0.44])
def test_transaction_csv_rejects_nondecimal_money(completed_job: dict, invalid):
    result = deepcopy(completed_job["result"])
    result["documents"][0]["rows"][0]["debit"] = invalid
    with pytest.raises(ValueError, match="exact finite decimal"):
        build_transactions_csv(result)


def test_transaction_csv_is_unavailable_before_result_or_without_rows(client: TestClient, tmp_path: Path):
    job = Job(
        job_id=f"job_{uuid.uuid4().hex}", idempotency_key=f"csv-pending-{uuid.uuid4().hex}",
        request_fingerprint="csv-pending", profile_id="journal-entries", case_name="CSV pending",
        directory=tmp_path / "not-a-stored-source-directory", files=[],
    )
    STORE.add_or_reuse(job)
    url = f"/api/ui/v1/jobs/{job.job_id}/transactions.csv"
    pending = client.get(url)
    assert pending.status_code == 409
    assert pending.json()["detail"]["code"] == "RESULT_NOT_READY"
    with job.lock:
        job.processing_state = "FAILED"
        job.result = {"job_id": job.job_id, "documents": [], "exports": {}}
    empty = client.get(url)
    assert empty.status_code == 409
    assert empty.json()["detail"]["code"] == "NO_TRANSACTION_ROWS"
    missing = client.get(f"/api/ui/v1/jobs/job_{uuid.uuid4().hex}/transactions.csv")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "JOB_NOT_FOUND"


def test_transaction_csv_and_descriptor_do_not_change_on_human_review(client: TestClient, completed_job: dict):
    result = completed_job["result"]
    descriptor = result["exports"]["transactions_csv"]
    before = client.get(descriptor["url"]).content
    link = result["documents"][0]["transaction_links"][0]
    response = client.patch(
        f"/api/ui/v1/jobs/{result['job_id']}/findings/{link['finding_id']}/review",
        json={"review_status": "NEEDS_FOLLOW_UP"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == link["status"]
    after = client.get(f"/api/ui/v1/jobs/{result['job_id']}/result").json()
    assert after["exports"]["transactions_csv"] == descriptor
    assert client.get(descriptor["url"]).content == before


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
    descriptor = result["exports"]["transactions_csv"]
    csv_response = client.get(descriptor["url"])
    assert csv_response.status_code == 200
    exported = list(csv.DictReader(io.StringIO(csv_response.text, newline="")))
    assert len(exported) == descriptor["row_count"] == len(by_client_id["good"]["rows"])
    assert {row["source_id"] for row in exported} == {by_client_id["good"]["source_id"]}
    assert {row["job_processing_state"] for row in exported} == {"PARTIAL"}
    assert {row["computational_outcome"] for row in exported} == {by_client_id["good"]["computational_outcome"]}


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
    assert reference_document["atlas"]["document_id"]
    assert reference_document["atlas"]["document_hash"] == hashlib.sha256(workbook).hexdigest()
    assert reference_document["atlas"]["role"] == "SUPPORTING"
    assert reference_document["atlas"]["evidence_count"] > 0
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


def test_incomplete_reference_workbook_fails_without_discarding_the_statement(client: TestClient):
    book = Workbook()
    book.remove(book.active)
    for name, spec in load("journal-entries").inputs["tables"].items():
        sheet = book.create_sheet(spec["sheet"])
        columns = list(spec["columns"])
        if name == "project_codes":
            columns.remove("New Project Code")
        sheet.append(columns)
        sheet.append(["example"] * len(columns))
    output = io.BytesIO()
    book.save(output)
    book.close()
    reference = output.getvalue()
    source = UNRESOLVED_STATEMENT.read_bytes()
    response = submit(
        client,
        [
            entry(UNRESOLVED_STATEMENT.name, source, client_file_id="statement"),
            entry("NAV_reference.xlsx", reference, client_file_id="reference", purpose="REFERENCE"),
        ],
        [source, reference],
        key=f"incomplete-reference-{uuid.uuid4().hex}",
    )
    assert response.status_code == 202, response.text
    status, result = wait_for_result(client, response.json()["job_id"])
    assert status["processing_state"] == "PARTIAL"
    assert result["reference_validation"]["status"] == "INVALID"
    assert "missing required columns: New Project Code" in result["reference_validation"]["error"]
    statement, workbook = result["documents"]
    assert statement["processing_state"] == "SUCCEEDED"
    assert len(statement["rows"]) == 16
    assert workbook["processing_state"] == "FAILED"
    assert workbook["atlas"]["role"] == "SUPPORTING"
    assert workbook["atlas"]["extraction_status"] == "COMPLETE"
    assert workbook["atlas"]["evidence_count"] > 0


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
