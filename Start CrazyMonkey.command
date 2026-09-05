#!/bin/bash
set -eu

CRAZYMONKEY_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$CRAZYMONKEY_ROOT"
CRAZYMONKEY_PYTHON="$CRAZYMONKEY_ROOT/backend/.venv/bin/python"

if [ ! -x "$CRAZYMONKEY_PYTHON" ]; then
    printf '%s\n' 'CrazyMonkey needs its local Python environment.' \
        'From this repository, run:' \
        '  python3 -m venv backend/.venv' \
        '  backend/.venv/bin/python -m pip install -r backend/requirements.txt'
    exit 1
fi

if ! "$CRAZYMONKEY_PYTHON" - <<'PY'
import importlib.util
import sys

modules = (
    "fastapi", "uvicorn", "pydantic", "pdfplumber", "pypdf", "multipart",
    "pandas", "openpyxl", "reportlab", "xlsxwriter", "jsonschema", "httpx",
    "openai", "dotenv",
)
missing = [name for name in modules if importlib.util.find_spec(name) is None]
if missing:
    print("Missing Python dependencies: " + ", ".join(missing))
    print("Run: backend/.venv/bin/python -m pip install -r backend/requirements.txt")
    sys.exit(1)
PY
then
    exit 1
fi

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    printf '%s\n' 'CrazyMonkey needs Node.js and npm available on PATH to build the frontend.'
    exit 1
fi

if [ ! -d "$CRAZYMONKEY_ROOT/frontend/node_modules" ]; then
    printf '%s\n' 'Frontend dependencies are missing.' \
        'From this repository, run: (cd frontend && npm ci)'
    exit 1
fi

printf '%s\n' 'Building the CrazyMonkey frontend...'
if ! (cd "$CRAZYMONKEY_ROOT/frontend" && npm run build); then
    printf '%s\n' 'The frontend build failed. Resolve the error above, then run this launcher again.'
    exit 1
fi

printf '\n%s\n' 'Open http://127.0.0.1:8012/?workspace=pack in your browser.' \
    'Keep this Terminal window open. Press Control-C to stop the server.'
exec "$CRAZYMONKEY_PYTHON" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8012
