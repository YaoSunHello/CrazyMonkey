"""Interpret the supported fee clauses from ATLAS evidence, never from files.

This deliberately narrow, credential-free interpreter is not a general legal
document reader. Unrecognised or ambiguous terms are returned as missing evidence.
ATLAS alone owns file extraction, source hashes, locators and evidence IDs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re

from pydantic import TypeAdapter

from app.atlas.models import NormalizedDocument, SourceRef
from .models import Amount, Rate


_AMOUNT_ADAPTER = TypeAdapter(Amount)
_RATE_ADAPTER = TypeAdapter(Rate)


class EvidenceCatalog:
    """A private validated snapshot; callers receive independent copies only."""

    def __init__(self, normalized_documents: list[NormalizedDocument]):
        self._documents: tuple[str, ...] = tuple(
            NormalizedDocument.model_validate_json(document.model_dump_json()).model_dump_json()
            if isinstance(document, NormalizedDocument)
            else NormalizedDocument.model_validate(document).model_dump_json()
            for document in normalized_documents
        )
        self._refs: dict[str, str] = {}
        document_ids: set[str] = set()
        for document in self.documents:
            if document.document.document_id in document_ids:
                raise ValueError("Duplicate source document ID")
            document_ids.add(document.document.document_id)
            for ref in document.evidence:
                if ref.evidence_id in self._refs:
                    raise ValueError("Evidence IDs must be globally unique")
                self._refs[ref.evidence_id] = ref.model_dump_json()

    @property
    def documents(self) -> list[NormalizedDocument]:
        return [NormalizedDocument.model_validate_json(value) for value in self._documents]

    def resolve(self, evidence_ids: list[str]) -> list[SourceRef]:
        refs = []
        for evidence_id in evidence_ids:
            if evidence_id not in self._refs:
                raise ValueError(f"Unknown evidence ID: {evidence_id}")
            refs.append(SourceRef.model_validate_json(self._refs[evidence_id]))
        return refs

    def validate_ref(self, ref: SourceRef) -> bool:
        """Reject a fabricated quote, locator, document ID or document hash."""
        try:
            trusted = self.resolve([ref.evidence_id])[0]
            candidate = SourceRef.model_validate_json(ref.model_dump_json())
        except (ValueError, AttributeError):
            return False
        return trusted.model_dump() == candidate.model_dump()


@dataclass
class SourceTerms:
    investor_id: str
    fund_name: str
    fee_base: Decimal | None = None
    annual_rate: Decimal | None = None
    period_fraction: Decimal | None = None
    reported: Decimal | None = None
    currency: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    tolerance: Decimal | None = None
    default_annual_rate: Decimal | None = None
    candidate_override_rate: Decimal | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    applicable_default: bool | None = None
    candidate_override: bool = False
    applicability_state: str = "AMBIGUOUS"
    input_evidence: dict[str, list[str]] = field(default_factory=dict)
    evidence_ids: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)


def _unique(values):
    return list(dict.fromkeys(values))


def _value(ref: SourceRef) -> str:
    # A formula cache is not an independently verified source value.
    if ref.formula:
        return ""
    return (ref.original_value if ref.original_value is not None else ref.quote or "").strip()


def _decimal(value: str) -> Decimal | None:
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value):
        return None
    try:
        return _AMOUNT_ADAPTER.validate_python(Decimal(value))
    except (InvalidOperation, ValueError):
        return None


def _percent(value: str) -> Decimal | None:
    """Move the decimal exponent exactly, independent of ambient precision."""
    parts = Decimal(value).as_tuple()
    try:
        return _RATE_ADAPTER.validate_python(Decimal((parts.sign, parts.digits, parts.exponent - 2)))
    except ValueError:
        return None


def _date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%d %B %Y").date()
    except ValueError:
        return None


_DATE = r"\d{1,2}\s+[A-Za-z]+\s+\d{4}"


class _Text:
    """Whitespace-insensitive matching with ORIGINAL evidence references."""

    def __init__(self, document: NormalizedDocument | None):
        self.parts: list[tuple[int, int, str]] = []
        self.text = ""
        for ref in document.evidence if document else []:
            if ref.kind != "PDF_TEXT":
                continue
            value = " ".join((ref.quote or "").split())
            start = len(self.text)
            self.text += value + " "
            self.parts.append((start, len(self.text), ref.evidence_id))

    def matches(self, pattern: str):
        return [
            (match, [eid for start, end, eid in self.parts if start < match.end() and end > match.start()])
            for match in re.finditer(pattern, self.text, re.I)
        ]

    def one(self, pattern: str):
        matches = self.matches(pattern)
        return matches[0] if len(matches) == 1 else (None, [])

    def has_uninterpreted_prose(self, patterns: list[str]) -> bool:
        """Fail closed if any substantive source statement is not understood.

        Recognising a default fee does not establish that a later waiver or
        qualification is absent. The offline vocabulary therefore covers every
        substantive statement, not just whichever snippets happen to match.
        """
        covered = [False] * len(self.text)
        for pattern in patterns:
            for match, _ in self.matches(pattern):
                covered[match.start():match.end()] = [True] * (match.end() - match.start())
        remainder = "".join(character for position, character in enumerate(self.text) if not covered[position])
        return bool(re.search(r"\w", remainder))


def _column(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


class _SourceRow(dict):
    def __init__(self):
        super().__init__()
        self.ambiguities: list[str] = []


def _register_rows(documents):
    rows = []
    for document in documents:
        if document.document.role != "INVESTOR_REGISTER":
            continue
        by_row = {}
        for ref in document.evidence:
            if ref.kind == "CSV_CELL":
                row = by_row.setdefault(ref.csv_row, _SourceRow())
                column = _column(ref.csv_column or "")
                if column in row:
                    row.ambiguities.append(f"Duplicate normalized register column {column}.")
                else:
                    row[column] = ref
                if column not in {"investor_id", "investor_name", "fee_base", "currency", "side_letter_expected", "side_letter_filename"}:
                    row.ambiguities.append(f"Unsupported register column {column} may qualify financial inputs.")
        rows.extend((document, row) for row in by_row.values() if "investor_id" in row)
    return rows


def _workbook_rows(documents):
    rows = []
    for document in documents:
        if document.document.role != "NAV_WORKBOOK":
            continue
        sheets = {}
        for ref in document.evidence:
            if ref.kind != "WORKBOOK_CELL":
                continue
            match = re.fullmatch(r"([A-Z]+)(\d+)", ref.cell or "")
            if match:
                sheets.setdefault(ref.sheet, {}).setdefault(int(match[2]), {})[match[1]] = ref
        document_rows = []
        document_ambiguities = []
        for sheet in sheets.values():
            headers = []
            for number, row in sheet.items():
                names = [_column(_value(ref)) for ref in row.values()]
                if set(names) >= {"investor_id", "reported_fee"}:
                    duplicates = sorted(name for name in set(names) if names.count(name) > 1)
                    headers.append((number, {_column(_value(ref)): column for column, ref in row.items()}, duplicates))
            if len(headers) != 1:
                document_ambiguities.append("NAV contains a populated sheet without exactly one supported fee table.")
                continue
            header_number, headers_by_name, duplicates = headers[0]
            supported_headers = {"investor_id", "investor_name", "fee_base_used", "annual_rate_used", "period_factor", "reported_fee", "currency", "value_provenance"}
            unknown_headers = set(headers_by_name) - supported_headers
            if unknown_headers:
                document_ambiguities.append("Unsupported NAV columns may qualify the reported fee: " + ", ".join(sorted(unknown_headers)) + ".")
            for number, row in sheet.items():
                if number <= header_number:
                    if number < header_number:
                        for ref in row.values():
                            value = _value(ref)
                            if value != "Synthetic administrator return — management fees are hard-coded values" and not re.fullmatch(r".+ — [A-Za-z0-9 ]+ NAV", value):
                                document_ambiguities.append("NAV contains an unsupported pre-table note requiring human interpretation.")
                    continue
                mapped = _SourceRow()
                mapped.update({name: row[column] for name, column in headers_by_name.items() if column in row})
                mapped.ambiguities = [f"Duplicate normalized NAV column {name}." for name in duplicates]
                if set(row) - set(headers_by_name.values()):
                    mapped.ambiguities.append("NAV contains data cells without supported column headings.")
                provenance = mapped.get("value_provenance")
                if provenance and _value(provenance) != "Hard-coded by administrator":
                    mapped.ambiguities.append("NAV value provenance contains unsupported source qualifications.")
                if "investor_id" in mapped and _value(mapped["investor_id"]):
                    document_rows.append((document, mapped))
                elif row:
                    document_ambiguities.append("NAV contains an unscoped data row or note requiring human interpretation.")
        for document, row in document_rows:
            row.ambiguities.extend(_unique(document_ambiguities))
            rows.append((document, row))
    return rows


def build_context(catalog: EvidenceCatalog) -> list[SourceTerms]:
    """Extract independently checkable terms for the supported management-fee case.

    Register Fee Base is the authoritative input; the administrator's reported
    workbook amount is the comparator. Side-letter identity, relationship and
    effective period must be evidenced before replacing the LPA default.
    """
    documents = catalog.documents
    lpas = [document for document in documents if document.document.role == "LPA"]
    lpa = lpas[0] if len(lpas) == 1 else None
    text = _Text(lpa)
    global_missing = []
    if not lpa:
        global_missing.append("Exactly one governing LPA is required; missing or multiple LPAs are ambiguous.")
    elif lpa.document.extraction_status != "COMPLETE":
        global_missing.append("Governing LPA extraction is incomplete or unconfirmed.")
    if any(document.document.role == "SUPPORTING" for document in documents):
        global_missing.append("Unclassified supporting documents may contain applicable terms and require human interpretation.")

    fund_match, fund_ids = text.one(r"^(.+?)\s+Limited Partnership Agreement\b")
    fund_name = fund_match[1].strip() if fund_match else "UNKNOWN"
    period, period_ids = text.one(rf"review period is ([A-Za-z0-9 ]+), from ({_DATE}) through ({_DATE})\.")
    period_start = _date(period[2]) if period else None
    period_end = _date(period[3]) if period else None
    default, default_ids = text.one(r"default annual management fee is (\d+(?:\.\d+)?)% of the applicable investor Fee Base\.")
    default_rate = _percent(default[1]) if default else None
    factor, factor_ids = text.one(r"For ([A-Za-z0-9 ]+) the quarterly fee is annual rate x (\d+(?:\.\d+)?) x Fee Base\.")
    fraction = _decimal(factor[2]) if factor and period and factor[1] == period[1] else None
    currency_match, currency_ids = text.one(r"Management fees are denominated in ([A-Z]{3}), with no other adjustments")
    lpa_currency = currency_match[1].upper() if currency_match else None
    rounding, rounding_ids = text.one(r"rounded to the nearest penny using round-half-up; comparison tolerance is ([A-Z]{3}) (\d+(?:\.\d+)?)\.")
    tolerance = _decimal(rounding[2]) if rounding and rounding[1].upper() == lpa_currency else None
    precedence, precedence_ids = text.one(r"A side-letter term applies only where investor identity, management-fee scope, effective date, and governing relationship are supported by the supplied evidence\.")
    expiry, expiry_ids = text.one(r"A future or expired override does not replace the default rate for the review period\.")
    if text.has_uninterpreted_prose([
        r"^(.+?)\s+Limited Partnership Agreement\b",
        r"fictional synthetic demo\b",
        r"Section 1\s*[—-]\s*Scope and period",
        r"Section 8\.1\s*[—-]\s*Management fee",
        r"Section 8\.2\s*[—-]\s*Investor-specific terms",
        r"This fictional agreement is created solely for the CrazyMonkey synthetic demonstration\.",
        rf"The review period is [A-Za-z0-9 ]+, from {_DATE} through {_DATE}\.",
        r"The default annual management fee is \d+(?:\.\d+)?% of the applicable investor Fee Base\.",
        r"For [A-Za-z0-9 ]+ the quarterly fee is annual rate x \d+(?:\.\d+)? x Fee Base\.",
        r"Management fees are denominated in [A-Z]{3}, with no other adjustments for this synthetic case\.",
        r"The calculated fee is rounded to the nearest penny using round-half-up; comparison tolerance is [A-Z]{3} \d+(?:\.\d+)?\.",
        r"A side-letter term applies only where investor identity, management-fee scope, effective date, and governing relationship are supported by the supplied evidence\.",
        r"A future or expired override does not replace the default rate for the review period\.",
        r"Synthetic demo document\s*[—-]\s*not legal advice and not a real fund agreement\.",
    ]):
        global_missing.append("The LPA contains additional or unsupported prose; all financial qualifications require human interpretation.")
    for field_name, valid in (
        ("fund identity", fund_match), ("review period", period_start and period_end and period_start <= period_end),
        ("default fee rate", default_rate is not None and 0 <= default_rate <= 1),
        ("period fraction", fraction is not None and 0 <= fraction <= 1),
        ("currency", lpa_currency), ("rounding and tolerance", tolerance is not None),
        ("side-letter precedence", precedence and expiry),
    ):
        if not valid:
            global_missing.append(f"Missing, conflicting or unsupported LPA {field_name}.")

    register_rows = _register_rows(documents)
    nav_rows = _workbook_rows(documents)
    investor_ids = sorted({_value(row["investor_id"]) for _, row in register_rows + nav_rows})
    if not investor_ids:
        return [SourceTerms("UNKNOWN", fund_name, missing_evidence=global_missing + ["No source-linked investor rows were found in a supported register and NAV workbook."])]

    result = []
    for investor_id in investor_ids:
        terms = SourceTerms(
            investor_id=investor_id, fund_name=fund_name,
            annual_rate=default_rate, period_fraction=fraction,
            period_start=period_start, period_end=period_end,
            currency=lpa_currency, tolerance=tolerance,
            default_annual_rate=default_rate,
            input_evidence={
                "fund_name": list(fund_ids), "investor_id": [], "fee_base": [],
                "annual_rate": _unique(default_ids + precedence_ids + expiry_ids),
                "period_fraction": list(factor_ids), "reported": [],
                "currency": list(currency_ids), "period_start": list(period_ids),
                "period_end": list(period_ids), "tolerance": list(rounding_ids),
            },
            missing_evidence=list(global_missing),
        )
        register_matches = [(doc, row) for doc, row in register_rows if _value(row["investor_id"]) == investor_id]
        nav_matches = [(doc, row) for doc, row in nav_rows if _value(row["investor_id"]) == investor_id]
        register = register_matches[0][1] if len(register_matches) == 1 else {}
        nav = nav_matches[0][1] if len(nav_matches) == 1 else {}
        for label, matches in (("investor register", register_matches), ("administrator NAV", nav_matches)):
            if len(matches) != 1:
                terms.missing_evidence.append(f"Expected one {label} row for {investor_id}; found {len(matches)}.")
            elif matches[0][0].document.extraction_status != "COMPLETE":
                terms.missing_evidence.append(f"The {label} source is incomplete or unconfirmed.")
            if len(matches) == 1:
                terms.missing_evidence.extend(matches[0][1].ambiguities)
        for row in (register, nav):
            if "investor_id" in row:
                terms.input_evidence["investor_id"].append(row["investor_id"].evidence_id)
        register_name, nav_name = register.get("investor_name"), nav.get("investor_name")
        if not register_name or not nav_name or not _value(register_name) or _value(register_name) != _value(nav_name):
            terms.missing_evidence.append("Investor names are missing or conflict between register and NAV identity records.")
        for name_ref in (register_name, nav_name):
            if name_ref:
                terms.input_evidence["investor_id"].append(name_ref.evidence_id)
        for key, source_name, row in (("fee_base", "fee_base", register), ("reported", "reported_fee", nav)):
            ref = row.get(source_name)
            value = _decimal(_value(ref)) if ref else None
            if value is None or (key == "fee_base" and value < 0):
                terms.missing_evidence.append(f"Missing or unsupported exact numeric {key} for {investor_id}.")
            else:
                setattr(terms, key, value)
                terms.input_evidence[key].append(ref.evidence_id)
        for label, row in (("register", register), ("NAV", nav)):
            ref = row.get("currency")
            if not ref or _value(ref) != lpa_currency:
                terms.missing_evidence.append(f"{label} currency is missing or conflicts with governing LPA.")
            elif ref:
                terms.input_evidence["currency"].append(ref.evidence_id)
        if nav_matches and period and fund_match:
            nav_doc = nav_matches[0][0]
            title_refs = [ref for ref in nav_doc.evidence if _value(ref) == f"{fund_name} — {period[1]} NAV"]
            if len(title_refs) != 1:
                terms.missing_evidence.append("NAV fund or reporting-period identity does not match the governing LPA.")
            else:
                title_id = title_refs[0].evidence_id
                for key in ("fund_name", "period_start", "period_end"):
                    terms.input_evidence[key].append(title_id)

        expected_ref = register.get("side_letter_expected")
        expected = _value(expected_ref).upper() if expected_ref else ""
        if expected not in {"YES", "NO"}:
            terms.missing_evidence.append("Register does not establish whether an investor side letter is expected.")
        elif expected_ref:
            terms.input_evidence["annual_rate"].append(expected_ref.evidence_id)
        filename_ref = register.get("side_letter_filename")
        expected_filename = _value(filename_ref) if filename_ref else ""
        if filename_ref:
            terms.input_evidence["annual_rate"].append(filename_ref.evidence_id)

        letters = []
        for document in documents:
            if document.document.role != "SIDE_LETTER":
                continue
            letter_text = _Text(document)
            identities = letter_text.matches(r"Investor ID: ([A-Za-z0-9_-]+)\.")
            matching_identity = any(match[1] == investor_id for match, _ in identities)
            matching_filename = bool(expected_filename and document.document.filename == expected_filename)
            if matching_identity or matching_filename:
                letters.append((document, letter_text, identities))
        if expected == "YES" and not letters:
            terms.missing_evidence.append(f"Expected side letter for {investor_id} was not supplied.")
            terms.annual_rate = None
        elif len(letters) > 1:
            terms.missing_evidence.append(f"Multiple side letters for {investor_id} require precedence review.")
            terms.annual_rate = None
        elif letters:
            document, letter_text, identities = letters[0]
            # All side-letter facts (including dates and relationship) support rate selection.
            letter_ids = [ref.evidence_id for ref in document.evidence]
            terms.input_evidence["annual_rate"].extend(letter_ids)
            valid_letter = True
            if letter_text.has_uninterpreted_prose([
                r"^[A-Za-z0-9_-]+ Side Letter\b",
                r"Fictional synthetic investor agreement\b",
                r"Section 1\s*[—-]\s*Investor identity",
                r"Section 3\.1\s*[—-]\s*Management fee term",
                r"Investor ID: [A-Za-z0-9_-]+\.",
                r"This letter supplements the .+? LPA for [A-Za-z0-9_-]+ only\.",
                r"No management-fee (?:rate )?variation is granted; the LPA default remains applicable\.",
                r"The annual management fee applicable to [A-Za-z0-9_-]+ is \d+(?:\.\d+)?% of the Fee Base\.",
                rf"Effective from {_DATE}; (?:no end date is specified|effective through {_DATE})\.",
                r"Synthetic demo document\s*[—-]\s*not legal advice and not a real fund agreement\.",
            ]):
                terms.missing_evidence.append("Side letter contains additional or unsupported prose requiring human interpretation.")
                valid_letter = False
            if document.document.extraction_status != "COMPLETE":
                terms.missing_evidence.append("Side-letter extraction is incomplete or unconfirmed.")
                valid_letter = False
            if len(identities) != 1 or identities[0][0][1] != investor_id:
                terms.missing_evidence.append("Side-letter investor identity is missing or contradictory.")
                valid_letter = False
            else:
                terms.input_evidence["investor_id"].extend(identities[0][1])
            relationship, relationship_ids = letter_text.one(r"This letter supplements the (.+?) LPA for ([A-Za-z0-9_-]+) only\.")
            if not relationship or relationship[1] != fund_name or relationship[2] != investor_id:
                terms.missing_evidence.append("Side letter does not establish the correct fund/investor governing relationship.")
                valid_letter = False
            else:
                terms.input_evidence["fund_name"].extend(relationship_ids)
                terms.input_evidence["investor_id"].extend(relationship_ids)
            effective, effective_ids = letter_text.one(rf"Effective from ({_DATE}); (no end date is specified|effective through ({_DATE}))\.")
            start = _date(effective[1]) if effective else None
            end = _date(effective[3]) if effective and effective[3] else None
            if not start or (effective and effective[3] and not end) or (end and start and end < start):
                terms.missing_evidence.append("Side-letter effective dates are missing, invalid or unsupported.")
                valid_letter = False
            no_override, _ = letter_text.one(r"No management-fee (?:rate )?variation is granted; the LPA default remains applicable\.")
            override, _ = letter_text.one(r"The annual management fee applicable to ([A-Za-z0-9_-]+) is (\d+(?:\.\d+)?)% of the Fee Base\.")
            if bool(no_override) == bool(override) or (override and override[1] != investor_id):
                terms.missing_evidence.append("Side-letter management-fee term is missing, conflicting or scoped to another investor.")
                valid_letter = False
            if override and _percent(override[2]) is None:
                terms.missing_evidence.append("Side-letter rate is outside the supported range.")
                valid_letter = False
            if valid_letter and start and period_start and period_end:
                terms.effective_from, terms.effective_to = start, end
                terms.candidate_override = bool(override)
                terms.candidate_override_rate = _percent(override[2]) if override else None
                if start > period_end or (end and end < period_start):
                    terms.annual_rate = default_rate
                    terms.applicable_default = True
                    terms.applicability_state = "DOES_NOT_APPLY"
                elif start > period_start or (end and end < period_end):
                    terms.missing_evidence.append("Side-letter change within the reporting period needs an evidenced proration rule.")
                    terms.annual_rate = None
                elif override:
                    rate = _percent(override[2])
                    if rate is None:
                        terms.missing_evidence.append("Side-letter rate is outside the supported range.")
                        terms.annual_rate = None
                    else:
                        terms.annual_rate = rate
                        terms.applicable_default = False
                        terms.applicability_state = "APPLIES"
                else:
                    terms.applicable_default = True
                    terms.applicability_state = "APPLIES"
            elif not valid_letter:
                terms.annual_rate = None
        elif expected == "NO":
            terms.applicable_default = True
            terms.applicability_state = "APPLIES"
        if terms.missing_evidence:
            terms.applicable_default = None
            terms.applicability_state = "AMBIGUOUS"
        terms.input_evidence = {key: _unique(ids) for key, ids in terms.input_evidence.items()}
        terms.evidence_ids = _unique([eid for ids in terms.input_evidence.values() for eid in ids])
        terms.missing_evidence = _unique(terms.missing_evidence)
        result.append(terms)
    return result
