#!/usr/bin/env bash
# Cross-OS dev launcher: start the Layer-1 service + Tauri dev window.
#
# Starts both halves of the dev loop in parallel:
#   1. Layer-1 service:   uv run npu-service serve --host 127.0.0.1 --port 8765
#   2. Desktop (Tauri):   bun run --cwd desktop tauri dev
#
# Prints PIDs + dev service URL. Traps Ctrl-C and SIGTERM so killing the
# launcher cleans up both children. WSL's localhost forwarding means the
# Windows-side Tauri window reaches a WSL-hosted dev service transparently.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_HOST="${SERVICE_HOST:-127.0.0.1}"
SERVICE_PORT="${SERVICE_PORT:-8765}"
SERVICE_URL="http://${SERVICE_HOST}:${SERVICE_PORT}"

usage() {
  cat <<USAGE
Usage: scripts/launch-dev.sh [-h|--help]

Start both halves of the dev loop in parallel. Ctrl-C stops both.

Environment overrides:
  SERVICE_HOST   interface for npu-service    (default: 127.0.0.1)
  SERVICE_PORT   port for npu-service          (default: 8765)

The Tauri dev URL is fixed by desktop/src-tauri/tauri.conf.json
(Vite dev server on http://localhost:1420). If you change SERVICE_PORT
you must also update tauri.conf.json's CSP connect-src directive.
USAGE
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
esac

# Fail fast if the service port is already bound — otherwise the second
# uvicorn silently exits and Tauri connects to whatever was there first.
if ss -tln | awk '{print $4}' | grep -q ":${SERVICE_PORT}\$"; then
  echo "ERROR: port ${SERVICE_PORT} is already in use. Stop the previous" >&2
  echo "       dev run or pick a different SERVICE_PORT." >&2
  exit 1
fi

cd "$REPO_ROOT"

service_pid=""
desktop_pid=""

cleanup() {
  trap - INT TERM EXIT
  for pid in "$service_pid" "$desktop_pid"; do
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

( cd "$REPO_ROOT/service" && exec uv run npu-service serve \
    --host "$SERVICE_HOST" --port "$SERVICE_PORT" ) &
service_pid=$!

( cd "$REPO_ROOT/desktop" && exec bun run tauri dev ) &
desktop_pid=$!

echo "launch-dev.sh: service pid=${service_pid} url=${SERVICE_URL}"
echo "launch-dev.sh: desktop pid=${desktop_pid} (bun run tauri dev)"
echo "launch-dev.sh: Ctrl-C to stop both."

# Wait on the first child to exit. When either dies, cleanup kills the
# other via the EXIT trap.
wait -n "$service_pid" "$desktop_pid"
exit $?
