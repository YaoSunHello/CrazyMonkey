"""Corpus-level reconciliation: the universe and the aggregates still tie.

Two kinds of test here, and both are needed.

The synthetic cases pin the *logic* — that a dropped row and an invented row
are different failures, that a compensating pair does not launder a broken
universe into a clean aggregate, and that an empty side is `CANNOT_VERIFY`
rather than a pass.

The dataset case pins the *numbers*. The seven supplied statements reconcile
exactly, and those totals are recorded here as a regression fixture: if a
future parser change moves 12,376,173.38 by a cent, the suite says so. They
were computed from the PDFs and the verified workbook independently of the
parser under test.

Offline, like the rest of `verification/`: no model, no sandbox, no network.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.ingestion.statements import parse_statement
from app.models import Provenance, Statement, StatementRow
from app.verification.reconciliation import (
    check_aggregate,
    check_stage_tie,
    check_universe,
    run_reconciliation,
)


STATEMENTS = (
    Path(__file__).resolve().parents[2]
    / "samples/01-bank-statements-to-journal-entries/statements"
)

# Measured from the seven supplied statements. See the module docstring.
CORPUS_ROWS = 100
CORPUS_SIGNED_TOTAL = Decimal("12376173.38")
CORPUS_ABSOLUTE_MOVEMENT = Decimal("172428933.02")


# --------------------------------------------------------------------------
# synthetic: the logic
# --------------------------------------------------------------------------


def _row(amount: str, balance: str) -> StatementRow:
    value = Decimal(amount)
    return StatementRow(
        account_number="240-149813-030",
        currency="EUR",
        credit=value if value > 0 else None,
        debit=value if value <= 0 else None,
        balance=Decimal(balance),
        provenance=Provenance(
            source_file="s.pdf", page=1, x0=0.0, top=0.0, x1=1.0, bottom=1.0
        ),
    )


def _statement(*rows: StatementRow) -> Statement:
    return Statement(
        source_file="s.pdf",
        account_short_code="EUR_8102",
        rows=list(rows),
    )


def _derived(*pairs: tuple[str, str]) -> list[dict]:
    return [{"amount": Decimal(a), "balance": Decimal(b)} for a, b in pairs]


SOURCE = _statement(
    _row("-301908.70", "20088.76"),
    _row("6550000.00", "6567807.35"),
    _row("-0.44", "20088.32"),
)


def test_identical_sides_reconcile():
    rows = _derived(
        ("-301908.70", "20088.76"), ("6550000.00", "6567807.35"), ("-0.44", "20088.32")
    )
    universe, aggregate = run_reconciliation([SOURCE], rows)
    assert universe.status == "PASS"
    assert aggregate.status == "PASS"


def test_dropped_row_fails_the_universe():
    rows = _derived(("-301908.70", "20088.76"), ("6550000.00", "6567807.35"))
    check = check_universe([SOURCE], rows)
    assert check.status == "FAIL"
    assert "1 dropped" in check.evidence


def test_invented_row_fails_the_universe():
    rows = _derived(
        ("-301908.70", "20088.76"),
        ("6550000.00", "6567807.35"),
        ("-0.44", "20088.32"),
        ("-999.00", "1.00"),
    )
    check = check_universe([SOURCE], rows)
    assert check.status == "FAIL"
    assert "1 not in source" in check.evidence


def test_compensating_pair_breaks_the_universe_but_not_the_aggregate():
    """The reason these are two checks and not one.

    Swapping a +100/-100 pair for a different +100/-100 pair leaves the signed
    total untouched. Only the universe notices.
    """
    source = _statement(_row("100.00", "100.00"), _row("-100.00", "0.00"))
    rows = _derived(("100.00", "555.00"), ("-100.00", "444.00"))
    assert check_aggregate([source], rows).status == "PASS"
    assert check_universe([source], rows).status == "FAIL"


def test_misread_magnitude_breaks_the_aggregate():
    rows = _derived(
        ("-301908.70", "20088.76"), ("655000.00", "6567807.35"), ("-0.44", "20088.32")
    )
    check = check_aggregate([SOURCE], rows)
    assert check.status == "FAIL"
    assert "difference" in check.evidence


def test_empty_side_cannot_verify_rather_than_passing():
    """A reconciliation with nothing on one side is not a clean reconciliation."""
    assert check_universe([SOURCE], []).status == "CANNOT_VERIFY"
    assert check_aggregate([SOURCE], []).status == "CANNOT_VERIFY"
    assert check_universe([], _derived(("1.00", "1.00"))).status == "CANNOT_VERIFY"


def test_reconciles_on_values_not_on_parsed_identifiers():
    """The rule the module exists to enforce.

    Derived rows carrying a mangled reference — the real failure that prompted
    this, where a two-token bank reference was clipped to its first word — must
    still reconcile, because the reference is not part of the key.
    """
    rows = _derived(
        ("-301908.70", "20088.76"), ("6550000.00", "6567807.35"), ("-0.44", "20088.32")
    )
    for row in rows:
        row["bank_reference"] = "TT"  # clipped from "TT JSL083B50KRNM"
    assert check_universe([SOURCE], rows).status == "PASS"


def test_stage_tie_catches_a_balanced_batch_carrying_the_wrong_amount():
    """Double entry alone passes this; the stage tie does not."""
    rows = _derived(("-301908.70", "20088.76"))
    journal = [
        {"amount": Decimal("30190.87"), "is_debit": "Yes"},
        {"amount": Decimal("30190.87"), "is_debit": "No"},
    ]
    check = check_stage_tie(rows, journal)
    assert check.status == "FAIL"

    correct = [
        {"amount": Decimal("301908.70"), "is_debit": "Yes"},
        {"amount": Decimal("301908.70"), "is_debit": "No"},
    ]
    assert check_stage_tie(rows, correct).status == "PASS"


# --------------------------------------------------------------------------
# dataset: the numbers
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def corpus() -> list[Statement]:
    paths = sorted(STATEMENTS.glob("*.pdf"))
    assert paths, f"no statements found under {STATEMENTS}"
    return [parse_statement(path) for path in paths]


def test_supplied_corpus_has_the_expected_shape(corpus):
    assert len(corpus) == 7
    assert sum(len(s.rows) for s in corpus) == CORPUS_ROWS


def test_supplied_corpus_reconciles_to_itself(corpus):
    """The parse round-trips: what came out of the PDFs still ties to them."""
    rows = [
        {"amount": row.amount, "balance": row.balance}
        for statement in corpus
        for row in statement.rows
    ]
    universe, aggregate = run_reconciliation(corpus, rows)
    assert universe.status == "PASS", universe.evidence
    assert aggregate.status == "PASS", aggregate.evidence


def test_supplied_corpus_totals_are_unchanged(corpus):
    """Regression fixture. A cent of drift here is a parser change."""
    signed = sum((row.amount for s in corpus for row in s.rows), Decimal(0))
    absolute = sum((abs(row.amount) for s in corpus for row in s.rows), Decimal(0))
    assert signed == CORPUS_SIGNED_TOTAL
    assert absolute == CORPUS_ABSOLUTE_MOVEMENT


# --------------------------------------------------------------------------
# cli wiring
# --------------------------------------------------------------------------


def test_derived_rows_reads_both_payload_shapes(tmp_path):
    """A bare list and a run payload with a `rows` key both load."""
    from app.cli import _derived_rows

    bare = tmp_path / "bare.json"
    bare.write_text('[{"amount": "-0.44", "balance": "20088.32"}]')
    assert _derived_rows(str(bare)) == [{"amount": "-0.44", "balance": "20088.32"}]

    wrapped = tmp_path / "wrapped.json"
    wrapped.write_text('{"run_id": "x", "rows": [{"amount": "1.00", "balance": "2.00"}]}')
    assert _derived_rows(str(wrapped)) == [{"amount": "1.00", "balance": "2.00"}]


def test_derived_rows_absent_is_empty_not_invented():
    """No --against means no second side, which the checks report honestly."""
    from app.cli import _derived_rows

    assert _derived_rows(None) == []
    assert check_universe([SOURCE], _derived_rows(None)).status == "CANNOT_VERIFY"
