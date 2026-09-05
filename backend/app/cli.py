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
import json
import sys
import time
from decimal import Decimal
from pathlib import Path

from app.ingestion.statements import parse_all, parse_statement
from app.models import Check, Statement
from app.verification.checks import run_parse_checks

ROOT = Path(__file__).resolve().parents[2]
STATEMENTS = ROOT / "samples" / "statements"
OUTPUTS = ROOT / "outputs"

MARK = {"PASS": "PASS", "FAIL": "FAIL", "UNRESOLVED": "UNRE"}


def log(message: str = "") -> None:
    print(message, file=sys.stderr, flush=True)


def _load(account: str | None) -> list[Statement]:
    if not STATEMENTS.exists() or not any(STATEMENTS.glob("*.pdf")):
        log(f"No statements found in {STATEMENTS}.")
        log("See samples/README.md for where to put the dataset.")
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

    show = subcommands.add_parser("parse", help="parse and print the rows")
    show.add_argument("--account", help="e.g. GBP_3252. Omit for all seven.")
    show.set_defaults(func=command_parse)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
