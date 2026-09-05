"""The verifier must catch a broken parse. These tests prove it does.

No LLM, no sandbox, no network. If these ever need `openai-agents` or
`daytona` installed to run, the verifier has stopped being independent of the
agent it is supposed to referee.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.ingestion.statements import parse_statement
from app.verification.checks import run_parse_checks

SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "statements"
GBP = SAMPLES / "20260331_NI_V_SCSP_CALDER_GBP_3252.pdf"

pytestmark = pytest.mark.skipif(
    not GBP.exists(), reason="statement samples not present — see samples/README.md"
)


@pytest.fixture(scope="module")
def statement():
    return parse_statement(GBP)


def status_of(checks, name):
    return next(c.status for c in checks if c.name == name)


def test_parses_every_transaction(statement):
    assert len(statement.rows) == 16
    assert statement.currency == "GBP"
    assert statement.account_number == "240-222731-132"


def test_clean_parse_has_no_failures(statement):
    assert [c for c in run_parse_checks(statement) if c.status == "FAIL"] == []


def test_balance_chain_holds(statement):
    assert status_of(run_parse_checks(statement), "balance_chain") == "PASS"


def test_closing_balance_matches_the_printed_figure(statement):
    assert statement.closing_balance == Decimal("103014.97")
    assert status_of(run_parse_checks(statement), "closing_balance") == "PASS"


def test_every_reference_is_a_literal_pdf_substring(statement):
    assert status_of(run_parse_checks(statement), "reference_provenance") == "PASS"
    for row in statement.rows:
        assert row.bank_reference in statement.full_text


def test_a_corrupted_amount_breaks_the_chain(statement):
    """The demo moment, as a test: change one number and the verifier objects.

    This is the property the whole design rests on. If a wrong amount could
    slip through, nothing downstream could be trusted.
    """
    statement.rows[3].debit = (statement.rows[3].debit or Decimal(0)) - Decimal("100.00")

    chain = next(c for c in run_parse_checks(statement) if c.name == "balance_chain")
    assert chain.status == "FAIL"
    assert "delta" in chain.evidence
    # The evidence names the row, so the agent knows where to look.
    assert "row 3->4" in chain.evidence


def test_a_dropped_row_is_caught_even_though_the_chain_still_links(statement):
    """Deleting a row keeps the remaining links self-consistent.

    Only the independent row count and the printed opening marker notice, which
    is exactly why the verifier does not rely on the chain alone.
    """
    del statement.rows[5]
    checks = run_parse_checks(statement)
    assert status_of(checks, "row_count") == "FAIL"
    assert status_of(checks, "printed_openings") == "FAIL"


def test_missing_marker_is_unresolved_not_failed():
    """Four of the seven statements print no opening marker.

    Absent evidence must not be reported as either a pass or a failure.
    """
    dkk = SAMPLES / "20260331_NI_A_B__FUND_II_CALDER_DKK_4319.pdf"
    if not dkk.exists():
        pytest.skip("sample not present")
    checks = run_parse_checks(parse_statement(dkk))
    assert status_of(checks, "printed_openings") == "UNRESOLVED"
    assert [c for c in checks if c.status == "FAIL"] == []
