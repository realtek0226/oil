param(
    [string]$ExcelPath = "",
    [string]$TaskName = "Zhonglu-OilResearch-DailyExcelImport",
    [string]$RunTime = "08:00",
    [string]$DatabaseUrl = "",
    [string]$DatabaseHost = "",
    [int]$DatabasePort = 5432,
    [string]$DatabaseName = "postgres",
    [string]$DatabaseUser = "postgres",
    [string]$DatabasePassword = "",
    [string]$Schema = "oil_research",
    [switch]$MappedOnly,
    [switch]$ReplaceSource,
    [switch]$RunAtStartup,
    [switch]$RunAtLogon,
    [int]$StartupDelayMinutes = 3
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$RunScript = Join-Path $Root "scripts\run_daily_excel_import.ps1"

if (-not (Test-Path -LiteralPath $RunScript)) {
    throw "Importer wrapper not found: $RunScript"
}

if (-not $ExcelPath) {
    $ExcelPath = Join-Path $Root "模型预测基础数据.xlsx"
}

$ArgumentParts = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$RunScript`"",
    "-ExcelPath", "`"$ExcelPath`"",
    "-Schema", "`"$Schema`""
)
if ($DatabaseUrl) {
    $ArgumentParts += @("-DatabaseUrl", "`"$DatabaseUrl`"")
}
if ($DatabaseHost) {
    $ArgumentParts += @("-DatabaseHost", "`"$DatabaseHost`"", "-DatabasePort", "$DatabasePort", "-DatabaseName", "`"$DatabaseName`"", "-DatabaseUser", "`"$DatabaseUser`"", "-DatabasePassword", "`"$DatabasePassword`"")
}
if ($MappedOnly) {
    $ArgumentParts += "-MappedOnly"
}
if ($ReplaceSource) {
    $ArgumentParts += "-ReplaceSource"
}

$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ($ArgumentParts -join " ") -WorkingDirectory $Root
$Triggers = @((New-ScheduledTaskTrigger -Daily -At $RunTime))
if ($RunAtStartup) {
    $StartupTrigger = New-ScheduledTaskTrigger -AtStartup
    if ($StartupDelayMinutes -gt 0) {
        $StartupTrigger.Delay = "PT$($StartupDelayMinutes)M"
    }
    $Triggers += $StartupTrigger
}
if ($RunAtLogon) {
    $LogonTrigger = New-ScheduledTaskTrigger -AtLogOn
    if ($StartupDelayMinutes -gt 0) {
        $LogonTrigger.Delay = "PT$($StartupDelayMinutes)M"
    }
    $Triggers += $LogonTrigger
}
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Triggers -Settings $Settings -Description "Import Model Prediction Base Data Excel into oil research database." -Force | Out-Null

Write-Host "Scheduled task created or updated: $TaskName"
Write-Host "Daily run time: $RunTime"
Write-Host "Run at startup: $RunAtStartup"
Write-Host "Run at logon: $RunAtLogon"
Write-Host "Startup delay minutes: $StartupDelayMinutes"
Write-Host "Excel path: $ExcelPath"
Write-Host "Database target: $(if ($DatabaseHost) { "$DatabaseHost`:$DatabasePort/$DatabaseName" } elseif ($DatabaseUrl) { 'custom database-url' } else { 'app config default' })"
Write-Host "Schema: $Schema"
Write-Host "Script: $RunScript"
Write-Host "Logs: $(Join-Path $Root 'logs')"
Write-Host "Summary: $(Join-Path $Root 'artifacts\daily_excel_import_summary.json')"
Write-Host "Manual test: powershell -NoProfile -ExecutionPolicy Bypass -File `"$RunScript`" -ExcelPath `"$ExcelPath`" -DatabaseHost <DB-IP> -DatabasePassword <PASSWORD> -DryRun"
Write-Host "Note: -RunAtStartup usually requires administrator PowerShell. If unavailable, use -RunAtLogon."
