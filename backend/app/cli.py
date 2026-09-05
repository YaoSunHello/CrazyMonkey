"""Command line entry point.

    python -m app.cli verify                     every statement
    python -m app.cli verify --account GBP_3252  one of them
    python -m app.cli parse  --account GBP_3252  show the parsed rows

Progress goes to stderr and results go to stdout, so `... > out.json` gives a
clean file while you still see the log.

Exit code 1 when any check FAILs. UNRESOLVED never fails the run: it means the
data does not resolve against the reference lists and a human has to decide,
which is a legitimate outcome rather than a broken parse.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from decimal import Decimal
from pathlib import Path

from app.ingestion.statements import parse_all, parse_statement
from app.models import Check, Statement
from app.profiles import DEFAULT_PROFILE
from app.verification.checks import run_parse_checks

ROOT = Path(__file__).resolve().parents[2]

# The organisers committed the dataset under its own folder; earlier we unpacked
# the zip flat into samples/statements/. Prefer the committed copy so a fresh
# clone works, but keep honouring an existing local drop-in. An empty directory
# does not count, or a stray mkdir would shadow the statements that are there.
CANDIDATES = (
    ROOT / "samples" / "01-bank-statements-to-journal-entries" / "statements",
    ROOT / "samples" / "statements",
)
STATEMENTS = next(
    (d for d in CANDIDATES if d.is_dir() and any(d.glob("*.pdf"))), CANDIDATES[0]
)

OUTPUTS = ROOT / "outputs"

MARK = {"PASS": "PASS", "FAIL": "FAIL", "UNRESOLVED": "UNRE"}


def log(message: str = "") -> None:
    print(message, file=sys.stderr, flush=True)


def _load(account: str | None) -> list[Statement]:
    if not STATEMENTS.exists() or not any(STATEMENTS.glob("*.pdf")):
        log(f"No statements found in {STATEMENTS}.")
        log("See backend/README.md for where the dataset lives.")
        raise SystemExit(2)

    statements = parse_all(STATEMENTS)
    if account:
        statements = [s for s in statements if s.account_short_code == account]
        if not statements:
            log(f"No statement matches account {account!r}.")
            raise SystemExit(2)
    return statements


def _report(statement: Statement, checks: list[Check]) -> None:
    log(f"  {statement.source_file}")
    log(
        f"    {statement.account_name} · {statement.currency} · "
        f"{len(statement.rows)} rows · {statement.date_range}"
    )
    for check in checks:
        log(f"    [{MARK[check.status]}] {check.name:22} {check.detail}")
        if check.evidence:
            for line in check.evidence.splitlines():
                log(f"           {line}")


def _corrupt(statements: list[Statement], row_index: int) -> None:
    """Deliberately damage one parsed amount, to prove the verifier notices.

    Nothing in the pipeline can do this; it exists so the failure path can be
    demonstrated on demand. The log says plainly that the damage was injected,
    because a demo that looks like a real failure but is not is worse than no
    demo at all.
    """
    statement = statements[0]
    row = statement.rows[row_index]
    before = row.amount
    if row.debit is not None:
        row.debit -= Decimal("100.00")
    else:
        row.credit -= Decimal("100.00")
    log("!! INJECTED FAULT — this is a deliberate test, not a real discrepancy.")
    log(
        f"!! {statement.account_short_code} row {row_index}: amount changed "
        f"from {before} to {row.amount} ({row.provenance.as_citation()})"
    )
    log("")


def command_verify(args: argparse.Namespace) -> int:
    started = time.monotonic()
    log("Parsing statements and verifying the arithmetic.")
    log("")

    statements = _load(args.account)
    if args.corrupt is not None:
        _corrupt(statements, args.corrupt)
    tally = {"PASS": 0, "FAIL": 0, "UNRESOLVED": 0}
    payload = []

    for statement in statements:
        checks = run_parse_checks(statement)
        for check in checks:
            tally[check.status] += 1
        _report(statement, checks)
        log("")
        payload.append(
            {
                "account": statement.account_short_code,
                "source_file": statement.source_file,
                "rows": len(statement.rows),
                "checks": [c.model_dump() for c in checks],
            }
        )

    rows = sum(len(s.rows) for s in statements)
    elapsed = time.monotonic() - started
    log(f"{len(statements)} statements · {rows} rows · {elapsed:.2f}s")
    log(
        f"{tally['PASS']} passed · {tally['FAIL']} failed · "
        f"{tally['UNRESOLVED']} unresolved (need a human)"
    )
    if tally["FAIL"]:
        log("")
        log("Refusing to emit journal entries: the arithmetic does not hold.")

    OUTPUTS.mkdir(exist_ok=True)
    written = OUTPUTS / "checks.json"
    written.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    log(f"Wrote {written.relative_to(ROOT)}")

    print(json.dumps(payload, indent=2, default=str))
    return 1 if tally["FAIL"] else 0


def command_parse(args: argparse.Namespace) -> int:
    statements = _load(args.account)
    for statement in statements:
        log(f"{statement.source_file} — {statement.account_name} ({statement.currency})")
        for index, row in enumerate(statement.rows):
            amount = f"{row.amount:>18,}"
            log(
                f"  {index:>3} {row.value_date:<12} {amount}  bal {row.balance:>16,}"
                f"  {row.provenance.as_citation()}"
            )
            log(f"      {row.bank_reference} · {row.trn_type}")
            if row.narrative:
                log(f"      {row.narrative[:140]}")
        log("")
    print(
        json.dumps(
            [s.model_dump(exclude={"page_text"}) for s in statements], indent=2, default=str
        )
    )
    return 0


def command_agent(args: argparse.Namespace) -> int:
    """Hand statements to the model and let the verifier referee."""
    from app.agent import main as run_one
    from app.batch import DEFAULT_PARALLEL, run_many
    from app.config import Settings

    pdfs = sorted(STATEMENTS.glob("*.pdf"))
    if not args.all:
        pdfs = [p for p in pdfs if args.account in p.stem]
        if not pdfs:
            log(f"No statement matches {args.account!r}.")
            return 2

    if len(pdfs) == 1:
        result = run_one(
            pdfs[0], allow_local=args.allow_local_execution, profile=args.profile
        )
        outcome = result["outcome"]
        log("")
        log(f"Run {outcome['run_id']} -> {result['run'].path}")
        print(json.dumps(outcome, indent=2))
        return 0 if outcome["passed"] else 1

    settings = Settings(_env_file=str(ROOT / ".env"))
    results = asyncio.run(
        run_many(
            pdfs,
            settings,
            limit=args.parallel or DEFAULT_PARALLEL,
            allow_local=args.allow_local_execution,
            profile=args.profile,
        )
    )
    outcomes = [r["outcome"] for r in results]
    print(json.dumps(outcomes, indent=2))
    return 0 if all(o.get("passed") for o in outcomes) else 1


def command_profiles(args: argparse.Namespace) -> int:
    """List the tracks a run can be started on.

    The same summaries the API serves, so what a person sees here and what a
    frontend offers cannot drift.
    """
    from app.profiles import load_all

    profiles = load_all()
    if not profiles:
        log("No profiles found.")
        return 2

    for profile in profiles:
        summary = profile.summary()
        log(f"{summary['id']}")
        log(f"    {summary['label']}")
        log(f"    passes: {', '.join(summary['passes']) or '(none)'}")
        if summary["tables"]:
            log(f"    tables: {', '.join(summary['tables'])}")
        log("")
    print(json.dumps([p.summary() for p in profiles], indent=2))
    return 0


def command_runs(args: argparse.Namespace) -> int:
    """List recorded runs, newest first."""
    from app.runs import list_runs

    records = list_runs()
    if not records:
        log("No runs recorded yet.")
        return 2
    log(f"{'run':<26} {'account':<12} {'result':<9} {'rows':>5} {'try':>4} {'secs':>6}")
    for record in records[: args.limit]:
        verdict = "accepted" if record.accepted else "rejected"
        log(
            f"{record.run_id:<26} {record.account:<12} {verdict:<9} "
            f"{record.rows:>5} {record.attempts:>4} {record.seconds:>6.0f}"
        )
    return 0


def command_show(args: argparse.Namespace) -> int:
    """Print the rows and the verdict from a recorded run."""
    from app.runs import resolve

    record = resolve(args.run)
    if record is None:
        log(f"No run matches {args.run!r}. Try `runs`.")
        return 2

    payload = json.loads((record.path / "rows.json").read_text(encoding="utf-8"))
    log(f"{record.run_id} — {payload['account']} — {payload['source_file']}")
    log(f"attempt {payload['attempt']} · accepted={payload['accepted']}")
    log("")
    for check in payload["checks"]:
        log(f"  [{MARK[check['status']]}] {check['name']:22} {check['detail']}")
    log("")
    for index, row in enumerate(payload["rows"]):
        amount = row.get("credit") or row.get("debit") or ""
        log(
            f"  {index:>3} {str(row.get('value_date','')):<12} {str(amount):>18}"
            f"  bal {str(row.get('balance','')):>16}  {row.get('bank_reference','')}"
        )
    print(json.dumps(payload, indent=2))
    return 0


def command_replay(args: argparse.Namespace) -> int:
    """Replay a recorded run at its original pacing.

    A live run needs the model up and takes minutes. Replaying a real recorded
    stream is the safe way to demonstrate it — and it is a *real* run, not a
    fixture, which is the only version worth showing.
    """
    from app.trace import Event, Trace

    from app.runs import resolve

    record = resolve(args.run)
    if record is None:
        log("No runs recorded yet. Run `agent` first.")
        return 2
    path = record.trace_path if hasattr(record, "trace_path") else record.path / "trace.jsonl"
    if not path.exists():
        log(f"Run {record.run_id} has no trace.jsonl.")
        return 2
    log(f"Replaying {record.run_id}")

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if not records:
        log("Recording is empty.")
        return 2

    trace = Trace()
    trace.started = time.monotonic()
    previous = records[0]["at"]
    for record in records:
        # Collapse dead time rather than speeding everything up uniformly, so
        # bursts stay readable and long pauses stop being long.
        gap = min((record["at"] - previous) / max(args.speed, 0.1), 1.2)
        if gap > 0:
            time.sleep(gap)
        previous = record["at"]
        trace._render(Event(**record))

    log("")
    log(f"Replayed {len(records)} events from {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    verify = subcommands.add_parser("verify", help="parse and run every check")
    verify.add_argument("--account", help="e.g. GBP_3252. Omit for all seven.")
    verify.add_argument(
        "--corrupt",
        type=int,
        metavar="ROW",
        help="damage this row's amount on purpose, to show the verifier catching it",
    )
    verify.set_defaults(func=command_verify)

    agent_cmd = subcommands.add_parser(
        "agent", help="let the model write the parser and satisfy the verifier"
    )
    agent_cmd.add_argument("--account", default="GBP_3252")
    agent_cmd.add_argument("--all", action="store_true", help="every statement")
    agent_cmd.add_argument(
        "--parallel", type=int, default=0, metavar="N",
        help="sandboxes at a time when running many (default 5)",
    )
    agent_cmd.add_argument(
        "--allow-local-execution",
        action="store_true",
        help="run model-written code in a local subprocess (no isolation)",
    )
    agent_cmd.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        metavar="ID",
        help=f"which track to run (default {DEFAULT_PROFILE}); see `profiles`",
    )
    agent_cmd.set_defaults(func=command_agent)

    profiles_cmd = subcommands.add_parser(
        "profiles", help="list the tracks a run can be started on"
    )
    profiles_cmd.set_defaults(func=command_profiles)

    replay = subcommands.add_parser("replay", help="replay the last recorded agent run")
    replay.add_argument("--speed", type=float, default=1.0, help="playback multiplier")
    replay.add_argument("--run", help="run id or prefix. Defaults to the latest.")
    replay.set_defaults(func=command_replay)

    runs_cmd = subcommands.add_parser("runs", help="list recorded agent runs")
    runs_cmd.add_argument("--limit", type=int, default=20)
    runs_cmd.set_defaults(func=command_runs)

    show_cmd = subcommands.add_parser("show", help="print rows and verdict from a run")
    show_cmd.add_argument("--run", help="run id or prefix. Defaults to the latest.")
    show_cmd.set_defaults(func=command_show)

    show = subcommands.add_parser("parse", help="parse and print the rows")
    show.add_argument("--account", help="e.g. GBP_3252. Omit for all seven.")
    show.set_defaults(func=command_parse)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
