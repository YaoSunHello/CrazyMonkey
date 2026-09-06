"""Serve the run console, and read the backend's artefacts off disk.

    python backend/test-simple-frontend/serve.py
    python backend/test-simple-frontend/serve.py --port 8080 --no-new-runs

Standard library only, and **it imports nothing from `app.*`**. That is what
lets this whole console live in one directory: it reads `outputs/`, `examples/`,
`profiles/` and `samples/` by path, so it cannot drag the backend along with it
and cannot break when the backend changes shape.

The one thing it does execute is `python -m app.cli agent`, and only when a
caller asks for a new run. That is a real spend of model calls and about seven
minutes, so the browser has to ask twice and this server can be told to refuse
outright with `--no-new-runs`.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
ROOT = BACKEND.parent

OUTPUTS = ROOT / "outputs"
RUNS = OUTPUTS / "runs"
EXAMPLES = ROOT / "examples"
PROFILES = ROOT / "profiles"

# The organisers committed the dataset under its own folder; an older working
# copy may still have the flat unpack. Same fallback order as app/cli.py, so
# this console lists exactly the statements the CLI would run.
STATEMENT_DIRS = (
    ROOT / "samples" / "01-bank-statements-to-journal-entries" / "statements",
    ROOT / "samples" / "statements",
)

# A run id is <timestamp>-<account>: 20260906-012135-USD_4373. Anything that
# does not look like one never reaches the filesystem.
RUN_ID = re.compile(r"^\d{8}-\d{6}-[A-Za-z0-9_]+$")
# The pseudo-account meaning "every statement in one batch".
ALL = "__all__"
ACCOUNT = re.compile(r"^[A-Za-z0-9_]{1,32}$")
PROFILE_ID = re.compile(r"^[a-z0-9-]{1,64}$")
# A filename and nothing else — no separators, no traversal.
FILENAME = re.compile(r"^[A-Za-z0-9 ._-]{1,120}$")

ALLOW_NEW_RUNS = True


# --------------------------------------------------------------------------
# Reading what the backend left behind
# --------------------------------------------------------------------------

def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def statements_dir() -> Path:
    return next(
        (d for d in STATEMENT_DIRS if d.is_dir() and any(d.glob("*.pdf"))),
        STATEMENT_DIRS[0],
    )


def run_record(directory: Path) -> dict:
    """One run, as the picker needs it.

    `summary.json` is only written when a run finishes. A run that was killed
    halfway still has a trace worth replaying, so everything here degrades to
    what the directory name and the file listing can tell us.
    """
    summary = read_json(directory / "summary.json")
    run_id = directory.name
    parts = run_id.split("-", 2)
    batch = "-".join(parts[:2]) if len(parts) >= 3 else run_id
    files = sorted(p.name for p in directory.iterdir() if p.is_file())

    when = ""
    if len(parts) >= 2 and len(parts[0]) == 8 and len(parts[1]) == 6:
        try:
            when = datetime.strptime(parts[0] + parts[1], "%Y%m%d%H%M%S").isoformat(" ")
        except ValueError:
            when = ""

    return {
        "run_id": run_id,
        "batch": batch,
        "when": when,
        "account": summary.get("account") or (parts[2] if len(parts) >= 3 else run_id),
        "source_file": summary.get("source_file", ""),
        "profile": summary.get("profile", ""),
        "model": summary.get("model", ""),
        "attempts": summary.get("attempts", 0),
        "accepted": bool(summary.get("accepted")),
        "rows": summary.get("rows", 0),
        "seconds": summary.get("seconds", 0.0),
        "note": summary.get("summary", ""),
        # A run with no summary.json never finished. Say that rather than
        # rendering it as a rejection, which is a different thing entirely.
        "finished": bool(summary),
        "files": files,
        "has_trace": "trace.jsonl" in files,
        "stages": sorted(
            {
                name.split("-attempt-")[0]
                for name in files
                if "-attempt-" in name
            }
        ),
    }


def list_runs() -> list[dict]:
    if not RUNS.is_dir():
        return []
    records = []
    for directory in sorted(RUNS.iterdir(), reverse=True):
        if directory.is_dir():
            records.append(run_record(directory))
    return records


def run_dir(run_id: str) -> Path | None:
    if not RUN_ID.match(run_id):
        return None
    directory = RUNS / run_id
    return directory if directory.is_dir() else None


def profiles() -> list[dict]:
    """Identity and shape, not the prompts — the same fields app/main.py serves."""
    found = []
    for path in sorted(PROFILES.glob("*.json")):
        document = read_json(path)
        found.append(
            {
                "id": document.get("id", path.stem),
                "label": document.get("label", path.stem),
                "passes": [
                    p.get("name", "") for p in document.get("passes", []) if isinstance(p, dict)
                ],
            }
        )
    return found


# --------------------------------------------------------------------------
# Starting a new run
# --------------------------------------------------------------------------

class Launch:
    """One `app.cli agent` child, and the log it is producing.

    The agent writes `trace.jsonl` in one go when it finishes, so there is no
    structured stream to tail while it is working. What there is, is the
    terminal renderer on stderr — plain text, because `app/trace.py` drops
    colour when stderr is not a terminal. So the live view shows those lines,
    and the moment the run directory appears the console can switch to the
    real event stream.
    """

    _counter = 0
    _lock = threading.Lock()
    all: dict[str, "Launch"] = {}

    def __init__(self, account: str, profile: str) -> None:
        with Launch._lock:
            Launch._counter += 1
            self.id = f"launch-{Launch._counter}"
            Launch.all[self.id] = self

        self.account = account
        self.profile = profile
        self.started = time.time()
        self.lines: list[str] = []
        self.run_id = ""
        self.returncode: int | None = None
        # `ALL` runs every statement in one batch. The console could previously
        # start exactly one document at a time, which meant adding files and
        # then picking a single one of them — the opposite of what anybody
        # wants from a page that lists seven statements.
        self.command = [sys.executable, "-m", "app.cli", "agent"]
        if account == ALL:
            self.command += ["--all", "--parallel", "4"]
        else:
            self.command += ["--account", account]
        self.command += ["--profile", profile]
        # Before, so a directory that already existed is never mistaken for
        # the one this launch is about to create.
        self._known = {p.name for p in RUNS.iterdir()} if RUNS.is_dir() else set()

        self.process = subprocess.Popen(
            self.command,
            cwd=str(BACKEND),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env={**os.environ, "PYTHONUNBUFFERED": "1", "NO_COLOR": "1"},
        )
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        for line in self.process.stdout:  # type: ignore[union-attr]
            self.lines.append(line.rstrip("\n"))
            if not self.run_id:
                self._look_for_directory()
        self.returncode = self.process.wait()
        self._look_for_directory()

    def _look_for_directory(self) -> None:
        if self.run_id or not RUNS.is_dir():
            return
        for directory in RUNS.iterdir():
            if directory.name not in self._known and directory.name.endswith(self.account):
                self.run_id = directory.name
                return

    def state(self, since: int = 0) -> dict:
        return {
            "id": self.id,
            "account": self.account,
            "profile": self.profile,
            "command": " ".join(self.command),
            "run_id": self.run_id,
            "running": self.returncode is None,
            "returncode": self.returncode,
            "seconds": round(time.time() - self.started, 1),
            "total_lines": len(self.lines),
            "lines": self.lines[since:],
        }


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "CrazyMonkeyConsole/1.0"

    # -- plumbing ----------------------------------------------------------

    def log_message(self, fmt: str, *args) -> None:
        # One line per request, without the double timestamp the default adds.
        sys.stderr.write(f"  {self.command} {self.path} — {fmt % args}\n")

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def json(self, payload, code: int = 200) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def fail(self, code: int, message: str) -> None:
        self.json({"error": message}, code)

    def text(self, body: str, content_type: str = "text/plain; charset=utf-8") -> None:
        self._send(200, body.encode("utf-8"), content_type)

    # -- routing -----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        try:
            if path.startswith("/api/"):
                self.api(path, query)
            else:
                self.static(path)
        except BrokenPipeError:
            pass  # the browser navigated away mid-response
        except Exception as exc:  # noqa: BLE001 — a dev server that dies is useless
            self.fail(500, f"{type(exc).__name__}: {exc}")

    do_HEAD = do_GET

    def upload(self) -> None:
        """Take a statement PDF from the browser and put it where runs find it.

        The console could only offer documents that happened to be in the
        repository, which makes it a demo of one dataset rather than a way to
        process a document. A PDF arrives as raw bytes with its name in the
        query string, lands in the statements directory, and then appears in the
        picker like any other.

        Deliberately narrow. The name is reduced to its final component and must
        look like a filename and nothing else, so nothing here can be talked
        into writing outside that directory. PDFs only — the extraction pass
        reads PDFs, and anything else would fail later and less clearly.
        """
        parsed = urlparse(self.path)
        wanted = parse_qs(parsed.query).get("name", [""])[0]
        name = Path(wanted).name
        if not name.lower().endswith(".pdf") or not FILENAME.match(name):
            self.fail(400, f"not a pdf filename: {wanted!r}")
            return

        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= 40 * 1024 * 1024:
            self.fail(400, "empty upload, or larger than 40MB")
            return

        blob = self.rfile.read(length)
        if not blob.startswith(b"%PDF"):
            self.fail(400, "that file is not a PDF")
            return

        target = statements_dir() / name
        target.write_bytes(blob)
        self.json({"filename": name, "account": Path(name).stem.split("_")[-1]})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/upload":
            self.upload()
            return
        if parsed.path != "/api/launch":
            self.fail(404, "no such endpoint")
            return
        if not ALLOW_NEW_RUNS:
            self.fail(403, "this server was started with --no-new-runs")
            return

        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self.fail(400, "body is not JSON")
            return

        account = str(body.get("account", ""))
        profile = str(body.get("profile", ""))
        if account != ALL and not ACCOUNT.match(account):
            self.fail(400, f"not an account code: {account!r}")
            return
        if not PROFILE_ID.match(profile):
            self.fail(400, f"not a profile id: {profile!r}")
            return
        if account != ALL and not any(account in p.stem for p in statements_dir().glob("*.pdf")):
            self.fail(400, f"no statement matches {account!r}")
            return
        if not (PROFILES / f"{profile}.json").is_file():
            self.fail(400, f"no profile {profile!r}")
            return

        launch = Launch(account, profile)
        sys.stderr.write(f"\n  launched: {' '.join(launch.command)}\n\n")
        self.json(launch.state())

    # -- the API -----------------------------------------------------------

    def api(self, path: str, query: dict) -> None:
        parts = [p for p in path.split("/") if p][1:]  # drop "api"

        if parts == ["health"]:
            self.json(
                {
                    "status": "ok",
                    "root": str(ROOT),
                    "runs": len(list_runs()),
                    "new_runs_allowed": ALLOW_NEW_RUNS,
                    "statements": statements_dir().is_dir(),
                }
            )

        elif parts == ["runs"]:
            self.json(
                {
                    "latest": (OUTPUTS / "latest").read_text(encoding="utf-8").strip()
                    if (OUTPUTS / "latest").is_file()
                    else "",
                    "runs": list_runs(),
                }
            )

        elif parts == ["examples"]:
            self.json(
                [
                    {"name": p.name, "bytes": p.stat().st_size}
                    for p in sorted(EXAMPLES.glob("*.json"), reverse=True)
                ]
            )

        elif len(parts) == 2 and parts[0] == "examples":
            target = EXAMPLES / parts[1]
            # resolve() before the comparison, or ../ walks straight out.
            if target.suffix != ".json" or EXAMPLES not in target.resolve().parents:
                self.fail(400, "not an example file")
            elif not target.is_file():
                self.fail(404, "no such example")
            else:
                self.text(target.read_text(encoding="utf-8"), "application/json; charset=utf-8")

        elif parts == ["profiles"]:
            self.json(profiles())

        elif parts == ["statements"]:
            directory = statements_dir()
            self.json(
                [
                    {"account": p.stem.split("_CALDER_", 1)[-1], "filename": p.name}
                    for p in sorted(directory.glob("*.pdf"))
                ]
            )

        elif len(parts) >= 2 and parts[0] == "launch":
            launch = Launch.all.get(parts[1])
            if launch is None:
                self.fail(404, "no such launch")
            else:
                self.json(launch.state(since=int(query.get("since", ["0"])[0])))

        elif parts and parts[0] == "runs":
            self.run_api(parts[1:], query)

        else:
            self.fail(404, "no such endpoint")

    def run_api(self, parts: list[str], query: dict) -> None:
        directory = run_dir(parts[0]) if parts else None
        if directory is None:
            self.fail(404, "no such run")
            return

        if len(parts) == 1:
            self.json(run_record(directory))

        elif parts[1] == "trace":
            trace = directory / "trace.jsonl"
            if not trace.is_file():
                self.fail(404, "this run has no trace.jsonl")
            else:
                self.text(trace.read_text(encoding="utf-8"))

        elif parts[1] == "rows":
            stage = (query.get("stage") or [""])[0]
            name = "rows.json" if not stage else f"rows-{stage}.json"
            # Filenames are built here, never taken from the caller, but the
            # stage still has to be a plain word.
            if stage and not stage.isalnum():
                self.fail(400, "not a stage")
                return
            target = directory / name
            if not target.is_file():
                self.fail(404, f"this run has no {name}")
            else:
                self.text(target.read_text(encoding="utf-8"), "application/json; charset=utf-8")

        elif parts[1] == "file" and len(parts) == 3:
            # Checked against the actual listing rather than parsed, so no
            # traversal is possible whatever the name looks like.
            if parts[2] not in {p.name for p in directory.iterdir() if p.is_file()}:
                self.fail(404, "no such file in this run")
            else:
                self.text((directory / parts[2]).read_text(encoding="utf-8", errors="replace"))

        else:
            self.fail(404, "no such endpoint")

    # -- static files ------------------------------------------------------

    def static(self, path: str) -> None:
        relative = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (HERE / relative).resolve()
        if HERE != target and HERE not in target.parents:
            self.fail(403, "outside the console directory")
            return
        if not target.is_file():
            self.fail(404, "not found")
            return
        kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if kind.startswith("text/") or kind in ("application/javascript", "application/json"):
            kind += "; charset=utf-8"
        self._send(200, target.read_bytes(), kind)


def main(argv: list[str] | None = None) -> int:
    global ALLOW_NEW_RUNS

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--no-new-runs",
        action="store_true",
        help="refuse to start runs; the console says so instead of offering it",
    )
    parser.add_argument("--no-open", action="store_true", help="do not open a browser")
    args = parser.parse_args(argv)
    ALLOW_NEW_RUNS = not args.no_new_runs

    url = f"http://{args.host}:{args.port}/"
    runs = list_runs()
    print(f"CrazyMonkey run console — {url}")
    print(f"  repository   {ROOT}")
    print(f"  runs on disk {len(runs)}" + (f" · newest {runs[0]['run_id']}" if runs else ""))
    print(f"  statements   {statements_dir()}")
    print(
        "  new runs     "
        + ("allowed — the browser asks twice before starting one" if ALLOW_NEW_RUNS
           else "refused (--no-new-runs)")
    )
    print()

    if not args.no_open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
