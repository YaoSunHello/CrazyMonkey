"""Renamed uploads keep their evidence; readable non-statements are rejected."""

from pathlib import Path

import pytest
from reportlab.pdfgen.canvas import Canvas

from app.ingestion.statements import (
    UnsupportedStatementError,
    ensure_supported_statement,
    parse_statement,
)
from app.verification.checks import run_parse_checks


SOURCE = (
    Path(__file__).resolve().parents[2]
    / "samples/01-bank-statements-to-journal-entries/statements"
    / "20260331_NI_A_B__FUND_II_CALDER_EUR_8102.pdf"
)


@pytest.fixture
def statement():
    return parse_statement(SOURCE)


@pytest.mark.parametrize("filename", ["statement.pdf", "my_renamed_statement.pdf"])
def test_renamed_statement_uses_printed_account_identity(tmp_path, statement, filename):
    renamed = tmp_path / filename
    renamed.write_bytes(SOURCE.read_bytes())
    parsed = parse_statement(renamed)
    ensure_supported_statement(parsed)

    assert statement.account_short_code == "EUR_8102"
    assert parsed.account_short_code == "EUR_240149813030"
    assert parsed.source_file == filename
    assert parsed.account_number == statement.account_number
    assert parsed.closing_balance == statement.closing_balance
    assert parsed.rows == statement.rows
    assert [(check.name, check.status) for check in run_parse_checks(parsed)] == [
        (check.name, check.status) for check in run_parse_checks(statement)
    ]


def test_readable_ordinary_pdf_is_not_a_supported_statement(tmp_path):
    path = tmp_path / "meeting_notes.pdf"
    canvas = Canvas(str(path))
    canvas.drawString(72, 720, "Meeting notes: discuss the account review tomorrow.")
    canvas.save()

    parsed = parse_statement(path)
    assert parsed.page_text
    assert parsed.rows == []
    with pytest.raises(UnsupportedStatementError, match="not a supported Calder"):
        ensure_supported_statement(parsed)


@pytest.mark.parametrize("missing", ["rows", "account", "currency", "closing", "evidence"])
def test_statement_guard_requires_essential_source_evidence(statement, missing):
    if missing == "rows":
        statement.rows = []
    elif missing == "account":
        statement.account_number = ""
    elif missing == "currency":
        statement.currency = ""
    elif missing == "closing":
        statement.closing_balance = None
    else:
        for row in statement.rows:
            row.bank_reference = ""
    with pytest.raises(UnsupportedStatementError):
        ensure_supported_statement(statement)


def test_layout_guard_leaves_bad_arithmetic_to_the_existing_verifier(statement):
    row = statement.rows[0]
    row.balance += 1
    ensure_supported_statement(statement)
    assert any(check.status == "FAIL" for check in run_parse_checks(statement))
