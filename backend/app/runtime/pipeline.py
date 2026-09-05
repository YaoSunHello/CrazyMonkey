"""The entire bounded runtime: one analysis, independent checks, at most one repair."""

from datetime import datetime, timezone
import re
from uuid import uuid4

from app.atlas.models import NormalizedDocument

from .analyst import FixtureAnalyst
from .assurance import red_team, verify
from .evidence import EvidenceCatalog, build_context
from .models import (
    AnalysisResult, FinalFinding, OutputPlan, OutputRecommendation,
    PipelineResult, TraceEvent,
)


def validate_case_id(case_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", case_id):
        raise ValueError("case_id must contain 1-80 letters, digits, underscores or hyphens")
    return case_id


def run_case(case_id: str, user_instruction: str,
             normalized_documents: list[NormalizedDocument], *, analyst=None) -> PipelineResult:
    """Consume trusted Atlas output; never accept agent-authored source records.

    The injectable analyst sees copies. Red-team and verifier see the independently
    captured evidence catalog. The sole repair branch is deliberately not a loop.
    """
    validate_case_id(case_id)
    if not user_instruction.strip() or len(user_instruction) > 10000:
        raise ValueError("A nonempty user instruction of at most 10000 characters is required")
    catalog = EvidenceCatalog(normalized_documents)
    runner = analyst if analyst is not None else FixtureAnalyst()
    if runner.mode not in {"DEMO_FIXTURE", "MODEL"}:
        raise ValueError("Analyst mode must explicitly be DEMO_FIXTURE or MODEL")
    run_id = f"{case_id}-{uuid4().hex[:12]}"
    created_at = datetime.now(timezone.utc)
    trace = []
    analyst_failed = False

    def event(stage, status, explanation, input_ids=(), output_ids=()):
        trace.append(TraceEvent(stage=stage, status=status,
                                timestamp=datetime.now(timezone.utc), explanation=explanation,
                                input_ids=list(input_ids), output_ids=list(output_ids)))

    def analyse(feedback=None):
        nonlocal analyst_failed
        analyst_failed = False
        try:
            proposal = runner.analyse(user_instruction, catalog.documents, feedback=feedback)
            raw = proposal.model_dump(mode="python") if isinstance(proposal, AnalysisResult) else proposal
            return AnalysisResult.model_validate(raw)
        except Exception:
            analyst_failed = True
            # Model/service failures are not evidence. Avoid leaking provider responses or secrets.
            return AnalysisResult(findings=[], limitations=[
                "Analyst execution or structured-output validation failed; human review is required."])

    event("INGESTED", "COMPLETE", "Captured validated Atlas normalized evidence; no source parsing repeated.",
          [doc.document.document_id for doc in catalog.documents], [run_id])
    first_analysis = analyse()
    event("ANALYSED", "FAILED" if analyst_failed else "COMPLETE",
          "Analyst failed to return a valid structured result." if analyst_failed else f"Structured candidate interpretation produced in {runner.mode} mode.",
          output_ids=[item.investor_id for item in first_analysis.findings])
    first_red_team = red_team(first_analysis, catalog)
    event("RED_TEAMED", first_red_team.status, "Independent source checks completed; primary result was not changed.")
    first_verifications = verify(first_analysis, catalog)
    event("VERIFIED", "PASSED" if all(v.status == "PASSED" for v in first_verifications) else "FAILED",
          "Python Decimal calculations and source-bound assertions checked.")

    analysis, challenged, verifications = first_analysis, first_red_team, first_verifications
    repair_count = 0
    if first_red_team.status != "PASS" or any(v.status != "PASSED" for v in first_verifications):
        repair_count = 1
        analysis = analyse(feedback={
            "red_team": first_red_team.model_dump(mode="json"),
            "verifications": [v.model_dump(mode="json") for v in first_verifications],
            "instruction": "Repair unsupported interpretations only. Do not change source evidence or reported fees.",
        })
        event("REPAIRED", "FAILED" if analyst_failed else "ATTEMPTED", "The single permitted repair attempt completed; no further retries are allowed.")
        challenged = red_team(analysis, catalog)
        event("RED_TEAMED", challenged.status, "Repaired interpretation independently checked against the same sources.")
    # Recheck even when no repair was needed. No result is promoted on the analyst's word.
    verifications = verify(analysis, catalog)
    contexts = {item.investor_id: item for item in build_context(catalog)}
    findings = []
    for verification in verifications:
        concerns = [c for c in challenged.challenges if c.investor_id in {verification.investor_id, "*"}]
        cannot_verify = verification.status == "CANNOT_VERIFY" or any(c.insufficient_evidence for c in concerns)
        status = "CANNOT_VERIFY" if cannot_verify else (
            "REVIEW_REQUIRED" if verification.status != "PASSED" or concerns else "PASS")
        term = contexts.get(verification.investor_id)
        refs = catalog.resolve(verification.evidence_ids)
        findings.append(FinalFinding(
            investor_id=verification.investor_id,
            fund_name=term.fund_name if term else "Unresolved fund",
            status=status, disposition="VERIFIED" if status == "PASS" else "NEEDS_HUMAN_REVIEW",
            reported=verification.reported, expected=verification.expected,
            difference=verification.difference, currency=verification.currency,
            evidence_ids=[ref.evidence_id for ref in refs], source_refs=refs,
            explanation="; ".join(verification.explanations) or "All deterministic source and amount checks passed.",
            unresolved_concerns=concerns,
        ))
    # Coverage is part of verification; absence of findings is never a successful review.
    status = "REVIEW_REQUIRED" if any(f.status == "REVIEW_REQUIRED" for f in findings) else (
        "CANNOT_VERIFY" if not findings or any(f.status == "CANNOT_VERIFY" for f in findings) else "PASS")
    event("FINAL_VERIFIED", status, "Final findings retain unresolved discrepancies and missing evidence for human review.",
          output_ids=[f.investor_id for f in findings])
    recommendations = [
        OutputRecommendation(format="XLSX", reason="Review numeric fee comparisons and their source references."),
        OutputRecommendation(format="PDF", reason="Share a readable findings and unresolved-evidence report."),
        OutputRecommendation(format="JSON", reason="Preserve structured findings, source IDs, and verification results."),
    ]
    plan = OutputPlan(recommendations=recommendations, requires_human_review=status != "PASS",
                      explanation="RELAY may generate versioned review artifacts. Sending email requires a separate explicit confirmation.")
    event("OUTPUT_PLANNED", "COMPLETE", "Planned review deliverables; no email was sent.")
    limitations = [
        "V0 management-fee review only; not legal advice, an audit opinion, or a full NAV certification.",
        "Evidence authenticity is relative to the trusted Atlas documents supplied at entry, not a digital signature of the original file.",
        "Unsupported or ambiguous financial terms require human interpretation; no missing evidence is inferred away.",
    ]
    if runner.mode == "DEMO_FIXTURE":
        limitations.append("DEMO_FIXTURE uses explicit deterministic supported-clause interpretation; no language model was invoked.")
    limitations.extend(analysis.limitations)
    result = PipelineResult(
        case_id=case_id, run_id=run_id, mode=runner.mode, created_at=created_at,
        status=status, disposition="VERIFIED" if status == "PASS" else "NEEDS_HUMAN_REVIEW",
        initial_analysis=first_analysis, analysis=analysis, initial_red_team=first_red_team,
        red_team=challenged, initial_verifications=first_verifications, verifications=verifications,
        repair_count=repair_count, findings=findings, output_plan=plan, trace=trace,
        limitations=list(dict.fromkeys(limitations)),
    )
    return PipelineResult.model_validate_json(result.model_dump_json())
