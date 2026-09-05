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
- Print a one-line summary to stdout when you finish, e.g. "parsed 16 rows".
- Reply with the complete contents of the file in a single ```python code block,
  and nothing else.
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
    checks: list[CheckSpec] = field(default_factory=list)
    nudges: list[Nudge] = field(default_factory=list)
    max_attempts: int = 4
    inherits_rows: bool = False

    def compose(self, *, document: str = "", failed: set[str] | None = None) -> str:
        """The full prompt: the engine's rules, the task, the checks, the notes."""
        failed = failed or set()
        parts = [CORE, self.prompt]

        described = [c for c in self.checks if c.describe]
        if described:
            width = max(len(c.name) for c in described)
            lines = [f"- {c.name:<{width}}  {c.describe}" for c in described]
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
    """Overlay `over` onto `base`, one level deep per key.

    Dicts merge key by key so a profile can override `output` without restating
    `inputs`. Lists replace wholesale — a profile that redeclares its passes
    means to replace them, and half-overlaying a list of passes by index would
    be a quietly surprising thing to do.
    """
    merged = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


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
        checks=[CheckSpec(**c) for c in raw.get("checks", [])],
        nudges=[Nudge(**{**n, "text": _text(n["text"])}) for n in raw.get("nudges", [])],
        max_attempts=raw.get("max_attempts", 4),
        inherits_rows=raw.get("inherits_rows", False),
    )


def load(profile_id: str) -> Profile:
    raw = _read(profile_id)
    passes = [_build_pass(p) for p in raw.get("passes", [])]
    if not passes:
        raise ValueError(f"profile {profile_id!r} declares no passes")

    names = [p.name for p in passes]
    if len(set(names)) != len(names):
        raise ValueError(f"profile {profile_id!r} has duplicate pass names: {names}")

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
