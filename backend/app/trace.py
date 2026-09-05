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
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Literal

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

    def subscribe(self, callback: Callable[[Event], None]) -> None:
        """Register a sink — an SSE queue, a log file. Must not block."""
        self._subscribers.append(callback)

    def emit(self, event: Event) -> Event:
        self.events.append(event)
        if not self.quiet:
            self._render(event)
        for callback in self._subscribers:
            callback(event)
        return event

    # -- convenience emitters ------------------------------------------------

    def think(self, text: str) -> Event:
        return self.emit(Event(kind="think", body=text))

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
