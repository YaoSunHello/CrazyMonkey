"""Deterministic checks over a parsed statement.

Pure functions. No LLM, no network, no printing, no imports from the agent or
the sandbox — this module must run, and its tests must pass, with
`openai-agents` and `daytona` uninstalled. That is the mechanical guarantee
that the agent is validated against exactly what ships, rather than against a
second implementation that has quietly drifted.

Every check returns PASS, FAIL or UNRESOLVED:

- FAIL       the arithmetic or structure is wrong. The parse is broken.
- UNRESOLVED the row parsed correctly but a value has no match in the
             reference data. A human decides. Never a failure.

The balance chain is the oracle. A statement is printed newest-first and each
row's `Balance` is the balance *after* that transaction, so the balance before
row i must equal the balance of row i+1 — the next row down is the older one.
Nothing about that depends on us reading the narrative correctly, which is why
it can referee the parse.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal

from app.models import Check, Statement

# Every transaction line carries a posting time; the day-boundary markers and
# page furniture do not. Counting them gives a row count derived from the raw
# text, independent of the column-band parse it is checking.
TIME = re.compile(r"\b\d{2}:\d{2}\b")


def _as_date(text: str) -> date | None:
    """Parse a statement date such as '31 Mar 2026'. None if it isn't one."""
    try:
        return datetime.strptime(text.strip(), "%d %b %Y").date()
    except ValueError:
        return None


def _check(name: str, scope: str, ok: bool, detail: str, evidence: str = "") -> Check:
    return Check(
        name=name,
        scope=scope,
        status="PASS" if ok else "FAIL",
        detail=detail,
        evidence=evidence,
    )


def check_balance_chain(statement: Statement) -> Check:
    """Balance[i] - Amount[i] == Balance[i+1] for every consecutive pair."""
    rows = statement.rows
    breaks: list[str] = []

    for i in range(len(rows) - 1):
        this, nxt = rows[i], rows[i + 1]
        if this.balance is None or nxt.balance is None:
            breaks.append(f"row {i}: missing balance")
            continue
        expected = this.balance - this.amount
        if expected != nxt.balance:
            breaks.append(
                f"row {i}->{i + 1}: {this.balance} - ({this.amount}) = {expected}, "
                f"but row {i + 1} reads {nxt.balance} "
                f"(delta {nxt.balance - expected}) [{this.provenance.as_citation()}]"
            )

    links = max(len(rows) - 1, 0)
    return _check(
        "balance_chain",
        statement.account_short_code,
        not breaks,
        f"{links - len(breaks)}/{links} links hold",
        "\n".join(breaks[:5]),
    )


def check_closing_balance(statement: Statement) -> Check:
    """The newest row's balance is the statement's printed closing balance."""
    if statement.closing_balance is None:
        return Check(
            name="closing_balance",
            scope=statement.account_short_code,
            status="UNRESOLVED",
            detail="no closing balance printed on the statement",
        )
    if not statement.rows:
        return _check("closing_balance", statement.account_short_code, False, "no rows parsed")

    newest = statement.rows[0].balance
    ok = newest == statement.closing_balance
    return _check(
        "closing_balance",
        statement.account_short_code,
        ok,
        f"newest row {newest} vs printed {statement.closing_balance}",
        "" if ok else f"delta {(newest or Decimal(0)) - statement.closing_balance}",
    )


def check_printed_openings(statement: Statement) -> Check:
    """Every 'Balance brought forward' marker is reproduced from the movements.

    A marker states the balance at the start of a day, so subtracting that day's
    transactions and every later one from the closing balance must reproduce it.

    This is the check that catches a transaction dropped or duplicated in the
    *middle* of a statement, which the chain alone cannot: removing a row leaves
    the surviving links perfectly consistent with each other. Deriving from the
    closing balance and the sum of movements is what makes the omission visible
    — and it is the same "opening plus movements equals closing" a fund manager
    would do by hand.
    """
    if not statement.printed_openings:
        return Check(
            name="printed_openings",
            scope=statement.account_short_code,
            status="UNRESOLVED",
            detail="statement prints no 'Balance brought forward' markers",
        )
    if not statement.rows or statement.rows[0].balance is None:
        return _check("printed_openings", statement.account_short_code, False, "no rows parsed")

    newest = statement.rows[0].balance
    problems: list[str] = []

    for marker_date, printed in statement.printed_openings.items():
        boundary = _as_date(marker_date)
        if boundary is None:
            continue
        movements = sum(
            (r.amount for r in statement.rows if (d := _as_date(r.value_date)) and d >= boundary),
            Decimal(0),
        )
        derived = newest - movements
        if derived != printed:
            problems.append(
                f"{marker_date}: closing {newest} - movements {movements} = {derived}, "
                f"but the statement prints {printed} (delta {derived - printed})"
            )

    checked = len(statement.printed_openings)
    return _check(
        "printed_openings",
        statement.account_short_code,
        not problems,
        f"{checked - len(problems)}/{checked} printed markers reproduce from the movements",
        "\n".join(problems[:5]),
    )


def check_row_count(statement: Statement) -> Check:
    """Parsed row count matches the transaction lines visible in the raw text."""
    expected = sum(len(TIME.findall(page)) for page in statement.page_text)
    ok = expected == len(statement.rows)
    return _check(
        "row_count",
        statement.account_short_code,
        ok,
        f"parsed {len(statement.rows)}, raw text shows {expected}",
        "" if ok else "a transaction line was dropped or duplicated by the parse",
    )


def check_one_amount_per_row(statement: Statement) -> Check:
    """Every row carries exactly one of credit or debit."""
    bad = [
        f"row {i}: credit={r.credit} debit={r.debit} [{r.provenance.as_citation()}]"
        for i, r in enumerate(statement.rows)
        if (r.credit is None) == (r.debit is None)
    ]
    return _check(
        "one_amount_per_row",
        statement.account_short_code,
        not bad,
        f"{len(statement.rows) - len(bad)}/{len(statement.rows)} rows have exactly one amount",
        "\n".join(bad[:5]),
    )


def _provenance_hint(reference: str, text: str) -> str:
    """Say *why* a reference is not in the document, where that is knowable.

    "not found in the PDF" is true but teaches nothing, and a caller that
    cannot see the cause will usually resubmit the same mistake. Two
    near-misses are common enough to name outright: extra whitespace inserted
    between characters, and a reference that is nearly right but for case.
    """
    # Character-joined text keeps the document's real spaces as *runs* of
    # spaces, so collapsing runs to one and dropping the singles recovers the
    # original: "T T   A B C" -> "TT ABC".
    unjoined = "  ".join(part.replace(" ", "") for part in reference.split("   "))
    unjoined = " ".join(unjoined.split("  "))
    for candidate in (unjoined, "".join(reference.split())):
        if candidate and candidate != reference and candidate in text:
            return (
                f" — but {candidate!r} is. The reference has whitespace inserted "
                "between characters; join them without separators."
            )
    squashed = "".join(reference.split())
    if squashed and squashed.lower() in text.lower().replace(" ", ""):
        return f" — {squashed!r} appears in the document with different spacing or case."
    return ""


def check_reference_provenance(statement: Statement) -> Check:
    """Every bank reference appears literally in the source PDF.

    This is what makes a citation defensible: the value on screen is not a
    reconstruction, it is a substring of the document the reviewer can open.
    """
    text = statement.full_text
    missing = [
        f"row {i}: {r.bank_reference!r} not found in the PDF text"
        f"{_provenance_hint(r.bank_reference, text)}"
        for i, r in enumerate(statement.rows)
        if r.bank_reference and r.bank_reference not in text
    ]
    return _check(
        "reference_provenance",
        statement.account_short_code,
        not missing,
        f"{len(statement.rows) - len(missing)}/{len(statement.rows)} references are literal PDF substrings",
        "\n".join(missing[:5]),
    )


PARSE_CHECKS = (
    check_balance_chain,
    check_closing_balance,
    check_printed_openings,
    check_row_count,
    check_one_amount_per_row,
    check_reference_provenance,
)


def run_parse_checks(statement: Statement) -> list[Check]:
    return [check(statement) for check in PARSE_CHECKS]
