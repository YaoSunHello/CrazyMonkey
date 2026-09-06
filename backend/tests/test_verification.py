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

ROOT = Path(__file__).resolve().parents[2]

# The committed dataset first, then the older flat drop-in. Same PDFs either way.
CANDIDATES = (
    ROOT / "samples" / "01-bank-statements-to-journal-entries" / "statements",
    ROOT / "samples" / "statements",
)
SAMPLES = next(
    (d for d in CANDIDATES if d.is_dir() and any(d.glob("*.pdf"))), CANDIDATES[0]
)
GBP = SAMPLES / "20260331_NI_V_SCSP_CALDER_GBP_3252.pdf"

pytestmark = pytest.mark.skipif(
    not GBP.exists(), reason="statement samples not present — see backend/README.md"
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


def test_missing_marker_cannot_be_verified_rather_than_unresolved():
    """Four of the seven statements print no opening marker.

    Absent evidence must not be reported as a pass or a failure — and the
    distinction between the two honest outcomes matters more than it looks.
    `UNRESOLVED` says the run fell short; `CANNOT_VERIFY` says the document does
    not carry what the check needs. Reported as the former, this looked like a
    shortfall, and the profile grew a nudge naming the two statements that print
    no markers so the model would not chase them. Two of those were hold-out
    documents — which stopped being a hold-out the moment somebody opened them
    to write that nudge. The right status removes the reason to look.
    """
    dkk = SAMPLES / "20260331_NI_A_B__FUND_II_CALDER_DKK_4319.pdf"
    if not dkk.exists():
        pytest.skip("sample not present")
    checks = run_parse_checks(parse_statement(dkk))
    assert status_of(checks, "printed_openings") == "CANNOT_VERIFY"
    assert [c for c in checks if c.status == "FAIL"] == []


def test_no_nudge_names_a_document():
    """A nudge naming a document is a note written by opening that document.

    Harmless-looking, and it is how a hold-out quietly stops being one. If a
    document needs special handling, the check that judges it should say so
    generically instead.
    """
    from app.profiles import available, load

    named = {
        (name, spec.name, tuple(nudge.documents))
        for name in available()
        for spec in load(name).passes
        for nudge in spec.nudges
        if nudge.documents
    }
    assert named == set(), f"nudges naming specific documents: {named}"


def test_provenance_failure_names_the_likely_cause(statement):
    """"Not found" teaches nothing; the near-miss is the useful part.

    A run failed 0/19 on this check because the model joined every character
    with a space. The evidence said only "not found in the PDF text", and four
    attempts went by without it being fixed.
    """
    from app.verification.checks import check_reference_provenance

    real = statement.rows[0].bank_reference
    statement.rows[0].bank_reference = " ".join(real)      # T T   A B C …

    check = check_reference_provenance(statement)
    assert check.status == "FAIL"
    assert real in check.evidence, "the evidence should show what would have matched"
    assert "whitespace inserted between characters" in check.evidence
