#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

PORT="${NPU_WINDOWS_CHROME_CDP_PORT:-9222}"
WINDOWS_CHROME_PATH="${NPU_WINDOWS_CHROME_PATH:-C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe}"
WINDOWS_PROFILE_ROOT="${NPU_WINDOWS_CHROME_PROFILE_ROOT:-C:\\dev\\chrome-profile}"
PROFILE_DIRECTORY="${NPU_WINDOWS_CHROME_PROFILE_DIRECTORY:-Default}"
TARGET_URL="${NPU_WINDOWS_CHROME_TARGET_URL:-about:blank}"
WSL_PROFILE_ROOT="${NPU_WSL_CHROME_PROFILE_ROOT:-/mnt/c/dev/chrome-profile}"

pwsh_script() {
  local script_path="$1"
  shift
  pwsh.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w "$script_path")" "$@"
}

case "${1:-}" in
  start)
    shift
    if [[ $# -gt 0 ]]; then
      TARGET_URL="$1"
    fi
    if [[ -f "$WSL_PROFILE_ROOT/$PROFILE_DIRECTORY/Preferences" ]]; then
      python3 "$SCRIPT_DIR/repair_profile_exit_type.py" \
        --profile-root "$WSL_PROFILE_ROOT" \
        --profile-directory "$PROFILE_DIRECTORY" >/dev/null
    fi
    pwsh_script "$SCRIPT_DIR/start_windows_chrome_cdp.ps1" \
      -Port "$PORT" \
      -ChromePath "$WINDOWS_CHROME_PATH" \
      -UserDataDir "$WINDOWS_PROFILE_ROOT" \
      -ProfileDirectory "$PROFILE_DIRECTORY" \
      -TargetUrl "$TARGET_URL" \
      -Fresh
    ;;
  probe)
    shift
    python3 "$SCRIPT_DIR/probe_cdp.py" --port "$PORT" "$@"
    ;;
  stop)
    shift
    pwsh_script "$SCRIPT_DIR/stop_windows_chrome.ps1" -Port "$PORT"
    ;;
  attach)
    shift
    attach_url="${1:-$TARGET_URL}"
    attach_screenshot="${2:-$ROOT_DIR/output/windows-chrome-cdp.png}"
    node "$SCRIPT_DIR/validate_web_over_cdp.mjs" \
      --port "$PORT" \
      --url "$attach_url" \
      --screenshot "$attach_screenshot"
    ;;
  print)
    pwsh_script "$SCRIPT_DIR/start_windows_chrome_cdp.ps1" \
      -Port "$PORT" \
      -ChromePath "$WINDOWS_CHROME_PATH" \
      -UserDataDir "$WINDOWS_PROFILE_ROOT" \
      -ProfileDirectory "$PROFILE_DIRECTORY" \
      -TargetUrl "$TARGET_URL" \
      -PrintOnly
    ;;
  *)
    cat <<EOF
Usage: scripts/windows_chrome_cdp.sh <start|probe|attach|stop|print> [url] [screenshot]

Defaults:
  PORT=$PORT
  WINDOWS_CHROME_PATH=$WINDOWS_CHROME_PATH
  WINDOWS_PROFILE_ROOT=$WINDOWS_PROFILE_ROOT
  WSL_PROFILE_ROOT=$WSL_PROFILE_ROOT
  PROFILE_DIRECTORY=$PROFILE_DIRECTORY
  TARGET_URL=$TARGET_URL
EOF
    exit 1
    ;;
esac
