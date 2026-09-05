"""Checks that know nothing about banks.

The six checks in `checks.py` are arithmetic over a statement. These are the
other half: whether a *resolution* is honest. They are parameterised and chosen
by name from a profile, so a second use case gets them by naming them rather
than by growing a second verifier.

Four properties are worth having, and between them they close the failure modes
both specifications call out by name:

    provenance    a value claimed to come from the document is really in it
    membership    a MATCH names a row that exists, verbatim, in a named table
    completeness  every row carries a status for every field that needs one
    vocabulary    a label is one of the declared labels

The one that matters most is **membership**, because the tempting failure is not
a wrong match, it is a confident one. `docs/business-case-2` puts it plainly:
"unmatched rows are forced to the nearest master-list name" is a failure
condition. So a `MATCH` has to name its table and its key, and the key has to be
there. A match that cannot say where it came from is a `FAIL`, not a pass — and
a missing input is `CANNOT_VERIFY`, never `MATCH`.

This module imports nothing from `agent.py`, `sandbox.py` or `profiles.py`, and
must not. The agent is judged by code it cannot reach or influence.
"""

from __future__ import annotations

from app.kit.reference_kit import Table, normalise
from app.models import Check

# What a resolution may say about itself. `MATCH` and `UNRESOLVED` are the
# honest outcomes; `FAIL` means the claim is broken; `CANNOT_VERIFY` means the
# input needed to decide was not in this run.
STATUSES = {"MATCH", "UNRESOLVED", "FAIL", "CANNOT_VERIFY"}


def _cap(items: list[str], limit: int = 5) -> str:
    """Evidence a person will actually read, with the count they need."""
    shown = "\n".join(items[:limit])
    if len(items) > limit:
        shown += f"\n… and {len(items) - limit} more"
    return shown


def _resolution(row: dict, field: str) -> dict:
    """A resolution as a dict, whatever shape the profile asked the agent for.

    Both specifications use a nested object (`counterparty_match`) in one place
    and a flat status (`counterparty_status`) in another. Accepting either here
    means the profile chooses its own field names without the checks forking.
    """
    value = row.get(field)
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return {"status": value}
    return {}


def check_provenance(rows: list[dict], scope: str, options: dict) -> Check:
    """A value the agent says it read out of the document must be in it.

    The organisers verified this is achievable: every counterparty string the
    staging sheet pulled from a narrative is still literally present in the
    corresponding PDF, in the bank's truncated uppercase form. So a value that
    is not there was invented, and this catches it.
    """
    field = options["field"]
    source = options.get("source", "narrative")

    problems = []
    claimed = 0
    for index, row in enumerate(rows):
        value = normalise(row.get(field))
        if not value:
            continue
        claimed += 1
        haystack = normalise(row.get(source)).casefold()
        if value.casefold() not in haystack:
            problems.append(f"row {index}: {value!r} is not in this row's {source}")

    if not claimed:
        return Check(
            name=f"{field}_provenance",
            scope=scope,
            status="CANNOT_VERIFY",
            detail=f"no row claims a {field}",
        )
    held = claimed - len(problems)
    return Check(
        name=f"{field}_provenance",
        scope=scope,
        status="PASS" if not problems else "FAIL",
        detail=f"{held}/{claimed} {field} values appear in their own {source}",
        evidence=_cap(problems),
    )


def check_membership(
    rows: list[dict], scope: str, options: dict, tables: dict[str, Table]
) -> Check:
    """A `MATCH` must name a row that is really in the table it names.

    This is the check that stops a near miss becoming an answer. It deliberately
    does not look for what the value *should* have matched: an unmatched row
    staying unmatched is the correct outcome, not a gap to close.
    """
    field = options["field"]
    pools = options.get("tables", [])

    def present(name: str, key: str) -> bool:
        for pool in pools:
            table_name, _, column = pool.partition(":")
            if name and name != table_name:
                continue
            table = tables.get(table_name)
            if table and column in table.columns and table.contains(column, key):
                return True
        return False

    counts = {status: 0 for status in STATUSES}
    problems = []
    for index, row in enumerate(rows):
        resolution = _resolution(row, field)
        status = normalise(resolution.get("status")).upper()

        if status not in STATUSES:
            problems.append(f"row {index}: status {status or '(missing)'!r} is not one of {sorted(STATUSES)}")
            continue
        counts[status] += 1
        if status != "MATCH":
            continue

        key = normalise(resolution.get("matched_name") or resolution.get("matched") or "")
        table_name = normalise(resolution.get("table"))
        if not key:
            problems.append(f"row {index}: MATCH with nothing matched")
        elif not present(table_name, key):
            where = f"table {table_name!r}" if table_name else "any declared table"
            problems.append(f"row {index}: MATCH on {key!r}, but it is not in {where}")

    summary = " · ".join(f"{n} {s}" for s, n in counts.items() if n)
    return Check(
        name=f"{field}_membership",
        scope=scope,
        status="PASS" if not problems else "FAIL",
        detail=summary or "no resolutions declared",
        evidence=_cap(problems),
    )


def check_completeness(rows: list[dict], scope: str, options: dict) -> Check:
    """Every row carries a status for every field that needs one.

    A row that simply omits a resolution is not unresolved — it is unexamined,
    and the difference matters to whoever has to review the queue.
    """
    fields = options["fields"]
    missing = []
    for index, row in enumerate(rows):
        for field in fields:
            status = normalise(_resolution(row, field).get("status")).upper()
            if status not in STATUSES:
                missing.append(f"row {index}: no status for {field}")

    total = len(rows) * len(fields)
    return Check(
        name="resolution_completeness",
        scope=scope,
        status="PASS" if not missing else "FAIL",
        detail=f"{total - len(missing)}/{total} resolutions carry a status",
        evidence=_cap(missing),
    )


def check_vocabulary(rows: list[dict], scope: str, options: dict) -> Check:
    """A label must be one of the labels the profile declared.

    Held as profile data rather than an enum in code because the supplied
    workbook uses seven classes where both specifications list six — it has
    `Investment Transfer` and `Other`, and no `Investor`. A vocabulary baked
    into the verifier would have made the real data wrong.
    """
    field = options["field"]
    allowed = {normalise(v).casefold() for v in options["allowed"]}

    problems = []
    for index, row in enumerate(rows):
        label = normalise(row.get(field))
        if not label:
            problems.append(f"row {index}: no {field}")
        elif label.casefold() not in allowed:
            problems.append(f"row {index}: {label!r} is not a declared {field}")

    held = len(rows) - len(problems)
    return Check(
        name=f"{field}_vocabulary",
        scope=scope,
        status="PASS" if not problems else "FAIL",
        detail=f"{held}/{len(rows)} rows carry a declared {field}",
        evidence=_cap(problems),
    )


# Every check this module offers, by the name a profile uses to ask for it.
# `run` dispatches through here so an unknown name is a clear error at the
# profile rather than a silently skipped check.
REGISTRY = {
    "provenance": check_provenance,
    "membership": check_membership,
    "completeness": check_completeness,
    "vocabulary": check_vocabulary,
}


def name_for(name: str, options: dict) -> str:
    """The name this check will report under.

    Exposed so a profile can announce a check to the model under the same name
    it will fail under. When those drift, a retry tells the agent that
    `counterparty_raw_provenance` failed after the prompt only ever mentioned
    `provenance`, and a nudge keyed to the check silently never fires.
    """
    if name == "completeness":
        return "resolution_completeness"
    field = options.get("field")
    return f"{field}_{name}" if field else name


def run(
    name: str,
    rows: list[dict],
    scope: str,
    options: dict,
    tables: dict[str, Table] | None = None,
) -> Check:
    if name not in REGISTRY:
        raise KeyError(f"no generic check {name!r} (have: {', '.join(sorted(REGISTRY))})")
    function = REGISTRY[name]
    if name == "membership":
        return function(rows, scope, options, tables or {})
    return function(rows, scope, options)
