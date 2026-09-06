"""The check that looks up from the batch to the row it came from.

`double_entry` asks whether a batch nets to zero, and a batch of 30,190.87
against a row of 301,908.70 does. Every internal check passes and the journal
is wrong by a decimal place — the one error nobody catches by reading the
journal, because the journal is self-consistent.

So the pairing matters more than either check alone: one asserts the journal
agrees with itself, the other that it still agrees with its source. The first
test here is the whole argument, and it fails if the two ever stop being
different questions.

Offline, like the rest of `verification/`: no model, no sandbox, no network.
"""

from __future__ import annotations

from app.verification import generic


def rows(row_amount: str, line_amount: str, batch: str = "2") -> list[dict]:
    return [
        {
            "amount": row_amount,
            "journal_lines": [
                {"batch": batch, "amount": line_amount, "is_debit": True},
                {"batch": batch, "amount": line_amount, "is_debit": False},
            ],
        }
    ]


def run(name: str, data: list[dict]):
    return generic.run(name, data, "EUR_8102", {}, {})


def test_a_balanced_batch_of_the_wrong_size_passes_double_entry_and_fails_here():
    """The reason this check exists."""
    slipped = rows("-301908.70", "30190.87")
    assert run("double_entry", slipped).status == "PASS"

    check = run("stage_tie", slipped)
    assert check.status == "FAIL"
    assert "301,908.70" in check.evidence
    assert "30,190.87" in check.evidence


def test_a_correct_journal_satisfies_both():
    correct = rows("-301908.70", "301908.70")
    assert run("double_entry", correct).status == "PASS"
    assert run("stage_tie", correct).status == "PASS"


def test_sign_of_the_row_does_not_matter():
    """A receipt and a payment both move their magnitude through the journal."""
    assert run("stage_tie", rows("301908.70", "301908.70")).status == "PASS"


def test_credit_and_debit_rows_are_read_when_there_is_no_amount():
    data = [
        {
            "debit": "-100.00",
            "journal_lines": [
                {"batch": "1", "amount": "100.00", "is_debit": True},
                {"batch": "1", "amount": "100.00", "is_debit": False},
            ],
        },
        {
            "credit": "50.00",
            "journal_lines": [
                {"batch": "2", "amount": "50.00", "is_debit": True},
                {"batch": "2", "amount": "50.00", "is_debit": False},
            ],
        },
    ]
    check = run("stage_tie", data)
    assert check.status == "PASS"
    assert "150.00" in check.evidence


def test_no_journal_lines_cannot_verify_rather_than_passing():
    """A profile that stops at resolution must not be turned red, or green."""
    check = run("stage_tie", [{"amount": "-301908.70"}])
    assert check.status == "CANNOT_VERIFY"


def test_a_one_sided_journal_fails():
    data = [
        {
            "amount": "-100.00",
            "journal_lines": [{"batch": "1", "amount": "100.00", "is_debit": True}],
        }
    ]
    assert run("stage_tie", data).status == "FAIL"


def test_registered_under_its_profile_name():
    assert "stage_tie" in generic.REGISTRY
