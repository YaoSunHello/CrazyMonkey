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
                    built.setdefault(key.casefold(), row)
            self._index[column] = built
        return self._index[column]

    def contains(self, column: str, value: str) -> bool:
        return normalise(value).casefold() in self._for(column)

    def find(self, column: str, value: str) -> dict | None:
        """The row this value names, or None. Exact, then case-insensitive.

        Never fuzzy. A near match is a candidate for a person, not an answer:
        52 of the 100 rows in the supplied data genuinely have no counterparty,
        and resolving those to the closest name would be the worst thing this
        pipeline could do.
        """
        return self._for(column).get(normalise(value).casefold())

    def values(self, column: str) -> list[str]:
        return sorted({row[column] for row in self.rows if row.get(column)})

    def candidates(self, column: str, value: str, limit: int = 5) -> list[str]:
        """Near matches, ranked. Offer these with an unresolved row; never apply one."""
        return difflib.get_close_matches(
            normalise(value), self.values(column), n=limit, cutoff=0.6
        )

    def to_json(self) -> dict:
        return {"name": self.name, "columns": self.columns, "rows": self.rows}

    @classmethod
    def from_json(cls, payload: dict) -> Table:
        return cls(
            name=payload.get("name", ""),
            columns=list(payload["columns"]),
            rows=list(payload["rows"]),
        )


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
