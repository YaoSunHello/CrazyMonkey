"""What a use case is, expressed as data.

The engine does not know about banks. It knows how to mount inputs, ask a model
for a script, run it in a sandbox, and judge the result with checks it names by
string. Everything that makes a run *about* something lives in a profile.

A profile declares four things and nothing else:

    inputs   which documents and reference tables to mount
    passes   per pass: the prompt, the kit, and which checks judge it
    output   how the canonical result is projected into this case's envelope
    label    what a person picking between tracks should see

That last one matters more than it looks. Profiles are JSON rather than Python
so the list can be served to a frontend and offered as tracks, and so a caller
can eventually send an override without the backend growing a plugin loader.

`extends` keeps the second profile honest. `pipeline-validation` runs the same
documents through the same passes as `journal-entries` and differs only in what
it emits — so it says so, and overrides one key. If a new profile ever needs
Python to express itself, the abstraction is wrong and should be fixed rather
than special-cased.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROFILES = ROOT / "profiles"

# The track a run takes when the caller names none, so every existing command
# keeps working and a second use case is a flag rather than a fork. It lives
# here rather than in `agent.py` so the CLI can offer it as a default without
# importing the model and sandbox stack — `verify` must keep running with
# `openai-agents` and `daytona` uninstalled.
DEFAULT_PROFILE = "journal-entries"

# What a check's `UNRESOLVED` verdict is allowed to cause. See `CheckSpec`.
SEVERITIES = {"advisory", "retry"}

# The part of the prompt the engine owns. It is the same for every use case and
# a profile cannot change it, because these are the rules that make the result
# judgeable at all: one script, one output, and no adjusting a number to get
# past a check.
CORE = """\
You are writing one Python file that will run once, in a sandbox, and produce a
single JSON result. A module `kit` is already available — import it, do not
rewrite it, and do not install anything.

Rules that hold for every task:

- Write the result exactly once, at the end, with the kit's write function.
- Never invent or adjust a value to make a check pass. A value you cannot read
  is a value you leave out, and the checks will say so plainly.
- **Print what you need to see.** Everything your script prints comes back to
  you if the attempt is rejected, so stdout is how you look at the data: the
  values that did not match, what the reference data holds near them, how many
  rows a pattern actually caught. A number you assumed is a number you will get
  wrong. Finish with a one-line summary, e.g. "parsed 16 rows".
- Reply with the complete contents of the file in a single ```python code block,
  and nothing else.

## What the checks are, and how much to trust each kind

You will be judged by checks, and knowing what they can and cannot see is part
of doing this well. They are not one thing.

**A check about a number or about existence is proof. Trust it completely.**
Does this balance chain close, does this batch net to zero, is this value
actually present in the list it claims, does this string really appear in the
document. There is no judgement in any of it. If one of these objects, it is
right and you are wrong — find the cause and fix it. Never argue with
arithmetic, and never adjust a figure to quiet it.

**A check that reports a count or a share is a measurement, not a verdict.**
How much *ought* to resolve is a fact about the document in front of you, and
the check cannot read it. One source is full of dealings with outside parties;
another is almost entirely internal movements naming nobody, and there a high
unresolved count is the correct answer rather than a failure. Read the number,
decide whether it is right *for this document*, and say why.

**You are the one who reads. Where no exact check contradicts you, your reading
stands.** A check works on shapes and strings; it cannot know what a name means
or which party a sentence is about. If something is obvious to you and nothing
exact says otherwise, go with it and record your reasoning.

**Never contort an answer to satisfy a rule you can see is crude.** If a check
would be quieter with a worse answer, give the better answer and explain the
disagreement in plain words. A reviewer can weigh that. What they cannot do is
recover the truth from an output bent to please a rule — and a wrong value that
passes silently is far more expensive than an honest one that gets discussed.

The point of all this is a result somebody can act on: correct where it can be
proved, judged where it must be, and clearly flagged where it is neither.
"""


@dataclass
class Nudge:
    """Guidance on how to go about something. Never on what counts as correct.

    A nudge is prompt text and only prompt text — the verifier never sees a
    profile, so a nudge cannot disable a check or move a tolerance. It exists
    because some things are learned from a failed run rather than known in
    advance, and the alternative is rediscovering them every time.

    Scope decides when it is shown:

        always            every attempt of the pass
        documents         only for the named documents
        check_failed      only on a retry where that check failed

    The last one keeps the retry prompt short. Advice about a check nobody
    failed is noise competing with the failure the model actually has to fix.
    """

    text: str
    documents: list[str] = field(default_factory=list)
    check_failed: str = ""

    @property
    def always(self) -> bool:
        return not self.documents and not self.check_failed

    def applies(self, document: str, failed: set[str]) -> bool:
        if self.check_failed:
            return self.check_failed in failed
        if self.documents:
            return document in self.documents
        return True


@dataclass
class CheckSpec:
    """One check the profile asks for, named by string.

    `name` selects engine code; `describe` is the plain-English line the model
    is shown. Keeping the wording next to the request rather than inside the
    check means a profile can explain a shared check in its own terms without
    forking it.
    """

    name: str
    describe: str = ""
    options: dict = field(default_factory=dict)
    # What an `UNRESOLVED` verdict from this check should cause.
    #
    #     advisory   report it and carry on          (the default, and today's
    #                                                 behaviour for every check)
    #     retry      spend another attempt on it
    #
    # This exists because of something measurable: across one day of runs the
    # verifier raised **111 UNRESOLVED verdicts and every one was discarded**,
    # since `agent.py` only retries on `FAIL`. `classification_review_rate`
    # caught a run labelling a third of its rows `Review` and said so to nobody,
    # and the nudge written to answer that check could never fire.
    #
    # Promotion changes only *when the agent is told* — never what the row
    # reports. An `UNRESOLVED` row stays `UNRESOLVED` in the output, and a pass
    # that exhausts its attempts with nothing worse than promoted advisories is
    # still accepted. Otherwise this would quietly turn the third state into a
    # failure, which is the one thing the whole design exists to avoid.
    #
    # Which advisories are worth another attempt is a fact about the use case,
    # so it lives in the profile rather than in the check.
    severity: str = "advisory"

    @property
    def reported_as(self) -> str:
        """The name this check will fail under, so the prompt can use it too.

        A statement check reports under its own name; a generic one is named
        for the field it is about. Asking the verifier rather than guessing
        keeps a nudge keyed to a check name firing.
        """
        from app.verification.generic import REGISTRY, name_for

        return name_for(self.name, self.options) if self.name in REGISTRY else self.name


@dataclass
class Pass:
    """One write → run → verify → retry cycle.

    Splitting a use case into passes is how a long task stays convergent. The
    extraction pass settles the rows against arithmetic; a later pass resolves
    them against reference data. Each carries its own attempt budget, so a
    resolution that will not come good cannot spend the extraction that already
    did.
    """

    name: str
    prompt: str
    kit: str = "statement_kit"
    # Which family of checks judges this pass. `generic` runs the parameterised
    # checks named below; `statement` runs the arithmetic verifier in
    # `verification/checks.py` — all of it, not a subset, because those are the
    # contract and the CLI runs them all. Named rather than inferred, so a
    # third use case says what judges it instead of us guessing from shape.
    judge: str = "generic"
    checks: list[CheckSpec] = field(default_factory=list)
    nudges: list[Nudge] = field(default_factory=list)
    max_attempts: int = 4
    # How many independent times to run this pass. Above one, the extra samples
    # are compared and disagreement is reported rather than hidden: two batches
    # over the same statements flipped 27 of 100 classifications, and a single
    # run states a coin flip as confidently as a certainty. Costs a full pass
    # each, so it is worth it only where the judgement is genuinely uncertain.
    samples: int = 1
    # How many rounds the agent may spend looking at the data before it
    # writes the real script. Zero keeps today's behaviour exactly: one
    # generation, one execution, a verdict. Each round costs a model call,
    # and only the first attempt spends them - a retry already carries the
    # verifier's objections, which beat a fresh look.
    explore: int = 0
    # Whether this pass reads the previous pass's rows instead of the source
    # document. Resolution builds on extraction; extraction starts from the PDF.
    inherits_rows: bool = False
    # Which mounted reference tables this pass may see. Empty means all of them,
    # which is what every profile did before and still does by default. See
    # `visible_tables` for why narrowing is sometimes the whole fix.
    uses_tables: list[str] = field(default_factory=list)

    def visible_tables(self, mounted: dict) -> dict:
        """The reference data this pass may see. Everything, unless it narrows.

        Mounting the whole workbook into every pass reads as generosity and is
        not. A resolution pass handed the chart of accounts beside the party
        lists had no way to tell which was which, so it mined all of them for
        "legal-form tokens", ended up with 253 including `CHARGES`, `CREDIT` and
        `INTEREST`, and then read `CHARGES` out of a narrative as a
        counterparty name. Nothing had told it a chart of accounts is not a list
        of parties, and nothing could have.

        Which lists belong to which stage is a fact about the client's data
        model, so the profile states it. Silence keeps every table, so no
        existing profile changes and a run never loses data by accident.
        """
        if not self.uses_tables:
            return mounted
        return {name: table for name, table in mounted.items() if name in set(self.uses_tables)}

    @property
    def retry_on(self) -> set[str]:
        """Checks whose `UNRESOLVED` verdict is worth spending another attempt.

        Reported names, not profile names, so the loop can match them against
        what the verifier actually emitted — the same reason `reported_as`
        exists for nudges.
        """
        return {c.reported_as for c in self.checks if c.severity == "retry"}

    def budget(self) -> str:
        """How many tries there are, said up front rather than discovered.

        The retry prompt has always counted attempts, so the model learned its
        budget only once it was already spending it. Knowing at the start
        changes what a sensible first attempt looks like — it is worth spending
        the exploration rounds on the hard part, and worth submitting something
        honest and partial rather than rewriting toward a perfection there is no
        room left to reach.

        And running out is no longer catastrophic, which the model should also
        know: work that cannot satisfy every check still goes forward carrying
        its own statuses and the failures beside it. That is a far better
        outcome than a rewrite gamble on the last attempt, and saying so removes
        the incentive to gamble.
        """
        rounds = (
            f"{self.explore} round(s) to look at the data first, then " if self.explore else ""
        )
        return (
            "## How many tries you have\n\n"
            f"{rounds}up to {self.max_attempts} attempts at the real file. Aim to be right "
            "in the first two or three: each attempt costs a full rewrite, and the later "
            "ones exist for problems you could not have foreseen, not for a plan you have "
            "not made yet.\n\n"
            "If you reach the last attempt and something still will not come good, do not "
            "gamble on a rewrite. Submit what you have with that part honestly marked — "
            "unresolved, or proposed with your reasoning — because incomplete work that "
            "says where it is incomplete goes forward and gets reviewed, while a run that "
            "risks everything on one more try can end with nothing to show at all."
        )

    def reference_brief(self) -> str:
        """Which mounted table is for what, taken from the checks themselves.

        The most expensive omission this prompt ever had. A resolution is judged
        against a fixed list of party pools declared in the `membership` check —
        and that list was never shown to the model. It was graded on a rule it
        could not read, and reconstructed it six different ways in six attempts,
        twice naming tables that do not exist and once dropping a real one.
        Meanwhile the prompt mentioned, approvingly, that "the mounted lists
        include the account-to-entity mapping" without saying that mapping is
        only for identifying the account holder — so the agent resolved three
        rows to a bank-account label and the run was rejected.

        Derived rather than written, which is the point: the profile declares
        each pool once, for the check that enforces it, and the model is shown
        the same declaration. There is no second list to drift.
        """
        pools: dict[str, list[str]] = {}
        owners: list[str] = []
        charts: list[str] = []
        for check in self.checks:
            field = check.options.get("field", "")
            for pool in check.options.get("tables", []):
                pools.setdefault(field, []).append(pool)
            owners += check.options.get("owner", [])
            charts += check.options.get("chart", [])

        if not (pools or owners or charts):
            return ""

        lines = []
        for field, entries in pools.items():
            lines.append(f"- **{field}** may only resolve against, in an order you decide:")
            lines += [f"      {entry}" for entry in dict.fromkeys(entries)]
        if charts:
            lines.append("- the chart of accounts, for booking values only, never for a party:")
            lines += [f"      {entry}" for entry in dict.fromkeys(charts)]
        if owners:
            lines.append(
                "- the account-to-owner mapping. Use it ONLY to work out whose account this"
            )
            lines.append(
                "  is, so you can exclude that party. It is a register of accounts, not of"
            )
            lines.append("  companies, and a value from it is never a counterparty:")
            lines += [f"      {entry}" for entry in dict.fromkeys(owners)]

        return (
            "## The reference data, and what each part is for\n\n"
            "Anything else this run mounts is for context. Resolving against a table not\n"
            "listed here fails, however real the value you find in it looks.\n\n"
            + "\n".join(lines)
        )

    def compose(self, *, document: str = "", failed: set[str] | None = None) -> str:
        """The full prompt: the engine's rules, the task, the data, the checks, the notes."""
        failed = failed or set()
        parts = [CORE, self.budget(), self.prompt]

        brief = self.reference_brief()
        if brief:
            parts.append(brief)

        described = [(c.reported_as, c.describe) for c in self.checks if c.describe]
        if described:
            width = max(len(name) for name, _ in described)
            lines = [f"- {name:<{width}}  {text}" for name, text in described]
            parts.append("## What the verifier checks\n\n" + "\n".join(lines))

        notes = [n.text for n in self.nudges if n.applies(document, failed)]
        if notes:
            parts.append("## Notes for this run\n\n" + "\n".join(f"- {n}" for n in notes))

        return "\n\n".join(part.strip() for part in parts) + "\n"


@dataclass
class Profile:
    id: str
    label: str
    description: str = ""
    inputs: dict = field(default_factory=dict)
    passes: list[Pass] = field(default_factory=list)
    output: dict = field(default_factory=dict)

    def get_pass(self, name: str) -> Pass:
        for item in self.passes:
            if item.name == name:
                return item
        known = ", ".join(p.name for p in self.passes)
        raise KeyError(f"profile {self.id!r} has no pass {name!r} (has: {known})")

    def summary(self) -> dict:
        """What a frontend needs to offer this as a track.

        Deliberately not the whole profile: the prompts are long, and a picker
        needs the identity and the shape, not the instructions.
        """
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "documents": self.inputs.get("documents", {}).get("describe", ""),
            "tables": sorted(self.inputs.get("tables", {})),
            "passes": [p.name for p in self.passes],
            "envelope": list(self.output.get("envelope", {})),
        }


def _merge(base: dict, over: dict) -> dict:
    """Overlay `over` onto `base`. A key the child declares replaces the parent's.

    Replacement rather than deep merge, deliberately. A child that writes an
    `output` block means *this* is my output — recursing would have merged its
    envelope into the parent's and emitted the union of two specifications,
    which is a bug that reads as a feature until someone counts the keys.

    The cost is that a child changing part of a block restates that block. That
    is a fair price for being able to read a profile and know what it emits
    without also reading its parent.
    """
    return {**base, **over}


def _read(profile_id: str, seen: tuple[str, ...] = ()) -> dict:
    if profile_id in seen:
        chain = " -> ".join([*seen, profile_id])
        raise ValueError(f"profile inheritance is circular: {chain}")

    path = PROFILES / f"{profile_id}.json"
    if not path.exists():
        known = ", ".join(available()) or "none found"
        raise FileNotFoundError(f"no profile {profile_id!r} in {PROFILES} (have: {known})")

    raw = json.loads(path.read_text(encoding="utf-8"))
    parent = raw.pop("extends", "")
    if parent:
        raw = _merge(_read(parent, (*seen, profile_id)), raw)
    return raw


def _text(value: str | list[str]) -> str:
    """Accept a string, or a list of lines.

    JSON has no multi-line string, and a prompt written as one escaped line is
    unreadable and therefore uneditable — which would defeat the point of
    holding prompts as data. A list of lines is still plain JSON, still
    round-trips to a frontend, and can be read in the file.
    """
    return "\n".join(value) if isinstance(value, list) else value


def _build_pass(raw: dict) -> Pass:
    return Pass(
        name=raw["name"],
        prompt=_text(raw["prompt"]),
        kit=raw.get("kit", "statement_kit"),
        judge=raw.get("judge", "generic"),
        checks=[CheckSpec(**c) for c in raw.get("checks", [])],
        nudges=[Nudge(**{**n, "text": _text(n["text"])}) for n in raw.get("nudges", [])],
        max_attempts=raw.get("max_attempts", 4),
        samples=raw.get("samples", 1),
        explore=raw.get("explore", 0),
        inherits_rows=raw.get("inherits_rows", False),
        uses_tables=raw.get("uses_tables", []),
    )


def _lint(profile_id: str, passes: list[Pass]) -> None:
    """Every field a pass is judged on must be explained by that pass's prompt.

    This exists because of a regression that no test could catch. A prompt
    section was replaced wholesale, taking with it the one line that said where
    a project code appears in a narrative — and project resolution went from
    10/10 to 0/7 while every check still reported green, because the checks ask
    whether an answer is *sound*, not whether the model was told what to look
    for.

    A prompt is code. The engine already knows which fields it will judge, so
    it can insist they are mentioned. Cheap, and it turns a silent quality
    collapse into a refusal to start.
    """
    for spec in passes:
        wanted = {
            check.options["field"] for check in spec.checks if check.options.get("field")
        }
        for group in (check.options.get("fields", []) for check in spec.checks):
            wanted.update(group)

        missing = sorted(f for f in wanted if f not in spec.prompt)
        if missing:
            raise ValueError(
                f"profile {profile_id!r}, pass {spec.name!r}: the prompt never mentions "
                f"{', '.join(missing)}, but the verifier judges "
                f"{'them' if len(missing) > 1 else 'it'}. A field the model is not told "
                f"about is a field it will get wrong quietly."
            )

        for check in spec.checks:
            if check.severity not in SEVERITIES:
                raise ValueError(
                    f"profile {profile_id!r}, pass {spec.name!r}, check {check.name!r}: "
                    f"severity {check.severity!r} is not one of {sorted(SEVERITIES)}. A "
                    f"misspelling here would silently mean 'advisory' and the retry "
                    f"nobody noticed was missing is the bug this whole field fixes."
                )


def load(profile_id: str) -> Profile:
    raw = _read(profile_id)
    passes = [_build_pass(p) for p in raw.get("passes", [])]
    if not passes:
        raise ValueError(f"profile {profile_id!r} declares no passes")

    names = [p.name for p in passes]
    if len(set(names)) != len(names):
        raise ValueError(f"profile {profile_id!r} has duplicate pass names: {names}")

    _lint(profile_id, passes)

    return Profile(
        id=raw.get("id", profile_id),
        label=raw.get("label", profile_id),
        description=raw.get("description", ""),
        inputs=raw.get("inputs", {}),
        passes=passes,
        output=raw.get("output", {}),
    )


def available() -> list[str]:
    if not PROFILES.is_dir():
        return []
    return sorted(p.stem for p in PROFILES.glob("*.json"))


def load_all() -> list[Profile]:
    """Every profile, skipping any that will not load.

    A broken profile must not take the discovery endpoint down with it — the
    frontend still needs to offer the tracks that do work. The failure is
    reported in place of the profile rather than swallowed.
    """
    out = []
    for name in available():
        try:
            out.append(load(name))
        except Exception as exc:  # noqa: BLE001 — one bad file is not a dead endpoint
            out.append(Profile(id=name, label=name, description=f"failed to load: {exc}"))
    return out
