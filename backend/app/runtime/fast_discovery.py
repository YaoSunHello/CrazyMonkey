"""Bounded, source-linked consistency checks and review-only anomalies.

Labels discover arithmetic relationships; they do not establish contractual
authority. No anomaly in this module authorizes a source-file correction.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from hashlib import sha256
import re

from .contracts import NumericInput
from .fast_dsl import FastCheck, _parse_date
from .investigation_evidence import EvidenceStore, source_text
from .semantics import Row, category, words


MAX_CHECKS = 40
MAX_NOTES = 100
_MONEY = {"base", "reported", "price", "total", "gross", "deductions", "net"}
_NUMERIC = _MONEY | {"rate", "factor", "quantity"}
_TOTALS = {"total", "subtotal", "sub total", "grand total", "overall total"}
_CURRENCIES = {"GBP", "USD", "EUR"}
_SYMBOLS = {"£": "GBP", "$": "USD", "€": "EUR"}


def _unit(field: str) -> str:
    return "money" if field in _MONEY else field if field in {"rate", "factor"} else "number"


def _spec(row: Row, field: str) -> NumericInput:
    return NumericInput(evidence_id=row.fields[field].evidence_id, unit=_unit(field))


def _ids(row: Row, fields=()) -> list[str]:
    refs = [row.fields[name].evidence_id for name in ("entity", *fields) if name in row.fields]
    refs.extend(row.labels[name].evidence_id for name in fields if name in row.labels)
    return list(dict.fromkeys(refs))[:200]


def _table(row: Row) -> tuple:
    entity = row.fields["entity"]
    # Header identity also separates two independent tables on the same sheet.
    header = tuple(sorted(ref.evidence_id for ref in row.labels.values()))
    return row.document_id, entity.sheet or "<csv>", header


def _note(notes: list, row: Row, code: str, reason: str, *, fields=(),
          status="CANNOT_VERIFY", evidence_ids=None, check_id=None) -> None:
    if len(notes) >= MAX_NOTES:
        return
    value = {
        "status": status, "code": code, "entity_id": row.entity_id[:150],
        "reason": reason, "evidence_ids": list(dict.fromkeys(evidence_ids or _ids(row, fields)))[:200],
    }
    if check_id:
        value["check_id"] = check_id
    notes.append(value)


def _currency(row: Row) -> tuple[str | None, bool]:
    declared = source_text(row.fields["currency"]).strip().upper() if "currency" in row.fields else ""
    if declared and declared not in _CURRENCIES:
        return None, False
    currencies = {declared} if declared else set()
    for name in _MONEY.intersection(row.fields):
        ref = row.fields[name]
        text = source_text(ref).strip("() ")
        prefix = re.match(r"^(GBP|USD|EUR|£|\$|€)\s*(?=[+-]?\d)", text)
        if prefix:
            currencies.add(_SYMBOLS.get(prefix[1], prefix[1]))
        number_format = re.sub(r"\[\$-[^\]]+\]", "", ref.number_format or "")
        currencies.update(currency for symbol, currency in _SYMBOLS.items() if symbol in number_format)
        currencies.update(re.findall(r"\b(?:GBP|USD|EUR)\b", number_format))
    if len(currencies) > 1:
        return None, False
    return next(iter(currencies), None), True


def _check(row: Row, name: str, operation: str, inputs: list[NumericInput], *,
           compare_to=None, currency=None, context=(), source="deterministic",
           check_type="consistency", rationale: str) -> FastCheck:
    evidence = list(dict.fromkeys([*(spec.evidence_id for spec in inputs),
                                  *([compare_to.evidence_id] if compare_to else []), *context]))
    identity = sha256((name + "|" + "|".join(evidence)).encode()).hexdigest()[:24]
    return FastCheck(
        check_id=f"{source}-{identity}", title=f"{name}: {row.entity_id}"[:200],
        entity_id=row.entity_id[:150], fund_name=row.fund_name[:200], operation=operation,
        inputs=inputs, compare_to=compare_to, currency=currency, rationale=rationale,
        context_evidence_ids=evidence[:200], source=source, check_type=check_type,
    )


def consistency_checks(store: EvidenceStore, rows: list[Row]) -> tuple[list[FastCheck], list[dict]]:
    """Return at most 40 arithmetic/date checks and 100 source-linked notes."""
    checks: list[FastCheck] = []
    notes: list[dict] = []
    groups: dict[tuple, list[Row]] = defaultdict(list)
    row_state: dict[int, tuple[set[str], str | None, bool]] = {}
    for row in rows:
        groups[_table(row)].append(row)
        valid = set()
        declared_fields = set(row.labels)
        declared_fields.update(category(header) for header in store.docs[row.document_id].csv_headers)
        for field in sorted((_NUMERIC | {"start", "end", "currency"}).intersection(declared_fields)):
            if field not in row.fields or not source_text(row.fields[field]).strip():
                _note(notes, row, "MISSING_CELL", f"The table declares a {field} column but this row has no supported value.", fields=(field,))
        for field in sorted(_NUMERIC.intersection(row.fields)):
            try:
                store.number(_spec(row, field))
                valid.add(field)
            except ValueError:
                _note(notes, row, "INVALID_PERCENTAGE" if field == "rate" else "INVALID_NUMERIC_INPUT",
                      f"The {field} source cannot supply an unambiguous supported {_unit(field)} value.", fields=(field,))
        currency, compatible = _currency(row)
        if not compatible:
            _note(notes, row, "CURRENCY_CONFLICT", "Declared or cell currencies are inconsistent or unsupported; money relationships were withheld.", fields=tuple(sorted(_MONEY | {"currency"})))
        row_state[id(row)] = valid, currency, compatible
        if words(row.entity_id) in _TOTALS:
            continue
        relationships = (
            ("Quantity times unit price", "MULTIPLY", ("quantity", "price"), "total", "quantity_price"),
            ("Gross less deductions", "SUBTRACT", ("gross", "deductions"), "net", "gross_less_deductions"),
        )
        if compatible:
            for title, operation, fields, comparator, check_type in relationships:
                if set((*fields, comparator)).issubset(valid) and len(checks) < MAX_CHECKS:
                    checks.append(_check(row, title, operation, [_spec(row, field) for field in fields],
                                         compare_to=_spec(row, comparator), currency=currency,
                                         context=_ids(row, (*fields, comparator, "currency")), check_type=check_type,
                                         rationale="Reconcile the explicitly labelled values within this source row. This checks schedule arithmetic only; contractual applicability needs separate review."))
        if {"start", "end"}.issubset(row.fields):
            try:
                left, right = (_parse_date(source_text(row.fields[field]).strip()) for field in ("start", "end"))
                if type(left) is not type(right):
                    raise ValueError
                # A same-day inclusive reporting period is valid, so do not
                # impose the DSL's strictly-before predicate on equal dates.
                if left == right:
                    continue
                left < right  # Reject mixed timezone-aware/naive timestamps.
                if len(checks) < MAX_CHECKS:
                    checks.append(_check(row, "Period start precedes end", "DATE_BEFORE",
                                         [_spec(row, "start"), _spec(row, "end")], context=_ids(row, ("start", "end")),
                                         rationale="The explicitly labelled reporting start must precede its distinct reporting end."))
            except (ValueError, TypeError):
                _note(notes, row, "AMBIGUOUS_DATE", "The period dates cannot be compared without guessing a date format or timezone.", fields=("start", "end"))
    for grouped in groups.values():
        all_details: list[Row] = []
        section_details: list[Row] = []
        for row in grouped:
            label = words(row.entity_id)
            if label not in _TOTALS:
                all_details.append(row)
                section_details.append(row)
                continue
            details = all_details if label in {"grand total", "overall total"} else section_details
            valid, currency, compatible = row_state[id(row)]
            for field in sorted({"reported", "total", "gross", "deductions", "net"}.intersection(valid)):
                if not details:
                    continue
                if len(details) > 16:
                    _note(notes, row, "TOTAL_OPERAND_LIMIT", "This total has more than the supported 16 directly cited detail rows.", fields=(field,))
                    continue
                detail_states = [row_state[id(detail)] for detail in details]
                if not compatible or any(field not in state[0] or not state[2] or state[1] != currency for state in detail_states):
                    _note(notes, row, "TOTAL_INCOMPLETE", "The total cannot include every preceding detail row with valid values and a consistent currency.", fields=(field,))
                    continue
                if len(checks) < MAX_CHECKS:
                    checks.append(_check(row, f"Sum of {field} detail rows", "SUM", [_spec(detail, field) for detail in details],
                                         compare_to=_spec(row, field), currency=currency,
                                         context=[*_ids(row, (field, "currency")), *[detail.fields["entity"].evidence_id for detail in details]],
                                         rationale="Reconcile an explicitly labelled total with every preceding detail row in its table section; subtotal rows are excluded from the grand total."))
            section_details = []
    return checks[:MAX_CHECKS], notes[:MAX_NOTES]


def anomaly_checks(store: EvidenceStore, rows: list[Row]) -> tuple[list[FastCheck], list[dict]]:
    """Expose duplicates as REVIEW_REQUIRED candidates, never patch proof.

Predicate results only establish equality. Repeated IDs/amounts may be valid;
callers must keep source='anomaly' findings under human review.
"""
    checks: list[FastCheck] = []
    notes: list[dict] = []
    groups: dict[tuple, list[Row]] = defaultdict(list)
    for row in rows:
        if words(row.entity_id) not in _TOTALS:
            groups[_table(row)].append(row)
    for grouped in groups.values():
        identities: dict[str, list[Row]] = defaultdict(list)
        amounts: dict[tuple, list[Row]] = defaultdict(list)
        for row in grouped:
            identities[row.entity_id.strip()].append(row)
            currency, compatible = _currency(row)
            if not compatible:
                continue
            for field in sorted({"reported", "total", "gross", "net"}.intersection(row.fields)):
                try:
                    value = store.number(_spec(row, field))
                except ValueError:
                    continue
                if value != Decimal(0):
                    amounts[(field, currency, value)].append(row)
        for duplicates in identities.values():
            for row in duplicates[1:]:
                first = duplicates[0]
                evidence = [first.fields["entity"].evidence_id, row.fields["entity"].evidence_id]
                check = _check(row, "Repeated identifier", "NOT_EQUAL", [_spec(first, "entity"), _spec(row, "entity")],
                               context=evidence, source="anomaly", check_type="anomaly",
                               rationale="The same identifier appears more than once within one source table. This can be legitimate and requires human review; no replacement value is established.")
                if len(checks) < MAX_CHECKS:
                    checks.append(check)
                    _note(notes, row, "DUPLICATE_IDENTIFIER", "Repeated identifier within one table; establish whether multiple rows are intentional before taking action.",
                          status="REVIEW_REQUIRED", evidence_ids=evidence, check_id=check.check_id)
        for (field, currency, _value), repeated in amounts.items():
            # Two matching invoice/fee values are commonplace. Require at least
            # three different entities before surfacing this weak signal.
            unique = {row.entity_id.strip() for row in repeated}
            if len(unique) < 3:
                continue
            first = repeated[0]
            other = next(row for row in repeated if row.entity_id.strip() != first.entity_id.strip())
            evidence = [ref for row in repeated[:16] for ref in _ids(row, (field,))]
            check = _check(other, f"Repeated nonzero {field} values", "NOT_EQUAL", [_spec(first, field), _spec(other, field)],
                           currency=currency, context=evidence, source="anomaly", check_type="anomaly",
                           rationale="At least three different entities share an identical nonzero monetary value in the same table and currency. Equality is only an anomaly signal and does not identify a correction.")
            if len(checks) < MAX_CHECKS:
                checks.append(check)
                _note(notes, other, "REPEATED_MONETARY_VALUE", "At least three entities share this nonzero monetary value; validate whether the repetition is expected.",
                      status="REVIEW_REQUIRED", evidence_ids=evidence, check_id=check.check_id)
    return checks[:MAX_CHECKS], notes[:MAX_NOTES]
