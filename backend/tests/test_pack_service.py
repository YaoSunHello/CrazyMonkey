"""Local pack integration tests; all ingestion and model requests are mocked."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import threading
import time
import types
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import pack_api
from app.pack_service import PackService, safe_relative_path
from app.runtime.model import RuntimeModelError


class FakeClient:
    name = "gemini/test-model"

    def __init__(self, *, gate=None, entered=None, behavior=None):
        self.calls = []
        self.payloads = []
        self.closed = False
        self.gate = gate
        self.entered = entered
        self.behavior = behavior or {}
        self.lock = threading.Lock()

    def complete_json(self, _system, payload, *, stage=None):
        relative = payload["file_profile"]["relative_path"]
        action = self.behavior.get(relative)
        with self.lock:
            self.payloads.append(deepcopy(payload))
            self.calls.append({"stage": stage, "provider": "gemini", "model": "test-model",
                               "response_id": f"test-{len(self.calls) + 1}", "usage": {},
                               "status": "error" if action == "error" else "success"})
        if self.entered:
            self.entered.set()
        if self.gate and not self.gate.wait(timeout=5):
            raise RuntimeModelError("Test model gate timed out")
        if action == "error":
            raise RuntimeModelError("Sanitized provider failure")
        evidence_id = payload["file_profile"]["sample_evidence"][0]["evidence_id"]
        return {
            "summary": "Bounded source review.", "role": "SOURCE",
            "findings": [{"title": "Review a source item", "severity": "INFO",
                          "explanation": "This is a review candidate, not a verified correction.",
                          "evidence_ids": ["invented-evidence" if action == "invalid_id" else evidence_id]}],
            "suggested_actions": ["Check the cited source."],
            "limitations": ["Only bounded source excerpts were reviewed."],
        }

    def close(self):
        self.closed = True


class PackServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.ingested = []
        self.ingestion_failures = set()
        self.evidence_ids = {}
        ingestion = types.ModuleType("app.pack_ingestion")
        ingestion.initialize_database = self.initialize_database
        ingestion.ingest_file = self.ingest_file
        self.ingestion_patch = patch.dict(sys.modules, {"app.pack_ingestion": ingestion})
        self.ingestion_patch.start()
        self.addCleanup(self.ingestion_patch.stop)

    def initialize_database(self, connection):
        connection.execute("CREATE TABLE documents(document_id TEXT PRIMARY KEY, relative_path TEXT NOT NULL)")
        connection.execute("CREATE TABLE evidence(evidence_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, locator TEXT NOT NULL, content_json TEXT NOT NULL)")
        connection.commit()

    def ingest_file(self, path, relative_path, connection):
        self.ingested.append((Path(path), relative_path))
        if relative_path in self.ingestion_failures:
            raise ValueError("Untrusted source parse detail must not escape")
        data = Path(path).read_bytes()
        document_id = "doc-" + sha256(relative_path.encode()).hexdigest()[:12]
        evidence_id = "ev-" + document_id
        self.evidence_ids[relative_path] = evidence_id
        content = {"text": data.decode()}
        connection.execute("INSERT INTO documents VALUES (?, ?)", (document_id, relative_path))
        connection.execute("INSERT INTO evidence VALUES (?, ?, ?, ?)", (evidence_id, document_id, "line 1", json.dumps(content)))
        return {
            "document_id": document_id, "relative_path": relative_path, "kind": "TEXT",
            "row_count": 1, "cell_count": 1, "page_count": 0, "sha256": sha256(data).hexdigest(),
            "sheets": [], "sample_evidence": [{"evidence_id": evidence_id, "locator": "line 1", **content}],
        }

    def service(self, fake=None, factory=None):
        fake = fake or FakeClient()
        service = PackService(output_root=self.root / "packs", client_factory=factory or (lambda: fake))
        self.addCleanup(lambda: service.pool.shutdown(wait=True))
        return service, fake

    def reserve_sources(self, service, paths):
        run_id, sources = service.reserve(paths, "Review these local source excerpts.")
        for relative in paths:
            path = sources / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("source text")
        return run_id, sources

    def http_client(self, service, configured=True):
        packs_patch = patch.object(pack_api, "packs", service)
        packs_patch.start()
        self.addCleanup(packs_patch.stop)
        config_patch = patch.object(pack_api, "load_local_config", return_value={
            "present": {"LLM_API_KEY": configured}, "provider": "gemini" if configured else None,
            "model": "gemini-test-model" if configured else None, "gemini_endpoint": configured,
            "ready": configured, "local_env_loaded": configured,
        })
        config_patch.start()
        self.addCleanup(config_patch.stop)
        app = FastAPI()
        app.include_router(pack_api.router)
        client = TestClient(app)
        self.addCleanup(client.close)
        return client

    def poll(self, client, run_id):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            response = client.get(f"/api/pack/runs/{run_id}")
            self.assertEqual(response.status_code, 200)
            result = response.json()
            if result["status"] in {"COMPLETE", "COMPLETE_WITH_ERRORS", "FAILED"}:
                return result
            time.sleep(0.01)
        self.fail("Mock pack run did not reach a terminal status")

    def test_reserve_rejects_traversal_hidden_unsupported_and_duplicate_paths(self):
        service, fake = self.service()
        for relative in ("../escape.txt", "/outside.txt", "folder/.secret.txt", "folder\\escape.txt", "hidden/.env", "script.py", "bad\x00.txt"):
            with self.subTest(relative=relative):
                with self.assertRaises(ValueError):
                    service.reserve([relative], "Review.")
        with self.assertRaises(ValueError):
            service.reserve(["same.txt", "same.txt"], "Review.")
        self.assertFalse(service.root.exists())
        self.assertEqual(fake.calls, [])
        run_id, sources = service.reserve(["nested/source.txt"], "Review.")
        self.assertTrue(sources.resolve().is_relative_to(service.root.resolve()))
        with self.assertRaises(ValueError):
            service.reserve(["another.txt"], "Review.")
        service.abort_upload(run_id)
        self.assertIsNone(service.active_run)

    def test_invalid_model_evidence_fails_only_its_file_and_never_becomes_a_finding(self):
        fake = FakeClient(behavior={"invalid.txt": "invalid_id"})
        service, _ = self.service(fake)
        run_id, _ = self.reserve_sources(service, ["valid.txt", "invalid.txt"])
        service.launch(run_id).result(timeout=5)
        result = service.get(run_id)
        self.assertEqual(result["status"], "COMPLETE_WITH_ERRORS")
        self.assertEqual(result["processed_files"], 2)
        self.assertEqual(result["model_call_count"], 2)
        good, invalid = result["files"]
        self.assertEqual(good["status"], "COMPLETE")
        self.assertEqual(good["findings"][0]["status"], "REVIEW_REQUIRED")
        self.assertEqual(invalid["status"], "FAILED")
        self.assertEqual(invalid["findings"], [])
        self.assertNotIn("invented-evidence", json.dumps(result))
        self.assertTrue(fake.closed)
        self.assertIsNone(service.active_run)

    def test_import_failure_does_not_discard_other_files_or_call_model_for_failed_file(self):
        self.ingestion_failures.add("broken.txt")
        service, fake = self.service()
        run_id, _ = self.reserve_sources(service, ["good.txt", "broken.txt"])
        service.launch(run_id).result(timeout=5)
        result = service.get(run_id)
        self.assertEqual(result["status"], "COMPLETE_WITH_ERRORS")
        self.assertEqual(result["model_call_count"], 1)
        self.assertEqual(result["files"][0]["status"], "COMPLETE")
        self.assertFalse(result["files"][1]["import_complete"])
        self.assertEqual(result["files"][1]["error"], "Import failed: ValueError")
        self.assertEqual([payload["file_profile"]["relative_path"] for payload in fake.payloads], ["good.txt"])
        self.assertNotIn("Untrusted source parse detail", json.dumps(result))

    def test_provider_failure_has_no_retry_or_synthetic_fallback(self):
        fake = FakeClient(behavior={"source.txt": "error"})
        service, _ = self.service(fake)
        run_id, _ = self.reserve_sources(service, ["source.txt"])
        service.launch(run_id).result(timeout=5)
        result = service.get(run_id)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["mode"], "LIVE_MODEL")
        self.assertEqual(result["model_call_count"], 1)
        self.assertEqual(result["files"][0]["findings"], [])
        self.assertEqual(fake.calls[0]["status"], "error")
        self.assertTrue(fake.closed)
        self.assertIsNone(service.active_run)

    def test_client_configuration_failure_stops_before_ingestion_and_releases_slot(self):
        def factory():
            raise RuntimeModelError("Missing Gemini configuration: LLM_API_KEY.")
        service, fake = self.service(factory=factory)
        run_id, _ = self.reserve_sources(service, ["source.txt"])
        service.launch(run_id).result(timeout=5)
        result = service.get(run_id)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["mode"], "LIVE_MODEL")
        self.assertEqual(result["model_call_count"], 0)
        self.assertEqual(self.ingested, [])
        self.assertIsNone(service.active_run)

    def test_actual_async_multipart_upload_launch_poll_and_evidence_api_shape(self):
        entered, gate = threading.Event(), threading.Event()
        self.addCleanup(gate.set)
        service, fake = self.service(FakeClient(gate=gate, entered=entered))
        client = self.http_client(service)
        config = client.get("/api/pack/config")
        self.assertEqual(config.status_code, 200)
        self.assertTrue(config.json()["configured"])
        response = client.post("/api/pack/runs", data={"relative_paths": ["nested/notes.txt"], "instruction": "Review the uploaded source."},
                               files=[("files", ("notes.txt", b"uploaded source text", "text/plain"))])
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(set(response.json()), {"run_id"})
        run_id = response.json()["run_id"]
        self.assertTrue(entered.wait(timeout=3))
        pending = client.get(f"/api/pack/runs/{run_id}").json()
        self.assertEqual(pending["status"], "ANALYSING")
        self.assertEqual(pending["files"][0]["relative_path"], "nested/notes.txt")
        self.assertTrue(pending["files"][0]["import_complete"])
        gate.set()
        result = self.poll(client, run_id)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["processed_files"], 1)
        self.assertEqual(result["model_call_count"], 1)
        self.assertEqual(result["files"][0]["findings"][0]["status"], "REVIEW_REQUIRED")
        self.assertEqual(self.ingested[0][0].read_bytes(), b"uploaded source text")
        runs = client.get("/api/pack/runs").json()
        self.assertEqual(runs["runs"][0]["run_id"], run_id)
        evidence_id = self.evidence_ids["nested/notes.txt"]
        evidence = client.get(f"/api/pack/runs/{run_id}/evidence/{evidence_id}")
        self.assertEqual(evidence.status_code, 200, evidence.text)
        self.assertEqual(evidence.json(), {"evidence_id": evidence_id, "relative_path": "nested/notes.txt", "locator": "line 1", "content": {"text": "uploaded source text"}})
        self.assertEqual(client.get(f"/api/pack/runs/{run_id}/evidence/unknown").status_code, 404)
        self.assertEqual(client.get("/api/pack/runs/invalid-run").status_code, 404)

    def test_upload_is_refused_when_local_configuration_is_not_ready(self):
        service, fake = self.service()
        client = self.http_client(service, configured=False)
        response = client.post("/api/pack/runs", data={"relative_paths": ["source.txt"]}, files=[("files", ("source.txt", b"source", "text/plain"))])
        self.assertEqual(response.status_code, 503)
        self.assertEqual(service.jobs, {})
        self.assertEqual(fake.calls, [])

    def test_oversized_upload_aborts_and_releases_slot_without_model_call(self):
        service, fake = self.service()
        client = self.http_client(service)
        with patch.object(pack_api, "MAX_FILE_BYTES", 4):
            response = client.post("/api/pack/runs", data={"relative_paths": ["source.txt"]}, files=[("files", ("source.txt", b"12345", "text/plain"))])
        self.assertEqual(response.status_code, 413)
        self.assertIsNone(service.active_run)
        self.assertEqual(fake.calls, [])
        self.assertEqual(next(iter(service.jobs.values()))["status"], "FAILED")

    def test_reloaded_completed_run_has_the_same_polling_shape(self):
        service, fake = self.service()
        run_id, _ = self.reserve_sources(service, ["source.txt"])
        service.launch(run_id).result(timeout=5)
        original = service.get(run_id)
        reloaded = PackService(output_root=service.root, client_factory=lambda: fake)
        self.addCleanup(lambda: reloaded.pool.shutdown(wait=True))
        self.assertEqual(reloaded.get(run_id), original)
        self.assertEqual(reloaded.list_runs()[0]["status"], "COMPLETE")


if __name__ == "__main__":
    unittest.main()
