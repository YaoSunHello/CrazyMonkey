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
import json
import os
import unicodedata
from dataclasses import dataclass, field

TABLES = os.environ.get("KIT_TABLES", "/data/tables.json")
ROWS = os.environ.get("KIT_ROWS", "/data/rows.json")
OUT = os.environ.get("KIT_OUT", "/work/result.json")


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


def lookup(value: object, pools: list, markers: list[str] | None = None) -> dict | None:
    """Find `value` in the first of `pools` that holds it. Exact only.

    `pools` is a list of `(table_name, column)` in the order to try — the
    caller decides that order, because which list wins is a judgement about the
    domain and not something the toolkit should have an opinion on.

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

    for candidate in tried:
        for name, column in pools:
            table = _load().get(name)
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
        table = _load().get(name)
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


def rows() -> list[dict]:
    """The rows the extraction pass produced, verified before they got here."""
    with open(ROWS, encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload["rows"] if isinstance(payload, dict) else payload


def write_result(enriched: list[dict]) -> str:
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump({"rows": enriched}, handle, indent=2)
    return f"wrote {len(enriched)} rows to {OUT}"
