"""Projecting one run into two different envelopes.

The design claim under test: two specifications wanting the same run described
differently should cost a JSON file, not a second pipeline. If a profile ever
needs Python to express its output, that claim is false and the abstraction
needs fixing rather than working around.

Offline. No model, no sandbox, no workbook.
"""

from __future__ import annotations

import json

import pytest

from app.emit import build, derive_review_queue, derive_summary
from app.profiles import load

CLEAN = {
    "page": 1,
    "narrative": "NI ABF I SCSP PMT FRM NI ABF II SCSP PROJECT CEPHALUS",
    "bank_reference": "10716RS62GWQ",
    "post_date": "31 Mar 2026",
    "value_date": "31 Mar 2026",
    "currency": "EUR",
    "credit": None,
    "debit": "-301908.70",
    "counterparty_raw": "NI ABF I SCSP",
    "counterparty_match": {"status": "MATCH", "matched_name": "NI ABF I SCSp"},
    "project_code_match": {"status": "MATCH", "matched_name": "Cephalus"},
    "classification": "Investment Transfer",
}

UNRESOLVED = {
    **CLEAN,
    "bank_reference": "NONREF",
    "narrative": "CHARGES FOR 2, OUTWARD SEPA PAYMENT",
    "debit": "-0.44",
    "counterparty_raw": None,
    "counterparty_match": {"status": "UNRESOLVED", "matched_name": None},
    "classification": "Other",
}


def context(rows=None, checks=None) -> dict:
    return {
        "run_id": "20260905-181232-EUR_8102",
        "profile": "journal-entries",
        "model": "gemini-3.8-flash",
        "account": "EUR_8102",
        "source_file": "statement.pdf",
        "input_documents": [{"filename": "statement.pdf", "sha256": "abc"}],
        "rows": rows if rows is not None else [CLEAN, UNRESOLVED],
        "checks": checks or [],
    }


# --- the two envelopes ---------------------------------------------------


def test_profile_one_emits_every_key_its_specification_names():
    required = {
        "run_id", "document_set", "source_files", "statement_rows",
        "mapping_results", "journal_entries", "checks", "review_queue", "summary",
    }
    assert set(build(load("journal-entries"), context())) == required


def test_profile_two_emits_every_key_its_specification_names():
    required = {
        "run_id", "input_documents", "extracted_rows", "mapping_summary",
        "verification_results", "review_queue", "export_candidates",
        "blocked_exports", "audit_trail",
    }
    assert set(build(load("pipeline-validation"), context())) == required


def test_the_second_profile_adds_no_python():
    """The test of the split. Profile 2 is a JSON file overriding one key."""
    raw = json.loads(
        (load.__globals__["PROFILES"] / "pipeline-validation.json").read_text(encoding="utf-8")
    )
    assert raw["extends"] == "journal-entries"
    assert set(raw) <= {"extends", "id", "label", "description", "output"}


def test_both_profiles_run_the_same_passes_and_checks():
    """Same work, different presentation — or the comparison is meaningless."""
    one, two = load("journal-entries"), load("pipeline-validation")
    assert [p.name for p in one.passes] == [p.name for p in two.passes]
    assert [[c.name for c in p.checks] for p in one.passes] == [
        [c.name for c in p.checks] for p in two.passes
    ]


# --- the row projections -------------------------------------------------


def test_profile_one_row_carries_its_citation():
    row = build(load("journal-entries"), context())["statement_rows"][0]
    assert row["source_citation"]["page"] == 1
    assert row["amount"] == pytest.approx(-301908.70)
    assert row["direction"] == "debit"
    assert row["account_short_code"] == "EUR_8102"


def test_profile_two_flattens_the_status_the_other_nests():
    row = build(load("pipeline-validation"), context())["extracted_rows"][0]
    assert row["counterparty_status"] == "MATCH"
    assert row["row_id"] == "EUR_8102-000"


# --- the export gate -----------------------------------------------------


def test_a_fully_resolved_row_is_a_candidate_and_an_unresolved_one_is_blocked():
    built = build(load("pipeline-validation"), context())
    assert len(built["export_candidates"]) == 1
    assert len(built["blocked_exports"]) == 1
    assert built["blocked_exports"][0]["review_reason"] == "COUNTERPARTY_UNRESOLVED"


def test_a_blocked_row_is_held_back_not_dropped():
    """Hiding an unresolved row is named as disallowed, and so is exporting it."""
    built = build(load("pipeline-validation"), context())
    total = len(built["export_candidates"]) + len(built["blocked_exports"])
    assert total == len(context()["rows"])


def test_a_row_that_was_never_resolved_cannot_be_exported():
    """Absence is not success.

    A run whose resolution pass never happened produces rows with no
    resolution keys at all. Treating that as clean is the failure both
    specifications name outright — "missing data becomes MATCH" — and it is
    invisible, because the row looks perfectly well formed.
    """
    unexamined = {key: value for key, value in CLEAN.items() if not key.endswith("_match")}
    built = build(load("pipeline-validation"), context(rows=[unexamined]))
    assert built["export_candidates"] == []
    assert built["blocked_exports"][0]["review_reason"] == "COUNTERPARTY_UNRESOLVED"


def test_an_unexamined_row_is_counted_as_such_in_the_summary():
    unexamined = {key: value for key, value in CLEAN.items() if not key.endswith("_match")}
    results = build(load("journal-entries"), context(rows=[unexamined]))["mapping_results"]
    assert results["counterparty_match"] == {"MISSING": 1}


def test_a_row_with_no_page_cannot_be_exported():
    """A financial value with no source reference is a hard fail in both specs."""
    built = build(load("pipeline-validation"), context(rows=[{**CLEAN, "page": None}]))
    assert built["blocked_exports"][0]["review_reason"] == "MISSING_SOURCE_CITATION"


def test_a_row_classified_for_review_is_blocked():
    built = build(load("pipeline-validation"), context(rows=[{**CLEAN, "classification": "Review"}]))
    assert built["blocked_exports"][0]["review_reason"] == "LOW_CLASSIFICATION_CONFIDENCE"


# --- the review queue ----------------------------------------------------


def test_the_queue_carries_what_a_reviewer_needs_to_decide():
    item = derive_review_queue(context())[0]
    assert item["reason"] == "COUNTERPARTY_UNRESOLVED"
    assert item["source_citation"]["page"] == 1
    assert item["raw_narrative"]
    assert item["amount"] == pytest.approx(-0.44)


def test_a_failing_check_reaches_the_queue_too():
    """It is not about one row, so it would otherwise vanish from the only
    surface a person actually reads."""
    failing = [{"name": "balance_chain", "status": "FAIL", "detail": "14/15 links hold"}]
    reasons = [item["reason"] for item in derive_review_queue(context(checks=failing))]
    assert "CHECK_FAIL" in reasons


def test_a_cannot_verify_check_stays_out_of_the_queue():
    """There is nothing for a reviewer to do about an input that was not in the
    run. It stays visible in `checks`; it does not pad the queue they work."""
    checks = [{"name": "printed_openings", "status": "CANNOT_VERIFY", "detail": "no markers"}]
    assert derive_review_queue(context(rows=[], checks=checks)) == []


def test_a_row_that_names_nobody_is_settled_not_unresolved():
    """A bank charge has no counterparty, and saying so is a finding.

    Blocking on CANNOT_VERIFY conflated "we looked and there is nothing there"
    with "we did not look", and put 95 of 100 rows into a queue a person then
    stops reading.
    """
    charge = {
        **CLEAN,
        "counterparty_raw": None,
        "counterparty_match": {"status": "CANNOT_VERIFY"},
    }
    built = build(load("pipeline-validation"), context(rows=[charge]))
    assert built["export_candidates"][0]["ready_for_export"] is True
    assert built["blocked_exports"] == []


def test_a_name_that_matched_nothing_still_blocks():
    """The other half of the same distinction — somebody has to decide this one."""
    built = build(load("pipeline-validation"), context(rows=[UNRESOLVED]))
    assert built["export_candidates"] == []
    assert built["blocked_exports"][0]["review_reason"] == "COUNTERPARTY_UNRESOLVED"


# --- the summary ---------------------------------------------------------


def test_the_summary_states_what_did_not_resolve():
    """Claiming 100% against data with known gaps is a named failure condition."""
    summary = derive_summary(context())
    assert summary == {
        "rows": 2,
        "ready_for_export": 1,
        "needs_review": 1,
        "checks": {},
    }


def test_mapping_results_count_every_status_not_just_the_good_one():
    results = build(load("journal-entries"), context())["mapping_results"]
    assert results["counterparty_match"] == {"MATCH": 1, "UNRESOLVED": 1}


def test_journal_entries_are_empty_rather_than_invented():
    """No pass builds them yet. An honest empty beats a plausible guess."""
    assert build(load("journal-entries"), context())["journal_entries"] == []
