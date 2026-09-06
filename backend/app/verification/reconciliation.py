"""Corpus-level reconciliation: does the derived dataset still say what the
documents said?

`checks.py` verifies one statement against itself, and `generic.py` verifies
one resolution against a reference table. Both work a row or a document at a
time. Neither answers the question a fund manager actually asks first, which is
about the whole run:

    Is every transaction still here, and does it still add up?

Two assertions, and they are separate failures:

    universe    the set of records is unchanged — nothing dropped, nothing
                invented, nothing duplicated
    aggregate   the sum of the money is unchanged, to the cent

A run can pass one and fail the other. Dropping a +100 and a -100 keeps the
aggregate and breaks the universe. Reading 1,000.00 as 100.00 keeps the
universe and breaks the aggregate. Reporting them as one number would let
either hide the other, so they are two checks.

**Reconcile on values, not on identifiers we parsed.** This is the design rule
that matters, and it was learned the hard way: keying this comparison on the
bank reference reported 52 rows missing and 52 extra on a dataset that in fact
ties exactly, because the extractor had clipped a two-token reference to its
first word. A parsed identifier is a *hypothesis produced by the thing under
test*. The amount and the running balance are facts the document carries. Key
on those and the reconciler still works precisely when the extractor is broken
— which is the only time anyone needs it.

Multisets, not sets. Two rows may legitimately carry the same amount and
balance is unique per row within a statement, but the pairing is not assumed
unique across a corpus, and collapsing duplicates would silently forgive a
dropped row that happened to have a twin.

Absent input is `CANNOT_VERIFY`, never `PASS`. A reconciliation with nothing on
one side is not a clean reconciliation.

This module imports nothing from `agent.py`, `sandbox.py` or `profiles.py`, and
must not. The agent is judged by code it cannot reach.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

from app.models import Check, Statement

# The key each side of a reconciliation is reduced to. Both components come
# straight off the document; neither depends on reading the narrative.
RowKey = tuple[Decimal, Decimal | None]

MONEY = "{:,.2f}"


def _fmt(value: Decimal) -> str:
    return MONEY.format(value)


def _sample(keys: Counter[RowKey], limit: int = 5) -> str:
    """Render a few offending keys so a reviewer can find them in the source."""
    items = []
    for (amount, balance), count in list(keys.items())[:limit]:
        bal = "no balance" if balance is None else _fmt(balance)
        suffix = f" x{count}" if count > 1 else ""
        items.append(f"{_fmt(amount)} @ {bal}{suffix}")
    remaining = sum(keys.values()) - sum(
        c for _, c in list(keys.items())[:limit]
    )
    if remaining > 0:
        items.append(f"and {remaining} more")
    return "; ".join(items)


def statement_keys(statements: list[Statement]) -> Counter[RowKey]:
    """The corpus reduced to its reconcilable facts."""
    return Counter(
        (row.amount, row.balance) for statement in statements for row in statement.rows
    )


def derived_keys(rows: list[dict]) -> Counter[RowKey]:
    """The same reduction over derived rows.

    Accepts the pipeline's dict rows rather than a model so this can referee
    any downstream stage — staging, export, or a rebuilt spreadsheet — without
    that stage having to depend on this module.
    """
    keys: list[RowKey] = []
    for row in rows:
        amount = row.get("amount")
        if amount is None:
            credit, debit = row.get("credit"), row.get("debit")
            amount = credit if credit is not None else debit
        if amount is None:
            continue
        balance = row.get("balance")
        keys.append(
            (
                Decimal(str(amount)),
                None if balance is None else Decimal(str(balance)),
            )
        )
    return Counter(keys)


def check_universe(
    statements: list[Statement], rows: list[dict], scope: str = "all"
) -> Check:
    """Every source transaction appears in the derived data exactly once."""
    if not statements or not rows:
        return Check(
            name="corpus_universe",
            scope=scope,
            status="CANNOT_VERIFY",
            detail="One side of the reconciliation is empty.",
            evidence=f"{len(statements)} statements, {len(rows)} derived rows",
        )

    source, derived = statement_keys(statements), derived_keys(rows)
    dropped, invented = source - derived, derived - source
    n_dropped, n_invented = sum(dropped.values()), sum(invented.values())

    if not n_dropped and not n_invented:
        return _pass(
            "corpus_universe",
            scope,
            f"All {sum(source.values())} source transactions present exactly once.",
            f"{len(statements)} statements -> {sum(derived.values())} rows",
        )

    parts = []
    if n_dropped:
        parts.append(f"{n_dropped} dropped ({_sample(dropped)})")
    if n_invented:
        parts.append(f"{n_invented} not in source ({_sample(invented)})")
    return Check(
        name="corpus_universe",
        scope=scope,
        status="FAIL",
        detail="Derived rows do not reconcile to the source documents.",
        evidence=(
            f"source {sum(source.values())}, derived {sum(derived.values())}: "
            + "; ".join(parts)
        ),
    )


def check_aggregate(
    statements: list[Statement], rows: list[dict], scope: str = "all"
) -> Check:
    """The signed total of the corpus survives to the derived data, to the cent."""
    if not statements or not rows:
        return Check(
            name="corpus_aggregate",
            scope=scope,
            status="CANNOT_VERIFY",
            detail="One side of the reconciliation is empty.",
            evidence=f"{len(statements)} statements, {len(rows)} derived rows",
        )

    source = sum(
        (row.amount for statement in statements for row in statement.rows), Decimal(0)
    )
    derived = sum(
        (amount for (amount, _), count in derived_keys(rows).items() for _ in range(count)),
        Decimal(0),
    )
    difference = source - derived

    evidence = (
        f"source {_fmt(source)}, derived {_fmt(derived)}, difference {_fmt(difference)}"
    )
    if difference == 0:
        return _pass(
            "corpus_aggregate", scope, "Signed totals tie exactly.", evidence
        )
    return Check(
        name="corpus_aggregate",
        scope=scope,
        status="FAIL",
        detail="Signed totals do not tie to the source documents.",
        evidence=evidence,
    )


def check_stage_tie(
    rows: list[dict], journal: list[dict], scope: str = "all"
) -> Check:
    """The journal moves exactly the money the derived rows describe.

    Each transaction becomes one debit and one credit of the same magnitude, so
    the journal's debit total, its credit total, and the absolute total of the
    rows above it are three ways of writing the same number. Checking all three
    catches a batch that balances internally while carrying the wrong amount —
    which `check_double_entry` alone would pass.
    """
    if not rows or not journal:
        return Check(
            name="stage_tie",
            scope=scope,
            status="CANNOT_VERIFY",
            detail="One side of the reconciliation is empty.",
            evidence=f"{len(rows)} rows, {len(journal)} journal lines",
        )

    movement = sum(
        (abs(amount) * count for (amount, _), count in derived_keys(rows).items()),
        Decimal(0),
    )
    debits = sum(
        (Decimal(str(line.get("amount", 0))) for line in journal if _is_debit(line)),
        Decimal(0),
    )
    credits = sum(
        (Decimal(str(line.get("amount", 0))) for line in journal if not _is_debit(line)),
        Decimal(0),
    )

    evidence = (
        f"rows {_fmt(movement)}, debits {_fmt(debits)}, credits {_fmt(credits)}"
    )
    if movement == debits == credits:
        return _pass(
            "stage_tie", scope, "Journal ties to the rows it was built from.", evidence
        )
    return Check(
        name="stage_tie",
        scope=scope,
        status="FAIL",
        detail="Journal does not tie to the rows it was built from.",
        evidence=evidence,
    )


def _is_debit(line: dict) -> bool:
    value = line.get("is_debit", line.get("isDebit"))
    if isinstance(value, str):
        return value.strip().lower() in {"yes", "true", "debit", "dr"}
    return bool(value)


def _pass(name: str, scope: str, detail: str, evidence: str) -> Check:
    return Check(name=name, scope=scope, status="PASS", detail=detail, evidence=evidence)


def run_reconciliation(
    statements: list[Statement],
    rows: list[dict],
    journal: list[dict] | None = None,
    scope: str = "all",
) -> list[Check]:
    """Every corpus-level gate, in the order a reviewer would want them."""
    checks = [
        check_universe(statements, rows, scope),
        check_aggregate(statements, rows, scope),
    ]
    if journal is not None:
        checks.append(check_stage_tie(rows, journal, scope))
    return checks
