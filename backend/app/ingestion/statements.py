"""Parse a Calder bank statement PDF into structured transaction rows.

Deterministic. No LLM, no guessing. Where a line cannot be read confidently it
is left for the verifier to catch rather than filled in with something
plausible — the balance chain is the oracle, and a wrong value that makes the
chain close is worse than an obvious hole.

Layout, measured from the real statements rather than assumed:

- Each page carries a header row (``Bank reference · Customer reference ·
  TRN type · Value date · Credit amount · Debit amount · Balance · Time ·
  Post date``). The x-position of each header word defines a column band, and
  every value below it sits inside its own band. Amounts are right-aligned but
  never cross a boundary, so assigning by a word's left edge is safe.
- A transaction's ``Bank reference`` sits on a baseline ~0.2pt off the rest of
  the row, so lines must be grouped with a tolerance or one transaction splits
  into two.
- The narrative is a wrapped continuation line carrying the literal label
  ``Narrative`` in the left column, with the text itself from the customer
  reference band rightwards.
- Statements run newest-first. Each row's ``Balance`` is the balance *after*
  that transaction. Day boundaries are ``Balance brought forward <date>`` /
  ``Balance as at close <date>`` markers whose amount sits in the *customer
  reference* band — so they are detected by text, never by column.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber

from app.models import Provenance, Statement, StatementRow

# The header words that open each column, in order. Their x-positions on the
# page become the band boundaries.
COLUMN_HEADERS = [
    ("bank_reference", "Bank"),
    ("customer_reference", "Customer"),
    ("trn_type", "TRN"),
    ("value_date", "Value"),
    ("credit", "Credit"),
    ("debit", "Debit"),
    ("balance", "Balance"),
    ("time", "Time"),
    ("post_date", "Post"),
]

# Words sharing a baseline within this many points belong to one visual line.
# 1.5 absorbs the ~0.2pt split baseline without merging adjacent rows, which
# are ~14pt apart.
LINE_TOLERANCE = 1.5

DATE = re.compile(r"^\d{1,2} [A-Z][a-z]{2} \d{4}$")
MARKER = re.compile(r"^Balance (?:as at close|brought forward)\s+(\d{1,2} [A-Z][a-z]{2} \d{4})")
AMOUNT = re.compile(r"-?[\d,]+\.\d{2}")


def _to_decimal(text: str) -> Decimal | None:
    """Parse a statement amount. Returns None for anything that isn't one."""
    text = text.strip()
    if not text:
        return None
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None


def _group_lines(words: list[dict]) -> list[list[dict]]:
    """Group words into visual lines by baseline, within LINE_TOLERANCE."""
    lines: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(word["top"] - lines[-1][0]["top"]) <= LINE_TOLERANCE:
            lines[-1].append(word)
        else:
            lines.append([word])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def _find_bands(lines: list[list[dict]]) -> dict[str, tuple[float, float]] | None:
    """Locate the header row and derive each column's x-range from it."""
    for line in lines:
        by_text = {w["text"]: w for w in line}
        if not all(header in by_text for _, header in COLUMN_HEADERS):
            continue
        starts = [by_text[header]["x0"] for _, header in COLUMN_HEADERS]
        names = [name for name, _ in COLUMN_HEADERS]
        # Each band runs from its own header to the next one; the last is open.
        edges = [s - 1.0 for s in starts] + [float("inf")]
        return {name: (edges[i], edges[i + 1]) for i, name in enumerate(names)}
    return None


def _cells(line: list[dict], bands: dict[str, tuple[float, float]]) -> dict[str, str]:
    """Bucket a line's words into columns by their left edge."""
    out: dict[str, list[str]] = {name: [] for name in bands}
    for word in line:
        for name, (lo, hi) in bands.items():
            if lo <= word["x0"] < hi:
                out[name].append(word["text"])
                break
    return {name: " ".join(parts) for name, parts in out.items()}


def _bbox(line: list[dict], page_no: int) -> Provenance:
    return Provenance(
        page=page_no,
        x0=min(w["x0"] for w in line),
        top=min(w["top"] for w in line),
        x1=max(w["x1"] for w in line),
        bottom=max(w["bottom"] for w in line),
    )


def _line_text(line: list[dict]) -> str:
    return " ".join(w["text"] for w in line)


# The page-1 details block is two label/value pairs side by side. Reading it
# from word positions rather than the extracted text matters: extract_text()
# collapses the horizontal gaps, so "Account name NI V SCSP Closing ledger
# balance brought forward 103,014.97" arrives as one line and no regex can
# tell where the account name ends.
DETAIL_BLOCKS = (
    ((30, 175), (175, 450)),   # left column:  label, value
    ((450, 650), (650, 1e4)),  # right column: label, value
)

DETAIL_FIELDS = {
    "Account name": "account_name",
    "Account number": "account_number",
    "Bank name": "bank_name",
    "Currency": "currency",
    "IBAN": "iban",
    "BIC": "bic",
    "Specified date range": "date_range",
}


def _in_range(line: list[dict], lo: float, hi: float) -> str:
    return " ".join(w["text"] for w in line if lo <= w["x0"] < hi)


def _statement_details(lines: list[list[dict]]) -> dict[str, str]:
    """Read the page-1 account block as label/value pairs from both columns."""
    pairs: dict[str, str] = {}
    for line in lines:
        for (label_lo, label_hi), (value_lo, value_hi) in DETAIL_BLOCKS:
            label = _in_range(line, label_lo, label_hi)
            value = _in_range(line, value_lo, value_hi)
            if label and value:
                pairs[label] = value
    return pairs


def parse_statement(path: str | Path) -> Statement:
    """Parse one statement PDF.

    The account short code is taken from the filename, which the dataset README
    documents as carrying the entity, bank, currency and account short code.
    """
    path = Path(path)
    parts = path.stem.split("_")
    currency_from_name, code = parts[-2], parts[-1]
    short_code = f"{currency_from_name}_{code}"

    statement = Statement(source_file=path.name, account_short_code=short_code)
    rows: list[StatementRow] = []
    current: StatementRow | None = None

    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            statement.page_text.append(page_text)

            lines = _group_lines(page.extract_words())
            bands = _find_bands(lines)
            if bands is None:
                continue

            if page_no == 1:
                details = _statement_details(lines)
                for label, attr in DETAIL_FIELDS.items():
                    if details.get(label):
                        setattr(statement, attr, details[label])
                statement.closing_balance = _to_decimal(
                    details.get("Closing ledger balance brought forward", "")
                )

            for line in lines:
                text = _line_text(line)
                cells = _cells(line, bands)

                marker = MARKER.match(text)
                if marker:
                    current = None
                    if text.startswith("Balance brought forward"):
                        amounts = AMOUNT.findall(text)
                        if amounts:
                            value = _to_decimal(amounts[-1])
                            if value is not None:
                                statement.printed_openings[marker.group(1)] = value
                    continue

                # A transaction needs a date in the value-date column and a
                # running balance. Anything else on the page is furniture.
                if DATE.match(cells["value_date"]) and _to_decimal(cells["balance"]) is not None:
                    current = StatementRow(
                        account_number=statement.account_number,
                        currency=statement.currency or currency_from_name,
                        bank_reference=cells["bank_reference"],
                        customer_reference=cells["customer_reference"],
                        trn_type=cells["trn_type"],
                        value_date=cells["value_date"],
                        post_date=cells["post_date"],
                        time=cells["time"],
                        credit=_to_decimal(cells["credit"]),
                        debit=_to_decimal(cells["debit"]),
                        balance=_to_decimal(cells["balance"]),
                        provenance=_bbox(line, page_no),
                    )
                    rows.append(current)
                    continue

                # The narrative is the line labelled `Narrative` in the left
                # column; its text starts at the customer reference band.
                if current is not None and cells["bank_reference"].strip() == "Narrative":
                    narrative = " ".join(
                        cells[name] for name, _ in COLUMN_HEADERS[1:] if cells[name]
                    ).strip()
                    current.narrative = (
                        f"{current.narrative} {narrative}".strip()
                        if current.narrative
                        else narrative
                    )
                    current.narrative_provenance = _bbox(line, page_no)

    statement.rows = rows
    return statement


def parse_all(directory: str | Path) -> list[Statement]:
    """Parse every statement in a directory, ordered by filename."""
    return [parse_statement(p) for p in sorted(Path(directory).glob("*.pdf"))]
