"""Independent source challenge and deterministic monetary verification.

The analyst supplies proposals, not facts. Both checks rebuild their source
interpretation from the immutable ATLAS evidence catalog. No calculation uses
an analyst's proposed value, quote, source hash, or arithmetic as authority.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext

from pydantic import TypeAdapter

from .evidence import EvidenceCatalog, SourceTerms, build_context
from .models import Amount, AnalysisResult, Challenge, Finding, RedTeamResult, Verification, exact_decimal


_CALCULATION_FIELDS = (
    "fee_base", "annual_rate", "period_fraction", "reported", "currency",
    "period_start", "period_end",
)
_CLAIM_FIELDS = ("fund_name", "investor_id", *_CALCULATION_FIELDS)
_DECIMAL_FIELDS = {"fee_base", "annual_rate", "period_fraction", "reported"}
_PENNY = Decimal("0.01")
_AMOUNT_ADAPTER = TypeAdapter(Amount)


def calculate_fee(fee_base: Decimal, annual_rate: Decimal, period_fraction: Decimal) -> Decimal:
    """Exact fee calculation; binary floats and non-finite inputs are rejected."""
    base, rate, fraction = (exact_decimal(value) for value in (fee_base, annual_rate, period_fraction))
    if base < 0 or not 0 <= rate <= 1 or not 0 <= fraction <= 1:
        raise ValueError("Fee base must be nonnegative and rate/period fraction must be between zero and one")
    with localcontext() as context:
        context.prec = 96
        return (base * rate * fraction).quantize(_PENNY, rounding=ROUND_HALF_UP)


def _canonical_ids(catalog: EvidenceCatalog, ids: list[str]) -> list[str]:
    """Return only IDs actually owned by the canonical source catalog."""
    result = []
    for evidence_id in dict.fromkeys(ids):
        try:
            catalog.resolve([evidence_id])
        except (ValueError, KeyError):
            continue
        result.append(evidence_id)
    return result


def _all_proposed_ids(finding: Finding) -> list[str]:
    ids = [*finding.evidence_ids]
    for claim in finding.claims:
        ids.extend(claim.evidence_ids)
    if finding.calculation is not None:
        for field_ids in finding.calculation.input_evidence.values():
            ids.extend(field_ids)
    return list(dict.fromkeys(ids))


def _matches(value: object, expected: object, field: str) -> bool:
    if expected is None:
        return False
    try:
        if field in _DECIMAL_FIELDS:
            return exact_decimal(value) == exact_decimal(expected)
        if field in {"period_start", "period_end"}:
            parsed = date.fromisoformat(value) if isinstance(value, str) else value
            return parsed == expected
        return value == expected
    except (ValueError, TypeError, InvalidOperation):
        return False


def _challenge(code: str, terms: SourceTerms | None, investor_id: str, explanation: str,
               catalog: EvidenceCatalog, *, ids: list[str] | None = None,
               insufficient: bool = False) -> Challenge:
    return Challenge(
        code=code, investor_id=investor_id, explanation=explanation,
        evidence_ids=_canonical_ids(catalog, ids if ids is not None else (terms.evidence_ids if terms else [])),
        insufficient_evidence=insufficient,
    )


def _proposal_challenges(finding: Finding, terms: SourceTerms,
                         catalog: EvidenceCatalog) -> list[Challenge]:
    """Check source assertions, including the field-to-evidence relationship."""
    challenges: list[Challenge] = []

    def add(code: str, explanation: str, *, ids: list[str] | None = None) -> None:
        challenges.append(_challenge(code, terms, finding.investor_id, explanation, catalog, ids=ids))

    proposed_ids = _all_proposed_ids(finding)
    if set(proposed_ids) != set(_canonical_ids(catalog, proposed_ids)):
        add("UNKNOWN_EVIDENCE", "The proposal cites evidence that does not exist in the ATLAS source catalog.")
    if set(finding.evidence_ids) != set(terms.evidence_ids):
        add("EVIDENCE_SCOPE_MISMATCH", "The finding omits required source evidence or includes evidence from a different investor/source scope.")
    if finding.fund_name != terms.fund_name:
        add("WRONG_FUND", "The proposed fund does not match the governing LPA and investor-source relationship.")
    if finding.missing_evidence and not terms.missing_evidence:
        add("UNSUPPORTED_MISSING_EVIDENCE", "The proposal asserts missing evidence although the required source terms are supported.")

    claims_by_field = {field: [claim for claim in finding.claims if claim.field == field] for field in _CLAIM_FIELDS}
    for field, claims in claims_by_field.items():
        expected = getattr(terms, field)
        field_ids = terms.input_evidence.get(field, [])
        if expected is None:
            if claims:
                add("UNSUPPORTED_CLAIM", f"The proposal asserts {field}, but that source fact is unresolved.", ids=field_ids)
            continue
        if len(claims) != 1:
            add("MISSING_OR_DUPLICATE_CLAIM", f"Exactly one source-supported {field} claim is required.", ids=field_ids)
            continue
        claim = claims[0]
        if not _matches(claim.value, expected, field):
            add("CONTRADICTORY_CLAIM", f"The {field} claim contradicts the governing source evidence.", ids=field_ids)
        if not field_ids or set(claim.evidence_ids) != set(field_ids):
            add("CLAIM_EVIDENCE_MISMATCH", f"The {field} claim is not bound to its complete source-specific evidence.", ids=field_ids)

    calculation = finding.calculation
    if calculation is None:
        if not terms.missing_evidence:
            add("MISSING_CALCULATION", "The proposal omits a calculation despite complete supported source inputs.")
        return challenges
    for field in _CALCULATION_FIELDS:
        expected = getattr(terms, field)
        field_ids = terms.input_evidence.get(field, [])
        if not _matches(getattr(calculation, field), expected, field):
            code = {"fee_base": "WRONG_FEE_BASE", "annual_rate": "WRONG_APPLICABLE_RATE"}.get(field, "WRONG_CALCULATION_INPUT")
            add(code, f"Proposed {field} does not match the independently interpreted governing source value.", ids=field_ids)
        if not field_ids or set(calculation.input_evidence.get(field, [])) != set(field_ids):
            add("CALCULATION_EVIDENCE_MISMATCH", f"The {field} calculation input omits required evidence or is bound to unrelated evidence.", ids=field_ids)
    for field, ids in calculation.input_evidence.items():
        if field not in terms.input_evidence or set(ids) != set(terms.input_evidence[field]):
            add("UNSUPPORTED_INPUT_REFERENCE", f"The calculation includes an unsupported evidence binding for {field}.")
    return challenges


def red_team(analysis: AnalysisResult, catalog: EvidenceCatalog) -> RedTeamResult:
    """Challenge the analyst independently, without changing its proposal."""
    source_terms = build_context(catalog)
    by_investor = {terms.investor_id: terms for terms in source_terms}
    counts = Counter(finding.investor_id for finding in analysis.findings)
    challenges: list[Challenge] = []
    if not source_terms:
        challenges.append(_challenge("NO_INVESTOR_EVIDENCE", None, "case",
                                     "No source-linked investor review can be established.", catalog, insufficient=True))
    for investor_id, count in counts.items():
        terms = by_investor.get(investor_id)
        if terms is None:
            challenges.append(_challenge("UNKNOWN_INVESTOR", None, investor_id,
                                         "The investor does not exist in the supplied canonical source context.", catalog))
        if count != 1:
            challenges.append(_challenge("DUPLICATE_FINDING", terms, investor_id,
                                         "The proposal contains more than one finding for this investor.", catalog))
    for terms in source_terms:
        if terms.investor_id not in counts:
            challenges.append(_challenge("OMITTED_INVESTOR", terms, terms.investor_id,
                                         "The analyst omitted an investor present in the source records.", catalog))
        if terms.missing_evidence:
            challenges.append(_challenge("MISSING_SOURCE", terms, terms.investor_id,
                                         "; ".join(terms.missing_evidence), catalog, insufficient=True))
    for finding in analysis.findings:
        terms = by_investor.get(finding.investor_id)
        if terms is not None:
            challenges.extend(_proposal_challenges(finding, terms, catalog))
    status = "PASS"
    if any(not challenge.insufficient_evidence for challenge in challenges):
        status = "CHALLENGE"
    elif challenges:
        status = "INSUFFICIENT_EVIDENCE"
    return RedTeamResult(status=status, challenges=challenges)


def verify(analysis: AnalysisResult, catalog: EvidenceCatalog) -> list[Verification]:
    """Recompute all investors from source facts, then test the analyst proposal.

    A financial discrepancy is a FAILED comparison even if the analyst correctly
    described it. Missing evidence is always CANNOT_VERIFY, never an amount pass.
    """
    source_terms = build_context(catalog)
    proposals: dict[str, list[Finding]] = {}
    for finding in analysis.findings:
        proposals.setdefault(finding.investor_id, []).append(finding)
    results: list[Verification] = []
    for terms in source_terms:
        findings = proposals.pop(terms.investor_id, [])
        checks = {"single_proposal": len(findings) == 1}
        explanations: list[str] = []
        supported_fields = (*_CALCULATION_FIELDS, "tolerance")
        checks["source_complete"] = not terms.missing_evidence and all(getattr(terms, field) is not None for field in supported_fields)
        checks["source_evidence_complete"] = all(terms.input_evidence.get(field) for field in (*_CLAIM_FIELDS, "tolerance"))
        if not checks["single_proposal"]:
            explanations.append("Exactly one analyst proposal is required for each source investor.")
        source_ids = _canonical_ids(catalog, terms.evidence_ids)
        checks["canonical_source_references"] = set(source_ids) == set(terms.evidence_ids)
        proposal_problems = _proposal_challenges(findings[0], terms, catalog) if len(findings) == 1 else []
        checks["proposal_supported"] = len(findings) == 1 and not proposal_problems
        explanations.extend(problem.explanation for problem in proposal_problems)
        if not checks["source_complete"] or not checks["source_evidence_complete"] or not checks["canonical_source_references"]:
            explanations.extend(terms.missing_evidence or ["Required source terms or source-specific evidence bindings are incomplete."])
            results.append(Verification(
                investor_id=terms.investor_id, status="CANNOT_VERIFY", reported=terms.reported,
                currency=terms.currency, evidence_ids=source_ids, checks=checks,
                explanations=list(dict.fromkeys(explanations)),
            ))
            continue
        try:
            expected = calculate_fee(terms.fee_base, terms.annual_rate, terms.period_fraction)
            reported, tolerance = exact_decimal(terms.reported), exact_decimal(terms.tolerance)
            with localcontext() as context:
                context.prec = 96
                difference = reported - expected
                checks["reported_whole_pennies"] = reported == reported.quantize(_PENNY, rounding=ROUND_HALF_UP)
                checks["valid_tolerance"] = tolerance >= 0
                checks["amount_within_tolerance"] = tolerance >= 0 and abs(difference) <= tolerance
            # Individually representable source amounts can have a difference
            # outside the public contract's bounds. Fail closed, not with a 500.
            _AMOUNT_ADAPTER.validate_python(expected)
            _AMOUNT_ADAPTER.validate_python(difference)
            checks["valid_review_dates"] = terms.period_start <= terms.period_end
            checks["valid_currency"] = isinstance(terms.currency, str) and len(terms.currency) == 3 and terms.currency.isalpha() and terms.currency.isupper()
        except (ValueError, TypeError, InvalidOperation) as error:
            checks["valid_source_calculation"] = False
            results.append(Verification(
                investor_id=terms.investor_id, status="CANNOT_VERIFY", reported=terms.reported,
                currency=terms.currency, evidence_ids=source_ids, checks=checks,
                explanations=[*explanations, f"Source calculation cannot be verified: {error}"],
            ))
            continue
        calculation = findings[0].calculation if len(findings) == 1 else None
        checks["claimed_expected_correct"] = calculation is not None and (calculation.claimed_expected is None or calculation.claimed_expected == expected)
        checks["claimed_difference_correct"] = calculation is not None and (calculation.claimed_difference is None or calculation.claimed_difference == difference)
        if not checks["claimed_expected_correct"]:
            explanations.append("The analyst's claimed expected amount is absent with its calculation or disagrees with trusted Decimal arithmetic.")
        if not checks["claimed_difference_correct"]:
            explanations.append("The analyst's claimed difference is absent with its calculation or disagrees with reported minus expected.")
        if not checks["amount_within_tolerance"]:
            explanations.append(f"Reported {reported} minus expected {expected} is {difference} {terms.currency}; tolerance is {tolerance}.")
        if not checks["reported_whole_pennies"]:
            explanations.append("Reported amount contains a fractional penny and requires human review.")
        passed = all(checks.values())
        if passed:
            explanations.append("All source, applicability, evidence, and exact Decimal comparison checks passed.")
        results.append(Verification(
            investor_id=terms.investor_id, status="PASSED" if passed else "FAILED",
            reported=reported, expected=expected, difference=difference, currency=terms.currency,
            calculation="fee_base × applicable_annual_rate × period_fraction; ROUND_HALF_UP to 0.01; difference = reported − expected",
            evidence_ids=source_ids, checks=checks, explanations=list(dict.fromkeys(explanations)),
        ))
    for investor_id in proposals:
        results.append(Verification(
            investor_id=investor_id, status="CANNOT_VERIFY",
            checks={"known_source_investor": False},
            explanations=["No canonical source-linked terms exist for the proposed investor."],
        ))
    if not results:
        results.append(Verification(
            investor_id="case", status="CANNOT_VERIFY", checks={"source_complete": False},
            explanations=["No source-linked investor review can be established."],
        ))
    return results
