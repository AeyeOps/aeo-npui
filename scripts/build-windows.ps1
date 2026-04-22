# scripts/build-windows.ps1 — Windows release build wrapper for aeo-npui.
#
# Runs `bun run tauri build` inside the Visual Studio Developer shell so
# cargo's `link.exe` invocation sees the MSVC LIB/INCLUDE paths (Windows
# SDK + VCRuntime). Also sets TAURI_SIGNING_PRIVATE_KEY if the local
# minisign key exists, so the updater-artifact signing step succeeds.
#
# Outputs:
#   desktop\src-tauri\target\release\bundle\nsis\aeo-npui_<ver>_x64-setup.exe
#   desktop\src-tauri\target\release\bundle\msi\aeo-npui_<ver>_x64_en-US.msi
#
# Usage (pwsh):
#   .\scripts\build-windows.ps1
#
# Called from WSL:
#   pwsh.exe -NoProfile -File "$(wslpath -w scripts/build-windows.ps1)"

[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'

# --- Locate Visual Studio Build Tools (via vswhere) -------------------
$vswhere = "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path $vswhere)) {
    throw "vswhere.exe not found. Run 'make bootstrap' (or bootstrap.ps1) first."
}
$vsInstallPath = (& $vswhere -all -products '*' `
    -requires 'Microsoft.VisualStudio.Workload.VCTools' `
    -property installationPath -latest 2>$null)
if (-not $vsInstallPath) {
    throw 'Visual Studio with VCTools workload not found. Run bootstrap.'
}
Write-Host "build-windows: using VS at $vsInstallPath"

# --- Enter VS Developer shell (sets PATH, INCLUDE, LIB, LIBPATH) -------
$devshellDll = Join-Path $vsInstallPath 'Common7\Tools\Microsoft.VisualStudio.DevShell.dll'
if (-not (Test-Path $devshellDll)) {
    throw "Microsoft.VisualStudio.DevShell.dll not found at $devshellDll"
}
Import-Module $devshellDll
Enter-VsDevShell -VsInstallPath $vsInstallPath -SkipAutomaticLocation `
    -DevCmdArguments '-arch=x64 -host_arch=x64' | Out-Null

# --- Make cargo + bun reachable ---------------------------------------
$env:PATH = "$env:USERPROFILE\.cargo\bin;" + $env:PATH
$bunExe = "$env:USERPROFILE\AppData\Local\Microsoft\WinGet\Links\bun.exe"
if (-not (Test-Path $bunExe)) {
    $bunExe = 'bun'  # fall back to whatever's on PATH
}

# --- Provide signing key if the local dev key exists -------------------
# The updater plugin's `createUpdaterArtifacts` triggers signing at the
# tail of `tauri build`. Without TAURI_SIGNING_PRIVATE_KEY the build
# produces bundles but exits non-zero at the signing step. The local
# dev key lives at ~/.tauri/aeo-npui.key on WSL. For Windows builds we
# look in $env:USERPROFILE\.tauri\aeo-npui.key (copy it manually if you
# want Windows-native builds to sign) or via WSL path translation when
# called from WSL.
if ($env:TAURI_SIGNING_PRIVATE_KEY) {
    Write-Host 'build-windows: TAURI_SIGNING_PRIVATE_KEY already set (from env).'
} else {
    $winKey = Join-Path $env:USERPROFILE '.tauri\aeo-npui.key'
    if (Test-Path $winKey) {
        $env:TAURI_SIGNING_PRIVATE_KEY = (Get-Content $winKey -Raw)
        Write-Host "build-windows: loaded signing key from $winKey"
    } else {
        Write-Warning @"
TAURI_SIGNING_PRIVATE_KEY not set and no key at $winKey.
The bundles will be produced but the tail-of-build signing step will
exit non-zero. For dev builds you can ignore that — bundles are emitted
before signing. Copy your minisign private key to $winKey to silence.
"@
    }
}

# The key generated in pre-flight §1.1.E is unencrypted, but tauri's
# signer still *prompts* for a password on stdin unless
# TAURI_SIGNING_PRIVATE_KEY_PASSWORD is explicitly set — even to an
# empty string. Without this, `tauri build` hangs indefinitely
# between "Finished 2 bundles" and the end of the signing step.
# Default to empty; user can override by presetting the env var.
if (-not $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD) {
    $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = ''
    Write-Host 'build-windows: TAURI_SIGNING_PRIVATE_KEY_PASSWORD="" (no-password key)'
}

# --- Run the build ----------------------------------------------------
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location (Join-Path $repoRoot 'desktop')

# Ensure Windows-native node_modules exists. When make-windows.sh
# rsync'd a fresh tree, the desktop/node_modules directory was excluded
# (Linux-side node_modules uses WSL-only symlinks Windows Node can't
# resolve). Frozen-lockfile keeps bun.lock authoritative.
Write-Host "build-windows: bun install --frozen-lockfile in $PWD"
& $bunExe install --frozen-lockfile
if ($LASTEXITCODE -ne 0) {
    throw "bun install failed (exit $LASTEXITCODE)"
}

Write-Host ''
Write-Host "build-windows: running '$bunExe run tauri build' in $PWD"
& $bunExe run tauri build
$exit = $LASTEXITCODE

Write-Host ''
Write-Host "build-windows: tauri build exit=$exit"
$bundleRoot = Join-Path $repoRoot 'desktop\src-tauri\target\release\bundle'
if (Test-Path $bundleRoot) {
    Write-Host 'build-windows: bundles produced:'
    Get-ChildItem -Path $bundleRoot -Recurse -File -Include '*.exe', '*.msi' |
        Select-Object -ExpandProperty FullName | ForEach-Object { Write-Host "  $_" }
}
exit $exit
