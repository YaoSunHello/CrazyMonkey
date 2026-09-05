"""The agent loop: write a parser, run it, satisfy the verifier, or try again.

Shaped after dimknaf/agent-arena, which solved this problem already. The
important structural choice, and the reason this works where a tool-calling
loop did not:

**One generation per attempt, not one per turn.** The model writes the whole
parser in a single streamed completion. We extract it, run it in the sandbox,
download what it produced, and verify on the host. If the verifier rejects it,
the exact failures go into the next attempt's prompt.

A turn-by-turn tool loop was tried first and was the wrong shape here: a
quantised local model takes ~220s a turn, so twenty turns is over an hour, and
it emitted malformed JSON for tool arguments часто enough to abort the run
outright. Removing tool calls removes both failure modes.

Two details carried over from agent-arena because they cost real time there:

- **Delete the previous attempt's output before each retry.** Otherwise an
  attempt that writes nothing leaves the last one's file on disk, you verify
  stale output, and the fallback never fires.
- **Route effort by the kind of failure.** A parse that broke on structure
  needs a different prompt from one that broke on arithmetic.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

from app.config import Settings
from app.llm import stream_completion
from app.sandbox import DATADIR, WORKDIR, build_executor
from app.trace import Trace
from app.verification.checks import run_parse_checks

MAX_ATTEMPTS = 4

TASK = f"""\
You are parsing a bank statement PDF into transaction rows for a fund administrator.

Write a Python file, `parse.py`, that runs in a sandbox where a module `kit` is
already available. Import it; do not rewrite it.

    kit.page_count() -> int
    kit.lines(page)  -> visual lines, top to bottom. Each has:
                          line.text            the whole line as a string
                          line.words           dicts with "text" and "x0"
                          line.between(a, b)   words whose left edge is in [a, b)
    kit.column_positions() -> dict of the left edge of every column, read from
                          the statement's own header row:
                          bank_reference, customer_reference, trn_type,
                          value_date, credit, debit, balance, time, post_date
    kit.write_result(rows) -> writes /work/result.json

Each row is a dict with these keys:
    bank_reference, trn_type, value_date, post_date, time, narrative,
    credit, debit, balance, account_number, currency, page

Amounts are strings, no thousands separators, sign exactly as printed. Exactly
one of credit/debit is set; the other is None. Rows in statement order, newest
first.

## What the verifier checks

- balance_chain          a row's balance minus its amount must equal the NEXT row's balance
- closing_balance        the first row's balance equals the closing balance printed on page 1
- printed_openings       every "Balance brought forward" marker must reproduce from the movements
- row_count              one row per transaction. "Balance as at close" and
                         "Balance brought forward" are day markers, NOT transactions
- one_amount_per_row     exactly one of credit/debit
- reference_provenance   every bank_reference appears literally in the PDF text

## Rules

- Never invent or adjust a number to make the chain close.
- Print a one-line summary to stdout at the end, e.g. "parsed 16 rows".

Reply with the complete contents of parse.py in a single ```python code block,
and nothing else.
"""


def extract_code(text: str) -> str:
    """Pull the Python out of a model reply.

    Tolerant on purpose: the model may fence it, label it, or just emit bare
    source. Anything that reaches the sandbox and fails to run is a run the
    verifier catches, so a permissive extractor costs nothing and a strict one
    throws away otherwise good attempts.
    """
    fenced = re.findall(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    if fenced:
        return max(fenced, key=len).strip()
    return text.strip()


def retry_prompt(failures: list[dict], attempt: int) -> str:
    """Fold the verifier's exact objections into the next attempt."""
    lines = [
        f"Your parse.py was REJECTED by the verifier. Attempt {attempt} of {MAX_ATTEMPTS}.",
        "",
        "These checks failed:",
    ]
    for failure in failures:
        lines.append(f"- {failure['name']}: {failure['detail']}")
        if failure.get("evidence"):
            for line in failure["evidence"].splitlines()[:4]:
                lines.append(f"    {line}")
    lines += [
        "",
        "The evidence names the row and the exact discrepancy. Fix the cause, not",
        "the symptom, and do not repeat the approach that just failed.",
        "",
        "Reply with the complete corrected parse.py in a single ```python code block.",
    ]
    return "\n".join(lines)


async def run_agent(
    statement: Path,
    settings: Settings,
    *,
    allow_local: bool = False,
    quiet: bool = False,
) -> dict:
    from app.ingestion.statements import parse_statement

    trace = Trace(quiet=quiet)
    trace.state(
        "starting",
        statement=statement.name,
        model=settings.resolved_model,
        max_attempts=MAX_ATTEMPTS,
    )

    data_dir = statement.parent / ".agent_data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "statement.pdf").write_bytes(statement.read_bytes())

    import os

    if settings.daytona_api_key:
        os.environ["DAYTONA_API_KEY"] = settings.daytona_api_key
        os.environ["DAYTONA_TARGET"] = settings.daytona_target

    executor = build_executor(trace, data_dir, allow_local=allow_local)
    await executor.start()

    truth = parse_statement(statement)
    statement_text = "\n\n".join(
        f"--- PAGE {number} ---\n{body}" for number, body in enumerate(truth.page_text, 1)
    )
    base = f"{TASK}\n\nThe statement text, for reference:\n\n{statement_text}\n"

    outcome = {"passed": False, "attempts": 0, "rows": 0, "summary": ""}
    failures: list[dict] = []

    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            outcome["attempts"] = attempt
            trace.state("attempt", n=attempt, of=MAX_ATTEMPTS)

            prompt = base if attempt == 1 else f"{base}\n\n{retry_prompt(failures, attempt)}"

            trace.tool("model", f"generating parse.py · attempt {attempt}", status="running")
            started = time.monotonic()

            # The model reasons in a separate channel before it answers. Show a
            # heartbeat rather than the raw thoughts: it can run to thousands of
            # tokens, and what matters on screen is that it is alive and how
            # much of the wait is thinking versus writing.
            counters = {"thought": 0, "code": 0}

            def on_thought(piece: str) -> None:
                counters["thought"] += len(piece)
                if counters["thought"] // 2000 != (counters["thought"] - len(piece)) // 2000:
                    trace.out(
                        f"thinking… {counters['thought'] // 1000}k chars, "
                        f"{time.monotonic() - started:.0f}s",
                        stream="stderr",
                    )

            def on_token(piece: str) -> None:
                counters["code"] += len(piece)

            reply = await stream_completion(
                settings, prompt, on_token=on_token, on_thought=on_thought
            )
            if counters["thought"]:
                trace.think(
                    f"reasoned for {counters['thought']:,} characters before answering"
                )
            source = extract_code(reply)
            trace.tool(
                "model",
                f"{len(source.splitlines())} lines · {time.monotonic() - started:.0f}s",
                status="ok",
            )
            if not source:
                failures = [{"name": "generation", "detail": "model returned no code"}]
                continue
            trace.code(f"{WORKDIR}/parse.py", source)

            # Stale output is worse than none: without this a run that writes
            # nothing gets verified against the previous attempt's file.
            await executor.remove(f"{WORKDIR}/result.json")
            await executor.put(f"{WORKDIR}/parse.py", source.encode("utf-8"))

            trace.tool("run_python", "parse.py", status="running")
            run = await executor.run_python("parse.py", timeout=180)
            trace.tool("run_python", f"exit {run.exit_code}", status="ok" if run.ok else "fail")

            try:
                payload = json.loads((await executor.get(f"{WORKDIR}/result.json")).decode())
                rows = payload["rows"] if isinstance(payload, dict) else payload
            except Exception as exc:  # noqa: BLE001 — a bad attempt is data, not a crash
                trace.tool("run_checks", f"no result.json — {exc}", status="fail")
                failures = [
                    {
                        "name": "result_json",
                        "detail": "parse.py did not produce a readable /work/result.json",
                        "evidence": (run.stderr or run.stdout or str(exc))[-800:],
                    }
                ]
                continue

            from app.tools import _load_agent_rows

            checked = parse_statement(statement)
            checked.rows = _load_agent_rows(rows)
            checks = run_parse_checks(checked)
            serialised = [c.model_dump() for c in checks]
            failed = [c for c in serialised if c["status"] == "FAIL"]
            trace.verdict(serialised, passed=not failed)

            outcome["rows"] = len(rows)
            if not failed:
                outcome["passed"] = True
                outcome["summary"] = f"{len(rows)} rows, every check green, attempt {attempt}"
                trace.state("accepted", attempt=attempt, rows=len(rows))
                break

            failures = failed
            trace.state("rejected", attempt=attempt, failed=len(failed))
        else:
            outcome["summary"] = f"still failing after {MAX_ATTEMPTS} attempts"
            trace.state("exhausted", attempts=MAX_ATTEMPTS)
    finally:
        await executor.close()

    return {"outcome": outcome, "events": len(trace.events), "trace": trace}


def main(statement: Path, *, allow_local: bool = False) -> dict:
    settings = Settings(_env_file=str(Path(__file__).resolve().parents[2] / ".env"))
    return asyncio.run(run_agent(statement, settings, allow_local=allow_local))
