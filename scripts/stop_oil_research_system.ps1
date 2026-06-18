param(
  [int]$Port = 8036
)

$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ArtifactDir = Join-Path $Root "artifacts"
$PidFile = Join-Path $ArtifactDir "oil-research-server.pid"
$LegacyPidFile = Join-Path $ArtifactDir "oil_research_server.pid"
$UrlFile = Join-Path $ArtifactDir "oil-research-server-url.txt"
$Stopped = New-Object System.Collections.Generic.List[int]

function Stop-ProcessByIdSafe {
  param([int]$ProcessId, [string]$Reason)
  if ($ProcessId -le 0) { return }
  if ($Stopped.Contains($ProcessId)) { return }
  $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
  if (-not $process) { return }
  try {
    Stop-Process -Id $ProcessId -Force -ErrorAction Stop
    $Stopped.Add($ProcessId) | Out-Null
    Write-Output "Stopped oil research server process: $ProcessId ($Reason)"
  } catch {
    Write-Output "Failed to stop process $ProcessId ($Reason): $($_.Exception.Message)"
  }
}

function Get-ListenerPidsByNetstat {
  param([int]$CandidatePort)
  $pids = New-Object System.Collections.Generic.List[int]
  $lines = & cmd /c "netstat -ano -p tcp | findstr LISTENING | findstr :$CandidatePort" 2>$null
  foreach ($line in @($lines)) {
    $parts = ($line -split '\s+') | Where-Object { $_ }
    if ($parts.Count -lt 5) { continue }
    $local = $parts[1]
    $pidText = $parts[$parts.Count - 1]
    if (($local -match ":$CandidatePort$") -and ($pidText -match '^\d+$')) {
      $pidValue = [int]$pidText
      if (-not $pids.Contains($pidValue)) { $pids.Add($pidValue) | Out-Null }
    }
  }
  return @($pids)
}

foreach ($candidatePidFile in @($PidFile, $LegacyPidFile)) {
  if (Test-Path $candidatePidFile) {
    $pidText = (Get-Content -Path $candidatePidFile -Raw -ErrorAction SilentlyContinue).Trim()
    if ($pidText -match '^\d+$') {
      Stop-ProcessByIdSafe -ProcessId ([int]$pidText) -Reason "pid file $([System.IO.Path]::GetFileName($candidatePidFile))"
    } elseif ($pidText) {
      Write-Output "Invalid PID file content removed: $pidText"
    }
  }
}
if (-not (Test-Path $PidFile) -and -not (Test-Path $LegacyPidFile)) {
  Write-Output "No server PID file found. Checking port $Port."
}


# Clean up legacy launcher processes from older local scripts in this workspace.
foreach ($processInfo in Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue) {
  $commandLine = [string]$processInfo.CommandLine
  if (($commandLine -like "*$Root*app.py*" -or $commandLine -like "* app.py*") -and $commandLine -notlike "*codex*") {
    Stop-ProcessByIdSafe -ProcessId ([int]$processInfo.ProcessId) -Reason "legacy app.py"
  }
}

foreach ($pidValue in Get-ListenerPidsByNetstat -CandidatePort $Port) {
  $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$pidValue" -ErrorAction SilentlyContinue
  $commandLine = if ($processInfo) { [string]$processInfo.CommandLine } else { "" }
  if ($commandLine -like "*uvicorn*app.main:app*" -or $commandLine -like "*$Root*" -or $commandLine -like "*app.main:app*--port*$Port*") {
    Stop-ProcessByIdSafe -ProcessId $pidValue -Reason "port $Port"
  }
}

Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
Remove-Item -Path $LegacyPidFile -Force -ErrorAction SilentlyContinue
Remove-Item -Path $UrlFile -Force -ErrorAction SilentlyContinue

if ($Stopped.Count -eq 0) {
  Write-Output "No oil research server process was running."
} else {
  Write-Output "Stopped $($Stopped.Count) process(es)."
}
