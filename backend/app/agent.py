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


EXPLORE_ASK = """\

Before you write it, you may look at the data.

Write a short throwaway script that PRINTS whatever you want to know — the first
few rows, what a narrative actually looks like, whether a pattern you are about
to rely on really holds, how many rows it would match. It is not the answer and
nothing is judged on it; it is a look at the data before you commit.

Its stdout comes back to you, capped, and then you write the real file.

Worth knowing: every previous run wrote its parser blind and made the same
mistake — capturing eighteen words of a narrative where three were wanted — and
printing five extracted values would have shown it immediately.

Reply with the throwaway script in a single ```python code block.
"""


async def _explore(
    spec, *, executor, trace, settings: Settings, base: str, rounds: int
) -> str:
    """Let the agent look at the data before it writes the real script.

    The turn loop, brought back deliberately and bounded. It was removed early
    on for a good reason — against a quantised model at ~220s a turn it was
    unusable — and never revisited when the model changed to one ten times
    faster. This is the part of it that pays.

    It cannot reintroduce what actually killed the original loop: the model
    writes *code*, not tool-call JSON, so there is no argument schema to
    malform and no way to abort a run by emitting a bad one. A script that
    fails to run just prints a traceback, which is itself informative.

    Returns a transcript to fold into the real prompt, or "" if nothing useful
    came back.
    """
    transcript = []
    for turn in range(1, rounds + 1):
        trace.tool("explore", f"round {turn} of {rounds}", status="running")
        prompt = base + EXPLORE_ASK
        if transcript:
            prompt += "\nWhat you have seen so far:\n\n" + "\n".join(transcript)

        reply = await stream_completion(settings, prompt, on_thought=trace.thought)
        trace.end_thought()
        source = extract_code(reply)
        if not source:
            break

        script = f"explore-{turn}.py"
        trace.code(f"{WORKDIR}/{script}", source)
        await executor.put(f"{WORKDIR}/{script}", source.encode("utf-8"))
        execution = await executor.run_python(script, timeout=120)

        # Capped hard. An exploration that prints a whole workbook would push
        # the real task out of the context window, which would cost far more
        # than the look is worth.
        seen = (execution.stdout or execution.stderr or "")[:4000]
        trace.tool("explore", f"{len(seen)} chars back", status="ok")
        transcript.append(f"--- you ran {script} and it printed ---\n{seen}")

    if not transcript:
        return ""
    return "\n\nYou looked at the data first. This is what you saw:\n\n" + "\n".join(transcript)


async def _agent_assertions(executor, trace) -> list[dict]:
    """What the agent says it checked about its own output.

    These are the agent's claims, recorded as claims. They prove nothing on
    their own — it could report `holds: true` without looking — so they are
    never a substitute for the verifier, and they are labelled `self-reported`
    wherever they appear.

    Their value is twofold, and both are real. Asking for them makes the agent
    look at its own output before submitting, which it has never had to do; and
    a claim that does *not* hold names the problem far more precisely than a
    check written in advance ever could, because the agent knows what it was
    unsure of.

    **They can only add failures.** A claim that does not hold fails the
    attempt; no claim can rescue one the real checks rejected. That asymmetry is
    what keeps them safe, and it is asserted in the tests.
    """
    try:
        raw = await executor.get(f"{WORKDIR}/assertions.json")
        claims = json.loads(raw.decode())
    except Exception:  # noqa: BLE001 — no assertions is the normal case
        return []
    if not isinstance(claims, list):
        return []

    out = []
    for claim in claims:
        if not isinstance(claim, dict) or not claim.get("name"):
            continue
        holds = bool(claim.get("holds"))
        out.append(
            {
                "name": f"self:{claim['name']}",
                "scope": "agent",
                "status": "PASS" if holds else "FAIL",
                "detail": f"self-reported — {str(claim.get('detail', ''))[:120]}",
                "evidence": "" if holds else str(claim.get("detail", ""))[:400],
            }
        )
    if out:
        broken = sum(1 for c in out if c["status"] == "FAIL")
        trace.tool(
            "assertions",
            f"{len(out)} self-reported · {broken} not holding",
            status="ok" if not broken else "fail",
        )
    return out


def _attach_samples(primary: list[dict], extra: list[list[dict]]) -> list[dict]:
    """Carry the other samples' readings on each row, under `_samples`.

    Aligned by position, and only where the counts agree — two samples of a
    pass that produced different numbers of rows are not comparable row by row,
    and pretending otherwise would report disagreements that are really an
    off-by-one. In that case the extra sample is dropped and the agreement
    check reports that it had nothing to compare.
    """
    usable = [other for other in extra if len(other) == len(primary)]
    if not usable:
        return primary
    return [
        {**row, "_samples": [other[index] for other in usable]}
        for index, row in enumerate(primary)
    ]


async def _install_kit(executor, name: str) -> None:
    """Put this pass's toolkit in the sandbox, as `kit`.

    Each pass gets one kit and always imports it under the same name, so the
    agent never has to be told which module to reach for. Written per pass
    rather than once per run because a resolution pass needs the reference
    lists where an extraction pass needs the PDF.
    """
    source = (Path(__file__).parent / "kit" / f"{name}.py").read_bytes()
    await executor.put(f"{WORKDIR}/kit.py", source)


def _judge(spec, rows: list[dict], statement: Path, account: str, tables: dict) -> list[dict]:
    """Run the checks this pass is judged by, and return them serialised.

    Two families. `statement` runs the arithmetic checks in
    `verification/checks.py` — every one of them, not the subset a profile
    happens to name, because those are the contract and the CLI runs them all.
    `generic` runs the parameterised checks a profile asks for by name.

    Either way the checks come from `verification/`, which imports nothing from
    here and cannot see a profile.
    """
    if spec.judge == "statement":
        from app.ingestion.statements import parse_statement
        from app.tools import _load_agent_rows

        checked = parse_statement(statement)
        checked.rows, unusable = _load_agent_rows(rows)
        serialised = [c.model_dump() for c in run_parse_checks(checked)]

        # A value the agent could not express as a number is its mistake to
        # fix, so it becomes a failed check like any other rather than an
        # exception that ends the run before anything is verified.
        if unusable:
            serialised.insert(
                0,
                {
                    "name": "values_parse",
                    "scope": account,
                    "status": "FAIL",
                    "detail": f"{len(unusable)} value(s) could not be read as numbers",
                    "evidence": "\n".join(unusable[:5]),
                },
            )
        return serialised

    from app.verification import generic

    return [
        generic.run(check.name, rows, account, check.options, tables).model_dump()
        for check in spec.checks
    ]


def retry_prompt(failures: list[dict], attempt: int, of: int, script: str = "parse.py") -> str:
    """Fold the verifier's exact objections into the next attempt."""
    lines = [
        f"Your {script} was REJECTED by the verifier. Attempt {attempt} of {of}.",
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
        f"Reply with the complete corrected {script} in a single ```python code block.",
    ]
    return "\n".join(lines)


async def _run_pass(
    spec,
    *,
    executor,
    trace,
    run,
    build_prompt,
    judge,
    settings: Settings,
    script: str,
    stage: str,
) -> dict:
    """One pass: write a script, run it, judge it, or try again.

    Lifted out of `run_agent` unchanged so a second pass reuses it rather than
    growing a parallel copy. The shape is the one that works and is not up for
    negotiation: **one generation per attempt**, the previous output deleted
    before each retry, and the verifier's exact objections folded into the next
    prompt.

    What varies between passes is only the prompt, the script name, and what
    `judge` does with the rows — never the loop.
    """
    outcome = {"passed": False, "attempts": 0, "rows": 0, "summary": "", "checks": []}
    failures: list[dict] = []
    rows: list[dict] = []

    for attempt in range(1, spec.max_attempts + 1):
        outcome["attempts"] = attempt
        trace.state("attempt", stage=stage, n=attempt, of=spec.max_attempts)

        base = build_prompt({f["name"] for f in failures})

        # Only on the first attempt. A retry already carries the verifier's
        # exact objections, which is better information than anything a fresh
        # look would produce, and paying for another round would be waste.
        if spec.explore and attempt == 1:
            base += await _explore(
                spec,
                executor=executor,
                trace=trace,
                settings=settings,
                base=base,
                rounds=spec.explore,
            )

        prompt = (
            base
            if attempt == 1
            else f"{base}\n\n{retry_prompt(failures, attempt, spec.max_attempts, script)}"
        )

        trace.tool("model", f"generating {script} · attempt {attempt}", status="running")
        started = time.monotonic()

        # The model reasons in a separate channel before it answers.
        # trace.thought keeps the last few lines of it on screen, updating in
        # place, so the wait shows what it is doing rather than a spinner.
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

        trace.code(f"{WORKDIR}/{script}", source)
        # Keep every attempt's source. When a run fails, the code that failed is
        # the first thing worth reading, and digging it out of a JSONL blob is
        # needless friction.
        run.write_attempt(attempt, source, stage=stage)

        # Stale output is worse than none: without this a run that writes
        # nothing gets verified against the previous attempt's file.
        await executor.remove(f"{WORKDIR}/result.json")
        await executor.remove(f"{WORKDIR}/assertions.json")
        await executor.put(f"{WORKDIR}/{script}", source.encode("utf-8"))

        trace.tool("run_python", script, status="running")
        execution = await executor.run_python(script, timeout=180)
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
                    "detail": f"{script} did not produce a readable /work/result.json",
                    "evidence": (execution.stderr or execution.stdout or str(exc))[-800:],
                }
            ]
            continue

        serialised = judge(rows)
        serialised += await _agent_assertions(executor, trace)
        failed = [c for c in serialised if c["status"] == "FAIL"]
        trace.verdict(serialised, passed=not failed)

        outcome["rows"] = len(rows)
        outcome["checks"] = serialised
        outcome["result"] = rows

        if not failed:
            outcome["passed"] = True
            outcome["summary"] = f"{len(rows)} rows, every check green, attempt {attempt}"
            trace.state("accepted", stage=stage, attempt=attempt, rows=len(rows))
            return outcome

        failures = failed
        trace.state("rejected", stage=stage, attempt=attempt, failed=len(failed))

    outcome["summary"] = f"still failing after {spec.max_attempts} attempts"
    trace.state("exhausted", stage=stage, attempts=spec.max_attempts)
    return outcome


async def run_agent(
    statement: Path,
    settings: Settings,
    *,
    allow_local: bool = False,
    quiet: bool = False,
    batch: str = "",
    profile: str = DEFAULT_PROFILE,
) -> dict:
    """Run every pass a profile declares, stopping at the first that fails.

    A later pass builds on an earlier one's output, so continuing past a
    rejection would resolve rows the verifier has already said are wrong.
    """
    import os

    from app.ingestion.statements import parse_statement
    from app.profiles import load as load_profile
    from app.reference.tables import dump as dump_tables
    from app.reference.tables import load_tables

    started_at = time.monotonic()
    truth = parse_statement(statement)
    account = truth.account_short_code
    loaded = load_profile(profile)

    run = RunDir(new_run_id(account, batch=batch))
    trace = Trace(quiet=quiet)
    trace.state(
        "starting",
        statement=statement.name,
        model=settings.resolved_model,
        profile=profile,
        passes=", ".join(p.name for p in loaded.passes),
        run=run.run_id,
    )

    # Per account, not per directory. Sharing one staging directory across
    # concurrent runs would hand each run whichever PDF was written last — and
    # every run would still come back green, having verified the wrong
    # document. Wrong output that looks right is worse than an error.
    data_dir = statement.parent / ".agent_data" / account
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "statement.pdf").write_bytes(statement.read_bytes())

    # A profile may ask questions rather than process rows. What each question
    # needs is declared; whether the run actually has it is decided here, once,
    # so the agent is told rather than left to guess — and so a refusal names a
    # real missing input rather than an assumed one.
    questions = loaded.inputs.get("questions") or []
    if questions:
        mounted = set(loaded.inputs.get("tables") or {})
        answerable = [
            {**q, "available": all(need in mounted for need in q.get("requires", []))}
            for q in questions
        ]
        (data_dir / "questions.json").write_text(
            json.dumps(answerable, indent=2), encoding="utf-8"
        )
        trace.tool(
            "questions",
            f"{sum(q['available'] for q in answerable)} of {len(answerable)} answerable "
            f"from what this run mounted",
            status="ok",
        )

    tables = load_tables(loaded.inputs)
    if tables:
        dump_tables(tables, data_dir / "tables.json")
        trace.tool(
            "reference",
            " · ".join(f"{n} {len(t.rows)}" for n, t in sorted(tables.items())),
            status="ok",
        )

    if settings.daytona_api_key:
        os.environ["DAYTONA_API_KEY"] = settings.daytona_api_key
        os.environ["DAYTONA_TARGET"] = settings.daytona_target

    executor = build_executor(trace, data_dir, allow_local=allow_local)
    await executor.start()

    statement_text = "\n\n".join(
        f"--- PAGE {number} ---\n{body}" for number, body in enumerate(truth.page_text, 1)
    )

    outcome = {"passed": False, "attempts": 0, "rows": 0, "summary": ""}
    rows: list[dict] = []
    all_checks: list[dict] = []

    try:
        for spec in loaded.passes:
            await _install_kit(executor, spec.kit)

            if spec.inherits_rows:
                # The previous pass's output becomes this one's input as data
                # rather than as prompt text. A hundred rows quoted into a
                # prompt is both expensive and something the model can copy
                # imperfectly; a file it reads is neither.
                await executor.put(
                    f"{DATADIR}/rows.json", json.dumps({"rows": rows}).encode("utf-8")
                )

            def build_prompt(failed: set[str], spec=spec) -> str:
                """Rebuilt each attempt, because a nudge can be scoped to a
                check and advice about a check nobody failed is noise competing
                with the failure that actually needs fixing."""
                task = spec.compose(document=account, failed=failed)
                if spec.inherits_rows:
                    return f"{task}\nThere are {len(rows)} rows to resolve.\n"
                return f"{task}\nThe statement text, for reference:\n\n{statement_text}\n"

            def judge(produced: list[dict], spec=spec) -> list[dict]:
                return _judge(spec, produced, statement, account, tables)

            result = await _run_pass(
                spec,
                executor=executor,
                trace=trace,
                run=run,
                build_prompt=build_prompt,
                judge=judge,
                settings=settings,
                script=f"{spec.name}.py",
                stage=spec.name,
            )

            # Sample the pass again when the profile asks for it, and carry the
            # extra readings on each row. Done here rather than inside the loop
            # so the retry mechanism is untouched: each sample converges on its
            # own, and only then are they compared.
            if spec.samples > 1 and result["passed"]:
                extra = []
                for sample in range(2, spec.samples + 1):
                    trace.state("sampling", stage=spec.name, n=sample, of=spec.samples)
                    again = await _run_pass(
                        spec,
                        executor=executor,
                        trace=trace,
                        run=run,
                        build_prompt=build_prompt,
                        judge=judge,
                        settings=settings,
                        script=f"{spec.name}-{sample}.py",
                        stage=f"{spec.name}-{sample}",
                    )
                    # An extra sample that could not satisfy the checks is not
                    # evidence about anything, so it is dropped rather than
                    # allowed to manufacture a disagreement.
                    if again["passed"] and again.get("result"):
                        extra.append(again["result"])

                if extra:
                    merged = _attach_samples(result["result"], extra)
                    result["result"] = merged
                    # Re-judge with the samples attached so the agreement check
                    # can see them. Agreement returns UNRESOLVED, never FAIL, so
                    # this cannot turn an accepted pass into a rejected one.
                    result["checks"] = judge(merged)
                    trace.verdict(result["checks"], passed=True)

            all_checks.extend(result["checks"])
            outcome["attempts"] += result["attempts"]
            if result.get("result"):
                rows = result["result"]
                outcome["rows"] = len(rows)

            # Keep the output even when it was rejected: the sandbox is about to
            # be destroyed, and a rejected attempt is the most useful thing to
            # look at when working out why.
            last = spec is loaded.passes[-1]
            written = run.write_rows(
                {
                    "account": account,
                    "source_file": statement.name,
                    "profile": profile,
                    "stage": spec.name,
                    "attempt": result["attempts"],
                    "accepted": result["passed"],
                    # Every check the run has done so far, not just this pass's.
                    # The arithmetic that settled the rows is part of why the
                    # output can be trusted, and dropping it from the record
                    # would leave an audit trail that cannot answer the
                    # question it exists for.
                    "checks": all_checks,
                    "rows": rows,
                },
                stage="" if last else spec.name,
            )
            outcome["output_file"] = str(written)
            trace.tool("output", f"{written.name} · {len(rows)} rows", status="ok")

            outcome["passed"] = result["passed"]
            outcome["summary"] = f"{spec.name}: {result['summary']}"
            if not result["passed"]:
                break
    finally:
        await executor.close()

    outcome["account"] = account
    outcome["run_id"] = run.run_id
    outcome["profile"] = profile
    outcome["checks"] = all_checks
    outcome["seconds"] = round(time.monotonic() - started_at, 1)

    trace.save(run.trace_path)
    run.write_summary(
        {
            "run_id": run.run_id,
            "account": account,
            "source_file": statement.name,
            "profile": profile,
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
