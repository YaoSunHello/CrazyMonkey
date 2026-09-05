"""Screening questions, and the two ways an answer can be useless.

An answer without its working cannot be checked by the analyst it is for — which
is the complaint this whole product exists to answer: *"I cannot trust any
number I get from them, so I have to check everything."* A bare number is
exactly what he already does not trust.

A refusal without a reason is the same failure wearing modesty. It reports a
dead end where it could have named the document to go and ask for, and an
analyst can do nothing with it either.

Both are held to the same standard here.
"""

from __future__ import annotations

from app.profiles import load
from app.verification import generic


def answer(**over) -> dict:
    base = {
        "question": "manager_concentration",
        "verdict": "BREACH",
        "because": "adding this fund takes the manager past the 12% ceiling",
        "explanation": {
            "inputs": [{"label": "manager exposure", "value": "48.2m", "from": "Commitments!D14"}],
            "steps": ["48.2 / 310.0 = 15.5%", "ceiling is 12%", "15.5% > 12%"],
        },
    }
    return {**base, **over}


def refusal(**over) -> dict:
    base = {
        "question": "leverage_ceiling",
        "verdict": "CANNOT_VERIFY",
        "because": "no portfolio-company leverage was supplied in this run",
        "missing": ["portfolio_leverage", "leverage_ceiling"],
    }
    return {**base, **over}


# --- an answer owes its working ------------------------------------------


def test_an_answer_with_inputs_and_steps_passes():
    assert generic.run("explanation", [answer()], "T", {}).status == "PASS"


def test_a_bare_verdict_fails():
    """The number on its own is what the customer says he cannot trust."""
    check = generic.run("explanation", [answer(explanation=None)], "T", {})
    assert check.status == "FAIL"
    assert "without showing the steps" in check.evidence


def test_steps_without_inputs_fail():
    """Arithmetic whose operands have no source is not traceable."""
    check = generic.run(
        "explanation", [answer(explanation={"steps": ["48.2 / 310.0 = 15.5%"]})], "T", {}
    )
    assert check.status == "FAIL"
    assert "without naming its inputs" in check.evidence


# --- a refusal owes what it needs ----------------------------------------


def test_a_refusal_that_names_its_missing_input_passes():
    assert generic.run("explanation", [refusal()], "T", {}).status == "PASS"


def test_a_refusal_with_no_reason_fails():
    check = generic.run("explanation", [refusal(because="")], "T", {})
    assert check.status == "FAIL"
    assert "without saying why" in check.evidence


def test_a_refusal_that_names_nothing_fails():
    """A dead end where a request would do."""
    check = generic.run("explanation", [refusal(missing=None)], "T", {})
    assert check.status == "FAIL"
    assert "without naming what it would need" in check.evidence


def test_a_refusal_may_say_what_it_would_need_instead_of_listing_inputs():
    """Prose is an acceptable answer to "what would you need"."""
    row = refusal(missing=None, would_need="target debt/EBITDA per portfolio company")
    assert generic.run("explanation", [row], "T", {}).status == "PASS"


# --- the profile matches what the data actually supports ------------------


def test_no_screening_question_is_answerable_from_this_data():
    """Measured, not assumed.

    Every supplied workbook was searched: `investment policy`, `geography`,
    `leverage`, `vintage`, `exclusion`, `concentration`, `side letter`,
    `hurdle`, `waterfall`, `MFN` and `key person` all return zero. If this test
    ever fails, either the data changed or the profile started claiming an
    input it does not have — and the second would be the beginning of a
    fabricated answer.
    """
    profile = load("mandate-fit")
    mounted = set(profile.inputs.get("tables") or {})
    for question in profile.inputs["questions"]:
        unmet = [need for need in question["requires"] if need not in mounted]
        assert unmet, f"{question['id']} claims to be answerable — check the data first"


def test_every_question_says_what_it_would_need():
    """So a refusal turns into the analyst's next action rather than a dead end."""
    for question in load("mandate-fit").inputs["questions"]:
        assert question.get("would_need"), question["id"]
        assert question.get("method"), question["id"]
