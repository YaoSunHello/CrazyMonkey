"""Finite, source-bound Turbo Audit operations; no I/O or semantic approval.

Only values linked to existing ATLAS evidence enter calculations. A successful
calculation is not proof that its entity, agreement or business rule applies.
Those questions belong to the independent semantic review layer.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, DecimalException, ROUND_HALF_UP, localcontext
from functools import reduce
from operator import mul
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from .contracts import NumericInput, Record
from .investigation_evidence import EvidenceStore, source_text


FastOperation = Literal[
    "EQUAL", "NOT_EQUAL", "ADD", "SUBTRACT", "MULTIPLY", "DIVIDE", "SUM",
    "PERCENT_OF", "DATE_BEFORE", "DATE_AFTER",
]
_PREDICATES = frozenset({"EQUAL", "NOT_EQUAL", "DATE_BEFORE", "DATE_AFTER"})
_BINARY = _PREDICATES | {"SUBTRACT", "DIVIDE", "PERCENT_OF"}
_MONTHS = {name: index for index, name in enumerate((
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
), start=1)}
_MONTH_PATTERN = "(?:" + "|".join(_MONTHS) + ")"


class FastCheck(Record):
    check_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    entity_id: str = Field(min_length=1, max_length=150)
    fund_name: str = Field(default="", max_length=200)
    check_type: Literal[
        "annual_charge", "quantity_price", "gross_less_deductions", "model_proposed",
        "consistency", "anomaly",
    ] = "consistency"
    operation: FastOperation
    inputs: list[NumericInput] = Field(min_length=1, max_length=16)
    compare_to: NumericInput | None = None
    currency: Literal["GBP", "USD", "EUR"] | None = None
    rationale: str = Field(min_length=1, max_length=3000)
    context_evidence_ids: list[str] = Field(default_factory=list, max_length=200)
    source: Literal["deterministic", "relationship", "contract", "anomaly"] = "deterministic"

    @model_validator(mode="after")
    def validate_operation_shape(self):
        if self.operation in _BINARY and len(self.inputs) != 2:
            raise ValueError(f"{self.operation} requires exactly two inputs")
        if self.operation != "SUM" and len(self.inputs) < 2:
            raise ValueError("only SUM accepts one input")
        if self.operation in _PREDICATES and self.compare_to is not None:
            raise ValueError("predicates compare their two inputs and cannot have compare_to")
        if self.operation == "PERCENT_OF" and self.inputs[1].unit != "rate":
            raise ValueError("PERCENT_OF requires its second input to have unit=rate")
        if any(not evidence_id or len(evidence_id) > 100 for evidence_id in self.context_evidence_ids):
            raise ValueError("context evidence IDs must have 1..100 characters")
        return self


class FastPlanBatch(Record):
    checks: list[FastCheck] = Field(default_factory=list, max_length=40)
    cannot_verify: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_checks(self):
        if len({check.check_id for check in self.checks}) != len(self.checks):
            raise ValueError("check IDs must be unique within a batch")
        return self


def parse_fast_checks(raw: dict) -> list[FastCheck]:
    """Validate the complete bounded model batch, rejecting unknown fields."""
    return FastPlanBatch.model_validate(raw).checks


def _resolve(evidence_id: str, store: EvidenceStore):
    ref = store.get(evidence_id)
    document = store.docs.get(ref.document_id)
    if (ref.evidence_id != evidence_id or document is None
            or ref.document_id != document.document.document_id
            or ref.document_hash != document.document.document_hash):
        raise ValueError("evidence/document hash mismatch")
    return ref


def _trusted_text(spec: NumericInput, store: EvidenceStore) -> str:
    ref = _resolve(spec.evidence_id, store)
    if ref.formula or ref.cache_status != "NOT_APPLICABLE":
        raise ValueError("formula/cached evidence cannot supply a verified input")
    if ref.data_type in ("b", "bool", "boolean", "e", "error"):
        raise ValueError("boolean/error cell cannot supply a verified input")
    raw = source_text(ref).strip()
    if not raw:
        raise ValueError("source value is missing")
    if spec.token is None:
        return raw
    token = spec.token.strip()
    if not token:
        raise ValueError("source token is empty")
    if ref.kind != "PDF_TEXT":
        if token != raw:
            raise ValueError("cell inputs must use the complete original cell value")
    elif not re.search(r"(?<![\w/.,+\-])" + re.escape(token) + r"(?![\w/%]|[.,]\d|[-+]\d)", raw):
        raise ValueError("token is not an exact bounded source substring")
    return token


def _parse_date(text: str) -> date | datetime:
    """Accept explicit ISO dates/timestamps or English full-month dates only."""
    if len(text) > 80:
        raise ValueError("date value exceeds the supported bound")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return date.fromisoformat(text)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?", text):
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    day_first = re.fullmatch(r"(\d{1,2}) (" + _MONTH_PATTERN + r") (\d{4})", text)
    month_first = re.fullmatch(r"(" + _MONTH_PATTERN + r") (\d{1,2}),? (\d{4})", text)
    if day_first:
        day, month, year = day_first.groups()
    elif month_first:
        month, day, year = month_first.groups()
    else:
        raise ValueError("date is not an explicit ISO or full-month date")
    return date(int(year), _MONTHS[month], int(day))


def _currency_check(check: FastCheck, specs: list[NumericInput], store: EvidenceStore) -> None:
    currencies: set[str] = set()
    symbols = {"£": "GBP", "$": "USD", "€": "EUR"}
    for spec in specs:
        text = _trusted_text(spec, store).strip("() ")
        explicit = re.match(r"^(GBP|USD|EUR|£|\$|€)\s*(?=[+-]?\d)", text)
        if explicit:
            currencies.add(symbols.get(explicit[1], explicit[1]))
        ref = store.get(spec.evidence_id)
        number_format = ref.number_format or ""
        for marker, currency in symbols.items():
            # Ignore Excel locale markers such as [$-409].
            if marker in re.sub(r"\[\$-[^\]]+\]", "", number_format):
                currencies.add(currency)
        currencies.update(re.findall(r"\b(?:GBP|USD|EUR)\b", number_format))
    if len(currencies) > 1 or (currencies and check.currency is not None and check.currency not in currencies):
        raise ValueError("explicit source currency does not match the check currency")


def execute_check(check: FastCheck, store: EvidenceStore, tolerance: Decimal = Decimal("0.01")) -> dict:
    """Return a source-linked calculation result, failing closed on invalid data.

    EQUAL/NOT_EQUAL use exact Decimal equality when both sources are numeric,
    otherwise exact trimmed source text. DATE predicates do not guess slash-date
    conventions or coerce calendar dates into timestamps. Financial arithmetic
    is rounded half up to cents; unlabelled numeric arithmetic remains exact.
    Original source-file freshness and semantic applicability are checked by
    callers, because this executor performs no I/O.
    """
    result = {
        "check_id": getattr(check, "check_id", "invalid"),
        "status": "CANNOT_VERIFY", "expected": None, "reported": None,
        "difference": None, "values": [], "reasons": [], "evidence_ids": [],
        "metadata": {"semantic_approval": False, "source_files_rechecked": False},
    }
    try:
        check = FastCheck.model_validate(check.model_dump() if isinstance(check, FastCheck) else check)
        result["check_id"] = check.check_id
        if not isinstance(tolerance, Decimal) or not tolerance.is_finite() or tolerance < 0:
            raise ValueError("tolerance must be a finite nonnegative Decimal")
        specs = [*check.inputs, *([check.compare_to] if check.compare_to is not None else [])]
        ids = list(dict.fromkeys([*(spec.evidence_id for spec in specs), *check.context_evidence_ids]))
        # Resolve the entire proposed evidence set before parsing or calculating.
        for evidence_id in ids:
            _resolve(evidence_id, store)
        result["evidence_ids"] = ids
        texts = [_trusted_text(spec, store) for spec in specs]
        result["metadata"].update({"operation": check.operation, "source": check.source,
                                    "currency": check.currency, "tolerance": str(tolerance)})
        with localcontext() as context:
            context.prec = 80
            if check.operation in ("DATE_BEFORE", "DATE_AFTER"):
                parsed = [_parse_date(text) for text in texts]
                if type(parsed[0]) is not type(parsed[1]):
                    raise ValueError("date operands must both be calendar dates or timestamps")
                predicate = parsed[0] < parsed[1] if check.operation == "DATE_BEFORE" else parsed[0] > parsed[1]
                result["values"] = [value.isoformat() for value in parsed]
                result["expected"], result["reported"] = "true", str(predicate).lower()
                result["status"] = "MATCH" if predicate else "DISCREPANCY"
                return result
            _currency_check(check, specs, store)
            if check.operation in ("EQUAL", "NOT_EQUAL"):
                try:
                    values = [store.number(spec) for spec in check.inputs]
                except ValueError:
                    if any(spec.unit != "number" for spec in check.inputs):
                        raise
                    values = texts
                equal = values[0] == values[1]
                predicate = equal if check.operation == "EQUAL" else not equal
                result["values"] = [str(value) for value in values]
                result["expected"], result["reported"] = "true", str(predicate).lower()
                result["status"] = "MATCH" if predicate else "DISCREPANCY"
                return result
            if check.compare_to is None:
                raise ValueError("numeric checks require a separate source comparator")
            if any(spec.evidence_id == check.compare_to.evidence_id and text == texts[-1]
                   for spec, text in zip(check.inputs, texts)):
                raise ValueError("expected inputs cannot alias the reported source value")
            values = [store.number(spec) for spec in check.inputs]
            reported = store.number(check.compare_to)
            result["values"] = [str(value) for value in values]
            if check.operation in ("ADD", "SUM"):
                exact = sum(values, Decimal(0))
            elif check.operation == "SUBTRACT":
                exact = values[0] - values[1]
            elif check.operation == "DIVIDE":
                exact = values[0] / values[1]
            else:  # MULTIPLY and PERCENT_OF have validated operand shapes.
                exact = reduce(mul, values, Decimal(1))
            if not exact.is_finite() or abs(exact) > Decimal("1e30"):
                raise ValueError("calculation exceeds the supported bound")
            money = check.currency is not None or any(spec.unit == "money" for spec in specs)
            expected = exact.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if money else exact
            difference = reported - expected
            result.update({"expected": str(expected), "reported": str(reported),
                           "difference": str(difference),
                           "status": "DISCREPANCY" if abs(difference) > tolerance else "MATCH"})
            result["metadata"].update({"unrounded_expected": str(exact),
                                       "rounding": "ROUND_HALF_UP_0.01" if money else "NONE"})
            return result
    except ValidationError:
        result["reasons"] = ["invalid bounded verification check"]
    except DecimalException:
        result["reasons"] = ["invalid bounded arithmetic (including division by zero)"]
    except (TypeError, ValueError, KeyError) as exc:
        result["reasons"] = [str(exc)]
    return result
