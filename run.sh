#!/usr/bin/env bash
# One command: install, test, then verify every statement.
set -euo pipefail
cd "$(dirname "$0")"

command -v uv >/dev/null || { echo "uv not found: https://docs.astral.sh/uv/"; exit 1; }

uv sync --quiet
uv run pytest -q
cd backend && uv run python -m app.cli verify "$@"
