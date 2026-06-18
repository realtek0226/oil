param(
    [string]$ExcelPath = "",
    [string]$DatabaseUrl = "",
    [string]$DatabaseHost = "",
    [int]$DatabasePort = 5432,
    [string]$DatabaseName = "postgres",
    [string]$DatabaseUser = "postgres",
    [string]$DatabasePassword = "",
    [string]$Schema = "oil_research",
    [switch]$MappedOnly,
    [switch]$ReplaceSource,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$LogDir = Join-Path $Root "logs"
$ArtifactDir = Join-Path $Root "artifacts"
New-Item -ItemType Directory -Force -Path $LogDir, $ArtifactDir | Out-Null

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogPath = Join-Path $LogDir "daily_excel_import_$Timestamp.log"
$SummaryPath = Join-Path $ArtifactDir "daily_excel_import_summary.json"
$LockPath = Join-Path $ArtifactDir "daily_excel_import.lock"

function Write-Log {
    param([string]$Message)
    $Line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $Line
    Add-Content -Path $LogPath -Value $Line -Encoding UTF8
}

function Convert-ToDatabaseUrl {
    param(
        [string]$HostValue,
        [int]$PortValue,
        [string]$NameValue,
        [string]$UserValue,
        [string]$PasswordValue
    )
    if (-not $HostValue) { return "" }
    $EncodedUser = [System.Uri]::EscapeDataString($UserValue)
    $EncodedPassword = [System.Uri]::EscapeDataString($PasswordValue)
    return "postgresql+psycopg://$EncodedUser`:$EncodedPassword@$HostValue`:$PortValue/$NameValue`?sslmode=disable"
}

if (Test-Path $LockPath) {
    $LockAgeMinutes = ((Get-Date) - (Get-Item $LockPath).LastWriteTime).TotalMinutes
    if ($LockAgeMinutes -lt 120) {
        Write-Log "Previous import is still running or lock file exists: $LockPath"
        exit 2
    }
    Write-Log "Removing stale lock older than 120 minutes: $LockPath"
    Remove-Item $LockPath -Force
}

New-Item -ItemType File -Path $LockPath -Force | Out-Null
try {
    if (-not $ExcelPath) {
        if ($env:GANGLIAN_EXCEL_PATH) {
            $ExcelPath = $env:GANGLIAN_EXCEL_PATH
        } else {
            $ExcelPath = Join-Path $Root "模型预测基础数据.xlsx"
        }
    }

    if (-not (Test-Path -LiteralPath $ExcelPath)) {
        throw "Excel file not found: $ExcelPath"
    }

    if (-not $DatabaseUrl -and $DatabaseHost) {
        $DatabaseUrl = Convert-ToDatabaseUrl -HostValue $DatabaseHost -PortValue $DatabasePort -NameValue $DatabaseName -UserValue $DatabaseUser -PasswordValue $DatabasePassword
    }

    $Python = "python"
    if ($env:PYTHON_EXE) {
        $Python = $env:PYTHON_EXE
    } elseif (Test-Path (Join-Path $Root ".venv\Scripts\python.exe")) {
        $Python = Join-Path $Root ".venv\Scripts\python.exe"
    }

    $StagingExcelPath = Join-Path $ArtifactDir "daily_excel_import_source.xlsx"
    Copy-Item -LiteralPath $ExcelPath -Destination $StagingExcelPath -Force

    # Pass a relative ASCII path to Python. This avoids Windows PowerShell argv encoding
    # problems when the project path or Excel path contains Chinese characters.
    $PythonExcelPath = "artifacts\daily_excel_import_source.xlsx"

    $Args = @(
        "scripts\import_ganglian_excel_timeseries.py",
        "--excel", $PythonExcelPath,
        "--summary-output", "artifacts\daily_excel_import_summary.json"
    )

    if (-not $MappedOnly) {
        $Args += "--all-columns"
    }
    if ($ReplaceSource) {
        $Args += "--replace-source"
    }
    if ($DryRun) {
        $Args += "--dry-run"
    }
    if ($DatabaseUrl) {
        $Args += @("--database-url", $DatabaseUrl)
    }
    if ($Schema) {
        $Args += @("--schema", $Schema)
    }

    Write-Log "Daily Excel import started"
    Write-Log "Excel path: $ExcelPath"
    Write-Log "Staged Excel path: $StagingExcelPath"
    Write-Log "Python Excel arg: $PythonExcelPath"
    Write-Log "Python: $Python"
    Write-Log "Database target: $(if ($DatabaseHost) { "$DatabaseHost`:$DatabasePort/$DatabaseName" } elseif ($DatabaseUrl) { 'custom database-url' } else { 'app config default' })"
    Write-Log "Schema: $Schema"
    Write-Log "Mode: $(if ($MappedOnly) { 'mapped indicators only' } else { 'all sheets and all indicators' })"
    if ($DryRun) { Write-Log "DryRun: parse only, database write disabled" }

    Write-Log "Checking Python dependencies"
    $DependencyCheck = @"
import importlib.util
missing = [name for name in ['pandas', 'openpyxl', 'sqlalchemy', 'psycopg'] if importlib.util.find_spec(name) is None]
if missing:
    print('MISSING_PYTHON_PACKAGES=' + ','.join(missing))
    raise SystemExit(13)
print('Python dependency check passed')
"@
    $DependencyCheckPath = Join-Path $ArtifactDir "daily_excel_dependency_check.py"
    Set-Content -LiteralPath $DependencyCheckPath -Value $DependencyCheck -Encoding UTF8
    $DependencyOutputPath = Join-Path $ArtifactDir "daily_excel_dependency_check_output.log"
    $DependencyErrorPath = Join-Path $ArtifactDir "daily_excel_dependency_check_error.log"
    Remove-Item $DependencyOutputPath, $DependencyErrorPath -Force -ErrorAction SilentlyContinue
    $DependencyProcess = Start-Process -FilePath $Python -ArgumentList @($DependencyCheckPath) -WorkingDirectory $Root -NoNewWindow -Wait -PassThru -RedirectStandardOutput $DependencyOutputPath -RedirectStandardError $DependencyErrorPath
    $DependencyExitCode = $DependencyProcess.ExitCode
    if (Test-Path $DependencyOutputPath) {
        Get-Content -LiteralPath $DependencyOutputPath -Encoding UTF8 | ForEach-Object { Write-Log $_ }
    }
    if (Test-Path $DependencyErrorPath) {
        Get-Content -LiteralPath $DependencyErrorPath -Encoding UTF8 | ForEach-Object { Write-Log $_ }
    }
    if ($DependencyExitCode -ne 0) {
        throw "Python dependency check failed with exit code: $DependencyExitCode. Install missing packages with: python -m pip install pandas openpyxl sqlalchemy psycopg[binary] pydantic pydantic-settings PyYAML requests numpy"
    }

    $ImporterStdoutPath = Join-Path $ArtifactDir "daily_excel_import_stdout.log"
    $ImporterStderrPath = Join-Path $ArtifactDir "daily_excel_import_stderr.log"
    $ImporterCombinedPath = Join-Path $ArtifactDir "daily_excel_import_stdout_stderr.log"
    Remove-Item $ImporterStdoutPath, $ImporterStderrPath, $ImporterCombinedPath -Force -ErrorAction SilentlyContinue
    Write-Log "Running importer; stdout: $ImporterStdoutPath"
    Write-Log "Running importer; stderr: $ImporterStderrPath"

    $Process = Start-Process -FilePath $Python -ArgumentList $Args -WorkingDirectory $Root -NoNewWindow -Wait -PassThru -RedirectStandardOutput $ImporterStdoutPath -RedirectStandardError $ImporterStderrPath
    $ImporterExitCode = $Process.ExitCode

    if (Test-Path $ImporterStdoutPath) {
        Get-Content -LiteralPath $ImporterStdoutPath -Encoding UTF8 | Set-Content -LiteralPath $ImporterCombinedPath -Encoding UTF8
        Get-Content -LiteralPath $ImporterStdoutPath -Encoding UTF8 | ForEach-Object { Write-Log $_ }
    }
    if (Test-Path $ImporterStderrPath) {
        Get-Content -LiteralPath $ImporterStderrPath -Encoding UTF8 | Add-Content -LiteralPath $ImporterCombinedPath -Encoding UTF8
        Get-Content -LiteralPath $ImporterStderrPath -Encoding UTF8 | ForEach-Object { Write-Log $_ }
    }
    if ($ImporterExitCode -ne 0) {
        throw "Importer failed with exit code: $ImporterExitCode. See stderr: $ImporterStderrPath; combined output: $ImporterCombinedPath"
    }

    if (Test-Path $SummaryPath) {
        Write-Log "Summary: $SummaryPath"
    }
    Write-Log "Daily Excel import finished"
} catch {
    Write-Log "Daily Excel import failed: $($_.Exception.Message)"
    exit 1
} finally {
    Remove-Item $LockPath -Force -ErrorAction SilentlyContinue
}
