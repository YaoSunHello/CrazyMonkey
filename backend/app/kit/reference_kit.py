"""Toolkit for a resolution pass: the rows already extracted, and the lists to
resolve them against.

Uploaded into the sandbox as `kit`, the same way `statement_kit` is for the
extraction pass. It reads JSON and uses only the standard library, because the
sandbox runs model-written code and is deliberately given nothing else.

The host imports `Table` and `normalise` from here rather than keeping its own
copy. One implementation means a lookup that succeeds in the sandbox cannot
fail in the verifier for want of the same whitespace rule — and that divergence
is exactly the class of bug this pipeline exists to catch, so it would be a poor
place to introduce one.

Available inside the sandbox:

    import kit
    for row in kit.rows():                 # what the extraction pass produced
        ...
    kit.tables()                           # names of the lists available
    t = kit.table("related_parties")
    t.contains("Related Party", name)      # exact, then case-insensitive
    t.find("Related Party", name)          # the whole row, or None
    t.candidates("Related Party", name)    # near matches, for a human to judge
    kit.write_result(rows)
"""

from __future__ import annotations

import difflib
import math
import json
import os
import unicodedata
from dataclasses import dataclass, field

# What the agent may use, and therefore what the engine advertises in the prompt.
#
# Declared here rather than written out in a profile, because a prompt that
# describes an API by hand drifts from it. Two such drifts cost real rounds:
# `write_assertions` was asked for without its shape, so a run passed a dict of
# counts instead of a list of claims and the call silently did nothing; and
# `candidates` was advertised with a parameter name it does not have, so every
# account paid a round to discover the TypeError. The signature is a fact about
# this code, so this code states it.
#
# `weigh` and `resemblance` are deliberately absent: they exist to rank
# `candidates` and are not something to call directly.
__all__ = [
    "rows",
    "tables",
    "table",
    "lookup",
    "candidates",
    "narrative_span",
    "variants",
    "trim_to",
    "normalise",
    "fold",
    "compact",
    "batches_balance",
    "questions",
    "write_result",
    "write_assertions",
]

TABLES = os.environ.get("KIT_TABLES", "/data/tables.json")
ROWS = os.environ.get("KIT_ROWS", "/data/rows.json")
OUT = os.environ.get("KIT_OUT", "/work/result.json")
ASSERTIONS = os.environ.get("KIT_ASSERTIONS", "/work/assertions.json")
QUESTIONS = os.environ.get("KIT_QUESTIONS", "/data/questions.json")


def normalise(value: object) -> str:
    """One string form for a cell, so lookups survive the source's whitespace.

    The supplied workbook has sheet and column names with trailing spaces, and
    cells that begin with a literal tab. Collapsing all runs of whitespace to a
    single space and trimming the ends handles every case seen so far, and does
    it in one place instead of at each call site.
    """
    if value is None:
        return ""
    return " ".join(str(value).split())


def fold(text: object) -> str:
    """The form two strings are compared in. Case and accents removed.

    Measured, not guessed: comparing narratives to master lists **case-
    sensitively recovers nothing at all**, because the bank writes in capitals
    and the lists are mixed case. Accents matter for the same reason — the
    narrative says `NI GMF II COOPERATIEF U.A.` and the list says
    `NI GMF II Coöperatief U.A.`, which `casefold` alone still keeps apart, and
    that difference alone hides five rows.

    Used for lookup keys only. Everything displayed to a person keeps the form
    the document actually used, because that is what they will be checking
    against.
    """
    decomposed = unicodedata.normalize("NFKD", normalise(text))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def compact(text: object) -> str:
    """Folded, with every non-alphanumeric removed.

    The last-resort comparison key. It survives the document's inserted
    commas, full stops and brackets, which is what lets `NORDVIK INFRAS,
    TRUCTURE V SCSP EUR)` be recognised as the same string as
    `Nordvik Infrastructure V SCSp`.

    Only ever a *comparison* key. Nothing is displayed in this form and no
    matched value is returned in it — the name handed onward is always the one
    the reference list holds.
    """
    return "".join(c for c in fold(text) if c.isalnum())


def variants(text: object, wrapper: str = ",") -> list[str]:
    """Every plausible reading of a value the source document line-wrapped.

    Fixed-width documents break without regard for word boundaries and mark it
    with a character — this bank uses a comma. The same marker appears in two
    different roles and they need opposite repairs:

        NORDVIK INFRASTR, UCTURE V SCSP   ->  NORDVIK INFRASTRUCTURE V SCSP
        NI ABF I, SCSP                    ->  NI ABF I SCSP

    One joins across the break, the other only drops the comma. Telling them
    apart needs a dictionary, and a heuristic that guessed would be wrong about
    a third of the time.

    So do not guess: return the readings, in order, and let the **lookup**
    decide. Whichever one is actually in a reference list is the right one, and
    that is a verifiable answer rather than an inference. Anything that matches
    nothing stays unresolved, which is the correct outcome.

    Generic to any fixed-width source, which is most bank and administrator
    output.
    """
    base = normalise(text)
    if not base:
        return []
    seen, out = set(), []
    for candidate in (
        base,                                                     # as written
        " ".join(base.replace(wrapper, " ").split()),             # break was between words
        " ".join(base.replace(wrapper + " ", "").split()),        # break was mid-word
        " ".join(base.replace(wrapper, "").split()),              # both, for a trailing marker
    ):
        stripped = candidate.strip(" .")
        if stripped and stripped not in seen:
            seen.add(stripped)
            out.append(stripped)
    return out


def trim_to(text: object, markers: list[str], keep: bool = True) -> str:
    """Cut a string at the first of `markers`, keeping the marker by default.

    A general string operation — it knows nothing about companies. The markers
    are supplied by the caller, which is how a document convention stays in the
    profile that declares it rather than being compiled into the toolkit.

    Matching is case-insensitive and on whole words, so `LTD` does not fire
    inside `LTDA`.
    """
    haystack = normalise(text)
    if not haystack or not markers:
        return haystack

    words = haystack.split()
    wanted = {normalise(m).casefold().strip(".") for m in markers if normalise(m)}
    for index, word in enumerate(words):
        if word.casefold().strip(".,)") in wanted:
            return " ".join(words[: index + 1] if keep else words[:index])
    return haystack


@dataclass
class Table:
    """One reference list. Named columns, rows as dicts, indexed on demand."""

    name: str
    columns: list[str]
    rows: list[dict] = field(default_factory=list)
    _index: dict = field(default_factory=dict, repr=False)

    def _for(self, column: str) -> dict:
        if column not in self._index:
            if column not in self.columns:
                raise KeyError(
                    f"table {self.name!r} has no column {column!r} "
                    f"(has: {', '.join(self.columns)})"
                )
            built: dict = {}
            for row in self.rows:
                key = row.get(column, "")
                if key:
                    built.setdefault(fold(key), row)
            self._index[column] = built
        return self._index[column]

    def contains(self, column: str, value: str) -> bool:
        return fold(value) in self._for(column)

    def find(self, column: str, value: str) -> dict | None:
        """The row this value names, or None. Case- and accent-insensitive.

        Accents are folded because the document and the list disagree about
        them: the narrative writes `NI GMF II COOPERATIEF U.A.` and the list
        holds `NI GMF II Coöperatief U.A.`. Case-folding alone still keeps
        those apart, and that difference on its own hid five rows.

        Never fuzzy beyond that. A near match is a candidate for a person, not
        an answer: 52 of the 100 rows in the supplied data genuinely have no
        counterparty, and resolving those to the closest name would be the
        worst thing this pipeline could do. For a near miss, use `candidates`
        and propose it — see the PROBABLE status.
        """
        return self._for(column).get(fold(value))

    def values(self, column: str) -> list[str]:
        return sorted({row[column] for row in self.rows if row.get(column)})

    def candidates(self, column: str, value: str, limit: int = 5) -> list[str]:
        """Near matches, ranked, for a person to judge.

        Compared in folded form, or nothing is ever near: the document shouts
        in capitals and the lists are mixed case, so `NI V KALVIK TOPCO LTD.`
        scored below the threshold against `NI V Kalvik Topco Limited` and this
        returned an empty list exactly when it was most needed.

        The names returned are the list's own. Offer one as a `PROBABLE` with a
        reason; never apply one silently.
        """
        pool = self.values(column)
        by_fold = {fold(entry): entry for entry in pool}
        near = difflib.get_close_matches(fold(value), list(by_fold), n=limit, cutoff=0.6)
        return [by_fold[match] for match in near]

    def to_json(self) -> dict:
        return {"name": self.name, "columns": self.columns, "rows": self.rows}

    @classmethod
    def from_json(cls, payload: dict) -> Table:
        return cls(
            name=payload.get("name", ""),
            columns=list(payload["columns"]),
            rows=list(payload["rows"]),
        )


def narrative_span(narrative: object, name: object) -> str:
    """The slice of `narrative` that `name` corresponds to, exactly as written.

    A resolution has to survive the provenance check, which asks whether the
    value is a literal substring of the document. But the value you *matched*
    on has been folded and unwrapped, so echoing it back fails. This walks the
    narrative and returns the original characters.

    Thirteen of fourteen generated scripts hand-rolled some version of this and
    each got a slightly different answer, which is reason enough for it to live
    here once.

    Returns "" when the name is not present, which is the honest answer — do
    not fall back to the folded form, because that is how an invented value
    reaches the output.
    """
    text = normalise(narrative)
    target = compact(name)
    if not text or not target:
        return ""

    # Walk forward, compacting as we go, so the document's inserted commas and
    # brackets do not stop a name being recognised.
    for start in range(len(text)):
        if not text[start].isalnum():
            continue
        for end in range(start, len(text)):
            seen = compact(text[start : end + 1])
            if len(seen) > len(target):
                break
            if not target.startswith(seen):
                break
            if seen == target:
                return text[start : end + 1].strip(" ,.")
    return ""


def _words(text: object) -> set[str]:
    """Comparable words. Whitespace-separated so a dotted abbreviation stays whole."""
    return {w for w in (compact(part) for part in normalise(text).split()) if w}


def weigh(pools: list, source: dict[str, Table] | None = None):
    """How much each word identifies, learned from the reference data itself.

    Two names sharing three words look alike until you notice which three. In
    one mounted set `ni` is in 1855 of 2726 names and `scsp` in hundreds, while
    `azurite` is in one — so a comparison that counts words equally is mostly
    measuring how common a naming convention is. That single mistake caused two
    separate failures: near-miss suggestions that offered a different fund, and
    a "this is the account holder" test that fired on a real counterparty
    because it shared the fund-family prefix with the account label.

    Inverse document frequency over whatever this run mounts, so it adapts to a
    different client's conventions instead of assuming these. Returns a function
    from word to weight; unknown words score as if they appeared once, which is
    the right default for something the reference data has never seen.
    """
    known = _load() if source is None else source
    frequency: dict[str, int] = {}
    total = 0
    for name, column in pools:
        table = known.get(name)
        if table is None or column not in table.columns:
            continue
        for entry in table.values(column):
            total += 1
            for word in _words(entry):
                frequency[word] = frequency.get(word, 0) + 1

    ceiling = math.log(total + 1) if total else 1.0
    return lambda word: math.log((total + 1) / (frequency.get(word, 0) + 1)) if total else 1.0, ceiling


def resemblance(left: object, right: object, weight) -> float:
    """How much of what identifies `left` is also in `right`.

    Deliberately one-directional, because the two callers ask different
    questions: whether a name *is* another one, and whether a proposal has
    quietly added an entity. Take the minimum of both directions for the
    symmetric question.
    """
    mine, theirs = _words(left), _words(right)
    if not mine:
        return 0.0
    total = sum(weight(w) for w in mine) or 1.0
    return sum(weight(w) for w in mine & theirs) / total


def candidates(
    value: object,
    pools: list,
    limit: int = 5,
    source: dict[str, Table] | None = None,
) -> list[dict]:
    """Near misses worth a person's judgement, ranked by what they share.

    The sibling of `lookup`: same pools, same order, but for the case where
    nothing matched exactly and you need to see what is close.

    **Ranked by how much the shared words identify, not by how similar the
    characters are**, and the difference decides whether this is useful. Raw
    character similarity treats every word as equal evidence: against one
    mounted set `ni` appears in 1855 of 2726 names and `scsp` in hundreds, so
    two names sharing only those look alike while differing in the word that
    means something. Asked for near misses on `NI ABF II SCSP`, character
    similarity offered `NI GCF II USD HedgeCo SCSp` — a different fund — and a
    run duly proposed it. Asked about `NI V AZURITE HOLDCO LTD` it returned
    nothing at all, though `NI V Azurite HoldCo Limited` was sitting in the
    reference data.

    Weighting a word by how rare it is across the mounted data fixes both, and
    knows nothing about the data to do it: a word in nearly every name carries
    nearly no information, a word in one name carries almost all of it. The same
    two queries now return the right entry first.

    Scored both directions, so a candidate that *adds* a rare word ranks below
    one that merely spells a word differently — adding `Co-Invest` makes a
    different vehicle, adding a jurisdiction suffix does not.

    Every result is a real entry, and none of them is an answer: `matched_name`
    here is a suggestion for a `PROBABLE` with a reason, never a `MATCH`.
    """
    known = _load() if source is None else source
    weight, _ = weigh(pools, known)

    mine = _words(value)
    if not mine:
        return []

    scored = []
    for name, column in pools:
        table = known.get(name)
        if table is None or column not in table.columns:
            continue
        for entry in table.values(column):
            score = min(resemblance(value, entry, weight), resemblance(entry, value, weight))
            if score:
                scored.append(
                    {"matched_name": entry, "table": name, "column": column,
                     "score": round(score, 3)}
                )
    scored.sort(key=lambda c: -c["score"])
    return scored[:limit]


def lookup(
    value: object,
    pools: list,
    markers: list[str] | None = None,
    source: dict[str, Table] | None = None,
) -> dict | None:
    """Find `value` in the first of `pools` that holds it. Exact only.

    `pools` is a list of `(table_name, column)` in the order to try — the
    caller decides that order, because which list wins is a judgement about the
    domain and not something the toolkit should have an opinion on.

    `source` is where the tables come from. The sandbox leaves it alone and gets
    the file the run mounted; the verifier passes the tables it already holds,
    so that **the check and the agent run the identical function**. That is the
    point: the coverage check's claim is that the agent's own toolkit, given the
    agent's own extracted span, finds something the agent said was not there. A
    second implementation could not make that claim.

    Two repairs are applied before giving up, both mechanical: the value is cut
    at a marker if `markers` are supplied, and each line-wrap reading from
    `variants` is tried. The lookup decides which reading was right, so nothing
    is inferred.

    Returns `{"matched_name", "table", "column", "tried"}` or None. The name
    returned is the one **the list holds**, not the one the document wrote —
    that is the value later stages need.

    Never fuzzy. For a near miss, use `Table.candidates` and propose it as
    PROBABLE with a reason; do not quietly resolve it here.
    """
    text = trim_to(value, markers) if markers else normalise(value)
    tried = variants(text)
    known = _load() if source is None else source

    for candidate in tried:
        for name, column in pools:
            table = known.get(name)
            if table is None or column not in table.columns:
                continue
            row = table.find(column, candidate)
            if row:
                return {
                    "matched_name": row[column],
                    "table": name,
                    "column": column,
                    "tried": tried,
                }

    # Last pass, still exact: compare with punctuation removed, and allow a
    # qualifier the *list* adds that the document never carries. Master lists
    # append a currency or jurisdiction — `NI GMF II Coöperatief U.A. - USD`,
    # `Trentbeck Audit - Lu` — where the narrative names the company alone.
    # The full list value is still what gets returned; the qualifier is only
    # ignored for the purpose of recognising it.
    wanted = {compact(c) for c in tried if compact(c)}
    if not wanted:
        return None
    for name, column in pools:
        table = known.get(name)
        if table is None or column not in table.columns:
            continue
        for entry in table.values(column):
            base = entry.split(" - ")[0] if " - " in entry else entry
            if compact(entry) in wanted or compact(base) in wanted:
                return {
                    "matched_name": entry,
                    "table": name,
                    "column": column,
                    "tried": tried,
                }
    return None


_loaded: dict[str, Table] = {}


def _load() -> dict[str, Table]:
    if not _loaded:
        with open(TABLES, encoding="utf-8") as handle:
            for name, payload in json.load(handle).items():
                _loaded[name] = Table.from_json(payload)
    return _loaded


def tables() -> list[str]:
    return sorted(_load())


def table(name: str) -> Table:
    loaded = _load()
    if name not in loaded:
        raise KeyError(f"no table {name!r} (have: {', '.join(sorted(loaded))})")
    return loaded[name]


def questions() -> list[dict]:
    """The questions this run is asked, and what each one needs to be answered.

    Each carries `requires` — the inputs without which it cannot be answered —
    and `available`, which the engine filled in by checking what was actually
    mounted. Where `available` is false the honest answer is CANNOT_VERIFY
    naming the missing input, and inventing the data instead is the single
    failure both specifications test for by name.

    Returns [] when the profile asks no questions, which is the usual case.
    """
    try:
        with open(QUESTIONS, encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, ValueError):
        return []


def rows() -> list[dict]:
    """The rows the extraction pass produced, verified before they got here."""
    with open(ROWS, encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload["rows"] if isinstance(payload, dict) else payload


def batches_balance(rows: list[dict], field: str = "journal_lines") -> dict:
    """Check your own double entry before you submit. Every batch nets to zero.

    This is the oracle the resolution step has been missing. The extraction step
    converges on its first attempt because the balance chain lets it *know*
    whether its parse is right; resolution has only ever been graded afterwards.
    Build the two journal lines and this tells you, here, whether they hold.

    Returns `{"ok", "batches", "balanced", "problems"}`. Run it, and if `ok` is
    false, fix the rows before writing the result — a rejected attempt costs a
    whole generation, and this costs nothing.

    Direction comes from `is_debit`, never from the transaction type: in this
    data every cash leg reads "Disbursed" including the credits, so a sign
    inferred from the type name is wrong on a quarter of the rows.
    """
    from decimal import Decimal, InvalidOperation

    batches: dict[str, list[dict]] = {}
    for index, row in enumerate(rows):
        for line in row.get(field) or []:
            batches.setdefault(str(line.get("batch", index)), []).append(line)

    problems = []
    for batch, lines in sorted(batches.items()):
        total = Decimal(0)
        for line in lines:
            try:
                amount = Decimal(str(line.get("amount", "0")).replace(",", ""))
            except (InvalidOperation, ValueError):
                problems.append(f"batch {batch}: {line.get('amount')!r} is not a number")
                break
            total += amount if line.get("is_debit") else -amount
        else:
            if len(lines) < 2:
                problems.append(f"batch {batch}: only {len(lines)} line")
            elif abs(total) > Decimal("0.01"):
                problems.append(f"batch {batch}: nets to {total}")

    return {
        "ok": not problems,
        "batches": len(batches),
        "balanced": len(batches) - len(problems),
        "problems": problems,
    }


def write_assertions(claims: list[dict]) -> str:
    """Record what you checked about your own output, and what you found.

    Each claim is `{"name", "holds", "detail"}`. A claim that does not hold
    fails the attempt and its detail reaches the next prompt, so this is worth
    using on anything you are unsure of rather than hoping.

    Two things to be clear about. These are **your** claims, recorded as such —
    they are not the verifier, they are read as your report of what you looked
    at. And they can only ever add a failure: nothing you assert can make an
    attempt pass that the real checks rejected. So there is no advantage in
    claiming something holds when you have not checked it, and real value in
    saying plainly that something does not.
    """
    with open(ASSERTIONS, "w", encoding="utf-8") as handle:
        json.dump(claims, handle, indent=2)
    failing = [c for c in claims if not c.get("holds")]
    return f"recorded {len(claims)} assertions, {len(failing)} not holding"


def write_result(enriched: list[dict]) -> str:
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump({"rows": enriched}, handle, indent=2)
    return f"wrote {len(enriched)} rows to {OUT}"
