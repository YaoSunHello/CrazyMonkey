"""Freeze the console and its recorded runs into a static site.

    python backend/test-simple-frontend/build_static.py
    python backend/test-simple-frontend/build_static.py --batch 20260906-095528

Vercel cannot run this pipeline and there is no configuration that would let it:
a run is minutes of model calls per document against a request ceiling measured
in seconds, it writes into `outputs/runs/`, and it needs a sandbox and an LLM
endpoint. So what gets deployed is everything the console can do **without**
starting a run — open a recorded run, read its trace, see the rows and the
checks, and take the CSV, the JSON and the notes away.

This imports `serve` and calls its own reader functions rather than
reimplementing them, so the snapshot is by construction what that server would
have answered. If the API changes shape, this changes with it or fails loudly.

The one thing a filesystem cannot express is a path that is both a file and a
directory, and the API has two: `/api/runs` beside `/api/runs/<id>`, and
`/api/runs/<id>` beside `/api/runs/<id>/trace`. Those three are written with a
`.json` suffix and `vercel.json` rewrites the clean path onto them. Everything
else is stored at exactly the path the browser asks for.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import serve  # noqa: E402 — the path has to be set first

# Copied verbatim. The console is the console; nothing here rewrites it beyond
# the one flag below.
ASSETS = ("index.html", "js", "assets")

# `?stage=` is a query string, and a static host has no query strings — every
# stage would serve the same rows. With this set, `js/api.js` asks for the path
# segment this build writes instead.
STATIC_FLAG = '<script>window.CM_STATIC = true;</script>\n'

VERCEL = {
    "cleanUrls": False,
    "trailingSlash": False,
    "rewrites": [
        # Order matters: /api/runs must be matched before /api/runs/:id.
        {"source": "/api/runs", "destination": "/api/runs.json"},
        {"source": "/api/examples", "destination": "/api/examples.json"},
        {"source": "/api/runs/:id", "destination": "/api/runs/:id.json"},
    ],
}


class Site:
    """Everything written, counted, so the build can say what it produced."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.files = 0

    def write(self, path: str, body: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        self.files += 1

    def json(self, path: str, payload) -> None:
        self.write(path, json.dumps(payload, default=str, indent=1))

    def copy(self, source: Path, path: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        self.files += 1

    @property
    def megabytes(self) -> float:
        total = sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file())
        return round(total / (1024 * 1024), 1)


def chosen_runs(batches: list[str]) -> list[dict]:
    """The runs to ship.

    All 124 on this disk are 30MB of mostly superseded attempts. Shipping a
    named batch keeps the deployed site to the runs somebody would actually be
    shown, and makes it explicit which ones those are.
    """
    runs = serve.list_runs()
    if not batches:
        newest = runs[0]["batch"] if runs else ""
        batches = [newest]
    wanted = set(batches)
    return [run for run in runs if run["batch"] in wanted]


def build(destination: Path, batches: list[str]) -> Site:
    if destination.exists():
        shutil.rmtree(destination)
    site = Site(destination)

    # -- the console itself -------------------------------------------------
    for name in ASSETS:
        source = HERE / name
        if source.is_dir():
            shutil.copytree(source, destination / name)
            site.files += sum(1 for p in source.rglob("*") if p.is_file())
        else:
            site.copy(source, name)

    page = (destination / "index.html").read_text(encoding="utf-8")
    # Before the first script, so the flag exists by the time api.js is parsed.
    marker = '<script src="js/api.js"></script>'
    if marker not in page:
        raise SystemExit("index.html no longer loads js/api.js — check ASSETS")
    (destination / "index.html").write_text(
        page.replace(marker, STATIC_FLAG + marker), encoding="utf-8"
    )

    # -- the read-only API --------------------------------------------------
    runs = chosen_runs(batches)

    site.json(
        "api/health",
        {
            "status": "ok",
            "root": "static snapshot",
            "runs": len(runs),
            # The launcher hides itself on this. The page then shows what it can
            # do rather than offering a button that cannot work.
            "new_runs_allowed": False,
            "statements": True,
            "static": True,
        },
    )

    latest = serve.OUTPUTS / "latest"
    site.json(
        "api/runs.json",
        {
            "latest": latest.read_text(encoding="utf-8").strip() if latest.is_file() else "",
            "runs": runs,
        },
    )

    for record in runs:
        run_id = record["run_id"]
        directory = serve.RUNS / run_id
        site.json(f"api/runs/{run_id}.json", record)

        trace = directory / "trace.jsonl"
        if trace.is_file():
            site.copy(trace, f"api/runs/{run_id}/trace")

        for source in sorted(directory.glob("rows*.json")):
            # rows.json -> /rows, rows-extract.json -> /rows-extract
            site.copy(source, f"api/runs/{run_id}/{source.stem}")

        for source in sorted(p for p in directory.iterdir() if p.is_file()):
            site.copy(source, f"api/runs/{run_id}/file/{source.name}")

    examples = sorted(serve.EXAMPLES.glob("*.json"), reverse=True)
    site.json("api/examples.json", [{"name": p.name, "bytes": p.stat().st_size} for p in examples])
    for source in examples:
        site.copy(source, f"api/examples/{source.name}")

    # Read straight off profiles/*.json — the dropdown is a selection, never an
    # upload, and this is where its contents come from.
    site.json("api/profiles", serve.profiles())
    site.json(
        "api/statements",
        [
            {"account": p.stem.split("_CALDER_", 1)[-1], "filename": p.name}
            for p in sorted(serve.statements_dir().glob("*.pdf"))
        ],
    )

    site.json("vercel.json", VERCEL)
    return site


def preview(destination: Path, host: str, port: int) -> None:
    """Serve the built site the way the deploy will.

    A plain static server is not a fair check: three paths in this API are a
    file *and* a directory, and on the deploy they only work because
    `vercel.json` rewrites them. Serving without those rewrites would 404 the
    run list and make a correct build look broken. So this reads the rewrites
    out of the file it just wrote and applies them — what you see here is what
    the deploy serves, or the preview is worthless.
    """
    import re
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    rules = []
    for rule in json.loads((destination / "vercel.json").read_text())["rewrites"]:
        # `:id` is path-to-regexp's named parameter, which is what Vercel reads.
        # Escape everything else, then put the one wildcard back.
        pattern = "(?P<id>[^/]+)".join(
            re.escape(part) for part in rule["source"].split(":id")
        )
        rules.append((re.compile(f"^{pattern}$"), rule["destination"]))

    class Preview(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(destination), **kw)

        def do_GET(self):  # noqa: N802
            for pattern, target in rules:
                found = pattern.match(self.path.split("?")[0])
                if found:
                    self.path = target.replace(":id", found.groupdict().get("id", ""))
                    break
            super().do_GET()

        def end_headers(self):
            # Everything here is JSON the browser must not cache between builds.
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def guess_type(self, path):
            # The API is written without extensions on purpose. This receives a
            # filesystem path, which on Windows uses backslashes — checking only
            # for "/api/" silently misses every one of them.
            name = str(path).replace("\\", "/")
            if "/api/" in name and not name.endswith((".js", ".css", ".html", ".pdf")):
                return "application/json"
            return super().guess_type(path)

        def log_message(self, fmt, *args):
            sys.stderr.write(f"  {fmt % args}\n")

    print(f"\n  preview  http://{host}:{port}/   (Ctrl-C to stop)\n")
    ThreadingHTTPServer((host, port), Preview).serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--batch",
        action="append",
        default=[],
        help="a batch id to include; repeatable. Defaults to the newest.",
    )
    parser.add_argument("--out", default=str(HERE / "dist"))
    parser.add_argument("--serve", type=int, metavar="PORT",
                        help="after building, serve it as the deploy would")
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args(argv)

    destination = Path(args.out).resolve()
    site = build(destination, args.batch)
    runs = chosen_runs(args.batch)

    print(f"built {destination}")
    print(f"  files    {site.files}")
    print(f"  size     {site.megabytes} MB")
    print(f"  runs     {len(runs)}")
    for record in runs:
        print(
            f"    {record['run_id']:<28} {record['profile'] or '?':<20}"
            f" {record['rows']:>4} rows  {'accepted' if record['accepted'] else 'not accepted'}"
        )
    print(f"  profiles {', '.join(p['id'] for p in serve.profiles())}")
    print()
    print(f"  vercel deploy --prod --cwd {destination}")

    if args.serve:
        preview(destination, args.host, args.serve)
    return 0


if __name__ == "__main__":
    sys.exit(main())
