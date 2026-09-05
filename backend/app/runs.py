"""Where a run's artefacts live, and how to find them again.

Every run gets its own directory. The previous design wrote a single
`agent_trace.jsonl`, so each run silently destroyed the one before it — the
successful run erased the failure you wanted to compare it against, and the
only way to see two runs was to have watched both live.

    outputs/runs/20260905-153722-GBP_3252/
        trace.jsonl      the full event stream
        rows.json        the structured output, with the checks that judged it
        attempt-1.py     the code the model actually wrote
        attempt-2.py     …and its next try
        summary.json     account, model, attempts, accepted, timings

`attempt-N.py` matters more than it looks: when a run fails, the first thing
worth reading is the code that failed, and burying it inside a JSONL blob makes
that needlessly hard.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / "outputs"
RUNS = OUTPUTS / "runs"


def new_run_id(account: str, *, started: datetime | None = None, batch: str = "") -> str:
    """A sortable directory name. `batch` groups documents run together."""
    stamp = (started or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"{batch or stamp}-{account}"


class RunDir:
    """The artefacts of one run, written as they happen.

    Written incrementally rather than at the end: a run that is killed halfway
    — which is how most of them end while you are still building the thing —
    should still leave behind what it had got to.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.path = RUNS / run_id
        self.path.mkdir(parents=True, exist_ok=True)

    @property
    def trace_path(self) -> Path:
        return self.path / "trace.jsonl"

    def write_attempt(self, attempt: int, source: str) -> Path:
        target = self.path / f"attempt-{attempt}.py"
        target.write_text(source, encoding="utf-8")
        return target

    def write_rows(self, payload: dict) -> Path:
        target = self.path / "rows.json"
        target.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return target

    def write_summary(self, payload: dict) -> Path:
        target = self.path / "summary.json"
        target.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return target

    def mark_latest(self) -> None:
        """Record which run is newest, so `replay` with no argument works.

        A plain file rather than a symlink: symlinks need elevation on Windows.
        """
        OUTPUTS.mkdir(exist_ok=True)
        (OUTPUTS / "latest").write_text(self.run_id, encoding="utf-8")


@dataclass
class RunRecord:
    run_id: str
    path: Path
    account: str = ""
    model: str = ""
    attempts: int = 0
    accepted: bool = False
    rows: int = 0
    seconds: float = 0.0

    @property
    def when(self) -> str:
        return self.run_id.split("-", 2)[0] + " " + self.run_id.split("-", 2)[1]


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def list_runs() -> list[RunRecord]:
    """Every recorded run, newest first."""
    if not RUNS.exists():
        return []
    records = []
    for directory in sorted(RUNS.iterdir(), reverse=True):
        if not directory.is_dir():
            continue
        summary = _read(directory / "summary.json")
        records.append(
            RunRecord(
                run_id=directory.name,
                path=directory,
                account=summary.get("account", directory.name.split("-")[-1]),
                model=summary.get("model", ""),
                attempts=summary.get("attempts", 0),
                accepted=bool(summary.get("accepted")),
                rows=summary.get("rows", 0),
                seconds=summary.get("seconds", 0.0),
            )
        )
    return records


def resolve(run_id: str | None) -> RunRecord | None:
    """Find a run by id, by prefix, or the latest when none is given."""
    records = list_runs()
    if not records:
        return None

    if not run_id:
        marker = OUTPUTS / "latest"
        if marker.exists():
            wanted = marker.read_text(encoding="utf-8").strip()
            for record in records:
                if record.run_id == wanted:
                    return record
        return records[0]

    for record in records:
        if record.run_id == run_id:
            return record
    # A prefix is enough — nobody wants to type a timestamp in full.
    matches = [r for r in records if r.run_id.startswith(run_id) or run_id in r.run_id]
    return matches[0] if matches else None
