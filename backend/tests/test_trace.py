"""Tests for the live reasoning window.

The failure this guards against is quiet and nasty: if a rendered line is wider
than the terminal it soft-wraps onto a second row, the cursor-up count in
`_redraw` no longer matches what was drawn, and the window walks up the screen
overwriting earlier output. Nothing errors — the log just eats itself.
"""

from __future__ import annotations

import app.trace as trace_module
from app.trace import THOUGHT_ROWS, Trace


def test_window_keeps_only_the_last_rows():
    trace = Trace(quiet=True)
    lines = trace._wrap_tail("word " * 400, THOUGHT_ROWS)
    assert len(lines) == THOUGHT_ROWS


def test_every_line_fits_the_terminal(monkeypatch):
    """No line may be wide enough to soft-wrap."""
    import shutil

    monkeypatch.setattr(shutil, "get_terminal_size", lambda _=None: type("S", (), {"columns": 80})())
    trace = Trace(quiet=True)
    for line in trace._wrap_tail("supercalifragilistic " * 200, THOUGHT_ROWS):
        assert len(line) <= 80 - 12


def test_newlines_do_not_smuggle_in_extra_rows():
    """Reasoning arrives with its own line breaks; they must not add rows."""
    trace = Trace(quiet=True)
    assert len(trace._wrap_tail("a\nb\nc\nd\ne\nf\ng\n", THOUGHT_ROWS)) <= THOUGHT_ROWS


def test_empty_reasoning_draws_nothing():
    trace = Trace(quiet=True)
    assert trace._wrap_tail("", THOUGHT_ROWS) == []
    assert trace._wrap_tail("   \n  ", THOUGHT_ROWS) == []


def test_redraw_tracks_how_many_rows_it_drew(monkeypatch):
    """The cursor-up count next time is exactly what was drawn this time."""
    monkeypatch.setattr(trace_module, "_COLOUR", True)
    trace = Trace(quiet=True)

    trace._redraw(["one", "two"])
    assert trace._thought_rows == 2

    trace._redraw(["one", "two", "three", "four"])
    assert trace._thought_rows == 4

    trace._redraw([])
    assert trace._thought_rows == 0


def test_end_thought_records_the_total_and_clears():
    trace = Trace(quiet=True)
    trace.thought("thinking about the balance chain. " * 50)
    event = trace.end_thought()

    assert event is not None
    assert event.kind == "think"
    assert event.meta["chars"] == 1700
    assert "1,700" in event.detail
    assert trace._thought_chars == 0
    assert trace._thought_buffer == ""


def test_end_thought_is_silent_when_nothing_was_thought():
    """A model that answers without reasoning should not leave a stray event."""
    assert Trace(quiet=True).end_thought() is None
