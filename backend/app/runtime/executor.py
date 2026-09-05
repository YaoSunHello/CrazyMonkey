"""Small arithmetic interpreter: no eval, exec, generated Python or I/O."""
from __future__ import annotations

from decimal import Decimal, DecimalException, ROUND_HALF_UP, localcontext
from functools import reduce
from operator import mul

from .contracts import Operation, VerificationPlan
from .investigation_evidence import EvidenceStore


def evaluate(node: str | Operation, values: dict[str, Decimal]) -> Decimal:
    if isinstance(node, str):
        return values[node]
    args = [evaluate(arg, values) for arg in node.operands]
    if node.operation == "multiply":
        result = reduce(mul, args, Decimal(1))
    elif node.operation == "add":
        result = sum(args, Decimal(0))
    elif node.operation == "subtract":
        result = args[0] - args[1]
    elif node.operation == "divide":
        result = args[0] / args[1]
    elif node.operation == "min":
        result = min(args)
    else:
        result = max(args)
    if not result.is_finite() or abs(result) > Decimal("1e30"):
        raise ValueError("calculation exceeds the supported bound")
    return result


def execute(plan: VerificationPlan, store: EvidenceStore, tolerance=Decimal("0.01")) -> dict:
    plan = VerificationPlan.model_validate(plan.model_dump())
    if not tolerance.is_finite() or tolerance < 0:
        raise ValueError("tolerance must be finite and nonnegative")
    for evidence_id in plan.context_evidence_ids:
        store.get(evidence_id)
    try:
        with localcontext() as context:
            context.prec = 50
            values = {key: store.number(spec) for key, spec in plan.inputs.items()}
            exact = evaluate(plan.operation, values)
            expected = exact.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            reported = values[plan.reported_input]
            difference = reported - expected
            return {"values": {k: str(v) for k, v in values.items()},
                    "unrounded_expected": str(exact), "expected": str(expected),
                    "reported": str(reported), "difference": str(difference),
                    "tolerance": str(tolerance), "rounding": "ROUND_HALF_UP_0.01",
                    "status": "DISCREPANCY" if abs(difference) > tolerance else "MATCH"}
    except DecimalException as exc:
        raise ValueError("invalid bounded arithmetic (including division by zero)") from exc
