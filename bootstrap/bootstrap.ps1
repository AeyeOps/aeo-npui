# Windows bootstrap dispatcher for aeo-npui system prerequisites.
#
# Reads bootstrap/winget.txt and installs each package via winget, then
# runs a set of post-install verifiers for packages whose "is this
# really fully installed?" check isn't captured by winget alone. The
# canonical case is Visual Studio BuildTools 2022 — winget reports it
# installed the moment the *bootstrapper* lands, but the C++ workload
# (Microsoft.VisualStudio.Workload.VCTools) may be missing. Without that
# workload, there's no `cl.exe`/`link.exe` and cargo build fails.
#
# winget self-elevates per package; no need to launch elevated.
#
# Usage:
#   Native Windows (pwsh):   .\bootstrap\bootstrap.ps1
#   From WSL:                handled by bootstrap.sh via pwsh.exe

[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $PSCommandPath
$manifest = Join-Path $here 'winget.txt'
if (-not (Test-Path $manifest)) {
    throw "winget.txt missing at $manifest"
}

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw 'winget not found. Install App Installer from the Microsoft Store first.'
}

# Packages that require `--override` to install the intended workload.
$Overrides = @{
    'Microsoft.VisualStudio.2022.BuildTools' = '--wait --quiet --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended'
}

$pkgs = Get-Content $manifest |
    ForEach-Object { $_ -replace '#.*$', '' } |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -ne '' }

if ($pkgs.Count -eq 0) {
    Write-Host 'bootstrap/winget.txt is empty; nothing to install.'
    exit 0
}

Write-Host 'Installing winget packages:'
$pkgs | ForEach-Object { Write-Host "  - $_" }

foreach ($id in $pkgs) {
    Write-Host ''
    $installArgs = @(
        'install', '--id', $id,
        '--accept-package-agreements',
        '--accept-source-agreements',
        '--silent'
    )
    if ($Overrides.ContainsKey($id)) {
        # --force ensures --override args apply even when winget sees the
        # package as "already installed". Without --force, winget routes
        # to the upgrade path and skips the installer's workload args.
        $installArgs += @('--force', '--override', $Overrides[$id])
        Write-Host "==> winget install --id $id --force --override '$($Overrides[$id])'"
    } else {
        Write-Host "==> winget install --id $id"
    }
    & winget @installArgs
    # 0 = success, -1978335189 = already installed. Treat as success.
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) {
        Write-Warning "winget exit $LASTEXITCODE for $id (non-fatal; continuing)"
    }
}

# --- Post-install verifiers ---------------------------------------------
# Winget's "installed" signal is not enough for products whose real
# payload is workload-gated. Each verifier checks a concrete artifact
# (file/dir) and runs the recovery installer if missing.

function Ensure-VCTools-Workload {
    $vswhere = "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) {
        Write-Warning 'vswhere.exe missing — BuildTools not installed; skipping VCTools check.'
        return
    }
    $bt = & $vswhere -products 'Microsoft.VisualStudio.Product.BuildTools' `
        -requires 'Microsoft.VisualStudio.Workload.VCTools' `
        -property installationPath -latest 2>$null
    if ($bt) {
        Write-Host "verify: VCTools workload present at $bt"
        return
    }

    $installPath = & $vswhere -products 'Microsoft.VisualStudio.Product.BuildTools' `
        -property installationPath -latest 2>$null
    if (-not $installPath) {
        Write-Warning 'verify: BuildTools not found at all — winget install may have failed.'
        return
    }

    Write-Host ''
    Write-Host "verify: BuildTools present at $installPath but VCTools workload MISSING."
    Write-Host '        Running vs_installer.exe modify --add VCTools (passive; UAC expected).'

    $installer = "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vs_installer.exe"
    $modifyArgs = @('modify',
        '--installPath', $installPath,
        '--add', 'Microsoft.VisualStudio.Workload.VCTools',
        '--includeRecommended',
        '--passive', '--norestart')
    & $installer @modifyArgs
    Write-Host "verify: vs_installer.exe exit=$LASTEXITCODE"
}

Write-Host ''
Write-Host 'Post-install verification:'
Ensure-VCTools-Workload

Write-Host ''
Write-Host 'bootstrap: done'
Write-Host ''
Write-Host 'NOTE: New PATH entries (rustup, bun) only apply to NEW shells.'
Write-Host '      Close this terminal and open a new one before `cargo`/`bun`.'
