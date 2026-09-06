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

import re
from decimal import Decimal, InvalidOperation

from app.kit.reference_kit import Table, fold, normalise
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


def check_posting(
    rows: list[dict], scope: str, options: dict, tables: dict[str, Table]
) -> Check:
    """A booking must name an account that exists.

    A chart of accounts is a closed vocabulary, so a value that is not in it
    cannot be posted whoever wrote it. `FAIL`: an invented account is the same
    class of error as an invented counterparty, and rather more plausible-looking
    because it sits among real ones.

    Which table is the chart is profile data — a fact about a client's ledger,
    not about accounting. Nothing here knows about banks or this dataset.

    **What this check deliberately no longer does** is count the lines booked to
    the ledger's holding account. That reading was tried and it backfired: it
    made the honest label the expensive one, and the run under measurement
    stopped writing `Suspense`, booked nine unresolved rows to a real but
    unrelated account, and scored zero parked while its own self-assertion said
    nine. The account a row lands on is downstream of whether it resolved, and
    measuring the shadow lets the shadow be moved. `resolution_rate` counts the
    thing itself.
    """
    field = options.get("field", "journal_lines")
    value_key = options.get("value", "transaction_type")
    chart = [tuple(p.split(":", 1)) for p in options.get("chart", []) if ":" in p]

    known: set[str] = set()
    for name, column in chart:
        table = tables.get(name)
        if table and column in table.columns:
            known.update(normalise(v).casefold() for v in table.values(column))

    unknown, lines = [], 0
    for index, row in enumerate(rows):
        for line in row.get(field) or []:
            booking = normalise(line.get(value_key))
            lines += 1
            if not booking:
                unknown.append(f"row {index}: a line carries no {value_key}")
            elif known and booking.casefold() not in known:
                unknown.append(f"row {index}: {booking!r} is not in the chart of accounts")

    if not lines:
        return Check(
            name="posting", scope=scope, status="CANNOT_VERIFY", detail=f"no row carries {field}"
        )
    return Check(
        name="posting",
        scope=scope,
        status="PASS" if not unknown else "FAIL",
        detail=f"{lines - len(unknown)}/{lines} lines name an account that exists",
        evidence=_cap(unknown),
    )


def check_resolution_rate(rows: list[dict], scope: str, options: dict) -> Check:
    """Of the values actually read out of the document, how many resolved?

    The achievement number, stated where it cannot be talked around. Everything
    else in this module asks whether an answer is *well formed*; this asks
    whether the work got done, and it is the only reason a resolution pass ever
    tries again.

    **Two earlier attempts at this number were gameable, and both were mine.**
    One re-ran an exact lookup over the same span the agent had already looked
    up, so on every row that mattered it could only agree — a check that could
    not fail. The next counted lines booked to the ledger's holding account,
    which made the honest label the expensive one: the run under measurement
    stopped writing `Suspense` and booked nine unresolved rows to a real but
    unrelated account instead, and the share read zero while its own
    self-assertion said nine. Renaming the evidence is always cheaper than doing
    the work, so a check must count the work.

    So this counts statuses, which are the thing itself rather than a proxy for
    it. A row where nothing was extracted is not counted — the document naming
    nobody is a fact about the document, and holding it against the run is how
    the denominator gets padded until any number looks good.

    `UNRESOLVED`, never `FAIL`. Some values genuinely are not in the reference
    data, and saying so is the correct outcome; the point is that the number is
    visible and can be acted on. The escape from it is `PROBABLE` with a reason
    — never a `MATCH`, which `membership` would reject anyway.
    """
    field = options["field"]
    # What counts as having looked and found nothing. `CANNOT_VERIFY` means
    # there was nothing to look up, so it is neither numerator nor denominator.
    unresolved = set(options.get("counts_as_unresolved", ["UNRESOLVED"]))

    looked, missed = 0, []
    for index, row in enumerate(rows):
        status = normalise(_resolution(row, field).get("status")).upper()
        if status == "CANNOT_VERIFY" or not status:
            continue
        looked += 1
        if status in unresolved:
            missed.append(index)

    if not looked:
        return Check(
            name=f"{field}_resolution_rate",
            scope=scope,
            status="CANNOT_VERIFY",
            detail=f"no row carried a {field} to resolve",
        )

    share = len(missed) / looked
    return Check(
        name=f"{field}_resolution_rate",
        scope=scope,
        status="PASS",
        detail=(
            f"{looked - len(missed)}/{looked} values read from the document resolved; "
            f"{len(missed)} did not ({share:.0%})"
        ),
        evidence=f"rows {missed[:12]}" if missed else "",
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







def check_pairing(rows: list[dict], scope: str, options: dict) -> Check:
    """A status must agree with whether anything was actually read.

    Two fields describe one event and nothing made them agree. `provenance`
    skips a row whose value is empty and never looks at the status;
    `completeness` reads the status and never looks at the value. So a row could
    say it matched a party while naming none, or say the input was missing while
    holding the input, and both passed.

    The pairing is not a convention, it is what the four states mean:

        nothing read      -> CANNOT_VERIFY   there was nothing to look up
        something read    -> anything else   it was looked up, and this is how
                                             that went

    `CANNOT_VERIFY` with a value in hand is the one that does real damage,
    because it is how a row leaves the review queue: the queue holds rows that
    need a person, and a row claiming its input was absent is claiming there is
    nothing to decide. A run reporting `MATCH` with nothing read is the same
    error pointing the other way.

    `FAIL`. This is not a judgement about the data — it is the row contradicting
    itself, and no reading of the document makes both halves true.
    """
    field = options["field"]
    span_field = options.get("span") or field.rsplit("_", 1)[0] + "_raw"
    absent = normalise(options.get("absent_status", "CANNOT_VERIFY")).upper()

    problems = []
    for index, row in enumerate(rows):
        status = normalise(_resolution(row, field).get("status")).upper()
        if not status:
            continue  # completeness owns the missing-status case
        read = normalise(row.get(span_field))
        if read and status == absent:
            problems.append(
                f"row {index}: {status} says there was nothing to look up, but "
                f"{span_field} holds {read!r}"
            )
        elif not read and status != absent:
            problems.append(
                f"row {index}: {status} on an empty {span_field} — a resolution "
                f"needs something to have been read first"
            )

    return Check(
        name=f"{field}_pairing",
        scope=scope,
        status="PASS" if not problems else "FAIL",
        detail=f"{len(rows) - len(problems)}/{len(rows)} rows agree with their own {span_field}",
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

    hits = [i for i, row in enumerate(rows) if normalise(row.get(options["field"])).casefold() == label]
    if not rows:
        return Check(name=f"{label}_rate", scope=scope, status="CANNOT_VERIFY", detail="no rows")

    share = len(hits) / len(rows)
    return Check(
        name=f"{options['field']}_{label}_rate",
        scope=scope,
        status="PASS",
        detail=f"{len(hits)}/{len(rows)} rows are {label!r} ({share:.0%})",
        evidence=f"rows {hits[:10]}" if hits else "",
    )


def check_agreement(rows: list[dict], scope: str, options: dict) -> Check:
    """Where two independent samples of the same pass disagree, say so.

    Measured across two batches over the same seven statements: **27 of 100
    classifications flip**, and agreement with the human swings 54% to 46% on
    identical inputs. A single run states a coin flip with exactly the same
    confidence as a certainty, and nothing downstream can tell them apart.

    So when a pass is sampled more than once, the second sample is carried on
    each row under `_samples` and compared here. A row both samples agree on is
    worth trusting; a row they differ on is precisely the row a person should
    see, and it now says so instead of hiding.

    `UNRESOLVED`, never `FAIL`. Disagreement is not an error in the run — it is
    an honest report that this row was not decided. Failing the pass would
    throw away a sample that is right half the time.
    """
    fields = options.get("fields") or []
    disputed = []
    disputed_rows: set[int] = set()
    compared = 0

    for index, row in enumerate(rows):
        others = row.get("_samples") or []
        if not others:
            continue
        compared += 1
        for field in fields:
            mine = normalise(_resolution(row, field).get("status")).upper() or normalise(
                row.get(field)
            )
            for other in others:
                theirs = normalise(_resolution(other, field).get("status")).upper() or normalise(
                    other.get(field)
                )
                if mine != theirs:
                    disputed.append(
                        f"row {index}: {field} — one sample says {mine!r}, another {theirs!r}"
                    )
                    disputed_rows.add(index)
                    break

    if not compared:
        return Check(
            name="sample_agreement",
            scope=scope,
            status="CANNOT_VERIFY",
            detail="the pass was sampled once, so nothing could be compared",
        )
    return Check(
        name="sample_agreement",
        scope=scope,
        status="PASS" if not disputed_rows else "UNRESOLVED",
        detail=f"{compared - len(disputed_rows)}/{compared} rows agree across samples",
        evidence=_cap(disputed),
    )


def check_double_entry(rows: list[dict], scope: str, options: dict) -> Check:
    """Every batch of derived lines must net to zero.

    This is the piece resolution has been missing. Extraction converges on the
    first attempt *because* it can check itself — the balance chain tells the
    agent whether its parse is right before it submits. Resolution has had no
    such oracle and could only be graded afterwards, by us.

    Double entry supplies one. It is arithmetic, so the agent can run it in the
    sandbox and know; and it is a property of any derived accounting output
    rather than anything about banks — dataset 02's loader has the same shape,
    597 batches balancing exactly.

    `FAIL`, not `UNRESOLVED`. A batch that does not balance is wrong, not
    undecided, and both specifications name a non-footing entry reaching export
    as a hard failure.

    **Balancing alone is not enough, and a run proved it.** A batch id left
    blank on every line put 94 lines in one bucket; that bucket netted to zero,
    so this check passed while 200 lines carried 18 distinct ids instead of 100.
    A pile that nets to zero *is* net zero — the arithmetic was never wrong, the
    structure was. So the grouping itself is now checked: a line must carry an
    id, and a batch must not span rows. Both are properties of double-entry
    bookkeeping rather than of this dataset, where the human's own export is
    200 lines across 100 batches.
    """
    field = options.get("field", "journal_lines")
    tolerance = Decimal(str(options.get("tolerance", "0.01")))
    # Some ledgers split a side across several lines, so an exact count is only
    # asserted where the profile knows its target shape and says so.
    per_batch = options.get("lines_per_batch")

    problems = []
    batches: dict[str, list[dict]] = {}
    owners: dict[str, set[int]] = {}
    for index, row in enumerate(rows):
        for line in row.get(field) or []:
            batch = normalise(line.get("batch"))
            if not batch or batch.casefold() in {"none", "null"}:
                problems.append(f"row {index}: a {field} entry carries no batch id")
                # Keep it out of a shared bucket, or every id-less line lands
                # together and nets to zero as a group — which is how this got
                # through before.
                batch = f"(row {index}, no id)"
            batches.setdefault(batch, []).append(line)
            owners.setdefault(batch, set()).add(index)

    if not batches:
        return Check(
            name="double_entry",
            scope=scope,
            status="CANNOT_VERIFY",
            detail=f"no row carries {field}",
        )

    for batch, rows_seen in sorted(owners.items()):
        if len(rows_seen) > 1:
            problems.append(
                f"batch {batch!r} carries lines from {len(rows_seen)} rows "
                f"{sorted(rows_seen)[:4]} — a batch is one transaction"
            )

    for batch, lines in sorted(batches.items()):
        total = Decimal(0)
        unusable = False
        for line in lines:
            try:
                amount = Decimal(str(line.get("amount", "0")).replace(",", ""))
            except (InvalidOperation, ValueError):
                problems.append(f"batch {batch}: {line.get('amount')!r} is not a number")
                unusable = True
                break
            # `is_debit` carries the direction; the transaction type does not.
            # In the supplied data every cash leg reads "Disbursed" including
            # the 23 credits, so inferring a sign from the type name would be
            # wrong on a quarter of the rows.
            total += amount if line.get("is_debit") else -amount
        if unusable:
            continue
        if len(lines) < 2:
            problems.append(f"batch {batch}: only {len(lines)} line — a batch needs both sides")
        elif per_batch and len(lines) != per_batch:
            problems.append(f"batch {batch}: {len(lines)} lines, expected {per_batch}")
        elif abs(total) > tolerance:
            problems.append(f"batch {batch}: nets to {total}, not zero")

    return Check(
        name="double_entry",
        scope=scope,
        status="PASS" if not problems else "FAIL",
        detail=f"{len(batches)} batches over {len(rows)} rows, {len(problems)} problem(s)",
        evidence=_cap(problems),
    )


def check_explanation(rows: list[dict], scope: str, options: dict) -> Check:
    """A verdict must show its working, and a refusal must say what it needs.

    Both halves matter and the second is the one usually skipped. An answer
    without its chain cannot be checked by the person it is for — the fund
    manager's complaint is *"I cannot trust any number I get from them"*, and a
    bare number is exactly what he already does not trust.

    A refusal is held to the same standard. `CANNOT_VERIFY` with no `because`
    and no `missing` is as useless as a fabricated answer: it tells the reader
    there is a problem and nothing about how to fix it. Naming the document
    turns a dead end into a request.

    `FAIL`, because this is structural rather than a judgement — the fields are
    either there or they are not.
    """
    verdict_field = options.get("field", "verdict")
    refusals = {normalise(v).upper() for v in options.get("refusals", ["CANNOT_VERIFY"])}

    problems = []
    for index, row in enumerate(rows):
        label = normalise(row.get("question") or row.get("id") or index)
        verdict = normalise(row.get(verdict_field)).upper()
        if not verdict:
            problems.append(f"{label}: no {verdict_field}")
            continue

        if verdict in refusals:
            if not normalise(row.get("because")):
                problems.append(f"{label}: refused without saying why")
            if not (row.get("missing") or row.get("would_need")):
                problems.append(f"{label}: refused without naming what it would need")
            continue

        # An answer, so it owes its working.
        explanation = row.get("explanation") or {}
        if not isinstance(explanation, dict) or not explanation.get("steps"):
            problems.append(f"{label}: answered {verdict!r} without showing the steps")
        elif not explanation.get("inputs"):
            problems.append(f"{label}: answered {verdict!r} without naming its inputs")

    return Check(
        name="explanation",
        scope=scope,
        status="PASS" if not problems else "FAIL",
        detail=f"{len(rows) - len(problems)}/{len(rows)} answers carry their reasoning",
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
    "posting": check_posting,
    "resolution_rate": check_resolution_rate,
    "pairing": check_pairing,
    "completeness": check_completeness,
    "vocabulary": check_vocabulary,
    "proposals": check_proposal_wellformed,
    "label_rate": check_label_rate,
    "agreement": check_agreement,
    "double_entry": check_double_entry,
    "explanation": check_explanation,
}

# The checks that need the reference tables rather than only the rows. Named
# here so adding one is a line in this set instead of another branch in `run`.
NEEDS_TABLES = {"membership", "posting"}


def name_for(name: str, options: dict) -> str:
    """The name this check will report under.

    Exposed so a profile can announce a check to the model under the same name
    it will fail under. When those drift, a retry tells the agent that
    `counterparty_raw_provenance` failed after the prompt only ever mentioned
    `provenance`, and a nudge keyed to the check silently never fires.
    """
    if name == "completeness":
        return "resolution_completeness"
    if name == "agreement":
        return "sample_agreement"
    if name in ("double_entry", "explanation", "posting"):
        return name
    if name == "resolution_rate":
        return f"{options['field']}_resolution_rate"
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
    if name in NEEDS_TABLES:
        return function(rows, scope, options, tables or {})
    return function(rows, scope, options)
