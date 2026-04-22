#!/usr/bin/env bash
# Unified bootstrap dispatcher for aeo-npui system prerequisites.
#
# POSIX entry point. Idempotent. Reads the appropriate per-OS manifest
# and invokes the native package manager:
#
#   - Linux (Debian-family): apt-get install $(<bootstrap/apt.txt)   (sudo)
#   - macOS:                 brew install     $(<bootstrap/brew.txt)
#   - WSL-on-Windows:        apt (Linux half) + delegate the Windows
#                            half to pwsh.exe bootstrap.ps1 (winget)
#
# Usage (or: `make bootstrap`):
#   bash bootstrap/bootstrap.sh
#
# On native Windows (no WSL), invoke bootstrap.ps1 directly from pwsh:
#   .\bootstrap\bootstrap.ps1

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

manifest_pkgs() {
  local file="$1"
  [ -f "$file" ] || return 0
  sed -e 's/#.*$//' -e '/^[[:space:]]*$/d' "$file"
}

is_wsl() {
  [ -r /proc/version ] && grep -qiE '(microsoft|wsl)' /proc/version
}

run_linux_apt() {
  mapfile -t pkgs < <(manifest_pkgs "$HERE/apt.txt")
  if [ "${#pkgs[@]}" -eq 0 ]; then
    echo "bootstrap: apt.txt empty; skipping Linux apt."
    return 0
  fi
  echo "bootstrap: apt-get install (${#pkgs[@]} packages; sudo required)"
  printf '  - %s\n' "${pkgs[@]}"
  sudo apt-get update
  sudo apt-get install -y --no-install-recommends "${pkgs[@]}"
}

run_macos_brew() {
  if ! command -v brew >/dev/null 2>&1; then
    echo "ERROR: Homebrew not found. Install from https://brew.sh first." >&2
    return 1
  fi
  mapfile -t pkgs < <(manifest_pkgs "$HERE/brew.txt")
  if [ "${#pkgs[@]}" -gt 0 ]; then
    echo "bootstrap: brew install (${#pkgs[@]} packages)"
    printf '  - %s\n' "${pkgs[@]}"
    brew install "${pkgs[@]}"
  else
    echo "bootstrap: brew.txt empty; skipping brew."
  fi
  echo
  echo "NOTE: Tauri on macOS also needs Xcode Command Line Tools."
  echo "      Run 'xcode-select --install' if you haven't already."
}

# Mirror the Tauri updater signing key from WSL to the current Windows
# user's home if we have one here but it's missing there. The key pair
# was generated in pre-flight §1.1.E; the pubkey lives in
# tauri.conf.json, but the private key must be readable from Windows
# for `tauri build` to emit signed updater artifacts. Without this
# sync, tauri build exits 1 at the updater-signing step (bundles are
# still emitted beforehand, but CI would see a non-zero exit).
sync_tauri_signing_key_to_windows() {
  local src="$HOME/.tauri/aeo-npui.key"
  if [ ! -f "$src" ]; then
    echo "bootstrap: no WSL-side Tauri signing key at $src; nothing to sync."
    return 0
  fi
  local win_userprofile wsl_userprofile dst_dir dst
  win_userprofile="$(cmd.exe /c 'echo %USERPROFILE%' | tr -d '\r')"
  if [ -z "$win_userprofile" ]; then
    echo "bootstrap: could not resolve Windows %USERPROFILE%; skipping key sync." >&2
    return 0
  fi
  wsl_userprofile="$(wslpath -u "$win_userprofile")"
  dst_dir="$wsl_userprofile/.tauri"
  dst="$dst_dir/aeo-npui.key"
  if [ -f "$dst" ]; then
    if cmp -s "$src" "$dst"; then
      echo "bootstrap: Windows-side Tauri key up to date."
    else
      echo "bootstrap: Windows-side Tauri key differs from WSL; preserving Windows copy."
    fi
    return 0
  fi
  mkdir -p "$dst_dir"
  cp "$src" "$dst"
  chmod 600 "$dst" 2>/dev/null || true
  echo "bootstrap: synced Tauri signing key to $win_userprofile\\.tauri\\aeo-npui.key"
}

# Delegate the Windows half of the bootstrap to bootstrap.ps1 via WSL
# interop. Prefers pwsh.exe (PowerShell 7+) over powershell.exe. The
# winget installers may pop UAC dialogs on the Windows desktop —
# intended, per user preference for must-have confirmations to surface.
run_windows_winget_via_wsl() {
  local psh
  if command -v pwsh.exe >/dev/null 2>&1; then
    psh="pwsh.exe"
  elif command -v powershell.exe >/dev/null 2>&1; then
    psh="powershell.exe"
    echo "bootstrap: pwsh.exe not found; falling back to powershell.exe."
    echo "           Microsoft.PowerShell is in winget.txt — after this"
    echo "           bootstrap lands, reruns will use pwsh.exe."
  else
    echo "ERROR: neither pwsh.exe nor powershell.exe on PATH. Cannot run" >&2
    echo "       the Windows-side bootstrap from WSL." >&2
    return 1
  fi

  local win_script
  win_script="$(wslpath -w "$HERE/bootstrap.ps1")"
  echo
  echo "bootstrap: delegating Windows prerequisites to $psh"
  echo "           $win_script"
  # cd to a non-UNC dir so cmd/ps doesn't warn about the WSL CWD; pwsh
  # runs the script via its full Windows path regardless of starting dir.
  (cd /tmp && "$psh" -NoLogo -NoProfile -ExecutionPolicy Bypass \
     -File "$win_script")
}

os="$(uname -s)"
case "$os" in
  Linux)
    if ! command -v apt-get >/dev/null 2>&1; then
      echo "ERROR: apt-get not found. aeo-npui bootstrap currently supports" >&2
      echo "       only Debian-family Linux. Extend bootstrap/ for others." >&2
      exit 1
    fi
    run_linux_apt
    if is_wsl; then
      sync_tauri_signing_key_to_windows
      run_windows_winget_via_wsl
    fi
    ;;
  Darwin)
    run_macos_brew
    ;;
  *)
    echo "ERROR: unsupported OS '$os'. Windows users: run bootstrap.ps1" >&2
    echo "       directly in pwsh/PowerShell." >&2
    exit 1
    ;;
esac

echo
echo "bootstrap: done"
