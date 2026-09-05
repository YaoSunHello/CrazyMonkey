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
# input needed to decide was not in this run; `PROBABLE` is a sourced proposal
# for a person to accept, never a resolution.
STATUSES = {"MATCH", "PROBABLE", "UNRESOLVED", "FAIL", "CANNOT_VERIFY"}

# Statuses whose `matched_name` must exist verbatim in a declared table. A
# proposal is held to the same sourcing standard as a match — what makes it a
# proposal is that the *equivalence* is judgement, not that the target is vague.
NAMES_A_TARGET = {"MATCH", "PROBABLE"}


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
        if status not in NAMES_A_TARGET:
            continue

        key = normalise(resolution.get("matched_name") or resolution.get("matched") or "")
        table_name = normalise(resolution.get("table"))
        if not key:
            problems.append(f"row {index}: {status} with nothing matched")
        elif not present(table_name, key):
            where = f"table {table_name!r}" if table_name else "any declared table"
            problems.append(f"row {index}: {status} on {key!r}, but it is not in {where}")

    summary = " · ".join(f"{n} {s}" for s, n in counts.items() if n)
    return Check(
        name=f"{field}_membership",
        scope=scope,
        status="PASS" if not problems else "FAIL",
        detail=summary or "no resolutions declared",
        evidence=_cap(problems),
    )


def check_span_plausibility(rows: list[dict], scope: str, options: dict) -> Check:
    """An extracted name should look like a name, not like a sentence.

    This exists because of a failure the other checks could not see. The
    extractor captured `NI ABF I, SCSP FOR PURCHASE 100PER OF ACC INT, IN
    CEPHALUS BIOGAS 001 LTD PREMIUM, ACCRUED INTEREST` — eighteen words —
    and every check passed: provenance was satisfied because the span *is* a
    literal substring, and membership honestly reported UNRESOLVED. So the run
    was accepted on attempt one with a quarter of its rows quietly unresolved,
    and the retry that would have fixed it never fired.

    `UNRESOLVED`, never `FAIL`. A long span is suspicious, not provably wrong,
    and failing a pass on a heuristic would blur the line between the checks
    that are exact and the checks that advise. It is enough that it shows in
    the report and reaches the next attempt's prompt.
    """
    field = options["field"]
    limit = int(options.get("max_words", 8))
    stops = {normalise(s).casefold() for s in options.get("stop_words", [])}

    problems = []
    seen = 0
    for index, row in enumerate(rows):
        value = normalise(row.get(field))
        if not value:
            continue
        seen += 1
        words = value.split()
        if len(words) > limit:
            problems.append(f"row {index}: {len(words)} words — {value[:60]!r}")
        elif stops and any(w.casefold().strip(".,") in stops for w in words):
            hit = next(w for w in words if w.casefold().strip(".,") in stops)
            problems.append(f"row {index}: contains {hit!r}, which reads as purpose text — {value[:50]!r}")

    if not seen:
        return Check(
            name=f"{field}_span",
            scope=scope,
            status="CANNOT_VERIFY",
            detail=f"no row claims a {field}",
        )
    return Check(
        name=f"{field}_span",
        scope=scope,
        status="PASS" if not problems else "UNRESOLVED",
        detail=f"{seen - len(problems)}/{seen} {field} values look like a name",
        evidence=_cap(problems),
    )


def check_proposal_wellformed(rows: list[dict], scope: str, options: dict) -> Check:
    """A `PROBABLE` must name a real candidate and say why it is probable.

    Membership already proves the proposed target exists. This adds the part
    that keeps a proposal honest rather than a guess in a costume: a reason,
    and a confidence that admits to being one.

    `FAIL`, unlike the span check, because this is not a judgement call — a
    proposal without a reason is malformed, and shipping it would let
    similarity quietly become resolution.
    """
    field = options["field"]
    problems = []
    proposals = 0

    for index, row in enumerate(rows):
        resolution = _resolution(row, field)
        if normalise(resolution.get("status")).upper() != "PROBABLE":
            continue
        proposals += 1
        if not normalise(resolution.get("why")):
            problems.append(f"row {index}: PROBABLE with no reason given")
        confidence = resolution.get("confidence")
        if not isinstance(confidence, (int, float)):
            problems.append(f"row {index}: PROBABLE with no confidence")
        elif not 0 < float(confidence) < 1:
            problems.append(f"row {index}: confidence {confidence} — a proposal is never 0 or 1")

    if not proposals:
        return Check(
            name=f"{field}_proposals",
            scope=scope,
            status="PASS",
            detail="no proposals offered",
        )
    return Check(
        name=f"{field}_proposals",
        scope=scope,
        status="PASS" if not problems else "FAIL",
        detail=f"{proposals - len(problems)}/{proposals} proposals carry a reason and a confidence",
        evidence=_cap(problems),
    )


def check_label_rate(rows: list[dict], scope: str, options: dict) -> Check:
    """A label that should be rare must actually be rare.

    The fallback label is the one that quietly absorbs everything the model
    could not decide. One run shipped `Review` on nine of eighteen rows with
    every other check green — technically a declared label, and useless to the
    person who then has to read half the statement by hand.

    The expected rate is profile data, because what counts as rare is a fact
    about the use case and not about the engine.
    """
    label = normalise(options["label"]).casefold()
    ceiling = float(options.get("max_share", 0.2))

    hits = [i for i, row in enumerate(rows) if normalise(row.get(options["field"])).casefold() == label]
    if not rows:
        return Check(name=f"{label}_rate", scope=scope, status="CANNOT_VERIFY", detail="no rows")

    share = len(hits) / len(rows)
    ok = share <= ceiling
    return Check(
        name=f"{options['field']}_{label}_rate",
        scope=scope,
        status="PASS" if ok else "UNRESOLVED",
        detail=f"{len(hits)}/{len(rows)} rows are {label!r} ({share:.0%}, expected at most {ceiling:.0%})",
        evidence="" if ok else f"rows {hits[:10]} — a fallback label absorbing this much is a decision not made",
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
    "span": check_span_plausibility,
    "proposals": check_proposal_wellformed,
    "label_rate": check_label_rate,
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
    if name == "label_rate":
        return f"{field}_{normalise(options.get('label', '')).casefold()}_rate"
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
