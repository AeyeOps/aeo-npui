#!/usr/bin/env bash
# One-shot Windows build driver for aeo-npui, invoked from WSL.
#
# This is the WSL-side complement to scripts/build-windows.ps1. It
# exists because `bun run tauri build` cannot run directly against the
# WSL 9P share:
#   1. `tauri build`'s beforeBuildCommand runs Vite, which needs a
#      Windows-native node_modules tree (`bun install` on the Linux
#      side emits Linux symlinks bun can't resolve through Windows
#      Node/Vite).
#   2. cargo compiling ~500 crates over 9P is measurably slower than
#      on a local NTFS drive.
#   3. cmd.exe invoked with a `\\wsl.localhost\…` CWD falls back to
#      C:\Windows (the UNC-is-not-supported path) and can fail
#      silently — see scripts/winlaunch.sh for the same pattern.
#
# Pattern (per user direction): stage the repo into a Windows-local
# directory the current user owns and build from there. We use
# $WIN_BUILD_DIR if set (a Windows path like C:\dev\aeo-npui-build),
# otherwise default to %TEMP%\aeo-npui-build — always writable by the
# logged-in user.
#
# Idempotent: syncs with --delete so re-runs pick up local edits
# without accumulating stale files. Bundles land at
# <WIN_BUILD_DIR>\desktop\src-tauri\target\release\bundle\.
#
# Usage (or `make build-windows`):
#   scripts/make-windows.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if ! command -v cmd.exe >/dev/null; then
  echo "ERROR: cmd.exe not on PATH — scripts/make-windows.sh must run on WSL." >&2
  exit 1
fi

# Pick the powershell flavour. pwsh.exe is preferred (PowerShell 7+,
# installed via winget.txt); powershell.exe is the fallback for first-
# ever bootstraps before pwsh is available.
if command -v pwsh.exe >/dev/null; then
  psh="pwsh.exe"
elif command -v powershell.exe >/dev/null; then
  psh="powershell.exe"
else
  echo "ERROR: neither pwsh.exe nor powershell.exe found." >&2
  exit 1
fi

# Resolve the Windows-local staging directory.
#   WIN_BUILD_DIR env → used verbatim.
#   else             → %TEMP%\aeo-npui-build (per-user, always writable).
if [ -n "${WIN_BUILD_DIR:-}" ]; then
  win_build_dir="$WIN_BUILD_DIR"
else
  win_temp="$(cmd.exe /c 'echo %TEMP%' | tr -d '\r')"
  [ -n "$win_temp" ] || { echo "ERROR: empty Windows %TEMP%." >&2; exit 1; }
  win_build_dir="${win_temp}\\aeo-npui-build"
fi

wsl_build_dir="$(wslpath -u "$win_build_dir")"
mkdir -p "$wsl_build_dir"

echo "make-windows: staging repo → $win_build_dir"
echo "               (wsl path:   $wsl_build_dir)"

# Mirror the working tree excluding anything platform-specific or heavy.
# --delete removes stale files from prior builds. Rsync is preferred;
# fall back to a tar-pipe if rsync isn't present.
if command -v rsync >/dev/null; then
  rsync -a --delete \
    --exclude='/node_modules/' \
    --exclude='/desktop/node_modules/' \
    --exclude='/desktop/dist/' \
    --exclude='/desktop/src-tauri/target/' \
    --exclude='/service/.venv/' \
    --exclude='/.venv/' \
    --exclude='/.git/' \
    --exclude='/.claude/' \
    --exclude='/tmp/' \
    --exclude='__pycache__/' \
    --exclude='.pytest_cache/' \
    --exclude='.ruff_cache/' \
    "$REPO_ROOT/" "$wsl_build_dir/"
else
  (cd "$(dirname "$REPO_ROOT")" && tar cf - \
    --exclude="$(basename "$REPO_ROOT")/node_modules" \
    --exclude="$(basename "$REPO_ROOT")/desktop/node_modules" \
    --exclude="$(basename "$REPO_ROOT")/desktop/dist" \
    --exclude="$(basename "$REPO_ROOT")/desktop/src-tauri/target" \
    --exclude="$(basename "$REPO_ROOT")/service/.venv" \
    --exclude="$(basename "$REPO_ROOT")/.venv" \
    --exclude="$(basename "$REPO_ROOT")/.git" \
    --exclude="$(basename "$REPO_ROOT")/.claude" \
    --exclude="$(basename "$REPO_ROOT")/tmp" \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    --exclude='.ruff_cache' \
    "$(basename "$REPO_ROOT")") \
  | (cd "$wsl_build_dir/.." && rm -rf "$wsl_build_dir" && tar xf - && mv "$(basename "$REPO_ROOT")" "$(basename "$wsl_build_dir")")
fi

# Build from the Windows-local CWD so pwsh/cmd inherit a real drive
# path as their working directory (sidesteps the UNC fallback that
# makes cmd.exe `start` and winget-delegation flaky — same fix as
# scripts/winlaunch.sh).
cd "$wsl_build_dir"

echo "make-windows: invoking $psh scripts/build-windows.ps1"
exec "$psh" -NoProfile -NoLogo -ExecutionPolicy Bypass \
  -File "$(wslpath -w "$wsl_build_dir/scripts/build-windows.ps1")"
