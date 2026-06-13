$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PidFile = Join-Path $Root "artifacts\oil-research-server.pid"

if (-not (Test-Path $PidFile)) {
  Write-Output "No server PID file found. Nothing to stop."
  exit 0
}

$PidText = (Get-Content -Path $PidFile -Raw).Trim()
if (-not $PidText) {
  Remove-Item -Path $PidFile -Force
  Write-Output "Empty PID file removed."
  exit 0
}

$Process = Get-Process -Id ([int]$PidText) -ErrorAction SilentlyContinue
if ($Process) {
  Stop-Process -Id $Process.Id -Force
  Write-Output "Stopped oil research server process: $($Process.Id)"
} else {
  Write-Output "Server process $PidText is not running."
}

Remove-Item -Path $PidFile -Force
