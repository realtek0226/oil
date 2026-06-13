param(
    [Parameter(Mandatory=$true)]
    [string]$ExcelPath,
    [int]$OpenWaitSeconds = 15,
    [int]$RefreshWaitSeconds = 240,
    [int]$UpdateClickX = 0,
    [int]$UpdateClickY = 0,
    [int]$LoginClickX = 0,
    [int]$LoginClickY = 0,
    [string]$ClickConfigPath = ""
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message)
}

function Invoke-ScreenClick {
    param([int]$X, [int]$Y, [string]$Label)
    if ($X -le 0 -or $Y -le 0) { return $false }
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class DesktopMouseClicker {
  [DllImport("user32.dll", CharSet=CharSet.Auto, CallingConvention=CallingConvention.StdCall)]
  public static extern void mouse_event(long dwFlags, long dx, long dy, long cButtons, long dwExtraInfo);
  public const int MOUSEEVENTF_LEFTDOWN = 0x02;
  public const int MOUSEEVENTF_LEFTUP = 0x04;
  public static void LeftClick() {
    mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0);
    mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0);
  }
}
"@ -ErrorAction SilentlyContinue
    Write-Step "Clicking $Label at ($X, $Y)"
    [System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point($X, $Y)
    Start-Sleep -Milliseconds 300
    [DesktopMouseClicker]::LeftClick()
    Start-Sleep -Milliseconds 800
    return $true
}

function Get-WorkbookStamp {
    param([string]$Path)
    $Item = Get-Item -LiteralPath $Path
    return [pscustomobject]@{ LastWriteTime = $Item.LastWriteTime; Length = $Item.Length }
}

function Get-ExcelProcessesBefore {
    @(Get-Process EXCEL -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
}

function Get-NewExcelProcess {
    param([int[]]$BeforeIds)
    $End = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $End) {
        $Processes = @(Get-Process EXCEL -ErrorAction SilentlyContinue | Where-Object { $BeforeIds -notcontains $_.Id })
        if ($Processes.Count -gt 0) {
            return ($Processes | Sort-Object StartTime -Descending | Select-Object -First 1)
        }
        Start-Sleep -Milliseconds 500
    }
    return $null
}

function Activate-ExcelWindow {
    param([System.Diagnostics.Process]$Process, [string]$Title)
    $WshShell = New-Object -ComObject WScript.Shell
    for ($i = 0; $i -lt 20; $i++) {
        try { $Process.Refresh() } catch {}
        if ($Process -and $Process.MainWindowTitle) {
            if ($WshShell.AppActivate($Process.MainWindowTitle)) { return $true }
        }
        if ($WshShell.AppActivate($Title)) { return $true }
        if ($WshShell.AppActivate("Excel")) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

if (-not (Test-Path -LiteralPath $ExcelPath)) {
    throw "Excel file not found: $ExcelPath"
}
$ExcelFullPath = (Resolve-Path -LiteralPath $ExcelPath).Path
if (-not $ClickConfigPath) {
    $ClickConfigPath = Join-Path (Join-Path (Split-Path -Parent $ExcelFullPath) "artifacts") "ganglian_click_config.json"
}
if (Test-Path -LiteralPath $ClickConfigPath) {
    $Config = Get-Content -LiteralPath $ClickConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($UpdateClickX -le 0 -and $Config.update_click_x) { $UpdateClickX = [int]$Config.update_click_x }
    if ($UpdateClickY -le 0 -and $Config.update_click_y) { $UpdateClickY = [int]$Config.update_click_y }
    if ($LoginClickX -le 0 -and $Config.login_click_x) { $LoginClickX = [int]$Config.login_click_x }
    if ($LoginClickY -le 0 -and $Config.login_click_y) { $LoginClickY = [int]$Config.login_click_y }
    Write-Step "Loaded click config: $ClickConfigPath"
}
if ($UpdateClickX -le 0 -or $UpdateClickY -le 0) {
    throw "Missing update button coordinate. Run set_ganglian_click_config.ps1 first, or pass -UpdateClickX/-UpdateClickY."
}

$BeforeStamp = Get-WorkbookStamp -Path $ExcelFullPath
Write-Step "Starting desktop Excel plugin refresh"
Write-Step "Excel path: $ExcelFullPath"
Write-Step "Before stamp: $($BeforeStamp.LastWriteTime), length=$($BeforeStamp.Length)"

$BeforeIds = Get-ExcelProcessesBefore
$Process = Start-Process -FilePath "excel.exe" -ArgumentList @("`"$ExcelFullPath`"") -PassThru
if (-not $Process) { $Process = Get-NewExcelProcess -BeforeIds $BeforeIds }
Start-Sleep -Seconds $OpenWaitSeconds
$Title = [System.IO.Path]::GetFileNameWithoutExtension($ExcelFullPath)
Activate-ExcelWindow -Process $Process -Title $Title | Out-Null
Start-Sleep -Milliseconds 800

# Maximize with keyboard so the coordinate layout is stable.
$WshShell = New-Object -ComObject WScript.Shell
$WshShell.SendKeys('% {SPACE}')
Start-Sleep -Milliseconds 300
$WshShell.SendKeys('x')
Start-Sleep -Seconds 1

if ($LoginClickX -gt 0 -and $LoginClickY -gt 0) {
    Invoke-ScreenClick -X $LoginClickX -Y $LoginClickY -Label "login button" | Out-Null
    Start-Sleep -Seconds 8
    Activate-ExcelWindow -Process $Process -Title $Title | Out-Null
}

Invoke-ScreenClick -X $UpdateClickX -Y $UpdateClickY -Label "update all pages button" | Out-Null
Write-Step "Waiting for refresh: $RefreshWaitSeconds seconds"
Start-Sleep -Seconds $RefreshWaitSeconds

# Save and close using normal Excel shortcuts.
Activate-ExcelWindow -Process $Process -Title $Title | Out-Null
$WshShell.SendKeys('^s')
Start-Sleep -Seconds 3
$WshShell.SendKeys('%{F4}')
Start-Sleep -Seconds 3

$AfterStamp = Get-WorkbookStamp -Path $ExcelFullPath
Write-Step "After stamp: $($AfterStamp.LastWriteTime), length=$($AfterStamp.Length)"
if ($AfterStamp.LastWriteTime -le $BeforeStamp.LastWriteTime -and $AfterStamp.Length -eq $BeforeStamp.Length) {
    throw "Workbook timestamp/size did not change after refresh; update may not have actually run."
}
Write-Step "Desktop Excel plugin refresh finished successfully"
