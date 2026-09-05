"""Independent source challenge: no planner calls and no executor reuse.

A valid calculation is not enough: this pass checks the cited row, governing
terms, dates and contradictions against the complete normalized source pack.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime
from decimal import Decimal, DecimalException, ROUND_HALF_UP, localcontext

from app.atlas.models import SourceRef
from .contracts import Challenge, ModelChallenge, Operation, VerificationPlan
from .investigation_evidence import EvidenceStore, NumericInput, source_text


def _flat(text: str) -> str:
    return " ".join(text.split()).casefold()


def _contains(text: str, term: str) -> bool:
    return bool(re.search(r"(?<![\w])" + re.escape(_flat(term)) + r"(?![\w])", _flat(text)))


def _coord(ref: SourceRef) -> tuple[str, int] | None:
    match = re.fullmatch(r"([A-Z]+)(\d+)", ref.cell or "")
    return (match[1], int(match[2])) if match else None


def _labels(store: EvidenceStore, ref: SourceRef) -> str:
    if ref.kind == "CSV_CELL":
        return ref.csv_column or ""
    pos = _coord(ref)
    if pos is None:
        return ""
    column, row = pos
    candidates = [r for r in store.docs[ref.document_id].evidence
                  if r.sheet == ref.sheet and _coord(r)]
    above = sorted([r for r in candidates if _coord(r)[0] == column and _coord(r)[1] < row],
                   key=lambda r: _coord(r)[1], reverse=True)
    left = [r for r in candidates if _coord(r)[1] == row and _coord(r)[0] < column]
    # Above-column headings describe horizontal tables; adjacent left labels
    # describe vertical schedules. Numeric values are never treated as labels.
    texts = [source_text(r) for r in above[:8] + left]
    return " | ".join(t for t in texts if re.search(r"[A-Za-z]{3}", t))


def _same_row(left: SourceRef, right: SourceRef) -> bool:
    if left.document_id != right.document_id or left.kind != right.kind:
        return False
    if left.kind == "CSV_CELL":
        return left.csv_row == right.csv_row
    return left.sheet == right.sheet and _coord(left) and _coord(right) and _coord(left)[1] == _coord(right)[1]


def _date_tokens(text: str) -> list[date]:
    matches = re.findall(r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]+\s+\d{4})\b", text)
    dates = []
    for token in matches:
        for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y"):
            try:
                dates.append(datetime.strptime(token, fmt).date())
                break
            except ValueError:
                continue
    return dates


def _period(text: str) -> tuple[date, date] | None:
    quarters = set(re.findall(r"\bQ([1-4])\s*[-/]?\s*(20\d{2})\b", text, re.I))
    if len(quarters) == 1:
        quarter, year = map(int, next(iter(quarters)))
        month = quarter * 3
        return date(year, month - 2, 1), date(year, month, calendar.monthrange(year, month)[1])
    dates = _date_tokens(text)
    if len(set(dates)) == 2:
        return min(dates), max(dates)
    return None


def _rates(text: str) -> list[Decimal]:
    # Rate interpretation is independent of the analyst's selection. Restrict
    # to sentences that actually describe an annual fee/charge, not dates or IDs.
    rates = []
    for phrase in _sentences(text):
        if re.search(r"annual|per annum|yearly", phrase, re.I) and re.search(r"fee|charge|rate|percentage", phrase, re.I):
            rates.extend(Decimal(token) / Decimal(100) for token in
                         re.findall(r"(?<![\w.])(\d+(?:\.\d+)?)\s*%", phrase))
    return list(dict.fromkeys(rates))


def _sentences(text: str) -> list[str]:
    # Preserve decimal points while distinguishing complete contractual clauses.
    return re.split(r"\.(?!\d)|[!?]", " ".join(text.split()))


def _period_factors(text: str, period: tuple[date, date] | None = None) -> set[Decimal]:
    factors = set()
    for phrase in _sentences(text):
        explicit_label = re.search(r"(?:period|quarter\w*|time|year)\s+(?:factor|fraction|multiplier)", phrase, re.I)
        formula = (re.search(r"quarter\w*|period", phrase, re.I)
                   and re.search(r"annual\s+(?:fee\s+)?rate", phrase, re.I)
                   and re.search(r"\bx\b|×|multipl", phrase, re.I))
        if explicit_label or formula:
            scoped_period = _period(phrase)
            if period is not None and scoped_period is not None and scoped_period != period:
                continue
            if period is not None and re.search(r"quarter", phrase, re.I) and scoped_period is None:
                start, end = period
                if (start.day != 1 or start.month not in {1, 4, 7, 10}
                        or end.year != start.year or end.month != start.month + 2
                        or end.day != calendar.monthrange(end.year, end.month)[1]):
                    continue
            for token in re.findall(r"(?<![\w.,+-])(\d+(?:\.\d+)?)(?![\w.%]|[.,]\d)", phrase):
                value = Decimal(token)
                if Decimal(0) < value <= Decimal(1):
                    factors.add(value)
    return factors


def _contract_limits(text: str, currency: str) -> list[str]:
    reasons = []
    if re.search(r"round[^!?]{0,70}(?:half.even|down|floor|ceiling|whole|integer|nearest\s+(?:pound|dollar|euro))", text, re.I):
        reasons.append("The governing rounding convention is unsupported by penny round-half-up execution.")
    if re.search(r"\b(?:rebate|credit|offset|adjustment|discount|waiver|waived|cap|minimum|maximum)\b", text, re.I):
        reasons.append("The governing agreement specifies an unresolved adjustment or limit to the simple annual charge.")
    if _scaled_money(text):
        reasons.append("The governing agreement uses unresolved monetary scale units.")
    for phrase in _sentences(text):
        if re.search(r"currency|denominat|payable|expressed|amounts?\s+(?:are\s+)?in", phrase, re.I):
            codes = set(re.findall(r"\b(?:GBP|USD|EUR|CHF|JPY|CAD|AUD|NZD|CNY|HKD|SGD)\b", phrase, re.I))
            codes = {code.upper() for code in codes}
            if codes and codes != {currency}:
                reasons.append("The governing agreement's currency does not match the proposed source currency.")
    return reasons


def _scaled_money(text: str) -> bool:
    return bool(re.search(r"thousands?|millions?|000s|000's|(?:GBP|USD|EUR|£|\$|€)\s*['’]?000\b|\(['’]?000\)", text, re.I))


def _compute(node: str | Operation, values: dict[str, Decimal]) -> Decimal:
    if isinstance(node, str):
        return values[node]
    parts = [_compute(child, values) for child in node.operands]
    if node.operation == "multiply":
        answer = Decimal(1)
        for part in parts:
            answer *= part
    elif node.operation == "add":
        answer = sum(parts, Decimal(0))
    elif node.operation == "subtract":
        answer = parts[0] - parts[1]
    elif node.operation == "divide":
        answer = parts[0] / parts[1]
    elif node.operation == "min":
        answer = min(parts)
    else:
        answer = max(parts)
    if not answer.is_finite() or abs(answer) > Decimal("1e30"):
        raise ValueError("independent arithmetic exceeds bounds")
    return answer


def challenge(plan: VerificationPlan, result: dict, store: EvidenceStore,
              tolerance: Decimal = Decimal("0.01"), *, semantic_review: ModelChallenge | None = None) -> Challenge:
    checks = {key: False for key in (
        "evidence_ids", "arithmetic", "investor_identity", "fund_identity", "currency",
        "rate_applicability", "effective_date", "fee_base", "period_interpretation", "contradictions")}
    if not tolerance.is_finite() or tolerance < 0:
        return Challenge(status="CHALLENGE", checks=checks, reasons=["Invalid configured comparison tolerance."])
    conflicts: list[str] = []
    missing: list[str] = []
    try:
        plan = VerificationPlan.model_validate(plan.model_dump())
        refs = {name: store.get(spec.evidence_id) for name, spec in plan.inputs.items()}
        for eid in plan.context_evidence_ids:
            store.get(eid)
        checks["evidence_ids"] = True
    except (ValueError, KeyError) as exc:
        return Challenge(status="CHALLENGE", checks=checks, reasons=[str(exc)])
    try:
        with localcontext() as ctx:
            ctx.prec = 50
            values = {name: store.number(spec) for name, spec in plan.inputs.items()}
            raw = _compute(plan.operation, values)
            expected = raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            reported = values[plan.reported_input]
            difference = reported - expected
            wanted = "DISCREPANCY" if abs(difference) > tolerance else "MATCH"
            checks["arithmetic"] = (
                Decimal(result["expected"]) == expected and Decimal(result["reported"]) == reported
                and Decimal(result["difference"]) == difference and result["status"] == wanted
                and Decimal(result["tolerance"]) == tolerance
                and Decimal(result["unrounded_expected"]) == raw
                and result["rounding"] == "ROUND_HALF_UP_0.01"
                and {k: Decimal(v) for k, v in result["values"].items()} == values)
            if not checks["arithmetic"]:
                conflicts.append("Independent Decimal calculation does not match the proposed result.")
    except (ValueError, KeyError, TypeError, DecimalException) as exc:
        return Challenge(status="CHALLENGE", checks=checks, reasons=[f"Arithmetic/input challenge: {exc}"])

    reported_ref = refs[plan.reported_input]
    table = store.docs[reported_ref.document_id]
    table_text = store.document_text(reported_ref.document_id)
    entity_refs = [r for r in table.evidence if _flat(source_text(r)) == _flat(plan.entity_id)]
    horizontal = any(_same_row(r, reported_ref) for r in entity_refs)
    vertical = (not horizontal and len(entity_refs) == 1
                and entity_refs[0].sheet == reported_ref.sheet
                and bool(re.search(r"investor|client|account|entity", _labels(store, entity_refs[0]), re.I)))
    checks["investor_identity"] = bool(horizontal or vertical)
    if not checks["investor_identity"]:
        conflicts.append("Reported amount is not linked to the claimed investor/account in its source row.")
    checks["fund_identity"] = bool(plan.fund_name and _contains(table_text, plan.fund_name))
    if not checks["fund_identity"]:
        missing.append("The reported source does not establish the claimed fund identity.")

    currency_sources = [source_text(r).strip().upper() for r in table.evidence
                        if _same_row(r, reported_ref) and re.search(r"currency|ccy", _labels(store, r), re.I)
                        and source_text(r).strip().upper() in {"GBP", "USD", "EUR"}]
    currency_symbols = {"£": "GBP", "$": "USD", "€": "EUR"}
    for ref in refs.values():
        if ref.kind != "PDF_TEXT":
            for symbol, code in currency_symbols.items():
                if symbol in (ref.number_format or "") or symbol in source_text(ref):
                    currency_sources.append(code)
    if currency_sources:
        checks["currency"] = set(currency_sources) == {plan.currency}
        if not checks["currency"]:
            conflicts.append("The declared currency contradicts the source row or monetary inputs.")
    else:
        missing.append("Source currency is not established for the reported amount.")
    if horizontal:
        explicit_funds = [source_text(r) for r in table.evidence if _same_row(r, reported_ref)
                          and re.fullmatch(r"fund(?: name)?", _labels(store, r).split(" | ")[0].strip(), re.I)]
        if explicit_funds and any(_flat(fund) != _flat(plan.fund_name) for fund in explicit_funds):
            checks["fund_identity"] = False
            conflicts.append("The row-specific fund identity disagrees with the proposed fund.")

    used = {name for name in refs if name != plan.reported_input}
    if horizontal:
        for name in used:
            ref = refs[name]
            if ref.kind != "PDF_TEXT" and not _same_row(ref, reported_ref):
                conflicts.append(f"Input {name} belongs to a different source row or investor.")
    if vertical:
        for name in used:
            ref = refs[name]
            if ref.kind != "PDF_TEXT" and (ref.document_id != reported_ref.document_id or ref.sheet != reported_ref.sheet):
                conflicts.append(f"Input {name} belongs to a different schedule from the reported amount.")
    if not re.search(r"reported|charged|amount|total|net|fee|charge", _labels(store, reported_ref), re.I):
        missing.append("The reported operand lacks an amount/charge/total heading.")
    for name, ref in refs.items():
        if (plan.inputs[name].unit == "money" or name == plan.reported_input) and _scaled_money(_labels(store, ref)):
            missing.append("A monetary operand uses unresolved scale units in its source heading.")
    if any(re.search(r"amounts?|figures?|values?|fees?|charges?", phrase, re.I) and _scaled_money(phrase)
           for phrase in _sentences(table_text)):
        missing.append("The source schedule contains unresolved monetary scale instructions.")

    if plan.check_type == "annual_charge":
        rate_names = [n for n in used if plan.inputs[n].unit == "rate"]
        factor_names = [n for n in used if plan.inputs[n].unit == "factor"]
        base_names = [n for n in used if plan.inputs[n].unit == "money"]
        if len(rate_names) != 1 or len(factor_names) != 1 or len(base_names) != 1:
            conflicts.append("Annual charge requires exactly one source-backed base, annual rate and period factor.")
        elif (plan.operation.operation != "multiply" or len(plan.operation.operands) != 3
              or any(not isinstance(arg, str) for arg in plan.operation.operands)
              or set(plan.operation.operands) != used):
            conflicts.append("Annual charge must multiply its three evidenced inputs once each.")
        else:
            rate_name, factor_name, base_name = rate_names[0], factor_names[0], base_names[0]
            base_ref, factor_ref, rate_ref = refs[base_name], refs[factor_name], refs[rate_name]
            checks["fee_base"] = bool(re.search(r"base|capital|commitment|balance|principal", _labels(store, base_ref), re.I))
            if not checks["fee_base"]:
                missing.append("The monetary operand is not supported as the charge base by its source label.")
            if _scaled_money(_labels(store, base_ref)):
                checks["fee_base"] = False
                missing.append("The base uses a scale multiplier not resolved by this bounded calculation.")
            factor_label = _labels(store, factor_ref)
            period = _period(table_text)
            if period is None:
                missing.append("A unique reporting start/end period cannot be established.")
            governing: list[tuple[str, list[Decimal], str]] = []
            matching_letters = []
            for document in store.documents:
                if not any(r.kind == "PDF_TEXT" for r in document.evidence):
                    continue
                text = store.document_text(document.document.document_id)
                if not plan.fund_name or not _contains(text, plan.fund_name):
                    continue
                rates = _rates(text)
                if _contains(text, plan.entity_id):
                    matching_letters.append((document, text, rates))
                elif re.search(r"default\s+annual|annual[^.!?]{0,70}default", text, re.I):
                    governing.append((document.document.document_id, rates, text))
            applicable_texts = [text for _, _, text in governing]
            for text in applicable_texts:
                missing.extend(_contract_limits(text, plan.currency))
            defaults = {rate for _, rates, _ in governing for rate in rates}
            applicable = []
            date_ok = period is not None
            for document, text, rates in matching_letters:
                if re.search(r"no\s+management.fee(?:\s+rate)?\s+variation", text, re.I):
                    missing.extend(_contract_limits(text, plan.currency))
                    applicable_texts.append(text)
                    continue
                if not rates:
                    missing.append("An investor-specific agreement does not establish an unambiguous annual rate.")
                    continue
                effective = re.search(r"effective\s+(?:from|on|as\s+of)\s+(.{1,45})", " ".join(text.split()), re.I)
                starts = _date_tokens(effective.group(1)) if effective else []
                expires = re.search(r"(?:expires?\s+(?:on\s+)?|effective\s+(?:to|until)\s+)(.{1,40})", text, re.I)
                ends = _date_tokens(expires.group(1)) if expires else []
                if len(starts) != 1 or period is None:
                    date_ok = False
                    missing.append("An investor-specific rate lacks a provable effective date for the reporting period.")
                    continue
                if starts[0] > period[1] or ends and ends[0] < period[0]:
                    continue
                if starts[0] > period[0] or ends and ends[0] < period[1]:
                    date_ok = False
                    missing.append("An investor-specific term changes within the reporting period; proration is unresolved.")
                    continue
                missing.extend(_contract_limits(text, plan.currency))
                applicable_texts.append(text)
                applicable.extend((rate, document.document.document_id) for rate in rates)
            contractual_factors = set().union(*(_period_factors(text, period) for text in applicable_texts))
            checks["period_interpretation"] = bool(
                period and re.search(r"period|quarter|factor", factor_label, re.I)
                and contractual_factors == {values[factor_name]})
            if contractual_factors and contractual_factors != {values[factor_name]}:
                conflicts.append("The selected period factor conflicts with governing contractual factors.")
            elif not checks["period_interpretation"]:
                missing.append("The selected factor is not explicitly supported for the established reporting period.")
            candidate_rates = {rate for rate, _ in applicable} if applicable else defaults
            checks["effective_date"] = date_ok
            if len(candidate_rates) > 1:
                conflicts.append("Conflicting governing annual rates exist for this investor and period.")
            elif len(candidate_rates) == 1:
                correct = next(iter(candidate_rates))
                checks["rate_applicability"] = values[rate_name] == correct
                allowed_docs = {doc for _, doc in applicable} if applicable else {doc for doc, _, _ in governing}
                if rate_ref.document_id not in allowed_docs:
                    checks["rate_applicability"] = False
                    conflicts.append("The selected annual rate is not cited from the applicable governing agreement.")
                if values[rate_name] != correct:
                    conflicts.append("Selected rate conflicts with the independently established applicable annual rate.")
            else:
                missing.append("No unique governing annual rate is established for this investor and fund.")

            # Registers supply corroboration and expected-document completeness,
            # even when the analyst did not cite them in its proposed check.
            for document in store.documents:
                csv = [r for r in document.evidence if r.kind == "CSV_CELL"]
                investor_rows = {r.csv_row for r in csv if _flat(source_text(r)) == _flat(plan.entity_id)}
                for row in investor_rows:
                    cells = {str(r.csv_column).casefold(): r for r in csv if r.csv_row == row}
                    for label, ref in cells.items():
                        if re.search(r"base|capital|commitment", label):
                            try:
                                other = store.number(NumericInput(evidence_id=ref.evidence_id, unit="money"))
                                if other != values[base_name]:
                                    checks["fee_base"] = False
                                    conflicts.append("The investor register contradicts the fee base used in the calculation.")
                            except ValueError:
                                missing.append("The investor register base cannot be numerically corroborated.")
                    expected_letter = any("expected" in label and _flat(source_text(ref)) in {"yes", "true", "1"}
                                          for label, ref in cells.items())
                    if expected_letter and not matching_letters:
                        missing.append("The investor register expects an investor-specific agreement that is absent.")
    elif plan.check_type in ("quantity_price", "gross_less_deductions"):
        labels = {name: _labels(store, refs[name]) for name in used}
        if plan.check_type == "quantity_price":
            role_patterns = (r"quantity|units|count|hours", r"unit.?price|price|hourly|unit.?rate")
            shape = plan.operation.operation == "multiply" and len(used) == 2
        else:
            role_patterns = (r"gross", r"deduction|withhold|discount|tax")
            shape = plan.operation.operation == "subtract" and len(used) == 2
        operands = plan.operation.operands
        simple = len(operands) == 2 and all(isinstance(arg, str) for arg in operands) and len(set(operands)) == 2
        proven = bool(shape and simple and any(
            re.search(role_patterns[0], labels[left], re.I) and re.search(role_patterns[1], labels[right], re.I)
            for left, right in ([operands] if plan.check_type == "gross_less_deductions"
                                else [operands, list(reversed(operands))])))
        if not proven:
            missing.append("The source labels do not establish the proposed arithmetic relationship.")
        checks.update(rate_applicability=proven, effective_date=True, fee_base=proven, period_interpretation=True)
    else:
        # An independently requested semantic review can support a novel DSL
        # relationship. It never bypasses the identity, currency, source-row,
        # arithmetic, or bound checks above, nor the known-template rules.
        semantic_support = False
        if semantic_review is not None:
            try:
                reviewed = ModelChallenge.model_validate(semantic_review.model_dump())
                for evidence_id in reviewed.evidence_ids:
                    store.get(evidence_id)
                semantic_support = reviewed.status == "PASS" and bool(reviewed.evidence_ids)
            except (ValueError, AttributeError):
                conflicts.append("Independent semantic review contains invalid or unresolved source evidence.")
        if not semantic_support:
            missing.append("This model-proposed relationship has no independently proven source semantics.")
        checks.update(rate_applicability=semantic_support, effective_date=semantic_support,
                      fee_base=semantic_support, period_interpretation=semantic_support)
    checks["contradictions"] = not conflicts
    if conflicts:
        return Challenge(status="CHALLENGE", checks=checks, reasons=conflicts + missing)
    if missing or not all(checks.values()):
        return Challenge(status="INSUFFICIENT_EVIDENCE", checks=checks, reasons=missing or ["Independent semantic support is incomplete."])
    return Challenge(status="PASS", checks=checks, reasons=[])
