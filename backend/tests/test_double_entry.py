"""Balancing is not the same as being right.

A batch that nets to zero is arithmetic. A *journal* also has structure: one
batch per transaction, both sides inside it. Only checking the arithmetic let a
real defect through — every line carried a blank batch id, so 94 lines landed in
one bucket, that bucket netted to zero, and the check passed while 200 lines
carried 18 distinct ids instead of 100. The arithmetic was never wrong. The
grouping was, and nothing was looking.

Two lines per batch and one batch per row are properties of double-entry
bookkeeping, not of any dataset.
"""

from __future__ import annotations

from app.verification import generic


def row(batch, amount="10.00", kind="Cash - Disbursed - EUR") -> dict:
    return {
        "journal_lines": [
            {"batch": batch, "amount": amount, "is_debit": True, "transaction_type": kind},
            {"batch": batch, "amount": amount, "is_debit": False, "transaction_type": kind},
        ]
    }


def run(rows, **options):
    return generic.run("double_entry", rows, "T", {"field": "journal_lines", **options})


# --- the arithmetic ------------------------------------------------------


def test_balanced_batches_pass():
    assert run([row("a"), row("b")]).status == "PASS"


def test_a_batch_that_does_not_net_to_zero_fails():
    rows = [row("a")]
    rows[0]["journal_lines"][1]["amount"] = "9.00"
    check = run(rows)
    assert check.status == "FAIL"
    assert "nets to" in check.evidence


def test_one_sided_batch_fails():
    rows = [{"journal_lines": [{"batch": "a", "amount": "10", "is_debit": True}]}]
    assert run(rows).status == "FAIL"


def test_no_lines_is_cannot_verify():
    assert run([{"narrative": "x"}]).status == "CANNOT_VERIFY"


# --- the structure, which is what actually broke --------------------------


def test_a_blank_batch_id_fails_instead_of_pooling_silently():
    """The defect that shipped.

    Every id-less line used to fall into one shared bucket. A pile of equal and
    opposite lines nets to zero however many rows it came from, so the check
    reported success on a journal that could not be posted.
    """
    check = run([row(""), row("")])
    assert check.status == "FAIL"
    assert "no batch id" in check.evidence


def test_a_null_batch_id_is_not_a_batch_called_none():
    """`str(None)` is `'None'`, which groups just as happily as a blank."""
    assert run([row(None), row("None")]).status == "FAIL"


def test_a_batch_shared_between_rows_fails():
    """A batch is one transaction. Two rows in one batch is a merge, not a total."""
    check = run([row("same"), row("same")])
    assert check.status == "FAIL"
    assert "carries lines from 2 rows" in check.evidence


def test_id_less_rows_are_kept_apart_so_each_is_reported():
    """Separating them is what makes the count honest, not just the verdict."""
    check = run([row(""), row(""), row("")])
    assert check.detail.startswith("3 batches over 3 rows")


# --- an exact shape, only where the profile knows it ----------------------


def test_an_extra_line_passes_unless_the_profile_declared_the_shape():
    """Some ledgers split a side across several lines, so this is not assumed."""
    rows = [row("a")]
    rows[0]["journal_lines"].append(
        {"batch": "a", "amount": "5.00", "is_debit": True, "transaction_type": "x"}
    )
    rows[0]["journal_lines"].append(
        {"batch": "a", "amount": "5.00", "is_debit": False, "transaction_type": "x"}
    )
    assert run(rows).status == "PASS"
    assert run(rows, lines_per_batch=2).status == "FAIL"
