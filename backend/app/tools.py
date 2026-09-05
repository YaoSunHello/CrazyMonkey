"""The agent's tools. Thin wrappers — no verification logic lives here.

`run_checks` calls the same `run_parse_checks` the CLI calls. There are no
agent-only checks, so a green run means the same thing whoever asked for it.

The verifier reads the source PDF itself rather than trusting anything the
agent reports about it. The agent supplies rows; the document supplies truth.
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from pathlib import Path

from agents import function_tool

from app.ingestion.statements import parse_statement
from app.models import Provenance, StatementRow
from app.sandbox import WORKDIR, Executor
from app.trace import Trace
from app.verification.checks import run_parse_checks

# Set by the runner before the agent starts. Single-process by design.
_executor: Executor | None = None
_trace: Trace | None = None
_statement_path: Path | None = None
_history: list[str] = []


def bind(executor: Executor, trace: Trace, statement_path: Path) -> None:
    global _executor, _trace, _statement_path
    _executor, _trace, _statement_path = executor, trace, statement_path
    _history.clear()


def attempt_history() -> list[str]:
    """What has already been rejected, so the agent is not amnesic across rounds."""
    return list(_history)


@function_tool
async def read_statement_text(page: int) -> str:
    """Read one page of the bank statement as line-numbered text.

    Args:
        page: 1-indexed page number.
    """
    _trace.tool("read_statement_text", f"page {page}", status="running")
    statement = parse_statement(_statement_path)
    if not 1 <= page <= len(statement.page_text):
        _trace.tool("read_statement_text", f"no page {page}", status="fail")
        return f"ERROR: statement has {len(statement.page_text)} pages"
    lines = statement.page_text[page - 1].splitlines()
    body = "\n".join(f"{n:>3}| {line}" for n, line in enumerate(lines, 1))
    _trace.tool(
        "read_statement_text",
        f"page {page} · {len(lines)} lines",
        status="ok",
    )
    _trace.out(body[:600])
    return f"PAGE {page} of {len(statement.page_text)}\n{body}"


@function_tool
async def write_file(filename: str, source: str) -> str:
    """Write a Python file into your workspace.

    Args:
        filename: e.g. "parse.py". Relative to your workspace.
        source: the complete file contents.
    """
    path = f"{WORKDIR}/{filename}"
    await _executor.put(path, source.encode("utf-8"))
    _trace.tool("write_file", filename, status="ok", lines=len(source.splitlines()))
    _trace.code(path, source)
    return f"Wrote {len(source.splitlines())} lines to {path}"


@function_tool
async def run_python(filename: str) -> str:
    """Execute a Python file in your workspace and return its output.

    Args:
        filename: e.g. "parse.py".
    """
    _trace.tool("run_python", filename, status="running")
    result = await _executor.run_python(filename, timeout=180)
    if result.stdout:
        _trace.out(result.stdout[:1500], stream="stdout")
    if result.stderr:
        _trace.out(result.stderr[:1500], stream="stderr")
    _trace.tool(
        "run_python",
        f"exit {result.exit_code}",
        status="ok" if result.ok else "fail",
    )
    tail = (result.stdout or "")[-2000:] + (result.stderr or "")[-2000:]
    return f"exit_code={result.exit_code}\n{tail or '(no output)'}"


def _load_agent_rows(payload: list[dict]) -> list[StatementRow]:
    rows: list[StatementRow] = []
    for index, item in enumerate(payload):
        rows.append(
            StatementRow(
                account_number=str(item.get("account_number", "")),
                currency=str(item.get("currency", "")),
                bank_reference=str(item.get("bank_reference", "")),
                trn_type=str(item.get("trn_type", "")),
                value_date=str(item.get("value_date", "")),
                post_date=str(item.get("post_date", "")),
                time=str(item.get("time", "")),
                credit=None if item.get("credit") in (None, "") else Decimal(str(item["credit"])),
                debit=None if item.get("debit") in (None, "") else Decimal(str(item["debit"])),
                balance=None if item.get("balance") in (None, "") else Decimal(str(item["balance"])),
                narrative=str(item.get("narrative", "")),
                provenance=Provenance(page=int(item.get("page", 1)), x0=0, top=index, x1=0, bottom=0),
            )
        )
    return rows


@function_tool
async def run_checks() -> str:
    """Run the verifier over result.json. MANDATORY before submitting.

    The verifier reads the source PDF itself; you supply only the rows. Every
    failing check names the row, the expected value, the actual value and the
    difference.
    """
    _trace.tool("run_checks", "the verifier", status="running")
    try:
        raw = await _executor.get(f"{WORKDIR}/result.json")
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — report, never crash the loop
        _trace.tool("run_checks", f"no readable result.json: {exc}", status="fail")
        return f"ERROR: could not read result.json — {exc}"

    rows = payload["rows"] if isinstance(payload, dict) else payload

    # Truth comes from the document, not from the agent's report of it.
    statement = parse_statement(_statement_path)
    statement.rows = _load_agent_rows(rows)

    checks = run_parse_checks(statement)
    serialised = [c.model_dump() for c in checks]
    failed = [c for c in checks if c.status == "FAIL"]
    _trace.verdict(serialised, passed=not failed)

    for check in failed:
        _history.append(f"{check.name}: {check.detail}")

    lines = [f"rows_supplied={len(rows)}"]
    for check in checks:
        lines.append(f"[{check.status}] {check.name}: {check.detail}")
        if check.evidence:
            lines.append("  " + check.evidence.replace("\n", "\n  "))
    lines.append(
        f"SUMMARY {sum(c.status == 'PASS' for c in checks)} pass, "
        f"{len(failed)} fail, {sum(c.status == 'UNRESOLVED' for c in checks)} unresolved"
    )
    if failed:
        lines.append("Not acceptable yet. Fix the parser and run the checks again.")
    return "\n".join(lines)


@function_tool
async def submit_result(rows_parsed: int, all_checks_pass: bool, summary: str) -> str:
    """Submit when — and only when — run_checks reports zero failures.

    Args:
        rows_parsed: how many transaction rows your parser produced.
        all_checks_pass: true only if the last run_checks showed 0 failures.
        summary: what you did, and anything you could not resolve.
    """
    _trace.tool("submit_result", f"{rows_parsed} rows", status="ok")
    return json.dumps(
        {"rows_parsed": rows_parsed, "all_checks_pass": all_checks_pass, "summary": summary}
    )


ALL_TOOLS = [read_statement_text, write_file, run_python, run_checks, submit_result]
