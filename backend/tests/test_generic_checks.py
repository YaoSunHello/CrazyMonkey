"""The checks that judge a resolution, and the failure they exist to catch.

The tempting failure is not a wrong match — it is a *confident* one. Both
specifications name it: "unmatched rows are forced to the nearest master-list
name" and "missing data becomes MATCH" are listed as failure conditions, not
inaccuracies. Most of what follows is about making those impossible to reach.

Offline, like the rest of `verification/`: no model, no sandbox, no network.
"""

from __future__ import annotations

import pytest

from app.kit.reference_kit import Table
from app.verification import generic


@pytest.fixture
def tables() -> dict[str, Table]:
    return {
        "related_parties": Table(
            name="related_parties",
            columns=["Related Party"],
            rows=[{"Related Party": "NI ABF I SCSp"}, {"Related Party": "Garrfield"}],
        )
    }


POOL = ["related_parties:Related Party"]


def row(**over) -> dict:
    base = {
        "narrative": "NI ABF I SCSP, PMT FRM NI ABF II SCSP PROJECT CEPHALUS",
        "counterparty_raw": "NI ABF I SCSP",
        "counterparty_match": {
            "status": "MATCH",
            "matched_name": "NI ABF I SCSp",
            "table": "related_parties",
        },
        "classification": "Investment Transfer",
    }
    return {**base, **over}


# --- provenance ----------------------------------------------------------


def test_a_value_taken_from_the_narrative_passes():
    check = generic.run("provenance", [row()], "T", {"field": "counterparty_raw"})
    assert check.status == "PASS"


def test_an_invented_value_fails_and_says_which_row():
    check = generic.run(
        "provenance", [row(counterparty_raw="ACME HOLDINGS")], "T", {"field": "counterparty_raw"}
    )
    assert check.status == "FAIL"
    assert "row 0" in check.evidence
    assert "ACME HOLDINGS" in check.evidence


def test_provenance_ignores_case_because_the_bank_shouts():
    """The bank writes in capitals; the value is still the one in the document."""
    check = generic.run(
        "provenance",
        [row(narrative="ni abf i scsp paid", counterparty_raw="NI ABF I SCSP")],
        "T",
        {"field": "counterparty_raw"},
    )
    assert check.status == "PASS"


def test_nothing_claimed_is_cannot_verify_not_pass():
    """No claims is not the same as every claim holding.

    A pass here would let a run that resolved nothing at all look identical to
    one that resolved everything correctly.
    """
    check = generic.run(
        "provenance", [row(counterparty_raw=None)], "T", {"field": "counterparty_raw"}
    )
    assert check.status == "CANNOT_VERIFY"


# --- membership: the check that matters ----------------------------------


def test_a_match_that_is_really_in_the_table_passes(tables):
    check = generic.run(
        "membership", [row()], "T", {"field": "counterparty_match", "tables": POOL}, tables
    )
    assert check.status == "PASS"


def test_a_fabricated_match_fails(tables):
    """The whole point. A confident wrong answer must not get through."""
    fabricated = row(
        counterparty_match={
            "status": "MATCH",
            "matched_name": "Totally Made Up Ltd",
            "table": "related_parties",
        }
    )
    check = generic.run(
        "membership", [fabricated], "T", {"field": "counterparty_match", "tables": POOL}, tables
    )
    assert check.status == "FAIL"
    assert "Totally Made Up Ltd" in check.evidence


def test_a_match_that_names_nothing_fails(tables):
    check = generic.run(
        "membership",
        [row(counterparty_match={"status": "MATCH"})],
        "T",
        {"field": "counterparty_match", "tables": POOL},
        tables,
    )
    assert check.status == "FAIL"
    assert "nothing matched" in check.evidence


def test_unresolved_is_an_honest_outcome_and_passes(tables):
    """52 of 100 rows genuinely have no counterparty. That is not a failure."""
    check = generic.run(
        "membership",
        [row(counterparty_match={"status": "UNRESOLVED", "matched_name": None})],
        "T",
        {"field": "counterparty_match", "tables": POOL},
        tables,
    )
    assert check.status == "PASS"
    assert "1 UNRESOLVED" in check.detail


def test_an_unknown_status_fails_rather_than_being_ignored(tables):
    """Both specs hard-fail a result that is not one of the four states."""
    check = generic.run(
        "membership",
        [row(counterparty_match={"status": "probably"})],
        "T",
        {"field": "counterparty_match", "tables": POOL},
        tables,
    )
    assert check.status == "FAIL"


def test_a_flat_status_string_is_accepted_too(tables):
    """`business-case-2` uses `counterparty_status`, the other spec nests it.

    Both must work, or a profile could not choose its own field names without
    forking the check.
    """
    check = generic.run(
        "membership",
        [row(counterparty_match="UNRESOLVED")],
        "T",
        {"field": "counterparty_match", "tables": POOL},
        tables,
    )
    assert check.status == "PASS"


# --- completeness and vocabulary -----------------------------------------


def test_an_omitted_resolution_is_not_unresolved():
    """It is unexamined, and the reviewer needs to know the difference."""
    check = generic.run(
        "completeness", [{"narrative": "x"}], "T", {"fields": ["counterparty_match"]}
    )
    assert check.status == "FAIL"
    assert "no status for counterparty_match" in check.evidence


def test_a_label_outside_the_declared_set_fails():
    check = generic.run(
        "vocabulary",
        [row(classification="Whatever")],
        "T",
        {"field": "classification", "allowed": ["Investment Transfer", "Other"]},
    )
    assert check.status == "FAIL"


def test_the_vocabulary_comes_from_the_profile_not_the_code():
    """The workbook uses seven labels where both specs list six.

    `Investment Transfer` and `Other` are real and `Investor` never appears. A
    vocabulary baked into the verifier would have made the real data wrong.
    """
    check = generic.run(
        "vocabulary",
        [row(classification="Investment Transfer")],
        "T",
        {"field": "classification", "allowed": ["Investment Transfer"]},
    )
    assert check.status == "PASS"


# --- agreement between samples -------------------------------------------


def sampled(primary: dict, other: dict) -> dict:
    return {**primary, "_samples": [other]}


def test_rows_two_samples_agree_on_pass():
    rows = [sampled({"classification": "Other"}, {"classification": "Other"})]
    check = generic.run("agreement", rows, "T", {"fields": ["classification"]})
    assert check.status == "PASS"


def test_a_disagreement_is_unresolved_not_a_failure():
    """The run is not broken — the row was not decided, and that is the finding.

    Failing here would throw away a sample that is right half the time.
    """
    rows = [sampled({"classification": "Review"}, {"classification": "Other"})]
    check = generic.run("agreement", rows, "T", {"fields": ["classification"]})
    assert check.status == "UNRESOLVED"
    assert "one sample says" in check.evidence


def test_a_row_differing_on_two_fields_is_still_one_row():
    """Counting disagreements rather than rows made 1 of 2 read as 0 of 2."""
    rows = [
        sampled(
            {"classification": "Review", "counterparty_match": {"status": "MATCH"}},
            {"classification": "Other", "counterparty_match": {"status": "UNRESOLVED"}},
        ),
        sampled({"classification": "Other"}, {"classification": "Other"}),
    ]
    check = generic.run(
        "agreement", rows, "T", {"fields": ["classification", "counterparty_match"]}
    )
    assert "1/2 rows agree" in check.detail


def test_one_sample_cannot_be_compared_with_itself():
    check = generic.run("agreement", [{"classification": "Other"}], "T", {"fields": ["classification"]})
    assert check.status == "CANNOT_VERIFY"


def test_samples_of_different_lengths_are_not_compared():
    """Two samples with different row counts are not comparable row by row, and
    aligning them anyway would report an off-by-one as a disagreement."""
    from app.agent import _attach_samples

    primary = [{"a": 1}, {"a": 2}]
    assert _attach_samples(primary, [[{"a": 1}]]) == primary
    merged = _attach_samples(primary, [[{"a": 9}, {"a": 8}]])
    assert merged[0]["_samples"] == [{"a": 9}]


# --- the registry --------------------------------------------------------


def test_an_unknown_check_name_is_a_clear_error():
    """A typo in a profile must not silently mean "no check ran"."""
    with pytest.raises(KeyError) as caught:
        generic.run("provenence", [], "T", {})
    assert "provenance" in str(caught.value)


def test_reported_names_match_what_a_profile_announces():
    """A nudge keyed to a check name only fires if these agree."""
    assert generic.name_for("provenance", {"field": "counterparty_raw"}) == (
        "counterparty_raw_provenance"
    )
    assert generic.name_for("completeness", {}) == "resolution_completeness"
