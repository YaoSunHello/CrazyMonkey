"""The agent may check its own work. It may not mark it.

The agent now writes claims about its own output alongside the output. That is
useful — it forces it to look, and it names a problem more precisely than a
check written in advance can. But a claim is not evidence: the agent could
report `holds: true` without looking at anything.

So the boundary is asymmetric and this file exists to hold it there:

    a claim that does not hold  ->  the attempt fails
    a claim that does hold      ->  changes nothing

If that ever inverts, every green run stops being evidence of anything, which
is the one property the whole design is built on.
"""

from __future__ import annotations

import asyncio
import json

from app.agent import _agent_assertions


class FakeExecutor:
    """Just enough executor to hand back an assertions file."""

    def __init__(self, payload):
        self.payload = payload

    async def get(self, path):
        if self.payload is None:
            raise FileNotFoundError(path)
        return json.dumps(self.payload).encode()


class FakeTrace:
    def __init__(self):
        self.tools = []

    def tool(self, name, detail, status="ok"):
        self.tools.append((name, detail, status))


def collect(payload):
    """Sync wrapper, so these run without adding a pytest-asyncio dependency."""
    return asyncio.run(_agent_assertions(FakeExecutor(payload), FakeTrace()))


# --- the asymmetry -------------------------------------------------------


def test_a_claim_that_does_not_hold_fails_the_attempt():
    checks = collect([{"name": "batches_balance", "holds": False, "detail": "batch 7 nets to 0.02"}])
    assert [c["status"] for c in checks] == ["FAIL"]
    assert "batch 7" in checks[0]["evidence"]


def test_a_claim_that_holds_cannot_rescue_a_failing_attempt():
    """The property everything else rests on.

    An attempt fails when any check FAILs. Assertions are appended to the
    verifier's checks, never merged with them, so a PASS from the agent sits
    beside a FAIL from the verifier and the FAIL still decides.
    """
    verifier_says = [{"name": "balance_chain", "status": "FAIL", "detail": "14/15"}]
    agent_says = collect([{"name": "all_good", "holds": True, "detail": "looks fine to me"}])

    combined = verifier_says + agent_says
    failed = [c for c in combined if c["status"] == "FAIL"]
    assert failed, "an agent's own PASS must not clear a verifier FAIL"
    assert failed[0]["name"] == "balance_chain"


def test_claims_are_labelled_as_the_agent_own():
    """A reader must never mistake a self-report for a verified fact."""
    checks = collect([{"name": "spans_short", "holds": True, "detail": "max 5 words"}])
    assert checks[0]["name"].startswith("self:")
    assert "self-reported" in checks[0]["detail"]
    assert checks[0]["scope"] == "agent"


# --- being robust about what comes back ----------------------------------


def test_no_assertions_file_is_the_normal_case():
    assert collect(None) == []


def test_a_malformed_assertions_file_is_ignored_not_fatal():
    """A bad claims file must not sink a run whose actual output is fine."""
    assert collect({"not": "a list"}) == []
    assert collect(["not a dict", 42]) == []


def test_a_claim_with_no_name_is_dropped():
    assert collect([{"holds": False, "detail": "anonymous"}]) == []


def test_a_long_detail_is_capped():
    """Evidence a person will read, and a prompt that stays affordable."""
    checks = collect([{"name": "x", "holds": False, "detail": "y" * 5000}])
    assert len(checks[0]["evidence"]) <= 400
