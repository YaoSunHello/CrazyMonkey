"""The agent's event stream, and a terminal renderer for it.

Every discrete thing the agent does becomes an `Event`. The renderer prints
them as they arrive; the same events serialise to JSON, so the frontend can
relay them over SSE later without the agent knowing anything about a browser.

Two rules borrowed from the agent-arena orchestrator, both learned the hard
way:

- Progress goes to stderr, results to stdout. Wire *both* streams from any
  subprocess, or you get a blank screen followed by a wall of text at the end.
- Never block inside a log callback. Callbacks here only append and print.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import textwrap
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Literal

# How many lines of live reasoning to keep on screen.
THOUGHT_ROWS = 4
# Characters of reasoning per recorded delta event. Small enough that a
# replay streams, large enough that 120k characters is tens of events.
THOUGHT_DELTA_CHARS = 250

EventKind = Literal["think", "tool", "code", "stdout", "stderr", "verdict", "state", "result"]
Status = Literal["running", "ok", "fail", "skip"]

# Colour is disabled when not a TTY, or when NO_COLOR is set, so piping to a
# file or into a video-capture tool gives clean text.
_COLOUR = sys.stderr.isatty() and not os.environ.get("NO_COLOR")


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOUR else text


DIM = lambda s: _c("2", s)          # noqa: E731
BOLD = lambda s: _c("1", s)         # noqa: E731
GREEN = lambda s: _c("32", s)       # noqa: E731
RED = lambda s: _c("31", s)         # noqa: E731
YELLOW = lambda s: _c("33", s)      # noqa: E731
BLUE = lambda s: _c("34", s)        # noqa: E731
CYAN = lambda s: _c("36", s)        # noqa: E731

GLYPH: dict[Status, str] = {
    "running": "●",
    "ok": "●",
    "fail": "●",
    "skip": "○",
}

TREE_MID = "  ├ "
TREE_END = "  ⎿ "


@dataclass
class Event:
    kind: EventKind
    label: str = ""
    detail: str = ""
    status: Status = "ok"
    body: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
    at: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)


class Trace:
    """Collects events, prints them, and can replay them later.

    The recorded stream is the audit trail: the sandbox is destroyed at the end
    of a run, but what the agent did survives.
    """

    def __init__(self, *, quiet: bool = False) -> None:
        self.events: list[Event] = []
        self.quiet = quiet
        self.started = time.monotonic()
        self._subscribers: list[Callable[[Event], None]] = []
        # Live reasoning window state.
        self._thought_buffer = ""
        self._thought_chars = 0
        self._thought_rows = 0
        self._thought_reported = 0
        self._thought_pending = ""

    def subscribe(self, callback: Callable[[Event], None]) -> None:
        """Register a sink — an SSE queue, a log file. Must not block."""
        self._subscribers.append(callback)

    def emit(self, event: Event) -> Event:
        """Record an event and draw it."""
        self.record(event)
        if not self.quiet:
            self._render(event)
        return event

    def record(self, event: Event) -> Event:
        """Record an event without drawing it.

        Used by the reasoning stream, which paints itself in place: the events
        still have to reach the recording and any subscriber, or a replay would
        show one lump of text where the live run streamed.
        """
        self.events.append(event)
        for callback in self._subscribers:
            callback(event)
        return event

    # -- convenience emitters ------------------------------------------------

    def think(self, text: str) -> Event:
        return self.emit(Event(kind="think", body=text))

    # -- live reasoning window ----------------------------------------------

    def thought(self, chunk: str) -> None:
        """Show the model's reasoning as it streams, in a rolling window.

        The model reasons for tens of seconds before any code appears, and that
        wait is the most interesting part of the run — but the reasoning can be
        long, so it gets a fixed four-row window that updates in place rather
        than scrolling the terminal.

        When stderr is not a terminal — every piped or backgrounded run — an
        in-place redraw is meaningless, so it degrades to a periodic heartbeat
        instead.
        """
        self._thought_buffer += chunk
        self._thought_chars += len(chunk)
        self._thought_pending += chunk

        # Record the stream, throttled. Without this a replay shows one lump of
        # text where the live run streamed. Throttling keeps a long reasoning
        # pass to tens of events rather than thousands of one-token ones.
        if len(self._thought_pending) >= THOUGHT_DELTA_CHARS:
            self.record(
                Event(kind="think", body=self._thought_pending, meta={"delta": True})
            )
            self._thought_pending = ""

        if not _COLOUR:
            # One line per 2k characters, so a log file stays readable.
            if self._thought_chars // 2000 != self._thought_reported:
                self._thought_reported = self._thought_chars // 2000
                elapsed = time.monotonic() - self.started
                print(
                    f"{' ' * 7} {TREE_MID}thinking… "
                    f"{self._thought_chars // 1000}k chars, {elapsed:.0f}s",
                    file=sys.stderr,
                    flush=True,
                )
            return

        rows = self._wrap_tail(self._thought_buffer, THOUGHT_ROWS)
        self._redraw(rows)

    def end_thought(self) -> Event | None:
        """Clear the live window and record what was reasoned."""
        if not self._thought_chars:
            return None
        self._redraw([])
        if self._thought_pending:
            self.record(Event(kind="think", body=self._thought_pending, meta={"delta": True}))
        total = self._thought_chars
        tail = self._thought_buffer[-1200:]
        self._thought_buffer, self._thought_chars, self._thought_reported = "", 0, 0
        self._thought_pending = ""
        return self.emit(
            Event(
                kind="think",
                detail=f"{total:,} characters of reasoning",
                body=tail,
                meta={"chars": total},
            )
        )

    def _wrap_tail(self, text: str, rows: int) -> list[str]:
        """The last `rows` display lines of `text`, wrapped to the terminal.

        Wrapping is not cosmetic: a line longer than the terminal soft-wraps
        onto a second row, which makes the cursor-up count below wrong and
        walks the window up the screen, eating earlier output.
        """
        width = max(shutil.get_terminal_size((100, 24)).columns - 12, 30)
        flat = " ".join(text.split())
        if not flat:
            return []
        wrapped = textwrap.wrap(flat, width=width) or []
        return wrapped[-rows:]

    def _redraw(self, rows: list[str]) -> None:
        """Replace the previously drawn window with `rows`."""
        out = sys.stderr
        for _ in range(self._thought_rows):
            out.write("\033[F\033[2K")
        for row in rows:
            out.write(f"{' ' * 7} {TREE_MID}{DIM(row)}\n")
        out.flush()
        self._thought_rows = len(rows)

    def tool(self, name: str, detail: str = "", status: Status = "running", **meta) -> Event:
        return self.emit(Event(kind="tool", label=name, detail=detail, status=status, meta=meta))

    def code(self, path: str, source: str, *, preview_lines: int = 14) -> Event:
        return self.emit(
            Event(
                kind="code",
                label=path,
                detail=f"{len(source.splitlines())} lines",
                body=source,
                meta={"preview_lines": preview_lines},
            )
        )

    def out(self, text: str, stream: EventKind = "stdout") -> Event:
        return self.emit(Event(kind=stream, body=text.rstrip("\n")))

    def verdict(self, checks: list[dict], passed: bool) -> Event:
        return self.emit(
            Event(
                kind="verdict",
                status="ok" if passed else "fail",
                meta={"checks": checks, "passed": passed},
            )
        )

    def state(self, phase: str, **meta) -> Event:
        return self.emit(Event(kind="state", label=phase, meta=meta))

    # -- rendering -----------------------------------------------------------

    def _stamp(self) -> str:
        return DIM(f"{time.monotonic() - self.started:6.1f}s")

    def _render(self, event: Event) -> None:
        write = lambda line: print(line, file=sys.stderr, flush=True)  # noqa: E731

        if event.kind == "think":
            write("")
            for line in event.body.splitlines():
                write(f"{self._stamp()} {DIM('✻ ' + line)}")

        elif event.kind == "tool":
            colour = {"ok": GREEN, "fail": RED, "running": BLUE, "skip": DIM}[event.status]
            write("")
            write(
                f"{self._stamp()} {colour(GLYPH[event.status])} {BOLD(event.label)}"
                f"{DIM('  ' + event.detail) if event.detail else ''}"
            )

        elif event.kind == "code":
            write(f"{' ' * 7} {TREE_MID}{CYAN(event.label)} {DIM(event.detail)}")
            lines = event.body.splitlines()
            limit = event.meta.get("preview_lines", 14)
            for number, line in enumerate(lines[:limit], start=1):
                write(f"{' ' * 7}   {DIM(f'{number:>4}')} {line}")
            if len(lines) > limit:
                write(f"{' ' * 7}   {DIM(f'     … {len(lines) - limit} more lines')}")

        elif event.kind in ("stdout", "stderr"):
            paint = DIM if event.kind == "stdout" else YELLOW
            for line in event.body.splitlines():
                write(f"{' ' * 7} {TREE_MID}{paint(line)}")

        elif event.kind == "verdict":
            checks = event.meta.get("checks", [])
            for check in checks:
                status = check.get("status", "PASS")
                icon = {"PASS": GREEN("✓"), "FAIL": RED("✗"), "UNRESOLVED": YELLOW("?")}[status]
                name = check.get("name", "")
                write(f"{' ' * 7} {TREE_MID}{icon} {name:<24}{DIM(check.get('detail', ''))}")
                for line in (check.get("evidence") or "").splitlines()[:3]:
                    write(f"{' ' * 7}   {DIM(line)}")
            tally = _tally(checks)
            summary = (
                f"{tally['PASS']} passed · {tally['FAIL']} failed · "
                f"{tally['UNRESOLVED']} unresolved"
            )
            write(f"{' ' * 7} {TREE_END}{(GREEN if event.status == 'ok' else RED)(summary)}")

        elif event.kind == "state":
            write("")
            bits = " · ".join(f"{k}={v}" for k, v in event.meta.items())
            write(f"{self._stamp()} {BOLD('▸ ' + event.label)} {DIM(bits)}")

        elif event.kind == "result":
            write("")
            write(f"{self._stamp()} {BOLD(event.label)} {DIM(event.detail)}")

    # -- persistence ---------------------------------------------------------

    def save(self, path) -> None:
        """Write the stream as JSONL — one event per line, replayable."""
        with open(path, "w", encoding="utf-8") as handle:
            for event in self.events:
                handle.write(event.to_json() + "\n")


def _tally(checks: list[dict]) -> dict[str, int]:
    tally = {"PASS": 0, "FAIL": 0, "UNRESOLVED": 0}
    for check in checks:
        tally[check.get("status", "PASS")] += 1
    return tally
