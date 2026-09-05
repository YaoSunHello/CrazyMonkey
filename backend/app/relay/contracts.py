from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from app.atlas.models import ReviewSnapshot as AtlasReviewSnapshot

from .models import OutputSnapshotView


class SnapshotContractError(ValueError):
    pass


_PRIVATE_KEYS = {
    "chain_of_thought",
    "chainofthought",
    "private_reasoning",
    "hidden_reasoning",
    "system_prompt",
    "developer_prompt",
    "model_prompt",
    "raw_prompt",
}


def reject_private_reasoning(value: Any, path: str = "snapshot") -> None:
    """Fail closed when payloads try to place private prompts/reasoning in exports."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_").replace(" ", "_")
            if normalized in _PRIVATE_KEYS:
                raise SnapshotContractError(f"private field is not exportable: {path}.{key}")
            reject_private_reasoning(child, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            reject_private_reasoning(child, f"{path}[{index}]")


def adapt_review_snapshot(payload: Mapping[str, Any], route_run_id: str | None = None) -> OutputSnapshotView:
    """Adapt one upstream payload into RELAY's non-authoritative output view.

    Canonical snake_case snapshots pass through with only harmless aliases filled.
    Beacon's current camelCase ReviewResult is mapped explicitly for the demo.
    """

    raw = dict(payload)
    reject_private_reasoning(raw)
    if _looks_like_atlas_snapshot(raw):
        normalized = _adapt_atlas_snapshot(raw)
    elif _looks_like_beacon_review(raw):
        normalized = _adapt_beacon_review(raw)
    else:
        schema_version = raw.get("schema_version")
        if schema_version != "relay-output-snapshot-v1":
            raise SnapshotContractError(
                "unsupported snapshot schema_version; add an explicit adapter before exporting"
            )
        normalized = _adapt_canonical_snapshot(raw)

    if route_run_id is not None:
        payload_run_id = normalized.get("run_id")
        if payload_run_id and payload_run_id != route_run_id:
            raise SnapshotContractError(
                f"run_id mismatch: route={route_run_id!r}, payload={payload_run_id!r}"
            )
        normalized["run_id"] = route_run_id

    try:
        return OutputSnapshotView.model_validate(normalized)
    except ValidationError as exc:
        raise SnapshotContractError(str(exc)) from exc


def _looks_like_atlas_snapshot(raw: Mapping[str, Any]) -> bool:
    return raw.get("contract_version") == 1 and "frozen_at" in raw


def _adapt_atlas_snapshot(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Project Atlas's strict ReviewSnapshot v1 into RELAY's output-only view."""

    try:
        atlas = AtlasReviewSnapshot.model_validate(raw)
    except ValidationError as exc:
        raise SnapshotContractError(f"invalid Atlas ReviewSnapshot v1: {exc}") from exc

    _validate_atlas_references(atlas)
    documents = {document.document_id: document for document in atlas.source_documents}
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for finding in atlas.findings:
        for source_ref in finding.source_refs:
            document = documents.get(source_ref.document_id)
            if document is None:
                raise SnapshotContractError(
                    f"Atlas evidence {source_ref.evidence_id!r} references unknown document "
                    f"{source_ref.document_id!r}"
                )
            if source_ref.document_hash != document.document_hash:
                raise SnapshotContractError(
                    f"Atlas evidence {source_ref.evidence_id!r} document hash does not match "
                    f"{source_ref.document_id!r}"
                )
            normalized_evidence = {
                "evidence_id": source_ref.evidence_id,
                "document_id": source_ref.document_id,
                "filename": document.filename,
                "document_role": document.role,
                "source_kind": source_ref.kind,
                "locator": source_ref.locator,
                "quoted_text": source_ref.quote,
                "value": source_ref.original_value,
                "context": _atlas_evidence_context(source_ref),
            }
            previous = evidence_by_id.get(source_ref.evidence_id)
            if previous is not None and previous != normalized_evidence:
                raise SnapshotContractError(
                    f"Atlas evidence id {source_ref.evidence_id!r} is reused with different content"
                )
            evidence_by_id[source_ref.evidence_id] = normalized_evidence

    findings_by_calculation = {
        finding.calculation_id: finding
        for finding in atlas.findings
        if finding.calculation_id is not None
    }
    calculations = []
    for calculation in atlas.calculations:
        finding = findings_by_calculation.get(calculation.calculation_id)
        if finding is None:
            raise SnapshotContractError(
                f"Atlas calculation {calculation.calculation_id!r} is not referenced by a finding"
            )
        if finding.investor_id != calculation.investor_id:
            raise SnapshotContractError(
                f"Atlas calculation {calculation.calculation_id!r} investor does not match its finding"
            )
        calculations.append(
            {
                "calculation_id": calculation.calculation_id,
                "finding_id": finding.finding_id,
                "investor_id": calculation.investor_id,
                "fee_base": _optional_float(calculation.fee_base),
                "annual_rate_fraction": _optional_float(calculation.annual_rate),
                "period_factor": _optional_float(calculation.period_factor),
                "expected_value": _optional_float(calculation.expected_amount),
                "reported_value": _optional_float(calculation.reported_amount),
                "difference": _optional_float(calculation.difference),
                "currency": calculation.currency,
                "expression": calculation.formula_description,
            }
        )

    known_evidence = set(evidence_by_id)
    terms = []
    for rule in atlas.rules:
        rule_evidence = _ordered_unique(
            [
                *rule.identity_evidence_ids,
                *(item for values in rule.input_evidence.values() for item in values),
            ]
        )
        missing_evidence = [item for item in rule_evidence if item not in known_evidence]
        if missing_evidence:
            raise SnapshotContractError(
                f"Atlas rule {rule.rule_id!r} references evidence absent from finding source_refs: "
                + ", ".join(missing_evidence)
            )
        terms.append(
            {
                "investor_id": rule.investor_id,
                "term": "Management fee",
                "default_rate_fraction": _optional_float(rule.default_annual_rate),
                "override_rate_fraction": _optional_float(rule.candidate_override_rate),
                "applicable_rate_fraction": _optional_float(rule.applicable_annual_rate),
                "effective_from": rule.effective_from.isoformat() if rule.effective_from else None,
                "effective_to": rule.effective_to.isoformat() if rule.effective_to else None,
                "fee_base": _optional_float(rule.fee_base),
                "currency": rule.currency or "GBP",
                "evidence_ids": rule_evidence,
                "applicability_state": rule.applicability_state,
            }
        )

    for finding in atlas.findings:
        missing_evidence = [item for item in finding.evidence_ids if item not in known_evidence]
        if missing_evidence:
            raise SnapshotContractError(
                f"Atlas finding {finding.finding_id!r} references evidence absent from source_refs: "
                + ", ".join(missing_evidence)
            )

    finding_by_concern: dict[str, str] = {}
    finding_by_verifier: dict[str, str] = {}
    for finding in atlas.findings:
        for concern_id in finding.challenger_concern_ids:
            finding_by_concern[concern_id] = finding.finding_id
        finding_by_verifier[finding.verifier_result_id] = finding.finding_id

    unresolved = []
    for finding in atlas.findings:
        if finding.status not in {"CANNOT_VERIFY", "UNSUPPORTED"}:
            continue
        unresolved.append(
            {
                "issue_id": f"atlas-unresolved-{finding.finding_id}",
                "finding_id": finding.finding_id,
                "severity": "REVIEW_REQUIRED",
                "summary": finding.actionable_next_step,
                "missing_evidence": finding.unresolved_questions,
            }
        )
    unresolved.extend(
        {
            "issue_id": f"atlas-unresolved-global-{index:03d}",
            "finding_id": None,
            "severity": "REVIEW_REQUIRED",
            "summary": item,
            "missing_evidence": [],
        }
        for index, item in enumerate(atlas.unresolved_items, start=1)
    )

    upstream_mode = str(atlas.mode)
    output_mode = "SYNTHETIC_DEMO" if upstream_mode == "SYNTHETIC_DEMO" else "LIVE"
    return {
        "run_id": atlas.run_id,
        "version": atlas.version,
        "fund_name": atlas.fund_name,
        "reporting_period": atlas.reporting_period,
        "mode": output_mode,
        "timestamp": atlas.frozen_at,
        "source": "ATLAS_REVIEW_SNAPSHOT_V1",
        "source_notice": f"Validated Atlas ReviewSnapshot v1; upstream mode: {upstream_mode}.",
        "source_documents": [
            {
                "document_id": document.document_id,
                "filename": document.filename,
                "role": document.role,
                "sha256": document.document_hash,
                "recognition": document.extraction_status,
                "supplied": True,
            }
            for document in atlas.source_documents
        ],
        "coverage": {
            "scope": "Management-fee checks only",
            "checks_expected": len(atlas.findings),
            "checks_completed": len(atlas.findings),
            "investor_ids": _ordered_unique(
                [finding.investor_id for finding in atlas.findings]
            ),
        },
        "findings": [
            {
                "finding_id": finding.finding_id,
                "investor_id": finding.investor_id,
                "check_type": "Management fee",
                "administrator_value": _optional_float(finding.reported_value),
                "expected_value": _optional_float(finding.expected_value),
                "difference": _optional_float(finding.difference),
                "difference_convention": "ATLAS_REPORTED_MINUS_EXPECTED",
                "variance_direction": _variance_direction(
                    _optional_float(finding.reported_value),
                    _optional_float(finding.expected_value),
                ),
                "currency": finding.currency or "GBP",
                "computational_status": finding.status,
                "human_review_status": finding.human_review_state,
                "explanation": finding.explanation,
                "calculation_id": finding.calculation_id,
                "evidence_ids": finding.evidence_ids,
            }
            for finding in atlas.findings
        ],
        "investor_terms": terms,
        "calculations": calculations,
        "evidence_references": list(evidence_by_id.values()),
        "challenger_concerns": [
            {
                "concern_id": concern.concern_id,
                "finding_id": finding_by_concern.get(concern.concern_id),
                "summary": _atlas_concern_summary(concern),
                "status": concern.state,
            }
            for concern in atlas.challenger_concerns
        ],
        "verifier_results": [
            {
                "verifier_result_id": result.verifier_result_id,
                "finding_id": finding_by_verifier.get(result.verifier_result_id),
                "status": result.status,
                "statement": _atlas_verifier_statement(result),
            }
            for result in atlas.verifier_results
        ],
        "human_review_decisions": [
            {
                "finding_id": finding.finding_id,
                "state": finding.human_review_state,
                "reviewer_label": finding.reviewer_label,
                "timestamp": finding.reviewed_at,
                "notes": finding.reviewer_note,
            }
            for finding in atlas.findings
        ],
        "audit_trail": [
            {
                "timestamp": event.timestamp,
                "run_version": event.run_version,
                "finding_id": event.finding_id,
                "reviewer": event.reviewer_label,
                "action": event.action,
                "previous_state": event.previous_review_state,
                "new_state": event.new_review_state,
                "note": event.note,
            }
            for event in atlas.audit_trail
        ],
        "unresolved_issues": unresolved,
        "limitations": atlas.limitations,
    }


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _validate_atlas_references(atlas: AtlasReviewSnapshot) -> None:
    collections = {
        "document": [item.document_id for item in atlas.source_documents],
        "rule": [item.rule_id for item in atlas.rules],
        "calculation": [item.calculation_id for item in atlas.calculations],
        "concern": [item.concern_id for item in atlas.challenger_concerns],
        "verifier result": [item.verifier_result_id for item in atlas.verifier_results],
        "finding": [item.finding_id for item in atlas.findings],
    }
    for label, identifiers in collections.items():
        if len(identifiers) != len(set(identifiers)):
            raise SnapshotContractError(f"Atlas snapshot contains duplicate {label} ids")

    rules = {item.rule_id: item for item in atlas.rules}
    calculations = {item.calculation_id: item for item in atlas.calculations}
    concerns = {item.concern_id: item for item in atlas.challenger_concerns}
    verifier_results = {
        item.verifier_result_id: item for item in atlas.verifier_results
    }
    finding_ids = {item.finding_id for item in atlas.findings}

    for calculation in atlas.calculations:
        rule = rules.get(calculation.rule_id)
        if rule is None:
            raise SnapshotContractError(
                f"Atlas calculation {calculation.calculation_id!r} references an unknown rule"
            )
        if (
            rule.rule_version != calculation.rule_version
            or rule.investor_id != calculation.investor_id
        ):
            raise SnapshotContractError(
                f"Atlas calculation {calculation.calculation_id!r} does not match its rule identity"
            )

    used_calculations: set[str] = set()
    used_verifiers: set[str] = set()
    for finding in atlas.findings:
        source_ref_ids = [item.evidence_id for item in finding.source_refs]
        if len(source_ref_ids) != len(set(source_ref_ids)):
            raise SnapshotContractError(
                f"Atlas finding {finding.finding_id!r} contains duplicate source reference ids"
            )
        if set(finding.evidence_ids) != set(source_ref_ids):
            raise SnapshotContractError(
                f"Atlas finding {finding.finding_id!r} evidence_ids do not match source_refs"
            )
        if finding.calculation_id is not None:
            calculation = calculations.get(finding.calculation_id)
            if calculation is None:
                raise SnapshotContractError(
                    f"Atlas finding {finding.finding_id!r} references an unknown calculation"
                )
            if calculation.investor_id != finding.investor_id:
                raise SnapshotContractError(
                    f"Atlas finding {finding.finding_id!r} calculation investor does not match"
                )
            if finding.calculation_id in used_calculations:
                raise SnapshotContractError(
                    f"Atlas calculation {finding.calculation_id!r} is referenced by multiple findings"
                )
            used_calculations.add(finding.calculation_id)
        for concern_id in finding.challenger_concern_ids:
            concern = concerns.get(concern_id)
            if concern is None:
                raise SnapshotContractError(
                    f"Atlas finding {finding.finding_id!r} references an unknown concern"
                )
            if concern.investor_id != finding.investor_id:
                raise SnapshotContractError(
                    f"Atlas finding {finding.finding_id!r} concern investor does not match"
                )
        verifier = verifier_results.get(finding.verifier_result_id)
        if verifier is None:
            raise SnapshotContractError(
                f"Atlas finding {finding.finding_id!r} references an unknown verifier result"
            )
        if verifier.investor_id != finding.investor_id:
            raise SnapshotContractError(
                f"Atlas finding {finding.finding_id!r} verifier investor does not match"
            )
        if finding.verifier_result_id in used_verifiers:
            raise SnapshotContractError(
                f"Atlas verifier result {finding.verifier_result_id!r} is used by multiple findings"
            )
        used_verifiers.add(finding.verifier_result_id)

    for event in atlas.audit_trail:
        if event.run_id != atlas.run_id or event.run_version != atlas.version:
            raise SnapshotContractError("Atlas audit event identity does not match its snapshot")
        if event.finding_id not in finding_ids:
            raise SnapshotContractError("Atlas audit event references an unknown finding")


def _ordered_unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _atlas_evidence_context(source_ref: Any) -> str | None:
    details = []
    if source_ref.normalized_value is not None:
        details.append(f"Normalized value: {source_ref.normalized_value}")
    if source_ref.formula is not None:
        details.append(f"Source formula: {source_ref.formula}")
    if source_ref.cached_value is not None:
        details.append(
            f"Cached value ({source_ref.cache_status}): {source_ref.cached_value}"
        )
    return "; ".join(details) or None


def _atlas_concern_summary(concern: Any) -> str:
    parts = [concern.suspected_problem, f"Required resolution: {concern.required_resolution}"]
    if concern.missing_fact:
        parts.append(f"Missing fact: {concern.missing_fact}")
    return " ".join(parts)


def _atlas_verifier_statement(result: Any) -> str:
    checks = "; ".join(
        f"{check.code}: {'PASS' if check.passed else 'FAIL'} - {check.explanation}"
        for check in result.checks
    )
    return result.explanation if not checks else f"{result.explanation} Checks: {checks}"


def _looks_like_beacon_review(raw: Mapping[str, Any]) -> bool:
    return "periodLabel" in raw or "fundName" in raw or any(
        isinstance(item, Mapping) and "checkName" in item for item in raw.get("findings", [])
    )


def _adapt_canonical_snapshot(raw: dict[str, Any]) -> dict[str, Any]:
    aliases = {
        "id": "run_id",
        "review_version": "version",
        "period": "reporting_period",
        "generated_at": "timestamp",
        "documents": "source_documents",
        "evidence": "evidence_references",
        "human_reviews": "human_review_decisions",
        "unresolved": "unresolved_issues",
    }
    for source, target in aliases.items():
        if source not in raw:
            continue
        if target in raw and raw[target] != raw[source]:
            raise SnapshotContractError(
                f"conflicting alias values for {source!r} and {target!r}"
            )
        if target not in raw:
            raw[target] = raw[source]
        raw.pop(source, None)

    if "timestamp" not in raw:
        raise SnapshotContractError("canonical snapshot must include a stable timestamp")
    if "coverage" not in raw:
        findings = raw.get("findings", [])
        raw["coverage"] = {
            "scope": "Management-fee checks only",
            "checks_completed": len(findings),
            "investor_ids": [item.get("investor_id") for item in findings if isinstance(item, Mapping)],
        }
    return raw


def _adapt_beacon_review(raw: Mapping[str, Any]) -> dict[str, Any]:
    source = str(raw.get("source", ""))
    if source == "DEVELOPMENT_FIXTURE":
        mode = "SYNTHETIC_DEMO"
    elif raw.get("mode"):
        mode = str(raw["mode"]).upper().replace(" ", "_")
    else:
        raise SnapshotContractError(
            "Beacon/Atlas review payload must include explicit mode; source=ATLAS is not proof of live data"
        )

    findings_in = list(raw.get("findings", []))
    if raw.get("version") is None:
        raise SnapshotContractError(
            "review-level version is required; finding versions cannot safely identify a frozen review"
        )
    version = int(raw["version"])
    if not raw.get("createdAt") and not raw.get("timestamp"):
        raise SnapshotContractError("review payload must include a stable createdAt/timestamp")
    timestamp = str(raw.get("createdAt") or raw.get("timestamp"))

    evidence_by_id: dict[str, dict[str, Any]] = {}
    calculations: list[dict[str, Any]] = []
    investor_terms: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    concerns: list[dict[str, Any]] = []
    verifier_results: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for item in findings_in:
        finding_id = str(item["id"])
        investor_id = str(item["investorId"])
        admin_amount, currency = _money(item.get("administratorValue"))
        expected_amount, expected_currency = _money(item.get("expectedValue"))
        difference_amount, difference_currency = _money(item.get("difference"))
        currency = currency or expected_currency or difference_currency or "GBP"
        calculation_id = None

        calculation = item.get("calculation")
        if isinstance(calculation, Mapping):
            calculation_id = f"calc-{finding_id}"
            parsed_inputs = _parse_calculation_inputs(calculation.get("inputs", []))
            calculations.append(
                {
                    "calculation_id": calculation_id,
                    "finding_id": finding_id,
                    "investor_id": investor_id,
                    "fee_base": parsed_inputs.get("fee_base"),
                    "annual_rate_fraction": parsed_inputs.get("annual_rate_fraction"),
                    "period_factor": parsed_inputs.get("period_factor"),
                    "expected_value": expected_amount,
                    "reported_value": admin_amount,
                    "difference": difference_amount,
                    "currency": currency,
                    "expression": calculation.get("expression"),
                }
            )

        evidence_ids: list[str] = []
        for evidence in item.get("evidence", []):
            evidence_id = str(evidence["id"])
            evidence_ids.append(evidence_id)
            normalized_evidence = {
                "evidence_id": evidence_id,
                "document_id": str(evidence.get("documentId", "unknown-document")),
                "filename": str(evidence.get("filename", "Unknown source")),
                "document_role": str(evidence.get("documentRole", "SUPPORTING")),
                "source_kind": str(evidence.get("sourceKind", "TEXT")),
                "locator": str(evidence.get("locator", "Not supplied")),
                "quoted_text": evidence.get("quote"),
                "value": evidence.get("value"),
                "context": evidence.get("context"),
            }
            if evidence_id in evidence_by_id and evidence_by_id[evidence_id] != normalized_evidence:
                raise SnapshotContractError(
                    f"evidence id {evidence_id!r} is reused with different content"
                )
            evidence_by_id[evidence_id] = normalized_evidence

        review_state = str(item.get("humanReviewState", "UNREVIEWED"))
        notes = list(item.get("notes", []))
        latest_note = notes[-1] if notes else {}
        decisions.append(
            {
                "finding_id": finding_id,
                "state": review_state,
                "reviewer_label": latest_note.get("author"),
                "timestamp": latest_note.get("createdAt"),
                "notes": latest_note.get("body"),
            }
        )
        for note in notes:
            audit.append(
                {
                    "timestamp": note.get("createdAt", timestamp),
                    "run_version": version,
                    "finding_id": finding_id,
                    "reviewer": note.get("author"),
                    "action": "HUMAN_REVIEW_NOTE",
                    "previous_state": None,
                    "new_state": review_state,
                    "note": note.get("body"),
                }
            )

        concern = item.get("challengerConcern")
        if concern:
            concerns.append(
                {
                    "concern_id": f"challenge-{finding_id}",
                    "finding_id": finding_id,
                    "summary": str(concern),
                    "status": "OPEN" if item.get("status") != "MATCH" else "RESOLVED",
                }
            )
        verifier = item.get("verifierStatement")
        if verifier:
            verifier_results.append(
                {
                    "verifier_result_id": f"verify-{finding_id}",
                    "finding_id": finding_id,
                    "status": "UNRESOLVED" if item.get("status") == "CANNOT_VERIFY" else "COMPLETE",
                    "statement": str(verifier),
                }
            )
        required_action = item.get("requiredAction")
        if item.get("status") in {"CANNOT_VERIFY", "UNSUPPORTED"} or required_action:
            missing = []
            if isinstance(required_action, Mapping) and required_action.get("documentRole"):
                missing.append(str(required_action["documentRole"]))
            unresolved.append(
                {
                    "issue_id": f"unresolved-{finding_id}",
                    "finding_id": finding_id,
                    "summary": str(
                        required_action.get("label")
                        if isinstance(required_action, Mapping)
                        else item.get("explanation", "Review required")
                    ),
                    "missing_evidence": missing,
                }
            )

        findings.append(
            {
                "finding_id": finding_id,
                "investor_id": investor_id,
                "check_type": str(item.get("checkName", "Management fee")),
                "administrator_value": admin_amount,
                "expected_value": expected_amount,
                "difference": difference_amount,
                "variance_direction": _variance_direction(admin_amount, expected_amount),
                "currency": currency,
                "computational_status": str(item.get("status", "UNSUPPORTED")),
                "human_review_status": review_state,
                "explanation": str(item.get("explanation", "")),
                "calculation_id": calculation_id,
                "evidence_ids": evidence_ids,
            }
        )

        rates = _find_rates(item)
        calc_values = calculations[-1] if calculation_id else {}
        investor_terms.append(
            {
                "investor_id": investor_id,
                "term": str(item.get("checkName", "Management fee")),
                "default_rate_fraction": rates.get("default_rate_fraction"),
                "override_rate_fraction": rates.get("override_rate_fraction"),
                "applicable_rate_fraction": calc_values.get("annual_rate_fraction"),
                "fee_base": calc_values.get("fee_base"),
                "currency": currency,
                "evidence_ids": evidence_ids,
                "applicability_state": "MISSING_EVIDENCE"
                if item.get("status") == "CANNOT_VERIFY"
                else "ESTABLISHED",
            }
        )

    documents = []
    for document in raw.get("documents", []):
        documents.append(
            {
                "document_id": str(document.get("id", "unknown-document")),
                "filename": str(document.get("filename", "Unknown source")),
                "role": str(document.get("role", "SUPPORTING")),
                "sha256": document.get("sha256"),
                "recognition": document.get("recognition"),
                "supplied": document.get("recognition") != "MISSING",
            }
        )

    known_document_ids = {document["document_id"] for document in documents}
    for evidence in evidence_by_id.values():
        if evidence["document_id"] not in known_document_ids:
            documents.append(
                {
                    "document_id": evidence["document_id"],
                    "filename": evidence["filename"],
                    "role": evidence["document_role"],
                    "sha256": None,
                    "recognition": "REFERENCED_IN_FINDING",
                    "supplied": True,
                }
            )
            known_document_ids.add(evidence["document_id"])

    investor_ids = [finding["investor_id"] for finding in findings]
    return {
        "run_id": str(raw.get("id") or raw.get("run_id") or ""),
        "version": version,
        "fund_name": raw.get("fundName"),
        "reporting_period": str(raw.get("periodLabel", "Reporting period not supplied")),
        "mode": mode,
        "timestamp": timestamp,
        "source": source or None,
        "source_notice": raw.get("sourceNotice"),
        "source_documents": documents,
        "coverage": {
            "scope": "Management-fee checks only",
            "checks_expected": len(findings),
            "checks_completed": len(findings),
            "investor_ids": investor_ids,
        },
        "findings": findings,
        "investor_terms": investor_terms,
        "calculations": calculations,
        "evidence_references": list(evidence_by_id.values()),
        "challenger_concerns": concerns,
        "verifier_results": verifier_results,
        "human_review_decisions": decisions,
        "audit_trail": audit,
        "unresolved_issues": unresolved,
        "adapter_metadata": {
            "source_contract": "Beacon ReviewResult",
            "version_source": "review payload",
            "missing_document_hashes_are_null": True,
        },
    }


def _money(value: Any) -> tuple[float | None, str | None]:
    if not isinstance(value, Mapping):
        return None, None
    try:
        amount = float(value["amount"])
    except (KeyError, TypeError, ValueError):
        amount = None
    currency = str(value["currency"]) if value.get("currency") else None
    return amount, currency


def _parse_number(value: str) -> float | None:
    cleaned = re.sub(r"[^0-9.\-]", "", value.replace(",", ""))
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def _parse_calculation_inputs(inputs: Any) -> dict[str, float | None]:
    result = {"fee_base": None, "annual_rate_fraction": None, "period_factor": None}
    if not isinstance(inputs, Sequence):
        return result
    for item in inputs:
        if not isinstance(item, Mapping):
            continue
        label = str(item.get("label", "")).lower()
        value = _parse_number(str(item.get("value", "")))
        if "base" in label:
            result["fee_base"] = value
        elif "rate" in label or "annual fee" in label:
            result["annual_rate_fraction"] = value / 100 if value is not None else None
        elif "factor" in label or "quarter" in label:
            result["period_factor"] = value
    return result


def _find_rates(item: Mapping[str, Any]) -> dict[str, float | None]:
    default_rate = None
    override_rate = None
    for evidence in item.get("evidence", []):
        if not isinstance(evidence, Mapping):
            continue
        text = " ".join(
            str(evidence.get(key, "")) for key in ("quote", "context", "value")
        )
        match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
        if not match:
            continue
        rate = float(match.group(1)) / 100
        if str(evidence.get("documentRole")) == "LPA":
            default_rate = rate
        elif str(evidence.get("documentRole")) == "SIDE_LETTER":
            override_rate = rate
    return {
        "default_rate_fraction": default_rate,
        "override_rate_fraction": override_rate,
    }


def _variance_direction(admin: float | None, expected: float | None) -> str:
    if admin is None or expected is None:
        return "UNKNOWN"
    if admin > expected:
        return "ADMINISTRATOR_OVERSTATED"
    if admin < expected:
        return "ADMINISTRATOR_UNDERSTATED"
    return "NO_VARIANCE"
