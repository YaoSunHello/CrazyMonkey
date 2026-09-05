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
it emitted malformed JSON for tool arguments often enough to abort the run
outright. Removing tool calls removes both failure modes.

One detail carried over from agent-arena because it cost real time there:
**delete the previous attempt's output before each retry.** Otherwise an
attempt that writes nothing leaves the last one's file on disk, you verify
stale output, and the fallback never fires.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

from app.config import Settings
from app.llm import stream_completion
from app.profiles import DEFAULT_PROFILE
from app.runs import RunDir, new_run_id
from app.sandbox import DATADIR, WORKDIR, build_executor
from app.trace import Trace
from app.verification.checks import run_parse_checks


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


def retry_prompt(failures: list[dict], attempt: int, of: int) -> str:
    """Fold the verifier's exact objections into the next attempt."""
    lines = [
        f"Your parse.py was REJECTED by the verifier. Attempt {attempt} of {of}.",
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
    batch: str = "",
    profile: str = DEFAULT_PROFILE,
) -> dict:
    from app.ingestion.statements import parse_statement
    from app.profiles import load as load_profile

    started_at = time.monotonic()
    truth = parse_statement(statement)
    account = truth.account_short_code

    spec = load_profile(profile).get_pass("extract")
    max_attempts = spec.max_attempts

    run = RunDir(new_run_id(account, batch=batch))
    trace = Trace(quiet=quiet)
    trace.state(
        "starting",
        statement=statement.name,
        model=settings.resolved_model,
        max_attempts=max_attempts,
        profile=profile,
        run=run.run_id,
    )

    # Per account, not per directory. Sharing one staging directory across
    # concurrent runs would hand each run whichever PDF was written last — and
    # every run would still come back green, having verified the wrong
    # document. Wrong output that looks right is worse than an error.
    data_dir = statement.parent / ".agent_data" / account
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "statement.pdf").write_bytes(statement.read_bytes())

    import os

    if settings.daytona_api_key:
        os.environ["DAYTONA_API_KEY"] = settings.daytona_api_key
        os.environ["DAYTONA_TARGET"] = settings.daytona_target

    executor = build_executor(trace, data_dir, allow_local=allow_local)
    await executor.start()

    statement_text = "\n\n".join(
        f"--- PAGE {number} ---\n{body}" for number, body in enumerate(truth.page_text, 1)
    )
    def build(failed: set[str]) -> str:
        """Compose the prompt for this attempt.

        Rebuilt each time rather than fixed once, because a nudge can be scoped
        to a check — advice about `reference_provenance` is only worth the
        model's attention on an attempt where that check actually failed.
        """
        task = spec.compose(document=account, failed=failed)
        return f"{task}\nThe statement text, for reference:\n\n{statement_text}\n"

    outcome = {"passed": False, "attempts": 0, "rows": 0, "summary": ""}
    failures: list[dict] = []

    try:
        for attempt in range(1, max_attempts + 1):
            outcome["attempts"] = attempt
            trace.state("attempt", n=attempt, of=max_attempts)

            failed_names = {f["name"] for f in failures}
            base = build(failed_names)
            prompt = (
                base
                if attempt == 1
                else f"{base}\n\n{retry_prompt(failures, attempt, max_attempts)}"
            )

            trace.tool("model", f"generating parse.py · attempt {attempt}", status="running")
            started = time.monotonic()

            # The model reasons in a separate channel before it answers.
            # trace.thought keeps the last few lines of it on screen, updating
            # in place, so the wait shows what it is doing rather than a
            # spinner.
            reply = await stream_completion(settings, prompt, on_thought=trace.thought)
            trace.end_thought()
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
            # Keep every attempt's source. When a run fails, the code that
            # failed is the first thing worth reading, and digging it out of a
            # JSONL blob is needless friction.
            run.write_attempt(attempt, source)

            # Stale output is worse than none: without this a run that writes
            # nothing gets verified against the previous attempt's file.
            await executor.remove(f"{WORKDIR}/result.json")
            await executor.put(f"{WORKDIR}/parse.py", source.encode("utf-8"))

            trace.tool("run_python", "parse.py", status="running")
            execution = await executor.run_python("parse.py", timeout=180)
            trace.tool(
                "run_python",
                f"exit {execution.exit_code}",
                status="ok" if execution.ok else "fail",
            )

            try:
                payload = json.loads((await executor.get(f"{WORKDIR}/result.json")).decode())
                rows = payload["rows"] if isinstance(payload, dict) else payload
            except Exception as exc:  # noqa: BLE001 — a bad attempt is data, not a crash
                trace.tool("run_checks", f"no result.json — {exc}", status="fail")
                failures = [
                    {
                        "name": "result_json",
                        "detail": "parse.py did not produce a readable /work/result.json",
                        "evidence": (execution.stderr or execution.stdout or str(exc))[-800:],
                    }
                ]
                continue

            from app.tools import _load_agent_rows

            checked = parse_statement(statement)
            checked.rows, unusable = _load_agent_rows(rows)
            checks = run_parse_checks(checked)
            serialised = [c.model_dump() for c in checks]

            # A value the agent could not express as a number is its mistake to
            # fix, so it becomes a failed check like any other rather than an
            # exception that ends the run before anything is verified.
            if unusable:
                serialised.insert(
                    0,
                    {
                        "name": "values_parse",
                        "scope": checked.account_short_code,
                        "status": "FAIL",
                        "detail": f"{len(unusable)} value(s) could not be read as numbers",
                        "evidence": "\n".join(unusable[:5]),
                    },
                )

            failed = [c for c in serialised if c["status"] == "FAIL"]
            trace.verdict(serialised, passed=not failed)

            outcome["rows"] = len(rows)

            # Keep the output even when it was rejected: the sandbox is about to
            # be destroyed, and a rejected attempt is the most useful thing to
            # look at when working out why.
            written = run.write_rows(
                {
                    "account": account,
                    "source_file": statement.name,
                    "attempt": attempt,
                    "accepted": not failed,
                    "checks": serialised,
                    "rows": rows,
                }
            )
            outcome["output_file"] = str(written)
            trace.tool("output", f"{written.name} · {len(rows)} rows", status="ok")

            if not failed:
                outcome["passed"] = True
                outcome["summary"] = f"{len(rows)} rows, every check green, attempt {attempt}"
                trace.state("accepted", attempt=attempt, rows=len(rows))
                break

            failures = failed
            trace.state("rejected", attempt=attempt, failed=len(failed))
        else:
            outcome["summary"] = f"still failing after {max_attempts} attempts"
            trace.state("exhausted", attempts=max_attempts)
    finally:
        await executor.close()

    outcome["account"] = account
    outcome["run_id"] = run.run_id
    outcome["seconds"] = round(time.monotonic() - started_at, 1)

    trace.save(run.trace_path)
    run.write_summary(
        {
            "run_id": run.run_id,
            "account": account,
            "source_file": statement.name,
            "model": settings.resolved_model,
            "attempts": outcome["attempts"],
            "accepted": outcome["passed"],
            "rows": outcome["rows"],
            "seconds": outcome["seconds"],
            "summary": outcome["summary"],
        }
    )
    run.mark_latest()

    return {"outcome": outcome, "events": len(trace.events), "trace": trace, "run": run}


def main(statement: Path, *, allow_local: bool = False, profile: str = DEFAULT_PROFILE) -> dict:
    settings = Settings(_env_file=str(Path(__file__).resolve().parents[2] / ".env"))
    return asyncio.run(
        run_agent(statement, settings, allow_local=allow_local, profile=profile)
    )
