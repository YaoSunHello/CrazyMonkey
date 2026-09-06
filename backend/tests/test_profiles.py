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


def test_a_child_keeps_what_it_does_not_declare():
    """So the second profile inherits inputs and passes by saying nothing."""
    merged = _merge({"inputs": {"a": 1}, "output": {"old": 1}}, {"output": {"x": 1}})
    assert merged["inputs"] == {"a": 1}


def test_a_declared_key_replaces_rather_than_merges():
    """Merging envelopes would emit the union of two specifications — a bug
    that reads as a feature until someone counts the keys."""
    merged = _merge({"output": {"envelope": {"a": 1}}}, {"output": {"envelope": {"b": 2}}})
    assert merged["output"] == {"envelope": {"b": 2}}


def test_merge_replaces_lists_wholesale():
    merged = _merge({"passes": [{"name": "a"}, {"name": "b"}]}, {"passes": [{"name": "c"}]})
    assert merged["passes"] == [{"name": "c"}]


# --- new capabilities stay off until measured -----------------------------


def test_optional_capabilities_default_to_off():
    """A profile that does not ask behaves exactly as it did before.

    Every capability added on this branch is opt-in, so the worst case of any
    of them is the baseline that already exists.
    """
    spec = a_pass()
    assert spec.explore == 0
    assert spec.samples == 1


def test_only_deliberately_enabled_capabilities_are_on():
    """One capability at a time, recorded here when it is switched on.

    Turning two on together makes neither attributable — the mistake that made
    a whole batch unreadable earlier. So anything enabled has to be listed, and
    listing it means someone decided.

    `explore` on `resolve` is the deliberate one. It was built, left off, and
    left unmeasured for a long time on reasoning that had expired: the loop was
    removed when a turn cost ~220s against a quantised model, and never
    revisited after the model changed. The failures it addresses were measured
    first — of the rows a run missed, 12 had exactly one master-list name
    sitting in the narrative all along, missed by boundary logic written without
    ever looking at a narrative.

    `samples` stays off: nothing has measured it, so nothing may switch it on.
    """
    expected = {("journal-entries", "resolve"), ("pipeline-validation", "resolve")}

    enabled = {
        (name, spec.name)
        for name in available()
        for spec in load(name).passes
        if spec.explore
    }
    assert enabled == expected, f"explore enabled somewhere unrecorded: {enabled ^ expected}"

    sampled = {
        (name, spec.name)
        for name in available()
        for spec in load(name).passes
        if spec.samples > 1
    }
    assert sampled == set(), f"sampling enabled without a measurement: {sampled}"


# --- the lint ------------------------------------------------------------


def test_a_prompt_that_stops_explaining_a_judged_field_is_refused():
    """The guard against a regression that shipped silently.

    Replacing a prompt section took out the line saying where a project code
    appears in a narrative. Project resolution went 10/10 to 0/7 with every
    check still green, because the checks ask whether an answer is sound, not
    whether the model was told what to look for.
    """
    from app.profiles import CheckSpec, _lint

    spec = a_pass(
        prompt="Resolve the counterparty.",
        checks=[CheckSpec(name="membership", options={"field": "project_code_match"})],
    )
    with pytest.raises(ValueError) as caught:
        _lint("test", [spec])
    assert "project_code_match" in str(caught.value)


def test_the_lint_accepts_a_prompt_that_does_explain_it():
    from app.profiles import CheckSpec, _lint

    spec = a_pass(
        prompt="Fill project_code_match from the word after PROJECT.",
        checks=[CheckSpec(name="membership", options={"field": "project_code_match"})],
    )
    _lint("test", [spec])  # must not raise


def test_the_lint_covers_multi_field_checks_too():
    from app.profiles import CheckSpec, _lint

    spec = a_pass(
        prompt="Fill counterparty_match.",
        checks=[
            CheckSpec(
                name="completeness",
                options={"fields": ["counterparty_match", "project_code_match"]},
            )
        ],
    )
    with pytest.raises(ValueError) as caught:
        _lint("test", [spec])
    assert "project_code_match" in str(caught.value)


def test_every_shipped_profile_passes_the_lint():
    """If this fails, a real run would have started against a broken prompt."""
    for name in available():
        load(name)


# --- what a pass is allowed to see ---------------------------------------


def test_a_pass_that_says_nothing_sees_every_table():
    """Silence must not narrow anything, or an old profile loses data quietly."""
    mounted = {"parties": object(), "chart": object()}
    assert a_pass().visible_tables(mounted) == mounted


def test_a_pass_sees_only_the_tables_it_names():
    """Generosity was the bug.

    A resolution pass handed the chart of accounts alongside the party lists
    mined all of them for legal-form tokens, ended up with `CHARGES`, `CREDIT`
    and `INTEREST` among them, and read `CHARGES` out of a narrative as a
    counterparty. Nothing had told it which list was which, and nothing could
    have — the profile knows, so the profile says.
    """
    mounted = {"parties": 1, "chart": 2, "codes": 3}
    assert a_pass(uses_tables=["parties", "codes"]).visible_tables(mounted) == {
        "parties": 1,
        "codes": 3,
    }


def test_naming_a_table_that_is_not_mounted_is_not_an_error():
    """A profile may declare more than a given run happens to mount."""
    assert a_pass(uses_tables=["parties", "absent"]).visible_tables({"parties": 1}) == {"parties": 1}


def test_the_resolution_pass_does_not_see_the_chart_of_accounts():
    """The specific narrowing that fixed a measured failure, kept honest."""
    resolve = load(DEFAULT_PROFILE).get_pass("resolve")
    assert resolve.uses_tables, "resolve must name its tables"
    assert "coa" not in resolve.uses_tables


# --- promoting an advisory to a retry ------------------------------------


def test_a_check_is_advisory_unless_the_profile_says_otherwise():
    """Silence keeps today's behaviour, so no existing profile changes."""
    from app.profiles import CheckSpec

    assert CheckSpec(name="label_rate").severity == "advisory"
    assert a_pass(checks=[CheckSpec(name="label_rate")]).retry_on == set()


def test_a_promoted_check_is_named_by_what_the_verifier_reports():
    """The loop matches on the emitted name, so a profile name would never fire.

    Same trap `reported_as` exists for: a nudge keyed to `label_rate` when the
    verifier emits `classification_review_rate` silently never fires.
    """
    from app.profiles import CheckSpec

    spec = a_pass(
        prompt="Set classification.",
        checks=[
            CheckSpec(
                name="label_rate",
                severity="retry",
                options={"field": "classification", "label": "Review"},
            )
        ],
    )
    assert spec.retry_on == {"classification_review_rate"}


def test_a_misspelled_severity_is_refused_rather_than_meaning_advisory():
    """Silently defaulting would restore the bug this field exists to fix.

    A day of runs raised 111 UNRESOLVED verdicts and discarded every one because
    only FAIL retried. A typo here would do the same thing again, invisibly.
    """
    from app.profiles import CheckSpec, _lint

    spec = a_pass(checks=[CheckSpec(name="label_rate", severity="retries")])
    with pytest.raises(ValueError) as caught:
        _lint("test", [spec])
    assert "severity" in str(caught.value)


def test_the_shipped_profiles_promote_the_checks_that_earn_it():
    """A record of a deliberate decision, so removing it is also deliberate."""
    promoted = {
        (name, spec.name): sorted(spec.retry_on)
        for name in available()
        for spec in load(name).passes
        if spec.retry_on
    }
    # Nothing is promoted any more, and that is the deliberate state: the checks
    # that used to be promoted were the ones judging language with a threshold,
    # and they are gone. What drives another attempt is now either a hard
    # mechanical failure or the agent's own assertion about its own work.
    assert promoted == {}, f"a check is promoted without a recorded reason: {promoted}"


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
