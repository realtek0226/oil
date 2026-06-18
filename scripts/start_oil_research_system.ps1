param(
  [string]$HostName = "0.0.0.0",
  [int]$Port = 8036,
  [int]$StartupTimeoutSeconds = 45,
  [switch]$NoBrowser,
  [switch]$KeepRunning
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = $Root

# Some Windows sessions expose both Path and PATH in the process
# environment. Start-Process builds a case-insensitive environment
# dictionary and fails with: "Item has already been added. Key Path/PATH".
# Normalize it before launching uvicorn.
$CurrentPathValue = [Environment]::GetEnvironmentVariable("Path", "Process")
if ([string]::IsNullOrWhiteSpace($CurrentPathValue)) {
  $CurrentPathValue = [Environment]::GetEnvironmentVariable("PATH", "Process")
}
if (-not [string]::IsNullOrWhiteSpace($CurrentPathValue)) {
  [Environment]::SetEnvironmentVariable("PATH", $null, "Process")
  [Environment]::SetEnvironmentVariable("Path", $CurrentPathValue, "Process")
}

$ArtifactDir = Join-Path $Root "artifacts"
New-Item -ItemType Directory -Force -Path $ArtifactDir | Out-Null
$PidFile = Join-Path $ArtifactDir "oil-research-server.pid"
$UrlFile = Join-Path $ArtifactDir "oil-research-server-url.txt"
$OutLog = Join-Path $ArtifactDir "server-$Port.out.log"
$ErrLog = Join-Path $ArtifactDir "server-$Port.err.log"
$LocalUrl = "http://127.0.0.1:$Port/workbench"

function Test-Health {
  param([int]$CandidatePort)
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$CandidatePort/health" -TimeoutSec 3
    return $response.StatusCode -eq 200
  } catch {
    return $false
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

function Stop-ListenerIfProjectPython {
  param([int]$CandidatePort)
  foreach ($pidValue in Get-ListenerPidsByNetstat -CandidatePort $CandidatePort) {
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$pidValue" -ErrorAction SilentlyContinue
    $commandLine = if ($processInfo) { [string]$processInfo.CommandLine } else { "" }
    if ($commandLine -like "*uvicorn*app.main:app*" -or $commandLine -like "*$Root*") {
      Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
      Start-Sleep -Milliseconds 500
    }
  }
}

if (Test-Health -CandidatePort $Port) {
  $listenerPids = Get-ListenerPidsByNetstat -CandidatePort $Port
  if ($KeepRunning) {
    if ($listenerPids.Count -gt 0) { Set-Content -Path $PidFile -Value $listenerPids[0] -Encoding ASCII }
    Set-Content -Path $UrlFile -Value $LocalUrl -Encoding ASCII
    Write-Output ""
    Write-Output "Oil research system is already running."
    if ($listenerPids.Count -gt 0) { Write-Output "Process ID: $($listenerPids[0])" }
    Write-Output "Local URL: $LocalUrl"
    if (-not $NoBrowser) { Start-Process $LocalUrl | Out-Null }
    exit 0
  }
  Write-Output "Existing oil research service detected on port $Port; restarting it to load latest code."
  Stop-ListenerIfProjectPython -CandidatePort $Port
  Start-Sleep -Seconds 1
}

if (Test-Path $PidFile) {
  $pidText = (Get-Content -Path $PidFile -Raw -ErrorAction SilentlyContinue).Trim()
  if ($pidText -match '^\d+$') { Stop-Process -Id ([int]$pidText) -Force -ErrorAction SilentlyContinue }
  Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
}

Stop-ListenerIfProjectPython -CandidatePort $Port

$python = "python"
if (Test-Path "E:\python\python.exe") { $python = "E:\python\python.exe" }

try {
  & $python -c "import fastapi, uvicorn" | Out-Null
} catch {
  Write-Output "Python dependencies are missing. Install requirements first."
  Write-Output "Python command: $python"
  exit 1
}

$arguments = @("-X", "utf8", "-m", "uvicorn", "app.main:app", "--host", $HostName, "--port", "$Port")
$process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $Root -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog -WindowStyle Hidden -PassThru

Set-Content -Path $PidFile -Value $process.Id -Encoding ASCII
Set-Content -Path $UrlFile -Value $LocalUrl -Encoding ASCII

$ready = $false
$deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Seconds 1
  if ($process.HasExited) { break }
  if (Test-Health -CandidatePort $Port) { $ready = $true; break }
}

if (-not $ready) {
  Write-Output "Server did not become ready within $StartupTimeoutSeconds seconds."
  Write-Output "Process ID: $($process.Id)"
  Write-Output "Logs:"
  Write-Output "  $OutLog"
  Write-Output "  $ErrLog"
  Write-Output "Last stderr lines:"
  Get-Content $ErrLog -Tail 40 -ErrorAction SilentlyContinue
  exit 1
}

Write-Output ""
Write-Output "Oil research system started."
Write-Output "Process ID: $($process.Id)"
Write-Output "Local URL: $LocalUrl"
Write-Output "Logs:"
Write-Output "  $OutLog"
Write-Output "  $ErrLog"
Write-Output ""
Write-Output "To stop the server, double-click stop_oil_research_system.bat."

if (-not $NoBrowser) { Start-Process $LocalUrl | Out-Null }
