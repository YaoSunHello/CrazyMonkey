"""Conservative offline source views; all values remain ATLAS references.

These label families are a deliberately limited fallback when no model is configured.
They discover available relationships, not investor-specific answers or file names.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from app.atlas.models import SourceRef
from .contracts import NumericInput
from .investigation_evidence import EvidenceStore, source_text


ALIASES = {
    "entity": ("investor id", "investor code", "client id", "account id", "limited partner", "account code", "participant", "investor", "client code", "customer", "account", "reference"),
    "name": ("investor name", "client name", "account name"),
    "fund": ("fund", "fund name", "vehicle", "partnership"),
    "base": ("fee base", "fee base used", "advisory charge base", "charge base", "assessment base", "assessable capital", "chargeable capital", "capital subject to charge"),
    "rate": ("annual rate used", "annual rate", "annual charge rate", "rate applied", "applied rate", "annual percentage", "yearly rate"),
    "factor": ("period factor", "quarterly factor", "quarter fraction", "accrual fraction", "year fraction", "period multiplier", "time fraction"),
    "reported": ("reported fee", "amount charged", "charge booked", "booked charge", "advisory charge", "management fee", "charge amount", "amount billed", "recorded charge"),
    "currency": ("currency", "ccy", "denomination"),
    "start": ("period start", "review start", "from", "start date"),
    "end": ("period end", "review end", "to", "end date"),
    "expected_document": ("side letter filename", "terms filename"),
    "document_required": ("side letter expected", "terms expected"),
    "quantity": ("quantity", "units", "number of units"),
    "price": ("unit price", "price per unit", "price"),
    "total": ("line total", "total amount", "extended amount", "line amount"),
    "gross": ("gross amount", "gross", "gross proceeds"),
    "deductions": ("deductions", "total deductions", "charges deducted"),
    "net": ("net amount", "net", "net proceeds"),
}


def words(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def category(value: str) -> str | None:
    normalized = words(value)
    for key, labels in ALIASES.items():
        if normalized in labels:
            return key
    return None


def contains(text: str, identity: str) -> bool:
    return bool(identity and re.search(r"(?<![\w-])" + re.escape(identity) + r"(?![\w-])", text, re.I))


@dataclass
class Row:
    fields: dict[str, SourceRef]
    labels: dict[str, SourceRef]
    context: list[str]
    document_id: str
    entity_id: str
    fund_name: str


def _fund(text: str) -> str:
    for line in text.splitlines():
        match = re.match(r"(?:fund(?: name)?|vehicle|partnership)\s*:\s*(.+)", line, re.I)
        if match:
            return match[1].strip().rstrip(".")
        if re.search(r"\b(?:Fund|Partnership)\b", line, re.I) and not category(line):
            value = re.split(r"\s+[—–]\s+|\s+-\s+|\s+Q[1-4]\s+20\d\d", line)[0]
            if len(value) < 150:
                return value.strip()
    return ""


def discover_rows(store: EvidenceStore) -> list[Row]:
    result = []
    def add(fields, labels, refs, doc_id, metadata):
        if "entity" not in fields:
            return
        entity = source_text(fields["entity"]).strip()
        if category(entity) or not entity:
            return
        fund = source_text(fields["fund"]) if "fund" in fields else _fund(metadata)
        context = list(dict.fromkeys([r.evidence_id for r in refs] + [r.evidence_id for r in labels.values()]))
        result.append(Row(fields, labels, context, doc_id, entity, fund))
    for document in store.docs.values():
        doc_id = document.document.document_id
        if document.csv_headers:
            grouped = {}
            for ref in document.evidence:
                grouped.setdefault(ref.csv_row, []).append(ref)
            for refs in grouped.values():
                fields = {category(r.csv_column or ""): r for r in refs if category(r.csv_column or "")}
                add(fields, {}, refs, doc_id, "")
            continue
        for sheet in document.workbook_sheets:
            refs = [r for r in document.evidence if r.sheet == sheet.name]
            cells = {}
            for ref in refs:
                match = re.fullmatch(r"([A-Z]+)(\d+)", ref.cell or "")
                if match:
                    cells[(int(match[2]), match[1])] = ref
            rows = sorted({r for r, _ in cells})
            header = None
            header_row = None
            for row_number in rows:
                current = {col: ref for (r, col), ref in cells.items() if r == row_number}
                candidates = {col: category(source_text(ref)) for col, ref in current.items()}
                candidates = {col: cat for col, cat in candidates.items() if cat}
                if len(candidates) >= 3 and "entity" in candidates.values():
                    header = {col: (cat, current[col]) for col, cat in candidates.items()}
                    header_row = row_number
                    continue
                if header:
                    fields = {cat: current[col] for col, (cat, _) in header.items() if col in current}
                    labels = {cat: ref for cat, ref in header.values()}
                    metadata_refs = [ref for (r, _), ref in cells.items() if r < header_row]
                    add(fields, labels, list(current.values()) + metadata_refs, doc_id,
                        "\n".join(source_text(r) for r in metadata_refs))
            # Key/value vertical schedules, independent of sheet name or row number.
            if header is None:
                fields, labels = {}, {}
                for row_number in rows:
                    current = sorted([(len(col), col, ref) for (r, col), ref in cells.items() if r == row_number])
                    for index, (_, _, ref) in enumerate(current[:-1]):
                        cat = category(source_text(ref))
                        if cat and not category(source_text(current[index + 1][2])):
                            if cat in fields:
                                # Multiple vertical entities are deliberately unsupported.
                                fields = {}
                                break
                            fields[cat] = current[index + 1][2]
                            labels[cat] = ref
                if len(fields) >= 3:
                    add(fields, labels, refs, doc_id, "\n".join(source_text(r) for r in refs))
    return result


DATE_PATTERN = r"(?:\d{4}-\d{2}-\d{2}|\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})"


def parse_date(text: str) -> date:
    for fmt in ("%Y-%m-%d", "%d %B %Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError("unsupported date")


def review_period(text: str) -> tuple[date, date] | None:
    match = re.search(r"(?:from\s+)?(" + DATE_PATTERN + r")\s+(?:through|to|until|[—–])\s+(" + DATE_PATTERN + r")", text, re.I)
    if match:
        return parse_date(match[1]), parse_date(match[2])
    quarters = set(re.findall(r"\bQ([1-4])\s+(20\d{2})\b", text, re.I))
    if len(quarters) == 1:
        quarter, year = map(int, next(iter(quarters)))
        month = quarter * 3
        return date(year, month - 2, 1), date(year, month, calendar.monthrange(year, month)[1])
    return None


def effective_window(text: str) -> tuple[date | None, date | None]:
    start = re.search(r"(?:effective\s+(?:from|on|as of)|commencing|with effect from)\s+(" + DATE_PATTERN + r")", text, re.I)
    end = re.search(r"(?:expires?\s+(?:on\s+)?|effective\s+(?:until|to)|ending|valid until)\s+(" + DATE_PATTERN + r")", text, re.I)
    return (parse_date(start[1]) if start else None, parse_date(end[1]) if end else None)


@dataclass
class TermDecision:
    rate: NumericInput | None = None
    context: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    period_factor: Decimal | None = None


def find_terms(store: EvidenceStore, row: Row) -> TermDecision:
    decision = TermDecision()
    workbook_text = store.document_text(row.document_id)
    if "start" in row.fields and "end" in row.fields:
        period = (parse_date(source_text(row.fields["start"])), parse_date(source_text(row.fields["end"])))
    else:
        period = review_period(workbook_text)
    relevant = []
    for document in store.docs.values():
        if not any(r.kind == "PDF_TEXT" for r in document.evidence):
            continue
        text = store.document_text(document.document.document_id)
        if row.fund_name and contains(text, row.fund_name):
            relevant.append((document, text))
            if period is None and not contains(text, row.entity_id):
                period = review_period(text)
    if not row.fund_name:
        decision.reasons.append("Fund identity could not be established from the schedule.")
    if period is None:
        decision.reasons.append("Reporting period could not be established.")
        return decision
    private, default = [], []
    for document, text in relevant:
        personal = contains(text, row.entity_id)
        is_default = bool(re.search(r"\bdefault\s+annual\b", text, re.I))
        if not personal and not is_default:
            continue
        refs = document.evidence
        decision.context.extend(r.evidence_id for r in refs)
        if personal:
            start, end = effective_window(text)
            if start is None:
                decision.reasons.append("Investor-specific terms have no supported effective date.")
                continue
            if start > period[1] or (end is not None and end < period[0]):
                continue
            if start > period[0] or (end is not None and end < period[1]):
                decision.reasons.append("Terms change within the period; proration is not established.")
                continue
        for ref in refs:
            quote = source_text(ref)
            if not re.search(r"(?:annual|per annum|yearly)", quote, re.I) or not re.search(r"(?:fee|charge|levy)", quote, re.I):
                continue
            percentages = re.findall(r"(?<![\w.])\d+(?:\.\d+)?\s*%", quote)
            if len(percentages) == 1:
                (private if personal else default).append(NumericInput(evidence_id=ref.evidence_id, token=percentages[0], unit="rate"))
            elif percentages:
                decision.reasons.append("Multiple possible rates in one term require interpretation.")
    choices = private or default
    if len(choices) == 1:
        decision.rate = choices[0]
    elif choices:
        decision.reasons.append("Multiple potentially applicable rate terms require resolution.")
    else:
        decision.reasons.append("No applicable contractual annual rate is supported.")
    if "factor" in row.fields:
        decision.period_factor = store.number(NumericInput(evidence_id=row.fields["factor"].evidence_id, unit="factor"))
    return decision
