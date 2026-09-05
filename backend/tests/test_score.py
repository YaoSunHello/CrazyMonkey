"""The benchmark, and the care it needs to be worth anything.

Two properties matter more than the arithmetic. Rows must join on something
that identifies them, so a dropped row shows up as unjoined rather than
silently shifting every comparison by one. And the workbook's own "no match"
sentinel must not be treated as a value to agree with.

`score.py` is a development benchmark and is not reachable from the agent — an
agent that can see the answer key is marking its own homework. That is asserted
at the bottom of this file rather than left as a convention.
"""

from __future__ import annotations

import re

from decimal import Decimal

from app.score import score_rows

TRUTH = {
    Decimal("103014.97"): {
        "counterparty_raw": "NI V KALVIK TOPCO LTD.",
        "counterparty_matched": "NI V Kalvik Topco Limited",
        "project_raw": "WILLOWBANK",
        "project_matched": "WILLOWBANK",
        "classification": "Investment",
    },
    Decimal("20088.32"): {
        "counterparty_raw": "",
        "counterparty_matched": "",
        "project_raw": "",
        "project_matched": "Flag for review - no project match",
        "classification": "Other",
    },
}


def agent_row(**over) -> dict:
    base = {
        "balance": "103014.97",
        "counterparty_raw": "NI V KALVIK TOPCO LTD.",
        "counterparty_match": {"status": "MATCH", "matched_name": "NI V Kalvik Topco Limited"},
        "project_code_match": {"status": "MATCH", "matched_name": "WILLOWBANK"},
        "classification": "Investment",
    }
    return {**base, **over}


def test_a_row_that_agrees_everywhere_scores_as_agreement():
    result = score_rows([agent_row()], TRUTH)
    assert result["joined"] == 1
    assert result["counterparty_matched"]["agree"] == 1
    assert result["classification"]["agree"] == 1


def test_matching_is_case_insensitive_not_exact():
    """The workbook's casing is inconsistent — `Cephalus` and `WILLOWBANK`."""
    row = agent_row(
        counterparty_match={"status": "MATCH", "matched_name": "ni v kalvik topco limited"}
    )
    assert score_rows([row], TRUTH)["counterparty_matched"]["agree"] == 1


def test_a_row_that_cannot_be_joined_is_not_scored():
    """Silence beats a confident score for a comparison that never happened."""
    result = score_rows([agent_row(balance="999.99")], TRUTH)
    assert result["joined"] == 0
    assert result["unjoined"] == 1
    assert result["classification"]["agree"] == 0


def test_rows_join_on_balance_not_position():
    """A dropped row would otherwise shift every comparison after it by one."""
    rows = [agent_row(balance="20088.32", classification="Other"), agent_row()]
    result = score_rows(rows, TRUTH)
    assert result["joined"] == 2
    assert result["classification"]["agree"] == 2


def test_the_no_match_sentinel_is_not_a_value_to_agree_with():
    """`Flag for review - no project match` means the human resolved nothing."""
    row = agent_row(
        balance="20088.32",
        classification="Other",
        project_code_match={"status": "MATCH", "matched_name": "Flag for review - no project match"},
    )
    result = score_rows([row], TRUTH)
    assert result["project_matched"]["agree"] == 0
    assert result["project_matched"]["agent_only"] == 1


def test_only_one_side_matching_is_reported_as_such():
    """Not as a disagreement — they are different situations for a reviewer."""
    row = agent_row(counterparty_match={"status": "UNRESOLVED", "matched_name": None})
    counts = score_rows([row], TRUTH)["counterparty_matched"]
    assert counts == {"agree": 0, "differ": 0, "agent_only": 0, "human_only": 1}


def test_disagreements_name_both_sides():
    row = agent_row(counterparty_match={"status": "MATCH", "matched_name": "Someone Else Ltd"})
    disagreement = score_rows([row], TRUTH)["disagreements"][0]
    assert disagreement["agent"] == "Someone Else Ltd"
    assert disagreement["human"] == "NI V Kalvik Topco Limited"


def test_both_profiles_hold_the_same_documents_back():
    """Or the two runs are not comparable, and neither number means anything."""
    from app.profiles import load

    one = load("journal-entries").output.get("holdout")
    two = load("pipeline-validation").output.get("holdout")
    assert one and one == two


def test_the_holdout_is_a_real_split_not_a_token_one():
    """A hold-out of one document proves nothing; of all of them, nothing either."""
    from app.profiles import load

    holdout = load("journal-entries").output["holdout"]
    assert 2 <= len(holdout) <= 4


def test_the_agent_cannot_reach_the_answer_key():
    """Asserted, not trusted. This is what makes every other number evidence."""
    from pathlib import Path

    import app.agent as agent_module

    reachable = [agent_module.__file__, str(Path(agent_module.__file__).parent / "tools.py")]
    for kit in ("statement_kit", "reference_kit"):
        reachable.append(str(Path(agent_module.__file__).parent / "kit" / f"{kit}.py"))

    # Look for an import, not for the word. Prose may legitimately mention
    # scoring; what must never happen is the module being reachable.
    forbidden = re.compile(r"^\s*(from\s+[\w.]*\bscore\b|import\s+[\w.]*\bscore\b)", re.M)
    for path in reachable:
        source = Path(path).read_text(encoding="utf-8")
        assert not forbidden.search(source), f"{path} imports the benchmark"
