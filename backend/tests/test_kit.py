"""The toolkit handed to the agent, pinned where it has already misled one.

`Line.between` returns a string and `Line.words_between` returns the word
dicts. A model that read `between` as "give me the words" wrote
`" ".join(w["text"] for w in line.between(a, b))`, which iterates the
characters of a string, and two of seven statements failed on
`TypeError: string indices must be integers` — five wasted attempts between
them. These tests exist so the two return types cannot quietly converge again.

No PDF is opened here: `Line` is a plain dataclass over word dicts, so the
column arithmetic is testable without the sandbox or the dataset.
"""

from __future__ import annotations

import pytest

from app.kit.statement_kit import Line


def word(text: str, x0: float) -> dict:
    return {"text": text, "x0": x0, "top": 100.0}


@pytest.fixture
def line() -> Line:
    # Two columns: a reference at x0 35, a narrative starting at x0 116.
    return Line(
        page=1,
        top=100.0,
        words=[word("TT", 35.0), word("JSL083B50KRNM", 48.0), word("CEPHALUS", 116.0)],
    )


def test_between_returns_a_string(line: Line) -> None:
    assert line.between(35, 116) == "TT JSL083B50KRNM"


def test_words_between_returns_the_dicts(line: Line) -> None:
    got = line.words_between(35, 116)
    assert [w["text"] for w in got] == ["TT", "JSL083B50KRNM"]
    assert got[0]["x0"] == 35.0


def test_the_two_do_not_return_the_same_shape(line: Line) -> None:
    """The distinction the failure turned on."""
    assert isinstance(line.between(35, 116), str)
    assert isinstance(line.words_between(35, 116), list)


def test_between_is_the_joined_form_of_words_between(line: Line) -> None:
    """They must stay two views of one thing, not drift apart."""
    joined = " ".join(w["text"] for w in line.words_between(35, 116))
    assert line.between(35, 116) == joined


def test_the_upper_bound_is_exclusive(line: Line) -> None:
    """A word sitting exactly on the next column's left edge belongs to it."""
    assert "CEPHALUS" not in line.between(35, 116)
    assert line.between(116, 200) == "CEPHALUS"


def test_text_covers_the_whole_line(line: Line) -> None:
    assert line.text == "TT JSL083B50KRNM CEPHALUS"
