param(
  [int]$Port = 9222,
  [string]$ChromePath = 'C:\Program Files\Google\Chrome\Application\chrome.exe',
  [string]$UserDataDir = 'C:\dev\chrome-profile',
  [string]$ProfileDirectory = 'Default',
  [string]$TargetUrl = 'about:blank',
  [switch]$Fresh,
  [switch]$PrintOnly
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ChromePath)) {
  throw "Chrome not found at $ChromePath"
}

New-Item -ItemType Directory -Force -Path $UserDataDir | Out-Null

$arguments = @(
  "--remote-debugging-port=$Port"
  "--user-data-dir=$UserDataDir"
  "--profile-directory=$ProfileDirectory"
  '--new-window'
  '--no-first-run'
  '--no-default-browser-check'
  '--disable-default-apps'
  '--disable-session-crashed-bubble'
  $TargetUrl
)

if ($Fresh) {
  Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Milliseconds 600
}

if ($PrintOnly) {
  [PSCustomObject]@{
    chrome_path = $ChromePath
    user_data_dir = $UserDataDir
    profile_directory = $ProfileDirectory
    port = $Port
    target_url = $TargetUrl
    arguments = $arguments
  } | ConvertTo-Json -Depth 4
  exit 0
}

Start-Process -FilePath $ChromePath -ArgumentList $arguments | Out-Null
Write-Output "LAUNCHED_PORT=$Port"
