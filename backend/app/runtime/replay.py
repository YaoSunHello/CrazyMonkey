"""Replay saved live audits by rechecking sources and rerunning deterministic code.

The saved semantic review is a historical decision, never a fresh Gemini
review. This module neither imports nor constructs a model client. Local hashes
detect corruption; case files are not a signed attestation from the provider.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from time import perf_counter

from pydantic import ValidationError

from app.atlas.ingestion import MAX_FILE_BYTES
from app.atlas.models import NormalizedDocument
from .challenger import challenge
from .contracts import Challenge, ModelChallenge
from .executor import execute
from .fast_dsl import FastCheck, execute_check
from .investigation_evidence import EvidenceStore
from .patches import apply_patches, propose_patch


SCHEMA_ID = "crazymonkey.verified-replay"
SCHEMA_VERSION = 1
CASE_FILES = (
    "manifest.json", "normalized_evidence.json", "verification_plan.json",
    "verifier_result.json", "red_team_result.json", "patch_proposal.json",
    "trace.json", "source_hashes.json",
)
MAX_CASE_FILE_BYTES = 32 * 1024 * 1024
MAX_CASE_TOTAL_BYTES = 64 * 1024 * 1024
MAX_CHECKS = 1000
_ACCEPTED = {"MATCH", "DISCREPANCY"}
_STATUSES = _ACCEPTED | {"CANNOT_VERIFY", "REVIEW_REQUIRED"}


def _error(message="INVALID_VERIFIED_CASE"):
    raise ValueError(message)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _bound_case_id(case_id: str) -> None:
    if not isinstance(case_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", case_id):
        _error("Case ID must contain 1..80 letters, digits, dots, underscores or hyphens")


def _source_records(store: EvidenceStore) -> list[dict]:
    records = []
    for normalized in store.documents:
        doc = normalized.document
        path = Path(doc.original_storage_key)
        if not path.is_absolute() or path.is_symlink():
            _error("SOURCE_CHANGED_REQUIRES_FRESH_AUDIT")
        if not path.is_file():
            _error(f"SOURCE_MISSING_REQUIRES_FRESH_AUDIT: {doc.filename}")
        try:
            with path.open("rb") as handle:
                data = handle.read(MAX_FILE_BYTES + 1)
        except OSError:
            _error(f"SOURCE_MISSING_REQUIRES_FRESH_AUDIT: {doc.filename}")
        if len(data) > MAX_FILE_BYTES or _sha(data) != doc.document_hash or len(data) != doc.size_bytes:
            _error("SOURCE_CHANGED_REQUIRES_FRESH_AUDIT")
        records.append({"document_id": doc.document_id, "filename": doc.filename,
                        "document_hash": doc.document_hash, "size_bytes": doc.size_bytes,
                        "original_storage_key": doc.original_storage_key})
    return records


def _complete_store(store: EvidenceStore) -> None:
    if not 1 <= len(store.documents) <= 32 or not 1 <= len(store.refs) <= 8000:
        _error("INVALID_VERIFIED_CASE: evidence bounds")
    for normalized in store.documents:
        doc = normalized.document
        warnings = [warning for warning in doc.warnings
                    if warning != "Document role requires reviewer confirmation"
                    and "uses CSV separator whitespace before quoted fields" not in warning]
        if doc.extraction_status in {"PARTIAL", "FAILED"} or warnings:
            _error("INCOMPLETE_SOURCE_AUDIT_REQUIRES_FRESH_AUDIT")


def _successful_live_trace(trace: dict) -> None:
    calls = trace.get("model_calls")
    if (not isinstance(calls, list) or not calls or len(calls) > 2 * MAX_CHECKS + 10
            or trace.get("gemini_call_count") != len(calls) or not trace.get("runtime_model")):
        _error("A verified case requires recorded successful live Gemini calls")
    discovery = {"contract_discovery", "relationship_discovery", "investigator"}
    if not any(isinstance(call, dict) and call.get("provider") == "gemini"
               and call.get("status") == "success" and call.get("stage") in discovery for call in calls):
        _error("A verified case requires recorded successful live Gemini discovery")


def _is_accepted(finding: dict) -> bool:
    review = finding["red_team"]
    return (finding["status"] in _ACCEPTED and review["status"] == "PASS"
            and finding["check"]["source"] != "anomaly" and finding["check"]["check_type"] != "anomaly"
            and bool(review["checks"]) and all(review["checks"].values()))


def _review_trace_binding(findings: list[dict], trace: dict) -> None:
    if any(finding.get("model_review") is not None for finding in findings):
        if not any(call.get("stage") in {"red_team", "red_team_after_repair"}
                   and call.get("provider") == "gemini" and call.get("status") == "success"
                   for call in trace["model_calls"]):
            _error("INVALID_VERIFIED_CASE: saved semantic decisions lack a live review call")


def _verify_findings(findings: list[dict], store: EvidenceStore) -> tuple[list[dict], list]:
    # The import is intentionally local: to_plan has no model calls, and this
    # avoids a cycle when the CLI imports replay support.
    from app.fast_audit import to_plan

    if not isinstance(findings, list) or not 1 <= len(findings) <= MAX_CHECKS:
        _error("INVALID_VERIFIED_CASE: check bounds")
    seen, refreshed, proposals = set(), [], []
    for saved in findings:
        check = FastCheck.model_validate(saved["check"])
        if check.check_id in seen or saved["check_id"] != check.check_id or saved["status"] not in _STATUSES:
            _error("INVALID_VERIFIED_CASE: check identity or status")
        seen.add(check.check_id)
        specs = check.inputs + ([check.compare_to] if check.compare_to is not None else [])
        for evidence_id in [spec.evidence_id for spec in specs] + check.context_evidence_ids:
            store.get(evidence_id)
        previous_review = Challenge.model_validate(saved["red_team"])
        model_review = ModelChallenge.model_validate(saved["model_review"]) if saved.get("model_review") else None
        if model_review:
            for evidence_id in model_review.evidence_ids:
                store.get(evidence_id)
            if model_review.status == "PASS" and not model_review.evidence_ids:
                _error("INVALID_VERIFIED_CASE: saved semantic PASS has no evidence")
        tolerance = Decimal(saved["calculation"]["metadata"]["tolerance"])
        if not tolerance.is_finite() or not 0 <= tolerance <= Decimal("1e12"):
            _error("INVALID_VERIFIED_CASE: tolerance")
        calculation = execute_check(check, store, tolerance)
        if calculation != saved["calculation"]:
            _error("DETERMINISTIC_REPLAY_MISMATCH_REQUIRES_FRESH_AUDIT")
        plan, verified_calculation = to_plan(check), None
        if check.currency is None and any(spec.unit == "money" for spec in specs) and _is_accepted(saved):
            _error("INVALID_VERIFIED_CASE: accepted financial check lacks currency")
        if plan is not None and calculation["status"] != "CANNOT_VERIFY":
            verified_calculation = execute(plan, store, tolerance)
            if (verified_calculation != saved.get("verified_calculation")
                    or calculation["status"] != verified_calculation["status"]
                    or any(Decimal(calculation[key]) != Decimal(verified_calculation[key])
                           for key in ("expected", "reported", "difference"))):
                _error("DETERMINISTIC_REPLAY_MISMATCH_REQUIRES_FRESH_AUDIT")
            review = challenge(plan, verified_calculation, store, tolerance, semantic_review=model_review)
        elif saved.get("verified_calculation") is not None:
            _error("INVALID_VERIFIED_CASE: inconsistent verifier plan binding")
        elif calculation["status"] == "CANNOT_VERIFY":
            review = Challenge(status="INSUFFICIENT_EVIDENCE", checks={"deterministic_execution": False},
                               reasons=calculation["reasons"])
        elif check.source == "deterministic" and check.operation in {"EQUAL", "NOT_EQUAL", "DATE_BEFORE", "DATE_AFTER"}:
            review = Challenge(status="PASS", checks={"source_consistency": True}, reasons=[])
        elif model_review and model_review.status == "PASS":
            review = Challenge(status="PASS", checks={"saved_semantic_review": True}, reasons=[])
        else:
            review = Challenge(status="INSUFFICIENT_EVIDENCE", checks={"semantic_support": False},
                               reasons=["The saved case has no accepted semantic decision for this relationship."])
        if model_review and model_review.status != "PASS":
            review = Challenge(status=model_review.status, checks=review.checks,
                               reasons=review.reasons + model_review.reasons)
        originally_accepted = _is_accepted(saved)
        if originally_accepted and (review.status != "PASS" or saved["status"] != calculation["status"]):
            _error("DETERMINISTIC_REPLAY_MISMATCH_REQUIRES_FRESH_AUDIT")
        status = calculation["status"] if originally_accepted else saved["status"]
        # Retain prior abstentions/conflicts; replay cannot promote them using
        # a new semantic interpretation or an omitted conflict review.
        if not originally_accepted:
            review = previous_review
        proposal = None
        if originally_accepted and status == "DISCREPANCY" and plan is not None and verified_calculation:
            try:
                proposal = propose_patch(plan, verified_calculation, store, review)
            except ValueError:
                # A verified discrepancy can lack a supported Excel correction
                # (for example, precision beyond Excel's bound). The saved audit
                # must also have withheld that proposal for replay to continue.
                proposal = None
        serialized = proposal.model_dump(mode="json") if proposal else None
        if serialized != saved.get("patch_proposal"):
            _error("INVALID_VERIFIED_CASE: patch is not bound to the saved verified calculation")
        if proposal is not None:
            proposals.append(proposal)
        ids = list(dict.fromkeys(calculation["evidence_ids"] + (model_review.evidence_ids if model_review else [])))
        refreshed.append({"check_id": check.check_id, "title": check.title, "entity_id": check.entity_id,
                          "status": status, "currency": check.currency, "check": check.model_dump(mode="json"),
                          "calculation": calculation, "verified_calculation": verified_calculation,
                          "red_team": review.model_dump(mode="json"),
                          "model_review": model_review.model_dump(mode="json") if model_review else None,
                          "model_review_origin": "SAVED_PRIOR_REVIEW_NO_FRESH_MODEL" if model_review else None,
                          "sources": [store.citation(evidence_id) for evidence_id in ids],
                          "patch_proposal": serialized})
    if not any(_is_accepted(finding) for finding in refreshed):
        _error("NO_ACCEPTED_REPLAY_REQUIRES_FRESH_AUDIT")
    return refreshed, proposals


def _envelope(case_id: str, **payload) -> dict:
    return {"schema_id": SCHEMA_ID, "schema_version": SCHEMA_VERSION, "case_id": case_id, **payload}


def save_case(result: dict, store: EvidenceStore, case_id: str,
              cases_root: Path = Path("outputs/cases")) -> Path:
    """Persist a complete successful LIVE_MODEL audit as one new immutable case."""
    _bound_case_id(case_id)
    if result.get("mode") != "LIVE_MODEL":
        _error("Only successful LIVE_MODEL audits can create verified replay cases")
    if result.get("ingestion_errors") or result.get("originals_unchanged") is not True:
        _error("INCOMPLETE_SOURCE_AUDIT_REQUIRES_FRESH_AUDIT")
    store = EvidenceStore(store.documents)
    _complete_store(store)
    if (result.get("file_count") != len(store.documents) or result.get("normalized_count") != len(store.documents)
            or result.get("evidence_count") != len(store.refs)):
        _error("INVALID_VERIFIED_CASE: source counts")
    _successful_live_trace(result)
    source_hashes = _source_records(store)
    findings = deepcopy([finding for finding in result["findings"] if _is_accepted(finding)])
    unverified = deepcopy([finding for finding in result["findings"] if not _is_accepted(finding)])
    if not findings:
        _error("NO_ACCEPTED_REPLAY_REQUIRES_FRESH_AUDIT")
    _review_trace_binding(findings, result)
    refreshed, _ = _verify_findings(findings, store)
    accepted_ids = [finding["check_id"] for finding in refreshed if _is_accepted(finding)]
    plan_hashes = {finding["check_id"]: _sha(_json_bytes(finding["check"])) for finding in findings}
    safe_call_keys = {"stage", "provider", "model", "response_id", "duration_ms", "status", "usage"}
    trace = {key: deepcopy(result.get(key)) for key in ("runtime_model", "gemini_call_count", "timings", "task_trace", "peak_concurrency")}
    trace["model_calls"] = [{key: deepcopy(value) for key, value in call.items() if key in safe_call_keys}
                            for call in result["model_calls"]]
    summary = {key: deepcopy(result.get(key)) for key in (
        "instruction", "created_at", "file_count", "normalized_count", "evidence_count", "cannot_verify",
        "diagnostics", "repair_attempted", "limitations")}
    summary["prior_unverified_findings"] = unverified
    records = lambda keys: [{"check_id": finding["check_id"], "plan_hash": plan_hashes[finding["check_id"]],
                             **{key: deepcopy(finding.get(key)) for key in keys}} for finding in findings]
    payloads = {
        "normalized_evidence.json": _envelope(case_id, documents=[doc.model_dump(mode="json") for doc in store.documents]),
        "verification_plan.json": _envelope(case_id, checks=[finding["check"] for finding in findings]),
        "verifier_result.json": _envelope(case_id, findings=records(("status", "calculation", "verified_calculation")), summary=summary),
        "red_team_result.json": _envelope(case_id, reviews=records(("red_team", "model_review"))),
        "patch_proposal.json": _envelope(case_id, proposals=records(("patch_proposal",))),
        "trace.json": _envelope(case_id, trace=trace),
        "source_hashes.json": _envelope(case_id, sources=source_hashes),
    }
    encoded = {name: _json_bytes(value) for name, value in payloads.items()}
    manifest = _envelope(case_id, status="VERIFIED_LIVE_CASE", source_mode="LIVE_MODEL",
                         created_at=result["created_at"], saved_at=datetime.now(timezone.utc).isoformat(),
                         check_count=len(findings), accepted_count=len(accepted_ids),
                         finding_count=sum(finding["status"] == "DISCREPANCY" for finding in findings),
                         accepted_check_ids=accepted_ids,
                         document_count=len(store.documents), evidence_count=len(store.refs),
                         plan_hashes=plan_hashes, files={name: _sha(data) for name, data in encoded.items()})
    encoded["manifest.json"] = _json_bytes(manifest)
    if max(map(len, encoded.values())) > MAX_CASE_FILE_BYTES or sum(map(len, encoded.values())) > MAX_CASE_TOTAL_BYTES:
        _error("Verified case exceeds the supported saved-file size bounds")
    cases_root = Path(cases_root).resolve()
    case_dir = cases_root / case_id
    cases_root.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(case_dir):
        _error("Case already exists; select a new case ID")
    created, published = False, []
    try:
        with tempfile.TemporaryDirectory(prefix=".saving-case-", dir=cases_root) as temporary:
            for name, data in encoded.items():
                (Path(temporary) / name).write_bytes(data)
            _source_records(store)
            case_dir.mkdir()  # Exclusive creation: never replace another case directory.
            created = True
            # Publish the manifest last; a interrupted incomplete save is never loadable.
            for name in [name for name in CASE_FILES if name != "manifest.json"] + ["manifest.json"]:
                os.link(Path(temporary) / name, case_dir / name)
                published.append(case_dir / name)
            _source_records(store)
        return case_dir
    except Exception:
        for path in published:
            path.unlink(missing_ok=True)
        if created:
            case_dir.rmdir()
        raise


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _error("INVALID_VERIFIED_CASE: duplicate JSON key")
        result[key] = value
    return result


def _read_json(path: Path) -> tuple[dict, bytes]:
    if path.is_symlink() or not path.is_file():
        _error(f"INVALID_VERIFIED_CASE: missing or unsafe {path.name}")
    with path.open("rb") as handle:
        data = handle.read(MAX_CASE_FILE_BYTES + 1)
    if len(data) > MAX_CASE_FILE_BYTES:
        _error("INVALID_VERIFIED_CASE: saved file exceeds the size bound")
    try:
        value = json.loads(data, object_pairs_hook=_no_duplicate_keys,
                           parse_constant=lambda _: _error("INVALID_VERIFIED_CASE: nonfinite JSON"))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        _error(f"INVALID_VERIFIED_CASE: malformed {path.name}")
    if not isinstance(value, dict):
        _error("INVALID_VERIFIED_CASE: JSON envelope")
    return value, data


def _load_case(case_dir: Path) -> tuple[dict, dict, EvidenceStore, list[dict]]:
    case_dir = Path(case_dir)
    if case_dir.is_symlink() or not case_dir.is_dir():
        _error("INVALID_VERIFIED_CASE: missing or unsafe case directory")
    if {path.name for path in case_dir.iterdir()} != set(CASE_FILES):
        _error("INVALID_VERIFIED_CASE: case must contain exactly the eight required files")
    manifest, raw = _read_json(case_dir / "manifest.json")
    case_id = manifest.get("case_id")
    _bound_case_id(case_id)
    if (case_id != case_dir.name or manifest.get("source_mode") != "LIVE_MODEL"
            or manifest.get("status") != "VERIFIED_LIVE_CASE"
            or not isinstance(manifest.get("files"), dict)
            or set(manifest["files"]) != set(CASE_FILES) - {"manifest.json"}):
        _error("INVALID_VERIFIED_CASE: manifest")
    payloads, total = {"manifest.json": manifest}, len(raw)
    for name, digest in manifest["files"].items():
        value, data = _read_json(case_dir / name)
        total += len(data)
        if total > MAX_CASE_TOTAL_BYTES or not isinstance(digest, str) or _sha(data) != digest:
            _error("INVALID_VERIFIED_CASE: file digest or total size")
        payloads[name] = value
    for value in payloads.values():
        if (value.get("schema_id") != SCHEMA_ID or value.get("schema_version") != SCHEMA_VERSION
                or value.get("case_id") != case_id):
            _error("INVALID_VERIFIED_CASE: schema or cross-file case identity")
    documents = payloads["normalized_evidence.json"].get("documents")
    if not isinstance(documents, list) or not 1 <= len(documents) <= 32:
        _error("INVALID_VERIFIED_CASE: normalized documents")
    store = EvidenceStore([NormalizedDocument.model_validate(doc) for doc in documents])
    _complete_store(store)
    records = _source_records(store)
    if records != payloads["source_hashes.json"].get("sources"):
        _error("INVALID_VERIFIED_CASE: source hash bindings")
    if (manifest.get("document_count") != len(store.documents) or manifest.get("evidence_count") != len(store.refs)):
        _error("INVALID_VERIFIED_CASE: evidence counts")
    trace = payloads["trace.json"]["trace"]
    _successful_live_trace(trace)
    checks = payloads["verification_plan.json"].get("checks")
    if not isinstance(checks, list) or not 1 <= len(checks) <= MAX_CHECKS or manifest.get("check_count") != len(checks):
        _error("INVALID_VERIFIED_CASE: check counts")
    parsed = [FastCheck.model_validate(check) for check in checks]
    check_ids = [check.check_id for check in parsed]
    plan_hashes = {check.check_id: _sha(_json_bytes(check.model_dump(mode="json"))) for check in parsed}
    if len(set(check_ids)) != len(check_ids) or plan_hashes != manifest.get("plan_hashes"):
        _error("INVALID_VERIFIED_CASE: verification plan bindings")
    combined = {check.check_id: {"check_id": check.check_id, "check": check.model_dump(mode="json")} for check in parsed}
    for filename, key, fields in (
        ("verifier_result.json", "findings", ("status", "calculation", "verified_calculation")),
        ("red_team_result.json", "reviews", ("red_team", "model_review")),
        ("patch_proposal.json", "proposals", ("patch_proposal",)),
    ):
        items = payloads[filename].get(key)
        if not isinstance(items, list) or len(items) != len(check_ids):
            _error("INVALID_VERIFIED_CASE: check record count")
        seen = set()
        for item in items:
            check_id = item.get("check_id")
            if check_id not in combined or check_id in seen or item.get("plan_hash") != plan_hashes[check_id]:
                _error("INVALID_VERIFIED_CASE: cross-file plan binding")
            seen.add(check_id)
            combined[check_id].update({field: item[field] for field in fields})
    findings = list(combined.values())
    _review_trace_binding(findings, trace)
    accepted = [finding["check_id"] for finding in findings if _is_accepted(finding)]
    if (not accepted or accepted != manifest.get("accepted_check_ids")
            or len(accepted) != len(findings)
            or manifest.get("accepted_count") != len(accepted)
            or manifest.get("finding_count") != sum(finding["status"] == "DISCREPANCY" for finding in findings)):
        _error("INVALID_VERIFIED_CASE: accepted finding binding")
    return manifest, payloads, store, findings


def list_cases(cases_root: Path = Path("outputs/cases")) -> list[dict]:
    """List case metadata and current cache/source integrity without model calls."""
    root = Path(cases_root)
    if not root.exists():
        return []
    if not root.is_dir():
        _error("Cases root must be a directory")
    directories = sorted(path for path in root.iterdir() if path.is_dir() and not path.name.startswith("."))
    if len(directories) > 1000:
        _error("Case listing exceeds the 1,000-case bound")
    result = []
    for path in directories:
        entry = {"case_id": path.name, "status": "INVALID_CASE", "findings": 0, "created_at": None, "path": str(path.resolve())}
        try:
            manifest, _, _, _ = _load_case(path)
            entry.update(status="VERIFIED", findings=manifest["finding_count"], created_at=manifest["created_at"])
        except (ValueError, ValidationError, KeyError, TypeError, OSError) as exc:
            message = str(exc)
            if message.startswith("SOURCE_CHANGED_REQUIRES_FRESH_AUDIT") or message.startswith("SOURCE_MISSING_REQUIRES_FRESH_AUDIT"):
                entry["status"] = message
        result.append(entry)
    return result


def replay_case(case_dir: Path, *, output_dir: Path, apply_verified_fixes: bool = False, progress=None) -> dict:
    """Recalculate a saved live case with zero model calls and optional new copies."""
    started = perf_counter()
    emit = progress or (lambda message: None)
    output = Path(output_dir).resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        _error("Replay output directory must be new or empty")
    if output.is_relative_to(Path(case_dir).resolve()):
        _error("Replay output must be outside the saved case")
    manifest, payloads, store, findings = _load_case(case_dir)
    if any(output.is_relative_to(Path(doc.document.original_storage_key).resolve().parent) for doc in store.documents):
        _error("Replay output must be outside source directories")
    timings = {"evidence_integrity_seconds": perf_counter() - started}
    emit("MODE: VERIFIED_REPLAY")
    emit("Gemini calls: 0")
    emit("Evidence integrity: PASS")
    phase = perf_counter()
    refreshed, proposals = _verify_findings(findings, store)
    _source_records(store)
    timings["deterministic_verification_seconds"] = perf_counter() - phase
    emit("Deterministic verification: PASS")
    phase = perf_counter()
    patches = apply_patches(proposals, store, output) if apply_verified_fixes else []
    _source_records(store)
    timings["patch_seconds"] = perf_counter() - phase
    summary = payloads["verifier_result.json"]["summary"]
    limitations = list(summary.get("limitations") or [])
    limitations += ["VERIFIED_REPLAY reruns deterministic verification, not live model discovery.",
                    "Semantic reviews shown are saved prior Gemini decisions; no new model review was requested.",
                    "Prior unresolved findings remain historical context and are not promoted or repaired by replay.",
                    "Local case hashes detect corruption but are not a provider signature or tamper-proof attestation."]
    timings["total_seconds"] = perf_counter() - started
    result = {"schema_version": 1, "mode": "VERIFIED_REPLAY", "runtime_model": None,
              "prior_runtime_model": payloads["trace.json"]["trace"]["runtime_model"],
              "created_at": datetime.now(timezone.utc).isoformat(), "instruction": summary.get("instruction", ""),
              "replay_of": manifest["case_id"], "source_audit_created_at": manifest["created_at"],
              "file_count": len(store.documents), "normalized_count": len(store.documents), "evidence_count": len(store.refs),
              "findings": refreshed, "cannot_verify": summary.get("cannot_verify") or [],
              "prior_unverified_findings": summary.get("prior_unverified_findings") or [],
              "diagnostics": summary.get("diagnostics") or [], "ingestion_errors": [], "patches": patches,
              "originals_unchanged": True, "repair_attempted": False, "model_calls": [], "gemini_call_count": 0,
              "parallel_check_count": len(refreshed), "peak_concurrency": {"verification": 1},
              "task_trace": [{"phase": "replay", "task": "deterministic_verification",
                              "start_seconds": timings["evidence_integrity_seconds"],
                              "end_seconds": timings["evidence_integrity_seconds"] + timings["deterministic_verification_seconds"]}],
              "timings": timings, "evidence_integrity": "PASS", "deterministic_verification": "PASS",
              "coverage": {status: sum(finding["status"] == status for finding in refreshed)
                           for status in ("MATCH", "DISCREPANCY", "CANNOT_VERIFY", "REVIEW_REQUIRED")},
              "limitations": limitations}
    return result
