from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, BaseModel, ConfigDict, Field, field_validator, model_validator


def exact_decimal(value: Any) -> Decimal:
    """Validate a financial scalar without accepting a lossy binary float."""

    if isinstance(value, bool):
        raise ValueError("financial values must be finite exact decimals")
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("financial values must be a finite number")
        raise ValueError("financial values must use an exact decimal string, Decimal, or integer")
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("financial values must be finite exact decimals") from exc
    if not result.is_finite():
        raise ValueError("financial values must be a finite number")
    return result


ExactDecimal = Annotated[Decimal, BeforeValidator(exact_decimal)]


class RelayModel(BaseModel):
    """Allowlisted boundary model: unknown upstream fields never reach artifacts."""

    model_config = ConfigDict(extra="ignore", frozen=True, allow_inf_nan=False)


class ReviewMode(StrEnum):
    SYNTHETIC_DEMO = "SYNTHETIC_DEMO"
    LIVE = "LIVE"


class FindingStatus(StrEnum):
    MATCH = "MATCH"
    DISCREPANCY = "DISCREPANCY"
    CANNOT_VERIFY = "CANNOT_VERIFY"
    UNSUPPORTED = "UNSUPPORTED"


class HumanReviewState(StrEnum):
    UNREVIEWED = "UNREVIEWED"
    REVIEWED = "REVIEWED"
    NEEDS_FOLLOW_UP = "NEEDS_FOLLOW_UP"
    TERM_CONFIRMED = "TERM_CONFIRMED"


class SourceDocument(RelayModel):
    document_id: str
    filename: str
    role: str
    sha256: str | None = None
    recognition: str | None = None
    supplied: bool = True

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.lower()
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError("sha256 must be a 64-character hexadecimal digest")
        return value


class Coverage(RelayModel):
    scope: str = "Management-fee checks only"
    checks_expected: int | None = None
    checks_completed: int
    investor_ids: tuple[str, ...] = ()

    @field_validator("scope")
    @classmethod
    def enforce_scope(cls, value: str) -> str:
        if value != "Management-fee checks only":
            raise ValueError("RELAY supports only: Management-fee checks only")
        return value


class EvidenceReference(RelayModel):
    evidence_id: str
    document_id: str
    filename: str
    document_role: str
    source_kind: str
    locator: str
    quoted_text: str | None = None
    value: str | None = None
    context: str | None = None


class Calculation(RelayModel):
    calculation_id: str
    finding_id: str
    investor_id: str
    fee_base: ExactDecimal | None = None
    annual_rate_fraction: ExactDecimal | None = Field(default=None, ge=0)
    period_factor: ExactDecimal | None = Field(default=None, ge=0)
    expected_value: ExactDecimal | None = None
    reported_value: ExactDecimal | None = None
    difference: ExactDecimal | None = None
    currency: str = "GBP"
    expression: str | None = None


class InvestorTerm(RelayModel):
    investor_id: str
    term: str
    default_rate_fraction: ExactDecimal | None = Field(default=None, ge=0)
    override_rate_fraction: ExactDecimal | None = Field(default=None, ge=0)
    applicable_rate_fraction: ExactDecimal | None = Field(default=None, ge=0)
    effective_from: str | None = None
    effective_to: str | None = None
    fee_base: ExactDecimal | None = None
    currency: str = "GBP"
    evidence_ids: tuple[str, ...] = ()
    applicability_state: str = "ESTABLISHED"


class Finding(RelayModel):
    finding_id: str
    investor_id: str
    check_type: str
    administrator_value: ExactDecimal | None = None
    expected_value: ExactDecimal | None = None
    difference: ExactDecimal | None = None
    difference_convention: str = "ABSOLUTE_ADMINISTRATOR_MINUS_EXPECTED"
    variance_direction: str = "UNKNOWN"
    currency: str = "GBP"
    computational_status: FindingStatus
    human_review_status: HumanReviewState = HumanReviewState.UNREVIEWED
    explanation: str
    calculation_id: str | None = None
    evidence_ids: tuple[str, ...] = ()


class ChallengerConcern(RelayModel):
    concern_id: str
    finding_id: str | None = None
    summary: str
    status: str = "OPEN"


class VerifierResult(RelayModel):
    verifier_result_id: str
    finding_id: str | None = None
    status: str
    statement: str


class HumanReviewDecision(RelayModel):
    finding_id: str
    state: HumanReviewState
    reviewer_label: str | None = None
    timestamp: datetime | None = None
    notes: str | None = None


class AuditEvent(RelayModel):
    timestamp: datetime
    run_id: str
    run_version: int = Field(ge=1)
    finding_id: str | None = None
    reviewer: str | None = None
    action: str
    previous_state: str | None = None
    new_state: str | None = None
    note: str | None = None


class UnresolvedIssue(RelayModel):
    issue_id: str
    finding_id: str | None = None
    severity: str = "REVIEW_REQUIRED"
    summary: str
    missing_evidence: tuple[str, ...] = ()


class OutputSnapshotView(RelayModel):
    """Frozen output boundary adapted from Atlas or the Beacon demo fixture.

    This is deliberately an output view, not a competing core review schema.
    """

    schema_version: Literal["relay-output-snapshot-v1"] = "relay-output-snapshot-v1"
    run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    version: int = Field(ge=1)
    fund_name: str | None = None
    reporting_period: str
    mode: ReviewMode
    timestamp: datetime
    source: str | None = None
    source_notice: str | None = None
    source_documents: tuple[SourceDocument, ...]
    coverage: Coverage
    findings: tuple[Finding, ...]
    investor_terms: tuple[InvestorTerm, ...] = ()
    calculations: tuple[Calculation, ...] = ()
    evidence_references: tuple[EvidenceReference, ...] = ()
    challenger_concerns: tuple[ChallengerConcern, ...] = ()
    verifier_results: tuple[VerifierResult, ...] = ()
    human_review_decisions: tuple[HumanReviewDecision, ...] = ()
    audit_trail: tuple[AuditEvent, ...] = ()
    unresolved_issues: tuple[UnresolvedIssue, ...] = ()
    limitations: tuple[str, ...] = ()

    @field_validator("timestamp")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_cross_references(self) -> "OutputSnapshotView":
        finding_ids = [finding.finding_id for finding in self.findings]
        document_ids = [document.document_id for document in self.source_documents]
        evidence_ids = [evidence.evidence_id for evidence in self.evidence_references]
        calculation_ids = [calculation.calculation_id for calculation in self.calculations]
        for label, values in (
            ("finding", finding_ids),
            ("document", document_ids),
            ("evidence", evidence_ids),
            ("calculation", calculation_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {label} ids are not allowed")

        known_findings = set(finding_ids)
        known_documents = set(document_ids)
        known_evidence = set(evidence_ids)
        known_calculations = set(calculation_ids)
        findings_by_id = {finding.finding_id: finding for finding in self.findings}
        calculations_by_id = {calculation.calculation_id: calculation for calculation in self.calculations}
        unresolved_findings = {
            issue.finding_id for issue in self.unresolved_issues if issue.finding_id is not None
        }
        for finding in self.findings:
            missing_evidence = set(finding.evidence_ids) - known_evidence
            if missing_evidence:
                raise ValueError(
                    f"finding {finding.finding_id!r} references unknown evidence: "
                    f"{sorted(missing_evidence)}"
                )
            if finding.calculation_id and finding.calculation_id not in known_calculations:
                raise ValueError(
                    f"finding {finding.finding_id!r} references unknown calculation "
                    f"{finding.calculation_id!r}"
                )
            if finding.calculation_id:
                calculation = calculations_by_id[finding.calculation_id]
                if calculation.finding_id != finding.finding_id:
                    raise ValueError(
                        f"finding {finding.finding_id!r} references a calculation linked to another finding"
                    )
            if finding.computational_status == FindingStatus.CANNOT_VERIFY:
                if finding.expected_value is not None or finding.difference is not None:
                    raise ValueError("CANNOT_VERIFY findings cannot contain expected/difference values")
                if finding.finding_id not in unresolved_findings:
                    raise ValueError("CANNOT_VERIFY findings require an unresolved issue")
            if finding.computational_status == FindingStatus.DISCREPANCY and any(
                value is None
                for value in (
                    finding.administrator_value,
                    finding.expected_value,
                    finding.difference,
                )
            ):
                raise ValueError("DISCREPANCY findings require administrator, expected and difference")

        for calculation in self.calculations:
            if calculation.finding_id not in known_findings:
                raise ValueError(
                    f"calculation {calculation.calculation_id!r} references unknown finding"
                )
            finding = findings_by_id[calculation.finding_id]
            if calculation.investor_id != finding.investor_id:
                raise ValueError(
                    f"calculation {calculation.calculation_id!r} investor does not match its finding"
                )
            if finding.calculation_id != calculation.calculation_id:
                raise ValueError(
                    f"calculation {calculation.calculation_id!r} is not referenced by its linked finding"
                )
        for term in self.investor_terms:
            missing_evidence = set(term.evidence_ids) - known_evidence
            if missing_evidence:
                raise ValueError(
                    f"investor term {term.investor_id!r} references unknown evidence: "
                    f"{sorted(missing_evidence)}"
                )
        for collection_name, records in (
            ("challenger concern", self.challenger_concerns),
            ("verifier result", self.verifier_results),
            ("human review decision", self.human_review_decisions),
            ("unresolved issue", self.unresolved_issues),
        ):
            for record in records:
                finding_id = record.finding_id
                if finding_id is not None and finding_id not in known_findings:
                    raise ValueError(f"{collection_name} references unknown finding {finding_id!r}")
        for event in self.audit_trail:
            if event.run_id != self.run_id:
                raise ValueError("audit event run_id must match the snapshot run_id")
            if event.run_version > self.version:
                raise ValueError("audit event run_version cannot exceed the snapshot version")
            if event.finding_id is not None and event.finding_id not in known_findings:
                raise ValueError("audit event references an unknown finding")
        for evidence in self.evidence_references:
            if evidence.document_id not in known_documents:
                raise ValueError(
                    f"evidence {evidence.evidence_id!r} references unknown document "
                    f"{evidence.document_id!r}"
                )
        if self.coverage.checks_completed != len(self.findings):
            raise ValueError("coverage.checks_completed must equal the number of findings")
        return self

    def summary_counts(self) -> dict[str, int]:
        counts = {status.value: 0 for status in FindingStatus}
        for finding in self.findings:
            counts[finding.computational_status.value] += 1
        return {
            "checks_completed": len(self.findings),
            "matches": counts[FindingStatus.MATCH.value],
            "discrepancies": counts[FindingStatus.DISCREPANCY.value],
            "cannot_verify": counts[FindingStatus.CANNOT_VERIFY.value],
            "unsupported": counts[FindingStatus.UNSUPPORTED.value],
            "unreviewed": sum(
                finding.human_review_status == HumanReviewState.UNREVIEWED
                for finding in self.findings
            ),
        }

    def evidence_by_id(self) -> dict[str, EvidenceReference]:
        return {evidence.evidence_id: evidence for evidence in self.evidence_references}

    def calculation_by_id(self) -> dict[str, Calculation]:
        return {calculation.calculation_id: calculation for calculation in self.calculations}

    def to_jsonable(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=False)
