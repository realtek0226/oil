param(
    [string]$ExcelPath = "",
    [string]$TaskName = "Zhonglu-Ganglian-ExcelPluginRefresh",
    [string]$RunTime = "07:50",
    [int]$OpenWaitSeconds = 8,
    [int]$RefreshWaitSeconds = 240,
    [switch]$Visible,
    [switch]$DesktopMode,
    [switch]$RunAtStartup,
    [switch]$RunAtLogon,
    [int]$StartupDelayMinutes = 3
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$RefreshScript = Join-Path $Root "scripts\refresh_ganglian_excel_plugin.ps1"

if (-not (Test-Path -LiteralPath $RefreshScript)) {
    throw "Refresh script not found: $RefreshScript"
}

if (-not $ExcelPath) {
    $ExcelPath = Join-Path $Root "????????.xlsx"
}

$ArgumentParts = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$RefreshScript`"",
    "-ExcelPath", "`"$ExcelPath`"",
    "-OpenWaitSeconds", "$OpenWaitSeconds",
    "-RefreshWaitSeconds", "$RefreshWaitSeconds"
)
if ($Visible -and -not $DesktopMode) {
    $ArgumentParts += "-Visible"
}

$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ($ArgumentParts -join " ") -WorkingDirectory $Root
$Triggers = @((New-ScheduledTaskTrigger -Daily -At $RunTime))
if ($RunAtStartup) {
    $StartupTrigger = New-ScheduledTaskTrigger -AtStartup
    if ($StartupDelayMinutes -gt 0) { $StartupTrigger.Delay = "PT$($StartupDelayMinutes)M" }
    $Triggers += $StartupTrigger
}
if ($RunAtLogon) {
    $LogonTrigger = New-ScheduledTaskTrigger -AtLogOn
    if ($StartupDelayMinutes -gt 0) { $LogonTrigger.Delay = "PT$($StartupDelayMinutes)M" }
    $Triggers += $LogonTrigger
}
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Triggers -Settings $Settings -Description "Open model base Excel and refresh Ganglian Data 2.0 plugin." -Force | Out-Null

Write-Host "Scheduled task created or updated: $TaskName"
Write-Host "Daily run time: $RunTime"
Write-Host "Excel path: $ExcelPath"
Write-Host "Visible Excel: $Visible"
Write-Host "Desktop mode: $DesktopMode"
Write-Host "Refresh wait seconds: $RefreshWaitSeconds"
Write-Host "Run at startup: $RunAtStartup"
Write-Host "Run at logon: $RunAtLogon"
Write-Host "Script: $RefreshScript"
Write-Host "Manual test: powershell -NoProfile -ExecutionPolicy Bypass -File `"$RefreshScript`" -ExcelPath `"$ExcelPath`" -Visible -RefreshWaitSeconds $RefreshWaitSeconds"
