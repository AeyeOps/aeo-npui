param(
  [int]$Port = 9222,
  [switch]$All,
  [switch]$ListOnly
)

$ErrorActionPreference = "Stop"

if (-not $All -and $Port -eq 0) {
  throw 'Pass -All or -Port <n>'
}

if ($All) {
  $procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'chrome.exe' }
} else {
  $procs = Get-CimInstance Win32_Process |
    Where-Object { $_.Name -eq 'chrome.exe' -and $_.CommandLine -match "--remote-debugging-port=$Port" }
}

if (-not $procs) {
  Write-Output 'NO_MATCHING_PROCESS'
  exit 0
}

if ($ListOnly) {
  $procs | Select-Object ProcessId, CommandLine
  exit 0
}

$procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Write-Output "STOPPED_COUNT=$($procs.Count)"
