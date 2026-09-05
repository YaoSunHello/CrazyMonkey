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
backend_python="${project_dir}/.venv/bin/python"
vite_entrypoint="${project_dir}/frontend/node_modules/vite/bin/vite.js"

validate_port() {
  if [[ ! "$2" =~ ^[0-9]{1,5}$ ]] || (( 10#$2 < 1 || 10#$2 > 65535 )); then
    echo "$1 port must be a number between 1 and 65535."
    exit 2
  fi
}

validate_port Backend "${backend_port}"
validate_port Frontend "${frontend_port}"
backend_port=$((10#${backend_port}))
frontend_port=$((10#${frontend_port}))
if [[ "${backend_port}" == "${frontend_port}" ]]; then
  echo "Backend and frontend must use different ports."
  exit 2
fi

for required_command in uv node curl lsof; do
  if ! command -v "${required_command}" >/dev/null 2>&1; then
    echo "Missing required command: ${required_command}. Install it before starting CrazyMonkey."
    exit 2
  fi
done
node_binary="$(command -v node)"

port_is_busy() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN -t >/dev/null 2>&1
}

owned_process_running() {
  [[ -n "$1" ]] && kill -0 "$1" 2>/dev/null
}

owned_group_running() {
  [[ -n "$1" ]] && {
    kill -0 -- "-$1" 2>/dev/null || owned_process_running "$1"
  }
}

signal_owned_group() {
  [[ -n "$2" ]] || return 0
  # Each service creates its own session before exec. The group therefore
  # contains only that service and its children, never this shell or another
  # application's listeners. The PID fallback covers a signal during startup
  # before the child has created its session.
  kill "-$1" -- "-$2" 2>/dev/null || kill "-$1" "$2" 2>/dev/null || true
}

stop_owned_processes() {
  trap '' INT TERM HUP
  signal_owned_group TERM "${frontend_pid}"
  signal_owned_group TERM "${backend_pid}"
  for _ in {1..20}; do
    if ! owned_group_running "${frontend_pid}" && ! owned_group_running "${backend_pid}"; then
      break
    fi
    sleep 0.25
  done
  signal_owned_group KILL "${frontend_pid}"
  signal_owned_group KILL "${backend_pid}"
  if [[ -n "${frontend_pid}" ]]; then wait "${frontend_pid}" 2>/dev/null || true; fi
  if [[ -n "${backend_pid}" ]]; then wait "${backend_pid}" 2>/dev/null || true; fi
}

trap stop_owned_processes EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

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

echo "Checking the Python environment against uv.lock…"
uv sync --frozen

if [[ ! -f "${vite_entrypoint}" ]]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "Missing npm. Install it to prepare the frontend dependencies."
    exit 2
  fi
  echo "Preparing the frontend environment from package-lock.json…"
  (cd "${project_dir}/frontend" && npm ci)
fi

default_origins="http://localhost:4173,http://127.0.0.1:4173,http://localhost:5173,http://127.0.0.1:5173"
configured_origins="${CRAZYMONKEY_CORS_ORIGINS:-${default_origins}},http://${frontend_host}:${frontend_port}"
backend_origin="http://${backend_host}:${backend_port}"
frontend_origin="http://${frontend_host}:${frontend_port}"

# macOS does not ship setsid(1), and its Bash 3.2 has no wait -n. Python creates
# an isolated process group, then replaces itself with the direct executable.
# The PID captured below is consequently both the service PID and its PGID.
session_exec='import os, sys; os.setsid(); os.execv(sys.argv[1], sys.argv[1:])'

json_endpoint_is_ready() {
  curl --fail --silent --connect-timeout 1 --max-time 2 "$1" |
    "${backend_python}" -c '
import json, sys
try:
    payload = json.load(sys.stdin)
except (ValueError, OSError):
    sys.exit(1)
sys.exit(0 if isinstance(payload, dict) and payload.get(sys.argv[1]) == sys.argv[2] else 1)
' "$2" "$3"
}

service_owns_port() {
  lsof -nP -a -p "$1" -iTCP:"$2" -sTCP:LISTEN -t >/dev/null 2>&1
}

echo "Starting CrazyMonkey backend from ${project_dir} on ${backend_origin}"
CRAZYMONKEY_CORS_ORIGINS="${configured_origins}" \
  "${backend_python}" -c "${session_exec}" "${backend_python}" \
    -m uvicorn app.main:app --app-dir backend --host "${backend_host}" --port "${backend_port}" &
backend_pid=$!

backend_ready="false"
readiness_deadline=$((SECONDS + 30))
while (( SECONDS < readiness_deadline )); do
  if ! owned_process_running "${backend_pid}"; then
    echo "The backend stopped during startup."
    exit 1
  fi
  if service_owns_port "${backend_pid}" "${backend_port}" &&
      json_endpoint_is_ready "${backend_origin}/health" status ok &&
      json_endpoint_is_ready "${backend_origin}/api/ui/v1/capabilities" api_version ui.v1; then
    backend_ready="true"
    break
  fi
  sleep 0.25
done

if [[ "${backend_ready}" != "true" ]]; then
  echo "The backend did not provide a healthy /health and /api/ui/v1/capabilities within 30 seconds."
  exit 1
fi

echo "Starting CrazyMonkey frontend from ${project_dir}/frontend on ${frontend_origin}"
(
  cd "${project_dir}/frontend"
  export VITE_API_MODE=live
  export VITE_API_BASE_URL="${backend_origin}"
  export CRAZYMONKEY_BACKEND_ORIGIN="${backend_origin}"
  exec "${backend_python}" -c "${session_exec}" "${node_binary}" "${vite_entrypoint}" \
    --host "${frontend_host}" --port "${frontend_port}" --strictPort
) &
frontend_pid=$!

frontend_ready="false"
readiness_deadline=$((SECONDS + 30))
while (( SECONDS < readiness_deadline )); do
  if ! owned_process_running "${backend_pid}" || ! owned_process_running "${frontend_pid}"; then
    echo "A CrazyMonkey service stopped during frontend startup."
    exit 1
  fi
  if service_owns_port "${frontend_pid}" "${frontend_port}" &&
      curl --fail --silent --connect-timeout 1 --max-time 2 "${frontend_origin}" >/dev/null 2>&1; then
    frontend_ready="true"
    break
  fi
  sleep 0.25
done

if [[ "${frontend_ready}" != "true" ]]; then
  echo "The frontend did not become ready within 30 seconds."
  exit 1
fi

echo
echo "CrazyMonkey V0 is ready: ${frontend_origin}"
echo "Backend API: ${backend_origin}"
echo "This process owns service groups ${backend_pid} and ${frontend_pid}; Ctrl-C stops them and their children."

while owned_process_running "${backend_pid}" && owned_process_running "${frontend_pid}"; do
  sleep 0.25
done

echo "A CrazyMonkey service exited unexpectedly. Stopping the other owned service."
exit 1
