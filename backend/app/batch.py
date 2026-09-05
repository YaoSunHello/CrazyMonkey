"""Run many statements at once, each in its own sandbox.

`run_agent` is already self-contained, so concurrency is a semaphore and a
gather — no separate processes needed. Each document gets its own Daytona
sandbox, which is where the real isolation lives.

The console cannot show five reasoning streams at once, so under a batch each
run is quiet and the display becomes one line per document, updated in place.
The full detail still goes to each run's own `trace.jsonl`.

The limit is Daytona's, not ours: five concurrent sandboxes at roughly eight
seconds each to provision.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

from app.agent import run_agent
from app.config import Settings
from app.runs import RUNS
from app.trace import BOLD, DIM, GREEN, RED, YELLOW, _COLOUR

DEFAULT_PARALLEL = 5


class BatchBoard:
    """One line per document, redrawn in place.

    Same discipline as the reasoning window: track how many rows were drawn so
    the cursor-up count is right, and fall back to plain appended lines when
    stderr is not a terminal.
    """

    def __init__(self, accounts: list[str]) -> None:
        self.started = time.monotonic()
        self.state: dict[str, str] = {account: "waiting" for account in accounts}
        self._rows = 0

    def set(self, account: str, status: str) -> None:
        self.state[account] = status
        self.draw()

    def draw(self) -> None:
        width = max(shutil.get_terminal_size((100, 24)).columns - 4, 40)
        lines = []
        for account, status in self.state.items():
            paint = DIM
            if status.startswith("accepted"):
                paint = GREEN
            elif status.startswith(("rejected", "failed", "error")):
                paint = RED
            elif status.startswith(("attempt", "generating", "running")):
                paint = YELLOW
            lines.append(f"  {BOLD(account.ljust(12))} {paint(status)}"[:width])

        if not _COLOUR:
            return  # plain mode: per-event lines are emitted by the caller instead

        for _ in range(self._rows):
            sys.stderr.write("\033[F\033[2K")
        for line in lines:
            sys.stderr.write(line + "\n")
        sys.stderr.flush()
        self._rows = len(lines)


async def run_many(
    statements: list[Path],
    settings: Settings,
    *,
    limit: int = DEFAULT_PARALLEL,
    allow_local: bool = False,
) -> list[dict]:
    """Run every statement, at most `limit` sandboxes at a time."""
    from app.ingestion.statements import parse_statement

    accounts = [parse_statement(p).account_short_code for p in statements]
    board = BatchBoard(accounts)
    batch = datetime.now().strftime("%Y%m%d-%H%M%S")
    gate = asyncio.Semaphore(limit)

    print(
        f"{len(statements)} statements · {limit} sandboxes at a time · batch {batch}",
        file=sys.stderr,
        flush=True,
    )
    board.draw()

    async def one(statement: Path, account: str) -> dict:
        async with gate:
            board.set(account, "starting sandbox")
            started = time.monotonic()
            try:
                result = await run_agent(
                    statement, settings, allow_local=allow_local, quiet=True, batch=batch
                )
            except Exception as exc:  # noqa: BLE001 — one failure must not sink the batch
                board.set(account, f"error · {type(exc).__name__}: {exc}"[:70])
                return {"outcome": {"passed": False, "account": account, "error": str(exc)}}

            outcome = result["outcome"]
            elapsed = time.monotonic() - started
            verdict = "accepted" if outcome["passed"] else "rejected"
            board.set(
                account,
                f"{verdict} · {outcome['rows']} rows · "
                f"attempt {outcome['attempts']} · {elapsed:.0f}s",
            )
            return result

    results = await asyncio.gather(*(one(s, a) for s, a in zip(statements, accounts)))

    elapsed = time.monotonic() - board.started
    passed = sum(1 for r in results if r["outcome"].get("passed"))
    rows = sum(r["outcome"].get("rows", 0) for r in results)
    print(
        f"\n{passed}/{len(results)} accepted · {rows} rows · {elapsed:.0f}s"
        f"\nRuns in {RUNS}",
        file=sys.stderr,
        flush=True,
    )
    return results
