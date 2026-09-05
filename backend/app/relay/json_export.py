from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .models import OutputSnapshotView
from .snapshot_store import FrozenSnapshot
from .utils import bounded_optional, bounded_text, iso_z, mode_label


def build_review_export(frozen: FrozenSnapshot, generated_at: datetime) -> dict[str, Any]:
    """Project the frozen view through an explicit public allowlist."""

    snapshot = frozen.snapshot
    counts = snapshot.summary_counts()
    audit = [
        {
            "timestamp": iso_z(event.timestamp),
            "run_version": event.run_version,
            "finding_id": event.finding_id,
            "reviewer": event.reviewer,
            "action": event.action,
            "previous_state": event.previous_state,
            "new_state": event.new_state,
            "note": bounded_text(event.note),
        }
        for event in snapshot.audit_trail
    ]
    audit.append(
        {
            "timestamp": iso_z(generated_at),
            "run_version": snapshot.version,
            "finding_id": None,
            "reviewer": "YLookup RELAY",
            "action": "OUTPUT_SNAPSHOT_FROZEN",
            "previous_state": None,
            "new_state": "FROZEN_OUTPUT",
            "note": "Snapshot identity fixed for this output request.",
        }
    )
    return {
        "schema_version": "ylookup-review-export-v1",
        "export_metadata": {
            "run_id": snapshot.run_id,
            "version": snapshot.version,
            "snapshot_sha256": frozen.snapshot_sha256,
            "generated_at": iso_z(generated_at),
            "reporting_period": snapshot.reporting_period,
            "mode": snapshot.mode.value,
            "mode_label": mode_label(snapshot.mode.value),
        },
        "review_metadata": {
            "fund_name": snapshot.fund_name,
            "scope": snapshot.coverage.scope,
            "source": snapshot.source,
            "source_notice": bounded_optional(snapshot.source_notice),
            "snapshot_timestamp": iso_z(snapshot.timestamp),
        },
        "summary": counts,
        "coverage": {
            "scope": snapshot.coverage.scope,
            "checks_expected": snapshot.coverage.checks_expected,
            "checks_completed": len(snapshot.findings),
            "investor_ids": list(snapshot.coverage.investor_ids),
        },
        "source_documents": [
            {
                "document_id": document.document_id,
                "filename": document.filename,
                "role": document.role,
                "sha256": document.sha256,
                "hash_status": "SUPPLIED" if document.sha256 else "NOT_SUPPLIED",
                "recognition": document.recognition,
                "supplied": document.supplied,
            }
            for document in snapshot.source_documents
        ],
        "findings": [
            {
                "finding_id": finding.finding_id,
                "investor_id": finding.investor_id,
                "check_type": finding.check_type,
                "administrator_value": finding.administrator_value,
                "expected_value": finding.expected_value,
                "difference": finding.difference,
                "difference_convention": finding.difference_convention,
                "variance_direction": finding.variance_direction,
                "currency": finding.currency,
                "computational_status": finding.computational_status.value,
                "human_review_status": finding.human_review_status.value,
                "explanation": bounded_text(finding.explanation),
                "calculation_id": finding.calculation_id,
                "evidence_ids": list(finding.evidence_ids),
            }
            for finding in snapshot.findings
        ],
        "investor_terms": [
            {
                "investor_id": term.investor_id,
                "term": term.term,
                "default_rate_fraction": term.default_rate_fraction,
                "override_rate_fraction": term.override_rate_fraction,
                "applicable_rate_fraction": term.applicable_rate_fraction,
                "effective_from": term.effective_from,
                "effective_to": term.effective_to,
                "fee_base": term.fee_base,
                "currency": term.currency,
                "evidence_ids": list(term.evidence_ids),
                "applicability_state": term.applicability_state,
            }
            for term in snapshot.investor_terms
        ],
        "calculations": [
            {
                "calculation_id": calculation.calculation_id,
                "finding_id": calculation.finding_id,
                "investor_id": calculation.investor_id,
                "fee_base": calculation.fee_base,
                "annual_rate_fraction": calculation.annual_rate_fraction,
                "period_factor": calculation.period_factor,
                "expected_value": calculation.expected_value,
                "reported_value": calculation.reported_value,
                "difference": calculation.difference,
                "currency": calculation.currency,
                "expression": bounded_text(calculation.expression),
            }
            for calculation in snapshot.calculations
        ],
        "evidence_references": [
            {
                "evidence_id": evidence.evidence_id,
                "document_id": evidence.document_id,
                "filename": evidence.filename,
                "document_role": evidence.document_role,
                "source_kind": evidence.source_kind,
                "locator": evidence.locator,
                "quoted_text": bounded_optional(evidence.quoted_text),
                "value": bounded_optional(evidence.value),
                "context": bounded_optional(evidence.context),
            }
            for evidence in snapshot.evidence_references
        ],
        "challenger_concerns": [
            {
                "concern_id": concern.concern_id,
                "finding_id": concern.finding_id,
                "summary": bounded_text(concern.summary),
                "status": concern.status,
            }
            for concern in snapshot.challenger_concerns
        ],
        "verifier_results": [
            {
                "verifier_result_id": result.verifier_result_id,
                "finding_id": result.finding_id,
                "status": result.status,
                "statement": bounded_text(result.statement),
            }
            for result in snapshot.verifier_results
        ],
        "human_review_decisions": [
            {
                "finding_id": decision.finding_id,
                "state": decision.state.value,
                "reviewer_label": decision.reviewer_label,
                "timestamp": iso_z(decision.timestamp) if decision.timestamp else None,
                "notes": bounded_optional(decision.notes),
            }
            for decision in snapshot.human_review_decisions
        ],
        "audit_trail": audit,
        "unresolved_issues": [
            {
                "issue_id": issue.issue_id,
                "finding_id": issue.finding_id,
                "severity": issue.severity,
                "summary": bounded_text(issue.summary),
                "missing_evidence": list(issue.missing_evidence),
            }
            for issue in snapshot.unresolved_issues
        ],
        "limitations": [bounded_text(item) for item in snapshot.limitations],
    }


def write_json_export(
    path: Path,
    frozen: FrozenSnapshot,
    generated_at: datetime,
    schema_path: Path,
) -> dict[str, Any]:
    payload = build_review_export(frozen, generated_at)
    validate_json_export(payload, schema_path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return payload


def validate_json_export(payload: dict[str, Any], schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path))
    if errors:
        messages = "; ".join(error.message for error in errors[:5])
        raise ValueError(f"review export failed schema validation: {messages}")
