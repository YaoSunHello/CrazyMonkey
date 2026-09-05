#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd "${script_dir}/.." && pwd)"
backend_port="${CRAZYMONKEY_BACKEND_PORT:-8000}"
frontend_port="${CRAZYMONKEY_FRONTEND_PORT:-4173}"
backend_host="127.0.0.1"
frontend_host="127.0.0.1"
backend_pid=""
frontend_pid=""

port_is_busy() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN -t >/dev/null 2>&1
}

stop_owned_processes() {
  if [[ -n "${frontend_pid}" ]] && kill -0 "${frontend_pid}" 2>/dev/null; then
    kill "${frontend_pid}" 2>/dev/null || true
  fi
  if [[ -n "${backend_pid}" ]] && kill -0 "${backend_pid}" 2>/dev/null; then
    kill "${backend_pid}" 2>/dev/null || true
  fi
}

trap stop_owned_processes EXIT INT TERM

if port_is_busy "${backend_port}"; then
  echo "Backend port ${backend_port} is already in use. Nothing was stopped."
  echo "Choose another port, for example: CRAZYMONKEY_BACKEND_PORT=8030 CRAZYMONKEY_FRONTEND_PORT=4200 ./scripts/start-v0.sh"
  exit 2
fi

if port_is_busy "${frontend_port}"; then
  echo "Frontend port ${frontend_port} is already in use. Nothing was stopped."
  echo "Choose another port, for example: CRAZYMONKEY_BACKEND_PORT=8030 CRAZYMONKEY_FRONTEND_PORT=4200 ./scripts/start-v0.sh"
  exit 2
fi

cd "${project_dir}"

if [[ ! -x "${project_dir}/.venv/bin/python" ]]; then
  echo "Preparing the Python environment from uv.lock…"
  uv sync --frozen
fi

if [[ ! -d "${project_dir}/frontend/node_modules" ]]; then
  echo "Preparing the frontend environment from package-lock.json…"
  (cd "${project_dir}/frontend" && npm ci)
fi

default_origins="http://localhost:4173,http://127.0.0.1:4173,http://localhost:5173,http://127.0.0.1:5173"
configured_origins="${CRAZYMONKEY_CORS_ORIGINS:-${default_origins}},http://${frontend_host}:${frontend_port}"

echo "Starting CrazyMonkey backend from ${project_dir} on http://${backend_host}:${backend_port}"
CRAZYMONKEY_CORS_ORIGINS="${configured_origins}" \
  uv run uvicorn app.main:app --app-dir backend --host "${backend_host}" --port "${backend_port}" &
backend_pid=$!

backend_ready="false"
for _ in {1..60}; do
  if ! kill -0 "${backend_pid}" 2>/dev/null; then
    echo "The backend stopped during startup."
    exit 1
  fi
  if curl --fail --silent "http://${backend_host}:${backend_port}/health" >/dev/null 2>&1; then
    backend_ready="true"
    break
  fi
  sleep 0.25
done

if [[ "${backend_ready}" != "true" ]]; then
  echo "The backend did not become healthy within 15 seconds."
  exit 1
fi

echo "Starting CrazyMonkey frontend from ${project_dir}/frontend on http://${frontend_host}:${frontend_port}"
(
  cd "${project_dir}/frontend"
  VITE_API_MODE=live \
  VITE_API_BASE_URL="http://${backend_host}:${backend_port}" \
    npm run dev -- --host "${frontend_host}" --port "${frontend_port}" --strictPort
) &
frontend_pid=$!

frontend_ready="false"
for _ in {1..60}; do
  if ! kill -0 "${frontend_pid}" 2>/dev/null; then
    echo "The frontend stopped during startup."
    exit 1
  fi
  if curl --fail --silent "http://${frontend_host}:${frontend_port}" >/dev/null 2>&1; then
    frontend_ready="true"
    break
  fi
  sleep 0.25
done

if [[ "${frontend_ready}" != "true" ]]; then
  echo "The frontend did not become ready within 15 seconds."
  exit 1
fi

echo
echo "CrazyMonkey V0 is ready: http://${frontend_host}:${frontend_port}"
echo "Backend API: http://${backend_host}:${backend_port}"
echo "This process owns PIDs ${backend_pid} and ${frontend_pid}; Ctrl-C stops only those two."

wait "${backend_pid}" "${frontend_pid}"
