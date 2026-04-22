#!/usr/bin/env bash
# Launch an installed Windows executable from WSL.
#
# WSL↔Windows interop has a sharp edge: when cmd.exe or pwsh.exe is
# invoked from a WSL-native CWD (/opt/…, /tmp, /home/…), the Windows
# child process inherits a UNC path (\\wsl.localhost\…) as its working
# directory. cmd.exe does not support UNC CWDs, warns "UNC paths are
# not supported. Defaulting to Windows directory", and silently falls
# back to C:\Windows. The fallback often lacks the permissions the
# launched process needs (observed: `start "" <exe>` returns
# "Access is denied." or stalls indefinitely — even for notepad).
#
# Fix: cd into a Windows-local directory the current Windows user
# owns BEFORE invoking cmd.exe. %TEMP% is always user-owned and
# always on a real drive, so it's the safe staging CWD for launches.
#
# Usage:
#   scripts/winlaunch.sh "C:\path\to\program.exe"
#
# To run the installed aeo-npui's principle-#4 WSL-origin smoke test:
#   LAD="$(cmd.exe /c 'echo %LOCALAPPDATA%' | tr -d '\r')"
#   scripts/winlaunch.sh "$LAD\\aeo-npui\\aeo-npui.exe"

set -euo pipefail

if [ $# -ne 1 ]; then
  echo "usage: $0 <windows-exe-path>" >&2
  echo "  e.g. $0 'C:\\Users\\me\\AppData\\Local\\aeo-npui\\aeo-npui.exe'" >&2
  exit 2
fi

exe="$1"

if ! command -v cmd.exe >/dev/null; then
  echo "ERROR: cmd.exe not found on PATH — scripts/winlaunch.sh requires WSL." >&2
  exit 1
fi

# Ask Windows for the current-user %TEMP%, then translate to /mnt/c so
# bash can cd there before handing off to cmd.exe.
win_temp="$(cmd.exe /c 'echo %TEMP%' | tr -d '\r')"
if [ -z "$win_temp" ]; then
  echo "ERROR: empty %TEMP% from Windows — WSL interop may be broken." >&2
  exit 1
fi
wsl_temp="$(wslpath -u "$win_temp")"
if [ ! -d "$wsl_temp" ]; then
  echo "ERROR: $wsl_temp does not exist or isn't accessible from WSL." >&2
  exit 1
fi

# cd into a Windows-local CWD so cmd.exe inherits a real drive path
# instead of falling back to C:\Windows. The empty "" after `start`
# is cmd.exe's window-title slot; required when the exe path itself
# is quoted (otherwise the first quoted string is read as the title).
cd "$wsl_temp"
exec cmd.exe /c start "" "$exe"
