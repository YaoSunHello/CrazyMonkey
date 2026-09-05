"""Minimal adapter from runtime results to the shared ATLAS/RELAY snapshot."""

from datetime import datetime, timezone

from app.atlas.models import (
    Calculation, ChallengerConcern, Finding, InvestorRule, ReviewSnapshot,
    VerifierCheck, VerifierResult,
)

from .evidence import EvidenceCatalog, build_context
from .models import PipelineResult


def to_snapshot(result: PipelineResult, documents, *, synthetic: bool = False) -> ReviewSnapshot:
    catalog = EvidenceCatalog(documents)
    contexts = {term.investor_id: term for term in build_context(catalog)}
    verifications = {item.investor_id: item for item in result.verifications}
    rules, calculations, concerns, verifiers, findings = [], [], [], [], []
    for index, final in enumerate(result.findings, start=1):
        term = contexts.get(final.investor_id)
        verified = verifications[final.investor_id]
        finding_id = f"finding-{index:03d}"
        rule_id, calculation_id = None, None
        if term and all(value is not None for value in (term.period_start, term.period_end, term.period_fraction)) and term.input_evidence.get("investor_id"):
            rule_id = f"rule-{index:03d}"
            rules.append(InvestorRule(
                rule_id=rule_id, rule_version=1, investor_id=final.investor_id,
                identity_evidence_ids=term.input_evidence["investor_id"],
                default_annual_rate=term.default_annual_rate,
                candidate_override_rate=term.candidate_override_rate,
                applicable_annual_rate=term.annual_rate,
                fee_basis="Register Fee Base, with source-supported LPA/side-letter applicability",
                fee_base=term.fee_base, currency=term.currency,
                period_start=term.period_start, period_end=term.period_end,
                period_factor=term.period_fraction,
                effective_from=term.effective_from, effective_to=term.effective_to,
                applicable_default=term.applicable_default, candidate_override=term.candidate_override,
                applicability_state=term.applicability_state,
                applicability_rationale="Selected terms were independently reconstructed from the cited LPA, register, and applicable side-letter evidence.",
                input_evidence=term.input_evidence,
                extraction_state="CANNOT_DETERMINE" if term.missing_evidence else "SUPPORTED",
                unresolved_questions=term.missing_evidence,
            ))
            if verified.expected is not None and not term.missing_evidence:
                calculation_id = f"calculation-{index:03d}"
                calculations.append(Calculation(
                    calculation_id=calculation_id, rule_id=rule_id, rule_version=1,
                    investor_id=final.investor_id,
                    formula_code="ANNUAL_RATE_X_PERIOD_FACTOR_X_FEE_BASE",
                    formula_description=f"{term.fee_base} × {term.annual_rate} × {term.period_fraction}; ROUND_HALF_UP to 0.01; difference = reported minus expected",
                    fee_base=term.fee_base, annual_rate=term.annual_rate, period_factor=term.period_fraction,
                    currency=term.currency, tolerance=term.tolerance,
                    expected_amount=verified.expected, reported_amount=verified.reported,
                    difference=verified.difference, input_evidence=term.input_evidence,
                ))
        concern_ids = []
        for number, concern in enumerate(final.unresolved_concerns, start=1):
            concern_id = f"concern-{index:03d}-{number:03d}"
            concern_ids.append(concern_id)
            concerns.append(ChallengerConcern(
                concern_id=concern_id, investor_id=final.investor_id, rule_id=rule_id,
                severity="CRITICAL" if concern.insufficient_evidence else "WARNING", state="UNRESOLVED",
                suspected_problem=f"{concern.code}: {concern.explanation}", evidence_ids=concern.evidence_ids,
                missing_fact=concern.explanation if concern.insufficient_evidence else None,
                required_resolution="Obtain or clarify the governing source evidence and rerun; a human review marker does not change verification.",
            ))
        clean_interpretation = not concern_ids and all(
            passed for code, passed in verified.checks.items() if code != "amount_within_tolerance")
        if final.status == "CANNOT_VERIFY" or calculation_id is None:
            status = "CANNOT_VERIFY"
        elif not clean_interpretation:
            status = "UNSUPPORTED"
        else:
            status = "MATCH" if final.status == "PASS" else "DISCREPANCY"
        verifier_id = f"verifier-{index:03d}"
        verifiers.append(VerifierResult(
            verifier_result_id=verifier_id, investor_id=final.investor_id,
            rule_id=rule_id, calculation_id=calculation_id, status=status,
            checks=[VerifierCheck(code=code, passed=passed, explanation=f"Source-bound check: {code}")
                    for code, passed in verified.checks.items()],
            blocking_concern_ids=concern_ids if status in {"CANNOT_VERIFY", "UNSUPPORTED"} else [],
            explanation=final.explanation,
        ))
        refs = catalog.resolve(final.evidence_ids)
        # Never copy an agent or caller's invented quotes/cells into an output snapshot.
        if len(refs) != len(final.source_refs) or any(not catalog.validate_ref(ref) for ref in final.source_refs):
            raise ValueError("Runtime finding contains a source reference outside the captured Atlas evidence")
        findings.append(Finding(
            finding_id=finding_id, investor_id=final.investor_id,
            reported_value=final.reported, expected_value=final.expected, difference=final.difference,
            currency=final.currency, status=status, calculation_id=calculation_id,
            evidence_ids=final.evidence_ids, source_refs=refs, challenger_concern_ids=concern_ids,
            verifier_result_id=verifier_id, explanation=final.explanation,
            actionable_next_step=("Review the supported comparison." if status == "MATCH" else
                                  "Investigate the discrepancy or obtain the missing evidence; record a human review decision."),
            unresolved_questions=[concern.explanation for concern in final.unresolved_concerns],
        ))
    periods = {(term.period_start, term.period_end) for term in contexts.values()
               if term.period_start and term.period_end}
    period = next(iter(periods)) if len(periods) == 1 else None
    reporting_period = f"{period[0].isoformat()} to {period[1].isoformat()}" if period else "Unresolved reporting period"
    funds = {item.fund_name for item in result.findings}
    snapshot = ReviewSnapshot(
        run_id=result.run_id, version=1,
        mode="SYNTHETIC_DEMO" if synthetic else ("LIVE_MODEL" if result.mode == "MODEL" else "LIVE_OFFLINE"),
        fund_name=next(iter(funds)) if len(funds) == 1 else "Unresolved fund scope",
        reporting_period=reporting_period, created_at=result.created_at, frozen_at=datetime.now(timezone.utc),
        source_documents=[document.document for document in catalog.documents],
        rules=rules, calculations=calculations, challenger_concerns=concerns,
        verifier_results=verifiers, findings=findings,
        unresolved_items=[f"{finding.investor_id}: {finding.explanation}" for finding in result.findings if finding.status != "PASS"],
        limitations=result.limitations,
    )
    return ReviewSnapshot.model_validate_json(snapshot.model_dump_json())
