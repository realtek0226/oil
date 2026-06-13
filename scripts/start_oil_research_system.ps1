param(
  [string]$HostName = "0.0.0.0",
  [int]$Port = 8036,
  [int]$MaxPortProbe = 20,
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

$ProcessPath = [Environment]::GetEnvironmentVariable("Path", "Process")
if (-not $ProcessPath) {
  $ProcessPath = [Environment]::GetEnvironmentVariable("PATH", "Process")
}
if ($ProcessPath) {
  [Environment]::SetEnvironmentVariable("PATH", $null, "Process")
  [Environment]::SetEnvironmentVariable("Path", $ProcessPath, "Process")
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$ArtifactDir = Join-Path $Root "artifacts"
New-Item -ItemType Directory -Force -Path $ArtifactDir | Out-Null

function Test-PortFree {
  param([int]$CandidatePort)
  $listener = $null
  try {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $CandidatePort)
    $listener.Start()
    return $true
  } catch {
    return $false
  } finally {
    if ($listener) { $listener.Stop() }
  }
}

function Get-LanAddresses {
  try {
    $addresses = Get-NetIPAddress -AddressFamily IPv4 |
      Where-Object {
        $_.IPAddress -notlike "127.*" -and
        $_.IPAddress -notlike "169.254.*" -and
        $_.PrefixOrigin -ne "WellKnown"
      } |
      Select-Object -ExpandProperty IPAddress -Unique
    return @($addresses)
  } catch {
    return @()
  }
}

try {
  & python -c "import fastapi, uvicorn" | Out-Null
} catch {
  Write-Output "Python dependencies are missing. Please install FastAPI/Uvicorn in this Python environment."
  Write-Output "Current command: python -m uvicorn app.main:app"
  exit 1
}

$SelectedPort = $null
for ($offset = 0; $offset -le $MaxPortProbe; $offset++) {
  $candidate = $Port + $offset
  if (Test-PortFree -CandidatePort $candidate) {
    $SelectedPort = $candidate
    break
  }
}

if (-not $SelectedPort) {
  Write-Output "No free port found from $Port to $($Port + $MaxPortProbe)."
  exit 1
}

$OutLog = Join-Path $ArtifactDir "server-$SelectedPort.out.log"
$ErrLog = Join-Path $ArtifactDir "server-$SelectedPort.err.log"
$PidFile = Join-Path $ArtifactDir "oil-research-server.pid"
$UrlFile = Join-Path $ArtifactDir "oil-research-server-url.txt"

$Args = @(
  "-m", "uvicorn",
  "app.main:app",
  "--host", $HostName,
  "--port", "$SelectedPort"
)

$Process = Start-Process -FilePath "python" `
  -ArgumentList $Args `
  -WorkingDirectory $Root `
  -RedirectStandardOutput $OutLog `
  -RedirectStandardError $ErrLog `
  -WindowStyle Hidden `
  -PassThru

Set-Content -Path $PidFile -Value $Process.Id -Encoding ASCII

$LocalUrl = "http://127.0.0.1:$SelectedPort/login"
Set-Content -Path $UrlFile -Value $LocalUrl -Encoding ASCII

$Ready = $false
for ($i = 0; $i -lt 60; $i++) {
  Start-Sleep -Seconds 1
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$SelectedPort/health" -TimeoutSec 2
    if ($response.StatusCode -eq 200) {
      $Ready = $true
      break
    }
  } catch {
    if ($Process.HasExited) { break }
  }
}

if (-not $Ready) {
  Write-Output "Server did not become ready. Check logs:"
  Write-Output "  $ErrLog"
  Write-Output "  $OutLog"
  exit 1
}

$LanAddresses = Get-LanAddresses
Write-Output ""
Write-Output "Oil research system started."
Write-Output "Process ID: $($Process.Id)"
Write-Output "Local URL: $LocalUrl"
foreach ($ip in $LanAddresses) {
  Write-Output "LAN URL:   http://$ip`:$SelectedPort/login"
}
Write-Output ""
Write-Output "Default account: admin / CHANGE_ME"
Write-Output "Logs:"
Write-Output "  $OutLog"
Write-Output "  $ErrLog"
Write-Output ""
Write-Output "To stop the server, double-click stop_oil_research_system.bat."

if (-not $NoBrowser) {
  Start-Process $LocalUrl | Out-Null
}
