#!/bin/bash
set -eu

CM_ORIGINAL_MODE=OFFLINE
case "${1:-}" in
    '') ;;
    --live-model) CM_ORIGINAL_MODE=LIVE_MODEL ;;
    --help|-h)
        printf '%s\n' 'Usage: ./Start Original Layer.command [--live-model]' \
            'Default: original V0 NAV workflow with the offline interpreter.' \
            '--live-model: enable Gemini for reviews you explicitly start.' \
            'Uses backend 8013 and frontend 4174; leaves other servers running.'
        exit 0 ;;
    *) printf '%s\n' 'Unknown option. Use --help or --live-model.' >&2; exit 2 ;;
esac
if [ "$#" -gt 1 ]; then
    printf '%s\n' 'Pass at most one option: --live-model or --help.' >&2
    exit 2
fi

CM_ORIGINAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
if [ "$CM_ORIGINAL_ROOT" != '/Users/leonardaarons-ditson/Desktop/crazymonkey' ]; then
    printf '%s\n' 'Run this launcher from the original Desktop/crazymonkey checkout.' >&2
    exit 1
fi
cd "$CM_ORIGINAL_ROOT"
CM_ORIGINAL_PYTHON="$CM_ORIGINAL_ROOT/backend/.venv/bin/python"
CM_ORIGINAL_VITE="$CM_ORIGINAL_ROOT/frontend/node_modules/vite/bin/vite.js"

for CM_ORIGINAL_FILE in backend/app/legacy_server.py backend/app/legacy_folder.py frontend/src/App.tsx frontend/vite.config.ts; do
    if [ ! -f "$CM_ORIGINAL_FILE" ]; then
        printf 'Required original-layer file is missing: %s\n' "$CM_ORIGINAL_FILE" >&2
        exit 1
    fi
done
if [ ! -x "$CM_ORIGINAL_PYTHON" ]; then
    printf '%s\n' 'Missing backend/.venv/bin/python. Install the repository Python dependencies first.' >&2
    exit 1
fi
if ! command -v node >/dev/null 2>&1 || [ ! -f "$CM_ORIGINAL_VITE" ]; then
    printf '%s\n' 'Node.js and the existing frontend dependencies are required. This launcher does not install them.' >&2
    exit 1
fi

"$CM_ORIGINAL_PYTHON" - <<'PY'
import importlib.util
import socket
import sys

modules = ("fastapi", "uvicorn", "pydantic", "pdfplumber", "pypdf", "multipart",
           "openpyxl", "reportlab", "xlsxwriter", "jsonschema", "httpx", "openai", "dotenv")
missing = [name for name in modules if importlib.util.find_spec(name) is None]
if missing:
    print("Missing Python dependencies: " + ", ".join(missing), file=sys.stderr)
    sys.exit(1)
for port in (8013, 4174):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", port))
    except OSError:
        print(f"Port {port} is unavailable. No existing process was stopped.", file=sys.stderr)
        sys.exit(1)
PY

CM_ORIGINAL_BACKEND_PID=''
CM_ORIGINAL_FRONTEND_PID=''
cleanup_original_layer() {
    trap - EXIT INT TERM
    for CM_ORIGINAL_PID in "$CM_ORIGINAL_FRONTEND_PID" "$CM_ORIGINAL_BACKEND_PID"; do
        if [ -n "$CM_ORIGINAL_PID" ] && kill -0 "$CM_ORIGINAL_PID" 2>/dev/null; then
            kill -TERM "$CM_ORIGINAL_PID" 2>/dev/null || true
        fi
    done
    for CM_ORIGINAL_PID in "$CM_ORIGINAL_FRONTEND_PID" "$CM_ORIGINAL_BACKEND_PID"; do
        if [ -n "$CM_ORIGINAL_PID" ]; then
            wait "$CM_ORIGINAL_PID" 2>/dev/null || true
        fi
    done
}
trap cleanup_original_layer EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

mkdir -p "$CM_ORIGINAL_ROOT/outputs/original-layer-servers"
CM_ORIGINAL_OUTPUT="$(mktemp -d "$CM_ORIGINAL_ROOT/outputs/original-layer-servers/session-XXXXXXXX")"
printf '\nOriginal V0 mode: %s\n' "$CM_ORIGINAL_MODE"
if [ "$CM_ORIGINAL_MODE" = LIVE_MODEL ]; then
    printf '%s\n' 'Reviews you start will send financial source evidence to Google Gemini.' \
        'Starting these servers does not run an audit or make a model request.'
else
    printf '%s\n' 'The original bounded offline interpreter makes no model calls.'
fi
printf '%s\n' 'Backend: http://127.0.0.1:8013' \
    'Open: http://127.0.0.1:4174/?workspace=nav' \
    'Wait for both server-ready messages below. Keep this Terminal window open.' \
    'Press Control-C to stop only the two servers started by this launcher.'
printf 'RELAY output: %s/relay\n' "$CM_ORIGINAL_OUTPUT"
printf '\n%s\n' 'To iterate every file in the supplied folder, use another Terminal:' \
    "cd '/Users/leonardaarons-ditson/Desktop/crazymonkey'" \
    "PYTHONPATH=backend backend/.venv/bin/python -m app.legacy_folder --input '/Users/leonardaarons-ditson/Downloads/Ylookup Hackathon Datasets' --mode OFFLINE" \
    "Add --match '01-bank-statements-to-journal-entries/*' to select that subfolder; repeat --match for more selections." \
    'Use --mode LIVE_MODEL only when you intend to send source evidence to Gemini.' \
    'Unsupported files and missing NAV inputs remain visible in the result.'

CRAZYMONKEY_LEGACY_MODE="$CM_ORIGINAL_MODE" \
CRAZYMONKEY_CORS_ORIGINS='http://127.0.0.1:4174,http://localhost:4174' \
CRAZYMONKEY_RELAY_OUTPUT_DIR="$CM_ORIGINAL_OUTPUT/relay" \
PYTHONPATH="$CM_ORIGINAL_ROOT/backend" \
    "$CM_ORIGINAL_PYTHON" -m uvicorn app.legacy_server:app --app-dir "$CM_ORIGINAL_ROOT/backend" --host 127.0.0.1 --port 8013 &
CM_ORIGINAL_BACKEND_PID=$!

(
    cd "$CM_ORIGINAL_ROOT/frontend"
    VITE_API_MODE=live VITE_API_BASE_URL='http://127.0.0.1:8013' \
    VITE_LEGACY_LAYER=1 VITE_LEGACY_MODE="$CM_ORIGINAL_MODE" \
    CM_ORIGINAL_VITE_CACHE="$CM_ORIGINAL_OUTPUT/vite-cache" \
        exec node --input-type=module <<'JS'
import { createServer } from "vite";

const server = await createServer({
    configLoader: "native",
    cacheDir: process.env.CM_ORIGINAL_VITE_CACHE,
    server: { host: "127.0.0.1", port: 4174, strictPort: true },
});
await server.listen();
server.printUrls();
JS
) &
CM_ORIGINAL_FRONTEND_PID=$!

while kill -0 "$CM_ORIGINAL_BACKEND_PID" 2>/dev/null && kill -0 "$CM_ORIGINAL_FRONTEND_PID" 2>/dev/null; do
    sleep 1
done
printf '%s\n' 'An original-layer server stopped. Shutting down its companion; other servers remain running.' >&2
exit 1
