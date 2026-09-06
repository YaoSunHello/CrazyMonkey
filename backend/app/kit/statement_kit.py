"""Toolkit uploaded into the sandbox for the agent to build on.

This is the same split agent-arena uses: we supply the mechanics, the agent
supplies the judgement. Here that means we hand over PDF access and the
output format, and the agent decides which lines are transactions, which
column each value belongs to, and how narratives attach to rows.

It also keeps the agent's own file short. A parser that has to do its own
pdfplumber plumbing runs to a hundred lines, and emitting that as a single
JSON tool argument is exactly how a generation hits its token ceiling and
leaves malformed arguments behind.

Available inside the sandbox as `kit`:

    import kit
    for line in kit.lines(page=1):
        print(line.text, [w["x0"] for w in line.words])
        print(line.between(35, 116))        # str  — one column's text
        print(line.words_between(35, 116))  # list[dict] — the words themselves
    kit.write_result(rows)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import pdfplumber

PDF = os.environ.get("KIT_PDF", "/data/statement.pdf")
OUT = os.environ.get("KIT_OUT", "/work/result.json")

# Words sharing a baseline within this many points are one visual line. A
# transaction's bank reference sits a fraction of a point off the rest of its
# row, so a tolerance of zero splits single transactions in two.
# What the agent may use. See the note in `reference_kit` — the engine renders
# this list into the prompt, so the signatures cannot drift from the code.
__all__ = ["page_count", "lines", "all_lines", "text", "column_positions", "write_result"]

LINE_TOLERANCE = 1.5


@dataclass
class Line:
    """One visual line of the statement."""

    page: int
    top: float
    words: list[dict] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(w["text"] for w in self.words)

    def words_between(self, x0: float, x1: float) -> list[dict]:
        """The word dicts whose left edge falls in [x0, x1), left to right.

        Use this when you need the words themselves — their `x0`, or to join
        them your own way. For the plain text of a column, `between` is
        shorter.
        """
        return [w for w in self.words if x0 <= w["x0"] < x1]

    def between(self, x0: float, x1: float) -> str:
        """The text of one column, **already joined into a string**.

        Returns a `str`, not a list of words — `words_between` is the one that
        returns the dicts. Writing `" ".join(w["text"] for w in
        line.between(a, b))` iterates the *characters* of this string and
        raises `TypeError: string indices must be integers`.
        """
        return " ".join(w["text"] for w in self.words_between(x0, x1))

    def starts_with(self, prefix: str) -> bool:
        return self.text.startswith(prefix)


def page_count() -> int:
    with pdfplumber.open(PDF) as pdf:
        return len(pdf.pages)


def lines(page: int) -> list[Line]:
    """Every visual line on a page, top to bottom, words left to right.

    Pages are **1-based**: the first page is `lines(1)`, and the last is
    `lines(page_count())`. Passing 0 raises rather than returning something
    surprising — an ambiguous index here previously cost callers a dozen lines
    of defensive probing, which is worse than a clear error.
    """
    total = page_count()
    if not 1 <= page <= total:
        raise ValueError(f"page must be between 1 and {total} (pages are 1-based), got {page}")
    with pdfplumber.open(PDF) as pdf:
        words = pdf.pages[page - 1].extract_words()
    grouped: list[Line] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if grouped and abs(word["top"] - grouped[-1].top) <= LINE_TOLERANCE:
            grouped[-1].words.append(word)
        else:
            grouped.append(Line(page=page, top=word["top"], words=[word]))
    for line in grouped:
        line.words.sort(key=lambda w: w["x0"])
    return grouped


def all_lines() -> list[Line]:
    return [line for page in range(1, page_count() + 1) for line in lines(page)]


def text(page: int) -> str:
    with pdfplumber.open(PDF) as pdf:
        return pdf.pages[page - 1].extract_text() or ""


def column_positions(page: int = 1) -> dict[str, float]:
    """Left edge of each column, taken from the page's own header row.

    Returns {} if the header is not on this page. Reading the positions from
    the header rather than hard-coding them means the parse survives a
    statement laid out slightly differently.
    """
    headers = {
        "bank_reference": "Bank",
        "customer_reference": "Customer",
        "trn_type": "TRN",
        "value_date": "Value",
        "credit": "Credit",
        "debit": "Debit",
        "balance": "Balance",
        "time": "Time",
        "post_date": "Post",
    }
    for line in lines(page):
        by_text = {w["text"]: w["x0"] for w in line.words}
        if all(word in by_text for word in headers.values()):
            return {name: by_text[word] for name, word in headers.items()}
    return {}


def write_result(rows: list[dict]) -> str:
    """Write result.json in the shape the verifier expects."""
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump({"rows": rows}, handle, indent=2)
    return f"wrote {len(rows)} rows to {OUT}"
