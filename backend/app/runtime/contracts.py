"""The model proposes evidence references and a bounded DSL, never answers."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NumericInput(Record):
    evidence_id: str = Field(min_length=1, max_length=100)
    # Exact numeric token in a prose quote; cells normally use their entire value.
    token: str | None = Field(default=None, max_length=80)
    unit: Literal["money", "rate", "factor", "number"] = "number"


class Operation(Record):
    operation: Literal["multiply", "add", "subtract", "divide", "min", "max"]
    operands: list[str | Operation] = Field(min_length=2, max_length=16)


class VerificationPlan(Record):
    check_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    check_type: Literal["annual_charge", "quantity_price", "gross_less_deductions", "model_proposed"]
    entity_id: str = Field(min_length=1, max_length=150)
    fund_name: str = Field(default="", max_length=200)
    currency: Literal["GBP", "USD", "EUR"]
    rationale: str = Field(min_length=1, max_length=3000)
    inputs: dict[str, NumericInput] = Field(min_length=2, max_length=16)
    reported_input: str
    operation: Operation
    context_evidence_ids: list[str] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def bounded_tree(self):
        count = 0
        used: set[str] = set()
        def visit(node, depth=0):
            nonlocal count
            count += 1
            if count > 48 or depth > 6:
                raise ValueError("operation exceeds the node/depth limit")
            if isinstance(node, str):
                if node not in self.inputs:
                    raise ValueError("operation refers to an unknown input")
                used.add(node)
            else:
                if node.operation in ("subtract", "divide") and len(node.operands) != 2:
                    raise ValueError("subtract/divide require two operands")
                for operand in node.operands:
                    visit(operand, depth + 1)
        visit(self.operation)
        if self.reported_input not in self.inputs or self.reported_input in used:
            raise ValueError("reported amount must be separate from the expected calculation")
        reported = self.inputs[self.reported_input]
        if any((self.inputs[key].evidence_id, self.inputs[key].token) == (reported.evidence_id, reported.token)
               for key in used):
            raise ValueError("expected inputs cannot alias the reported source value")
        if set(self.inputs) != used | {self.reported_input}:
            raise ValueError("every supplied input must be used")
        return self


class PlanBatch(Record):
    checks: list[VerificationPlan] = Field(default_factory=list, max_length=20)
    cannot_verify: list[str] = Field(default_factory=list, max_length=100)


class Challenge(Record):
    status: Literal["PASS", "CHALLENGE", "INSUFFICIENT_EVIDENCE"]
    checks: dict[str, bool]
    reasons: list[str] = Field(default_factory=list, max_length=100)


class ModelChallenge(Record):
    status: Literal["PASS", "CHALLENGE", "INSUFFICIENT_EVIDENCE"]
    reasons: list[str] = Field(default_factory=list, max_length=50)
    evidence_ids: list[str] = Field(default_factory=list, max_length=200)
