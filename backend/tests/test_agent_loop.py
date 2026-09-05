"""Tests for the parts of the loop that do not need a model.

Code extraction and retry-prompt construction sit between the model and the
sandbox, so when they are wrong the failure looks like a model problem and
costs an expensive round trip to diagnose. They are pure functions; test them
for free instead.
"""

from __future__ import annotations

from app.agent import extract_code, retry_prompt


def test_extracts_a_fenced_python_block():
    reply = "Here is the parser:\n\n```python\nimport kit\nprint('hi')\n```\n\nHope that helps."
    assert extract_code(reply) == "import kit\nprint('hi')"


def test_extracts_an_unlabelled_fence():
    assert extract_code("```\nimport kit\n```") == "import kit"


def test_prefers_the_longest_block_when_the_model_shows_its_working():
    reply = (
        "First a sketch:\n```python\npass\n```\n"
        "and the real thing:\n```python\nimport kit\nrows = []\nkit.write_result(rows)\n```"
    )
    assert "kit.write_result" in extract_code(reply)


def test_falls_back_to_bare_source():
    """A model that forgets the fence should not cost an attempt."""
    assert extract_code("import kit\nrows = []") == "import kit\nrows = []"


def test_retry_prompt_carries_the_evidence_not_just_the_verdict():
    """The agent needs the discrepancy, not the news that it failed.

    A retry that says only "balance_chain failed" gives the model nothing to
    act on, and it will usually re-submit something very similar.
    """
    failures = [
        {
            "name": "balance_chain",
            "detail": "14/15 links hold",
            "evidence": "row 3->4: 16336662.18 - (-105.22) = 16336767.40, "
            "but row 4 reads 16336667.40 (delta -100.00)",
        }
    ]
    prompt = retry_prompt(failures, attempt=2)

    assert "balance_chain" in prompt
    assert "14/15 links hold" in prompt
    assert "delta -100.00" in prompt
    assert "row 3->4" in prompt
    assert "Attempt 2" in prompt
    assert "do not repeat the approach that just failed" in prompt


def test_retry_prompt_handles_a_failure_with_no_evidence():
    prompt = retry_prompt([{"name": "result_json", "detail": "no readable result.json"}], 3)
    assert "result_json" in prompt
    assert "Attempt 3" in prompt


def test_a_thousands_separator_is_accepted_not_fatal():
    """The model copying "103,014.97" off the statement is a formatting slip.

    Rejecting the whole attempt for it would waste a round trip, and raising
    would end the run before a single check had been evaluated.
    """
    from app.tools import _load_agent_rows

    rows, problems = _load_agent_rows([{"balance": "103,014.97", "debit": "-5.21"}])
    assert str(rows[0].balance) == "103014.97"
    assert problems == []


def test_an_unreadable_amount_is_reported_not_raised():
    from app.tools import _load_agent_rows

    rows, problems = _load_agent_rows([{"balance": "n/a"}, {"balance": "12.00"}])
    assert rows[0].balance is None
    assert str(rows[1].balance) == "12.00"
    assert problems == ["row 0: balance 'n/a' is not a number"]


def test_a_bad_page_number_does_not_stop_the_row():
    from app.tools import _load_agent_rows

    rows, problems = _load_agent_rows([{"balance": "1.00", "page": "front"}])
    assert rows[0].provenance.page == 1
    assert any("page" in p for p in problems)
