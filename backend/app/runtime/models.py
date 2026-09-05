"""Public V0 runtime contracts. Money crosses JSON boundaries as decimal strings."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from app.atlas.models import SourceRef


def exact_decimal(value):
    if isinstance(value, (float, bool)):
        raise ValueError("Use a decimal string, Decimal, or integer; floats are not accepted")
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError("Financial values must be finite")
    return result


Amount = Annotated[Decimal, BeforeValidator(exact_decimal), Field(max_digits=24, decimal_places=8)]
Rate = Annotated[Amount, Field(ge=0, le=1)]
Identifier = Annotated[str, Field(min_length=1, max_length=200)]
Mode = Literal["DEMO_FIXTURE", "MODEL"]
FinalStatus = Literal["PASS", "REVIEW_REQUIRED", "CANNOT_VERIFY"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Claim(Contract):
    field: Literal["fund_name", "investor_id", "fee_base", "annual_rate", "period_fraction", "reported", "currency", "period_start", "period_end"]
    value: str
    evidence_ids: list[Identifier] = Field(min_length=1)


class CalculationRequest(Contract):
    fee_base: Amount = Field(ge=0)
    annual_rate: Rate
    period_fraction: Rate
    reported: Amount
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    period_start: date
    period_end: date
    input_evidence: dict[str, list[Identifier]]
    # Optional agent assertions are checked, never used as calculation inputs.
    claimed_expected: Amount | None = None
    claimed_difference: Amount | None = None


class Finding(Contract):
    investor_id: Identifier
    fund_name: Identifier
    calculation: CalculationRequest | None = None
    claims: list[Claim] = Field(default_factory=list)
    evidence_ids: list[Identifier] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    explanation: str


class OutputRecommendation(Contract):
    format: Literal["PDF", "XLSX", "JSON"]
    reason: str


class AnalysisResult(Contract):
    findings: list[Finding]
    output_recommendations: list[OutputRecommendation] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class Challenge(Contract):
    code: str
    investor_id: str
    explanation: str
    evidence_ids: list[str] = Field(default_factory=list)
    insufficient_evidence: bool = False


class RedTeamResult(Contract):
    status: Literal["PASS", "CHALLENGE", "INSUFFICIENT_EVIDENCE"]
    challenges: list[Challenge] = Field(default_factory=list)


class Verification(Contract):
    investor_id: str
    status: Literal["PASSED", "FAILED", "CANNOT_VERIFY"]
    reported: Amount | None = None
    expected: Amount | None = None
    difference: Amount | None = None
    currency: str | None = None
    calculation: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    checks: dict[str, bool] = Field(default_factory=dict)
    explanations: list[str] = Field(default_factory=list)


class FinalFinding(Contract):
    investor_id: str
    fund_name: str
    status: FinalStatus
    disposition: Literal["VERIFIED", "NEEDS_HUMAN_REVIEW"]
    reported: Amount | None = None
    expected: Amount | None = None
    difference: Amount | None = None
    currency: str | None = None
    evidence_ids: list[str]
    source_refs: list[SourceRef]
    explanation: str
    unresolved_concerns: list[Challenge]


class TraceEvent(Contract):
    stage: Literal["INGESTED", "ANALYSED", "RED_TEAMED", "VERIFIED", "REPAIRED", "FINAL_VERIFIED", "OUTPUT_PLANNED"]
    status: str
    timestamp: datetime
    explanation: str
    input_ids: list[str] = Field(default_factory=list)
    output_ids: list[str] = Field(default_factory=list)


class OutputPlan(Contract):
    recommendations: list[OutputRecommendation]
    delivery: Literal["RETURN_TO_CALLER"] = "RETURN_TO_CALLER"
    requires_human_review: bool
    explanation: str


class PipelineResult(Contract):
    contract_version: Literal["runtime.v0.1"] = "runtime.v0.1"
    case_id: str
    run_id: str
    mode: Mode
    created_at: datetime
    status: FinalStatus
    disposition: Literal["VERIFIED", "NEEDS_HUMAN_REVIEW"]
    initial_analysis: AnalysisResult
    analysis: AnalysisResult
    initial_red_team: RedTeamResult
    red_team: RedTeamResult
    initial_verifications: list[Verification]
    verifications: list[Verification]
    repair_count: Literal[0, 1]
    findings: list[FinalFinding]
    output_plan: OutputPlan
    trace: list[TraceEvent]
    limitations: list[str]
