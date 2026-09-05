"""A use case expressed as data, and the guarantees that keeps it honest.

These run offline. `profiles.py` deliberately imports nothing from `agent.py`,
`llm.py` or `sandbox.py`, so a profile can be loaded, composed and served by the
API without the model or sandbox stack installed.
"""

from __future__ import annotations

import json

import pytest

from app.profiles import (
    CORE,
    DEFAULT_PROFILE,
    Nudge,
    Pass,
    _merge,
    available,
    load,
    load_all,
)


# --- the shipped profiles ------------------------------------------------


def test_the_default_profile_exists():
    """Every command falls back to this one, so its absence breaks everything."""
    assert DEFAULT_PROFILE in available()


def test_every_shipped_profile_loads():
    for name in available():
        profile = load(name)
        assert profile.passes, f"{name} declares no passes"
        assert profile.label


def test_a_missing_profile_names_the_ones_that_exist():
    with pytest.raises(FileNotFoundError) as caught:
        load("no-such-track")
    assert DEFAULT_PROFILE in str(caught.value)


def test_summary_is_json_serialisable():
    """It is served over HTTP and may be sent back as an override."""
    for profile in load_all():
        json.loads(json.dumps(profile.summary()))


# --- prompt composition --------------------------------------------------


def a_pass(**over) -> Pass:
    base = {"name": "extract", "prompt": "Parse the thing."}
    return Pass(**{**base, **over})


def test_the_engine_rules_lead_every_prompt():
    """A profile supplies the task; it does not get to drop the contract."""
    composed = a_pass().compose()
    assert composed.startswith(CORE.strip()[:40])
    assert "never invent or adjust a value" in composed.lower()


def test_check_descriptions_reach_the_model():
    from app.profiles import CheckSpec

    composed = a_pass(checks=[CheckSpec(name="balance_chain", describe="it must foot")]).compose()
    assert "balance_chain" in composed
    assert "it must foot" in composed


def test_a_check_with_no_description_is_not_announced():
    """Naming a check without saying what it means teaches the model nothing."""
    from app.profiles import CheckSpec

    composed = a_pass(checks=[CheckSpec(name="quiet_check")]).compose()
    assert "What the verifier checks" not in composed


# --- nudge scoping -------------------------------------------------------


def test_an_unscoped_nudge_is_always_shown():
    composed = a_pass(nudges=[Nudge(text="mind the gap")]).compose(document="ANY")
    assert "mind the gap" in composed


def test_a_document_nudge_reaches_only_its_documents():
    spec = a_pass(nudges=[Nudge(text="no markers here", documents=["EUR_0894"])])
    assert "no markers here" in spec.compose(document="EUR_0894")
    assert "no markers here" not in spec.compose(document="GBP_3252")


def test_a_check_nudge_waits_for_that_check_to_fail():
    """Advice about a check nobody failed is noise competing with the real failure."""
    spec = a_pass(nudges=[Nudge(text="join them properly", check_failed="reference_provenance")])
    assert "join them properly" not in spec.compose(document="GBP_3252")
    assert "join them properly" in spec.compose(
        document="GBP_3252", failed={"reference_provenance"}
    )


def test_a_check_nudge_ignores_a_different_failure():
    spec = a_pass(nudges=[Nudge(text="join them properly", check_failed="reference_provenance")])
    assert "join them properly" not in spec.compose(failed={"balance_chain"})


def test_no_notes_section_when_nothing_applies():
    assert "Notes for this run" not in a_pass().compose()


# --- inheritance ---------------------------------------------------------


def test_merge_overlays_dicts_key_by_key():
    """So a profile can override `output` without restating `inputs`."""
    merged = _merge({"inputs": {"a": 1, "b": 2}, "output": {}}, {"output": {"x": 1}})
    assert merged == {"inputs": {"a": 1, "b": 2}, "output": {"x": 1}}


def test_merge_replaces_lists_wholesale():
    """Half-overlaying a list of passes by index would be quietly surprising."""
    merged = _merge({"passes": [{"name": "a"}, {"name": "b"}]}, {"passes": [{"name": "c"}]})
    assert merged["passes"] == [{"name": "c"}]


# --- the firewall --------------------------------------------------------


def test_a_profile_cannot_reach_the_verifier():
    """A nudge shapes how the agent works, never what counts as correct.

    Enforced by import direction, not by convention: if `verification` ever
    imports `profiles`, a profile could start deciding its own pass mark.
    """
    import app.verification.checks as checks

    source = open(checks.__file__, encoding="utf-8").read()
    assert "profiles" not in source
    assert "import app.agent" not in source
