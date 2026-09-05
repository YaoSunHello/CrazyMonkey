"""Data shapes shared by the parser, the verifier and the journal builder.

Every number the pipeline emits carries the page and bounding box it was read
from, so a reviewer can be shown the exact place on the statement it came from.
The workbook's own `Process` sheet asks for precisely this: "Spot check rows
against the statements using the Ylookup citation feature."
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class Provenance(BaseModel):
    """Where on the source PDF a value was read from."""

    page: int = Field(description="1-indexed page number")
    x0: float
    top: float
    x1: float
    bottom: float

    def as_citation(self) -> str:
        return f"p{self.page} @ ({self.x0:.0f},{self.top:.0f})-({self.x1:.0f},{self.bottom:.0f})"


class StatementRow(BaseModel):
    """One transaction line from a bank statement.

    Amounts are Decimal, never float: these are money, and the balance chain is
    checked for exact equality.
    """

    account_number: str
    currency: str

    bank_reference: str = ""
    customer_reference: str = ""
    trn_type: str = ""
    value_date: str = ""
    post_date: str = ""
    time: str = ""

    credit: Decimal | None = None
    debit: Decimal | None = None
    balance: Decimal | None = None

    narrative: str = ""

    provenance: Provenance
    narrative_provenance: Provenance | None = None

    @property
    def amount(self) -> Decimal:
        """Signed movement. Credits are positive, debits negative.

        The statement already prints debits with a leading minus, so this is a
        selection rather than a negation.
        """
        if self.credit is not None:
            return self.credit
        if self.debit is not None:
            return self.debit
        return Decimal(0)

    @property
    def is_credit(self) -> bool:
        return self.credit is not None


class Statement(BaseModel):
    """One parsed statement PDF."""

    source_file: str
    account_short_code: str
    account_name: str = ""
    account_number: str = ""
    currency: str = ""
    bank_name: str = ""
    iban: str = ""
    bic: str = ""

    date_range: str = ""
    closing_balance: Decimal | None = None
    printed_openings: dict[str, Decimal] = Field(
        default_factory=dict,
        description="'Balance brought forward <date>' markers, keyed by date string",
    )

    rows: list[StatementRow] = Field(default_factory=list)
    page_text: list[str] = Field(
        default_factory=list, description="Raw text per page, for provenance checks"
    )

    @property
    def full_text(self) -> str:
        return "\n".join(self.page_text)


CheckStatus = Literal["PASS", "FAIL", "UNRESOLVED"]


class Check(BaseModel):
    """The result of one deterministic verification.

    Three states, not a boolean, because "does not resolve" is neither a pass
    nor a failure:

    - ``PASS``       the check holds.
    - ``FAIL``       arithmetic or structure is wrong. The parse is broken and
                     the agent must repair it. Blocks emitting anything.
    - ``UNRESOLVED`` the row parsed fine, but a value has no match in the
                     reference data. A human decides; this never blocks.

    A boolean would force ``UNRESOLVED`` into one of the two wrong buckets: as
    a failure it blocks output that is legitimately complete, and as a pass it
    launders missing evidence into a confident answer. 52 of the 100 rows in
    the supplied dataset genuinely have no counterparty match — that is the
    difficulty of the exercise, not a defect.

    `evidence` is what a human is shown; it must be concrete enough to act on
    without opening the code — expected vs actual, the delta, and a citation.
    """

    name: str
    scope: str = Field(description="Account short code, or 'all'")
    status: CheckStatus
    detail: str = ""
    evidence: str = ""

    @property
    def blocking(self) -> bool:
        return self.status == "FAIL"


class Exception_(BaseModel):
    """A row the pipeline deliberately refuses to decide on.

    Missing or ambiguous evidence must never become a pass. Each exception
    carries where it came from and the ranked candidates considered, so a
    reviewer can accept one in a click rather than starting from nothing.
    """

    account: str
    row_index: int
    field: str
    reason: str
    citation: str = ""
    candidates: list[str] = Field(default_factory=list)


class Repair(BaseModel):
    """A correction the agent applied to the deterministic parse."""

    account: str
    row_index: int
    field: str
    before: str
    after: str
    why: str


class RunResult(BaseModel):
    """The agent's terminal payload — `submit_result`'s argument.

    `parse_all_green` refers to arithmetic only. Judgement gaps live in
    `exceptions` and are not failures.
    """

    accounts_processed: int
    rows_parsed: int
    checks_passed: int
    checks_failed: int
    parse_all_green: bool
    repairs: list[Repair] = Field(default_factory=list)
    exceptions: list[Exception_] = Field(default_factory=list)
    summary: str
