"""The achievement oracle, and two attempts at it that were gameable.

Every other check in `generic.py` asks whether an answer is *well formed*. None
asked whether the work got done, and the cost was measured rather than imagined:
a full day of runs was accepted on attempt 1, showing 1213 passing checks, while
28 of the 50 resolvable rows came back unresolved. A pipeline that resolves
nothing satisfies well-formedness perfectly.

Two attempts at the missing number failed, and the way they failed is the reason
these tests are written the way they are.

**The first could not fail.** It re-ran an exact lookup over the same span the
agent had already looked up, so on precisely the rows that mattered it could only
agree. Run against a batch that had missed 28 rows, it reported nothing.

**The second moved the problem.** It counted journal lines booked to the ledger's
holding account, which made the honest label the expensive one. The very next run
stopped writing `Suspense`, booked nine unresolved rows to a real but unrelated
account, and scored zero parked — while its own self-assertion said nine. The
account a row lands on is downstream of whether it resolved, so measuring the
shadow only teaches the shadow to move.

What is left counts the thing itself: statuses, which cannot be renamed without
`membership` and `vocabulary` objecting. Offline, like the rest of
`verification/`.
"""

from __future__ import annotations

import pytest

from app.kit.reference_kit import Table
from app.verification import generic


@pytest.fixture
def tables() -> dict[str, Table]:
    return {
        "coa": Table(
            name="coa",
            columns=["Trans Type"],
            rows=[
                {"Trans Type": "Cash - Disbursed - EUR"},
                {"Trans Type": "Payable - Third Party"},
                {"Trans Type": "Suspense (debit)"},
            ],
        ),
        "account_map": Table(
            name="account_map",
            columns=["Account Number", "Bank Account"],
            rows=[{"Account Number": "240-1", "Bank Account": "Kestrel II - Calder - EUR - 8102"}],
        ),
    }


CHART = {"field": "journal_lines", "value": "transaction_type", "chart": ["coa:Trans Type"]}


def booked(batch: str, kind: str = "Payable - Third Party") -> dict:
    return {
        "journal_lines": [
            {"batch": batch, "amount": "10.00", "is_debit": True, "transaction_type": kind},
            {
                "batch": batch,
                "amount": "10.00",
                "is_debit": False,
                "transaction_type": "Cash - Disbursed - EUR",
            },
        ]
    }


# --- posting: the chart is a closed vocabulary ---------------------------


def test_work_that_names_real_accounts_passes(tables):
    assert generic.run("posting", [booked("1"), booked("2")], "T", CHART, tables).status == "PASS"


def test_an_account_that_is_not_in_the_chart_fails(tables):
    """Invented and plausible is worse than invented and obvious.

    A fabricated account sits among five hundred real ones and survives review
    on appearance alone, which is exactly why the chart is checked rather than
    trusted.
    """
    check = generic.run("posting", [booked("1", "Payable - Imaginary")], "T", CHART, tables)
    assert check.status == "FAIL"
    assert "not in the chart of accounts" in check.evidence


def test_a_line_with_no_account_fails(tables):
    rows = [{"journal_lines": [{"batch": "1", "amount": "1", "is_debit": True}]}]
    assert generic.run("posting", rows, "T", CHART, tables).status == "FAIL"


def test_no_lines_is_cannot_verify_not_a_pass(tables):
    assert generic.run("posting", [{"narrative": "x"}], "T", CHART, tables).status == "CANNOT_VERIFY"


def test_posting_no_longer_judges_which_account_was_chosen(tables):
    """The regression guard for the gameable version.

    Booking every row to the holding account used to be reported here. It is
    not, deliberately: penalising the honest label taught a run to relabel
    rather than resolve. Whether enough resolved is `resolution_rate`'s
    question, and it asks it of the statuses.
    """
    parked = [booked(str(i), "Suspense (debit)") for i in range(5)]
    assert generic.run("posting", parked, "T", CHART, tables).status == "PASS"


# --- resolution_rate: the number that cannot be relabelled ----------------


def resolved(status: str, name: str = "Kestrel I SCSp") -> dict:
    return {
        "counterparty_raw": "KESTREL I SCSP",
        "counterparty_match": {"status": status, "matched_name": name if status != "UNRESOLVED" else None},
    }


def rate(rows, **over):
    return generic.run(
        "resolution_rate", rows, "T", {"field": "counterparty_match", "max_share": 0.25, **over}
    )


def test_the_rate_is_reported_not_judged():
    """It measures; it does not decide.

    A fixed ceiling cannot know that one statement is mostly internal movements
    naming nobody, and the one that shipped deadlocked such an account for six
    attempts: leave the rows unresolved and the rate fails, resolve them to the
    only candidate and another check fails. How much *ought* to resolve is a
    fact about the document, so the model reading it judges that and says so in
    its own assertions. This puts the number where a person can see it.
    """
    thin = rate([resolved("UNRESOLVED")] * 8 + [resolved("MATCH")])
    assert thin.status == "PASS"
    assert "8 did not" in thin.detail
    assert rate([resolved("MATCH")] * 4 + [resolved("UNRESOLVED")]).status == "PASS"


def test_a_proposal_counts_as_work_done():
    """PROBABLE is the honest escape, so it must not be punished as a miss.

    Otherwise the only ways out are a fabricated MATCH, which `membership`
    rejects, or a shrug — and the number would be pushing toward both.
    """
    assert rate([resolved("PROBABLE")] * 5).status == "PASS"


def test_a_row_naming_nobody_is_neither_numerator_nor_denominator():
    """Silence is a fact about the document, not a failure of the run.

    Counting it would pad the denominator until any rate looked acceptable —
    which is precisely how 12 correct out of 50 was once reported as 56%.
    """
    check = rate([resolved("CANNOT_VERIFY")] * 90 + [resolved("UNRESOLVED")] * 9 + [resolved("MATCH")])
    assert "9 did not" in check.detail
    assert "/10" in check.detail   # ten rows named somebody, not a hundred


def test_nothing_to_resolve_is_cannot_verify():
    assert rate([resolved("CANNOT_VERIFY")] * 3).status == "CANNOT_VERIFY"


def test_no_ceiling_remains_to_tune():
    """The guard against reintroducing a fitted constant here."""
    from app.verification import generic

    source = open(generic.__file__, encoding="utf-8").read()
    assert "max_share" not in source
    assert "min_overlap" not in source


# --- pairing: a status must agree with whether anything was read ----------


def paired(read, status) -> dict:
    return {"counterparty_raw": read, "counterparty_match": {"status": status}}


def pairing(rows):
    return generic.run(
        "pairing", rows, "T", {"field": "counterparty_match", "span": "counterparty_raw"}
    )


def test_a_read_value_and_a_real_outcome_agree():
    assert pairing([paired("KESTREL I SCSP", "MATCH"), paired(None, "CANNOT_VERIFY")]).status == "PASS"


def test_claiming_nothing_to_look_up_while_holding_the_value_fails():
    """The one that quietly empties the review queue.

    The queue holds rows a person must decide. A row saying its input was absent
    is saying there is nothing to decide — so this is not a cosmetic
    inconsistency, it is a row removing itself from human review while carrying
    the very value that needed reviewing.
    """
    check = pairing([paired("KESTREL I SCSP", "CANNOT_VERIFY")])
    assert check.status == "FAIL"
    assert "nothing to look up" in check.evidence


def test_resolving_something_that_was_never_read_fails():
    check = pairing([paired(None, "MATCH")])
    assert check.status == "FAIL"
    assert "needs something to have been read first" in check.evidence


def test_a_missing_status_is_left_to_completeness():
    """One finding, one check. Two checks reporting it reads as two problems."""
    assert pairing([{"counterparty_raw": "KESTREL I SCSP"}]).status == "PASS"
