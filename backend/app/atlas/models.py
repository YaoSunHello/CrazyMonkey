"""Canonical, validated records shared by ATLAS, BEACON, and RELAY."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ExactText = Annotated[str, StringConstraints(strip_whitespace=False)]
ExactNonEmpty = Annotated[str, StringConstraints(strip_whitespace=False, min_length=1)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Money = Annotated[Decimal, Field(max_digits=24, decimal_places=6)]
Rate = Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("1"), decimal_places=8)]


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        use_enum_values=True,
    )


class DocumentRole(str, Enum):
    NAV_WORKBOOK = "NAV_WORKBOOK"
    LPA = "LPA"
    SIDE_LETTER = "SIDE_LETTER"
    INVESTOR_REGISTER = "INVESTOR_REGISTER"
    SUPPORTING = "SUPPORTING"


class ExtractionStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    FAILED = "FAILED"


class EvidenceKind(str, Enum):
    PDF_TEXT = "PDF_TEXT"
    WORKBOOK_CELL = "WORKBOOK_CELL"
    CSV_CELL = "CSV_CELL"


class RuleState(str, Enum):
    SUPPORTED = "SUPPORTED"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    CANNOT_DETERMINE = "CANNOT_DETERMINE"


class ApplicabilityState(str, Enum):
    APPLIES = "APPLIES"
    DOES_NOT_APPLY = "DOES_NOT_APPLY"
    AMBIGUOUS = "AMBIGUOUS"


class FindingStatus(str, Enum):
    MATCH = "MATCH"
    DISCREPANCY = "DISCREPANCY"
    CANNOT_VERIFY = "CANNOT_VERIFY"
    UNSUPPORTED = "UNSUPPORTED"


class HumanReviewState(str, Enum):
    UNREVIEWED = "UNREVIEWED"
    REVIEWED = "REVIEWED"
    NEEDS_FOLLOW_UP = "NEEDS_FOLLOW_UP"
    TERM_CONFIRMED = "TERM_CONFIRMED"


class ConcernSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class ConcernState(str, Enum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"


class RunMode(str, Enum):
    SYNTHETIC_DEMO = "SYNTHETIC_DEMO"
    LIVE_OFFLINE = "LIVE_OFFLINE"
    LIVE_MODEL = "LIVE_MODEL"


class StageCode(str, Enum):
    READING_FILES = "READING_FILES"
    EXTRACTING_TERMS = "EXTRACTING_TERMS"
    CHALLENGING_ASSUMPTIONS = "CHALLENGING_ASSUMPTIONS"
    CHECKING_CALCULATIONS = "CHECKING_CALCULATIONS"
    PREPARING_REVIEW = "PREPARING_REVIEW"


class StageState(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"


class SourceDocument(StrictModel):
    document_id: NonEmpty
    filename: ExactNonEmpty
    document_hash: Sha256
    role: DocumentRole
    mime_type: NonEmpty
    size_bytes: int = Field(ge=0)
    extraction_status: ExtractionStatus
    warnings: list[str] = Field(default_factory=list)
    original_storage_key: ExactNonEmpty


class SourceRef(StrictModel):
    evidence_id: NonEmpty
    document_id: NonEmpty
    document_hash: Sha256
    kind: EvidenceKind
    page: int | None = Field(default=None, ge=1)
    section: str | None = None
    text_start: int | None = Field(default=None, ge=0)
    text_end: int | None = Field(default=None, ge=0)
    sheet: ExactText | None = None
    cell: str | None = None
    csv_row: int | None = Field(default=None, ge=1)
    csv_column: ExactText | None = None
    quote: ExactText | None = None
    original_value: ExactText | None = None
    normalized_value: str | None = None
    formula: ExactText | None = None
    cached_value: ExactText | None = None
    cache_status: Literal["NOT_APPLICABLE", "PRESENT_UNVERIFIED", "MISSING"] = (
        "NOT_APPLICABLE"
    )
    data_type: str | None = None
    number_format: ExactText | None = None

    @model_validator(mode="after")
    def validate_locator_and_support(self) -> "SourceRef":
        if self.kind == EvidenceKind.PDF_TEXT and self.page is None:
            raise ValueError("PDF evidence requires a page")
        if self.kind == EvidenceKind.WORKBOOK_CELL and not (self.sheet and self.cell):
            raise ValueError("workbook evidence requires sheet and cell")
        if self.kind == EvidenceKind.CSV_CELL and not (self.csv_row and self.csv_column):
            raise ValueError("CSV evidence requires row and column")
        if not self.quote and not self.original_value:
            raise ValueError("evidence requires exact supporting text or original value")
        if (
            self.text_start is not None
            and self.text_end is not None
            and self.text_end < self.text_start
        ):
            raise ValueError("text_end must not precede text_start")
        return self

    @property
    def locator(self) -> str:
        if self.kind == EvidenceKind.PDF_TEXT:
            suffix = f", {self.section}" if self.section else ""
            return f"page {self.page}{suffix}"
        if self.kind == EvidenceKind.WORKBOOK_CELL:
            return f"{self.sheet}!{self.cell}"
        return f"row {self.csv_row}, {self.csv_column}"


class WorkbookSheet(StrictModel):
    name: ExactNonEmpty
    max_row: int = Field(ge=0)
    max_column: int = Field(ge=0)
    hidden: bool = False
    frozen_panes: str | None = None
    merged_ranges: list[str] = Field(default_factory=list)


class NormalizedDocument(StrictModel):
    document: SourceDocument
    evidence: list[SourceRef]
    workbook_sheets: list[WorkbookSheet] = Field(default_factory=list)
    csv_headers: list[str] = Field(default_factory=list)
    layout: dict[str, str | int | bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_evidence_documents(self) -> "NormalizedDocument":
        evidence_ids: set[str] = set()
        for ref in self.evidence:
            if ref.evidence_id in evidence_ids:
                raise ValueError("evidence IDs must be unique within a document")
            evidence_ids.add(ref.evidence_id)
            if (
                ref.document_id != self.document.document_id
                or ref.document_hash != self.document.document_hash
            ):
                raise ValueError("evidence must reference the containing document and hash")
        return self


class StageProgress(StrictModel):
    code: StageCode
    label: NonEmpty
    state: StageState = StageState.PENDING
    detail: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class InvestorRule(StrictModel):
    rule_id: NonEmpty
    rule_version: int = Field(ge=1)
    investor_id: NonEmpty
    identity_evidence_ids: list[NonEmpty] = Field(min_length=1)
    term_type: Literal["MANAGEMENT_FEE"] = "MANAGEMENT_FEE"
    default_annual_rate: Rate | None = None
    candidate_override_rate: Rate | None = None
    applicable_annual_rate: Rate | None = None
    fee_basis: NonEmpty | None = None
    fee_base: Money | None = None
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] | None = None
    period_start: date
    period_end: date
    period_factor: Rate
    effective_from: date | None = None
    effective_to: date | None = None
    applicable_default: bool | None = None
    candidate_override: bool = False
    applicability_state: ApplicabilityState
    applicability_rationale: NonEmpty
    input_evidence: dict[NonEmpty, list[NonEmpty]]
    extraction_state: RuleState
    unresolved_questions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_date_ranges(self) -> "InvestorRule":
        if self.period_end < self.period_start:
            raise ValueError("period_end must not precede period_start")
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to < self.effective_from
        ):
            raise ValueError("effective_to must not precede effective_from")
        return self


class Calculation(StrictModel):
    calculation_id: NonEmpty
    rule_id: NonEmpty
    rule_version: int = Field(ge=1)
    investor_id: NonEmpty
    formula_code: Literal["ANNUAL_RATE_X_PERIOD_FACTOR_X_FEE_BASE"]
    formula_description: NonEmpty
    fee_base: Money
    annual_rate: Rate
    period_factor: Rate
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
    rounding: Literal["ROUND_HALF_UP_0.01"] = "ROUND_HALF_UP_0.01"
    tolerance: Money = Field(ge=Decimal("0"))
    expected_amount: Money
    reported_amount: Money
    difference: Money
    input_evidence: dict[NonEmpty, list[NonEmpty]]


class ChallengerConcern(StrictModel):
    concern_id: NonEmpty
    investor_id: NonEmpty
    rule_id: NonEmpty | None = None
    severity: ConcernSeverity
    state: ConcernState
    suspected_problem: NonEmpty
    evidence_ids: list[NonEmpty] = Field(default_factory=list)
    missing_fact: str | None = None
    required_resolution: NonEmpty


class VerifierCheck(StrictModel):
    code: NonEmpty
    passed: bool
    explanation: NonEmpty


class VerifierResult(StrictModel):
    verifier_result_id: NonEmpty
    investor_id: NonEmpty
    rule_id: NonEmpty | None = None
    calculation_id: NonEmpty | None = None
    status: FindingStatus
    checks: list[VerifierCheck]
    blocking_concern_ids: list[NonEmpty] = Field(default_factory=list)
    explanation: NonEmpty

    @model_validator(mode="after")
    def validate_asserted_result(self) -> "VerifierResult":
        if self.status in (FindingStatus.MATCH, FindingStatus.DISCREPANCY):
            if self.calculation_id is None or not self.checks:
                raise ValueError("an asserted result requires a calculation and verifier checks")
            if self.blocking_concern_ids:
                raise ValueError("an asserted result cannot have blocking concerns")
            if self.status == FindingStatus.MATCH and any(not check.passed for check in self.checks):
                raise ValueError("a match cannot have failed verifier checks")
        return self


class Finding(StrictModel):
    finding_id: NonEmpty
    investor_id: NonEmpty
    check_type: Literal["MANAGEMENT_FEE"] = "MANAGEMENT_FEE"
    reported_value: Money | None = None
    expected_value: Money | None = None
    difference: Money | None = None
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] | None = None
    status: FindingStatus
    human_review_state: HumanReviewState = HumanReviewState.UNREVIEWED
    calculation_id: NonEmpty | None = None
    evidence_ids: list[NonEmpty]
    source_refs: list[SourceRef]
    challenger_concern_ids: list[NonEmpty] = Field(default_factory=list)
    verifier_result_id: NonEmpty
    explanation: NonEmpty
    actionable_next_step: NonEmpty
    unresolved_questions: list[str] = Field(default_factory=list)
    reviewer_label: str | None = None
    reviewer_note: str | None = None
    reviewed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_evidence_and_assertion(self) -> "Finding":
        ref_ids = [ref.evidence_id for ref in self.source_refs]
        if (
            len(set(ref_ids)) != len(ref_ids)
            or len(set(self.evidence_ids)) != len(self.evidence_ids)
            or set(self.evidence_ids) != set(ref_ids)
        ):
            raise ValueError("finding evidence IDs must resolve exactly to unique source references")
        if self.status in (FindingStatus.MATCH, FindingStatus.DISCREPANCY):
            required = (
                self.reported_value, self.expected_value, self.difference,
                self.currency, self.calculation_id,
            )
            if any(value is None for value in required) or not self.source_refs:
                raise ValueError("an asserted finding requires amounts, currency, calculation and evidence")
        return self


class ReviewDecision(StrictModel):
    finding_id: NonEmpty
    action: HumanReviewState
    reviewer_label: NonEmpty
    note: NonEmpty


class AuditEvent(StrictModel):
    event_id: NonEmpty
    run_id: NonEmpty
    run_version: int = Field(ge=1)
    finding_id: NonEmpty
    action: HumanReviewState
    reviewer_label: NonEmpty
    timestamp: datetime
    note: NonEmpty
    previous_review_state: HumanReviewState
    new_review_state: HumanReviewState
    affected_artifact_ids: list[NonEmpty] = Field(default_factory=list)


class CoverageSummary(StrictModel):
    checks_completed: int = Field(ge=0)
    matches: int = Field(ge=0)
    discrepancies: int = Field(ge=0)
    cannot_verify: int = Field(ge=0)
    unsupported: int = Field(ge=0)
    unreviewed: int = Field(ge=0)


class ReviewSnapshot(StrictModel):
    contract_version: Literal[1] = 1
    run_id: NonEmpty
    version: int = Field(ge=1)
    mode: RunMode
    fund_name: NonEmpty
    reporting_period: NonEmpty
    created_at: datetime
    frozen_at: datetime
    source_documents: list[SourceDocument]
    rules: list[InvestorRule]
    calculations: list[Calculation]
    challenger_concerns: list[ChallengerConcern]
    verifier_results: list[VerifierResult]
    findings: list[Finding]
    audit_trail: list[AuditEvent] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)
    limitations: list[NonEmpty]
    summary: CoverageSummary | None = None

    @model_validator(mode="after")
    def validate_record_references(self) -> "ReviewSnapshot":
        def index(records: list, key: str) -> dict:
            result = {getattr(record, key): record for record in records}
            if len(result) != len(records):
                raise ValueError(f"duplicate {key} in snapshot")
            return result

        def linked(records: dict, record_id: str, investor_id: str):
            record = records.get(record_id)
            if record is None or record.investor_id != investor_id:
                raise ValueError("snapshot references must resolve to the same investor")
            return record

        documents = index(self.source_documents, "document_id")
        rules = index(self.rules, "rule_id")
        calculations = index(self.calculations, "calculation_id")
        concerns = index(self.challenger_concerns, "concern_id")
        verifiers = index(self.verifier_results, "verifier_result_id")
        index(self.findings, "finding_id")
        for calculation in self.calculations:
            rule = linked(rules, calculation.rule_id, calculation.investor_id)
            if calculation.rule_version != rule.rule_version:
                raise ValueError("calculation must reference the stored rule version")
        for concern in self.challenger_concerns:
            if concern.rule_id is not None:
                linked(rules, concern.rule_id, concern.investor_id)
        for verifier in self.verifier_results:
            if verifier.rule_id is not None:
                linked(rules, verifier.rule_id, verifier.investor_id)
            if verifier.calculation_id is not None:
                calculation = linked(calculations, verifier.calculation_id, verifier.investor_id)
                if verifier.rule_id is not None and verifier.rule_id != calculation.rule_id:
                    raise ValueError("verifier rule must match its calculation")
            for concern_id in verifier.blocking_concern_ids:
                linked(concerns, concern_id, verifier.investor_id)
        evidence: dict[str, SourceRef] = {}
        for finding in self.findings:
            verifier = linked(verifiers, finding.verifier_result_id, finding.investor_id)
            if finding.status != verifier.status or finding.calculation_id != verifier.calculation_id:
                raise ValueError("finding status and calculation must match its verifier result")
            if finding.calculation_id is not None:
                calculation = linked(calculations, finding.calculation_id, finding.investor_id)
                for finding_field, calculation_field in (
                    ("reported_value", "reported_amount"), ("expected_value", "expected_amount"),
                    ("difference", "difference"), ("currency", "currency"),
                ):
                    value = getattr(finding, finding_field)
                    if value is not None and value != getattr(calculation, calculation_field):
                        raise ValueError("finding values must match their referenced calculation")
            for concern_id in finding.challenger_concern_ids:
                linked(concerns, concern_id, finding.investor_id)
            for ref in finding.source_refs:
                document = documents.get(ref.document_id)
                if document is None or document.document_hash != ref.document_hash:
                    raise ValueError("finding evidence must reference a stored document and hash")
                if ref.evidence_id in evidence and evidence[ref.evidence_id] != ref:
                    raise ValueError("one evidence ID cannot identify different source references")
                evidence[ref.evidence_id] = ref
        return self

    @model_validator(mode="after")
    def compute_and_validate_summary(self) -> "ReviewSnapshot":
        statuses = [finding.status for finding in self.findings]
        computed = CoverageSummary(
            checks_completed=len(self.findings),
            matches=statuses.count(FindingStatus.MATCH),
            discrepancies=statuses.count(FindingStatus.DISCREPANCY),
            cannot_verify=statuses.count(FindingStatus.CANNOT_VERIFY),
            unsupported=statuses.count(FindingStatus.UNSUPPORTED),
            unreviewed=sum(
                finding.human_review_state == HumanReviewState.UNREVIEWED
                for finding in self.findings
            ),
        )
        if self.summary is not None and self.summary != computed:
            raise ValueError("summary must be derived from findings")
        object.__setattr__(self, "summary", computed)
        return self


class RunStatus(StrictModel):
    run_id: NonEmpty
    state: Literal["QUEUED", "PROCESSING", "COMPLETE", "FAILED"]
    stages: list[StageProgress]
    error: str | None = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
