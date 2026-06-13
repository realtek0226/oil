param(
    [Parameter(Mandatory=$true)]
    [string]$ExcelPath,
    [int]$OpenWaitSeconds = 10,
    [int]$RefreshWaitSeconds = 240,
    [switch]$Visible,
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

function Release-ComObject {
    param([object]$Object)
    if ($Object) {
        try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($Object) | Out-Null } catch {}
    }
}

function Get-WorkbookStamp {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        $Item = Get-Item -LiteralPath $Path
        return [pscustomobject]@{ LastWriteTime = $Item.LastWriteTime; Length = $Item.Length }
    }
    return $null
}

function Load-UIAutomation {
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
}

function Find-ElementByNameLike {
    param(
        [System.Windows.Automation.AutomationElement]$Root,
        [string[]]$Patterns,
        [int]$TimeoutSeconds = 20
    )
    $EndTime = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $EndTime) {
        foreach ($Pattern in $Patterns) {
            $Condition = New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::NameProperty,
                $Pattern
            )
            $Element = $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $Condition)
            if ($Element) { return $Element }
        }

        $All = $Root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
        foreach ($Element in $All) {
            $Name = $Element.Current.Name
            if (-not $Name) { continue }
            foreach ($Pattern in $Patterns) {
                if ($Name -like "*$Pattern*") { return $Element }
            }
        }
        Start-Sleep -Milliseconds 500
    }
    return $null
}

function Invoke-Element {
    param([System.Windows.Automation.AutomationElement]$Element)
    if (-not $Element) { return $false }
    try {
        $Pattern = $Element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
        $Pattern.Invoke()
        return $true
    } catch {}
    try {
        $Point = $Element.GetClickablePoint()
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point([int]$Point.X, [int]$Point.Y)
        Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class MouseClicker {
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
        [MouseClicker]::LeftClick()
        return $true
    } catch {
        return $false
    }
}


function Invoke-ScreenClick {
    param(
        [int]$X,
        [int]$Y,
        [string]$Label = "screen point"
    )
    if ($X -le 0 -or $Y -le 0) { return $false }
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class CoordinateMouseClicker {
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
    Write-Step "Clicking $Label at screen coordinate ($X, $Y)"
    [System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point($X, $Y)
    Start-Sleep -Milliseconds 200
    [CoordinateMouseClicker]::LeftClick()
    Start-Sleep -Milliseconds 800
    return $true
}

function Export-ControlNames {
    param(
        [System.Windows.Automation.AutomationElement]$Root,
        [string]$Path
    )
    $Lines = New-Object System.Collections.Generic.List[string]
    $All = $Root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($Element in $All) {
        try {
            $Name = $Element.Current.Name
            $ClassName = $Element.Current.ClassName
            $ControlType = $Element.Current.ControlType.ProgrammaticName
            $Rect = $Element.Current.BoundingRectangle
            if ($Name -or $ClassName) {
                $Lines.Add(("Name={0}`tClass={1}`tType={2}`tRect={3},{4},{5},{6}" -f $Name, $ClassName, $ControlType, [int]$Rect.X, [int]$Rect.Y, [int]$Rect.Width, [int]$Rect.Height))
            }
        } catch {}
    }
    Set-Content -LiteralPath $Path -Value $Lines -Encoding UTF8
}

function Get-ExcelRootElement {
    param([int]$WindowHandle)
    for ($i = 0; $i -lt 30; $i++) {
        if ($WindowHandle -ne 0) {
            $Element = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$WindowHandle)
            if ($Element) { return $Element }
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Cannot find Excel main window handle. Run with -Visible and make sure desktop session is unlocked."
}

if (-not (Test-Path -LiteralPath $ExcelPath)) {
    throw "Excel file not found: $ExcelPath"
}

$ExcelFullPath = (Resolve-Path -LiteralPath $ExcelPath).Path
$BeforeStamp = Get-WorkbookStamp -Path $ExcelFullPath
$Excel = $null
$Workbook = $null

if (-not $ClickConfigPath) {
    $ClickConfigPath = Join-Path (Join-Path (Split-Path -Parent $ExcelFullPath) "artifacts") "ganglian_click_config.json"
}
if (Test-Path -LiteralPath $ClickConfigPath) {
    try {
        $ClickConfig = Get-Content -LiteralPath $ClickConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($UpdateClickX -le 0 -and $ClickConfig.update_click_x) { $UpdateClickX = [int]$ClickConfig.update_click_x }
        if ($UpdateClickY -le 0 -and $ClickConfig.update_click_y) { $UpdateClickY = [int]$ClickConfig.update_click_y }
        if ($LoginClickX -le 0 -and $ClickConfig.login_click_x) { $LoginClickX = [int]$ClickConfig.login_click_x }
        if ($LoginClickY -le 0 -and $ClickConfig.login_click_y) { $LoginClickY = [int]$ClickConfig.login_click_y }
        Write-Step "Loaded click config: $ClickConfigPath"
    } catch {
        Write-Step "Click config exists but cannot be parsed: $ClickConfigPath; $($_.Exception.Message)"
    }
}

try {
    Load-UIAutomation
    Write-Step "Starting Ganglian Excel plugin refresh"
    Write-Step "Excel path: $ExcelFullPath"
    Write-Step "Before stamp: $($BeforeStamp.LastWriteTime), length=$($BeforeStamp.Length)"

    $Excel = New-Object -ComObject Excel.Application
    $Excel.Visible = $true
    $Excel.DisplayAlerts = $false
    $Excel.AskToUpdateLinks = $false
    $Workbook = $Excel.Workbooks.Open($ExcelFullPath, 0, $false)
    if ($Workbook.ReadOnly) {
        throw "Workbook opened as read-only. Close other Excel instances/users editing this file, or check file permissions: $ExcelFullPath"
    }
    try { $Excel.WindowState = -4137 } catch {}
    Start-Sleep -Seconds $OpenWaitSeconds

    $Root = Get-ExcelRootElement -WindowHandle $Excel.Hwnd

    # Activate Excel with shell first; the root AutomationElement may not be focusable.
    $WshShell = New-Object -ComObject WScript.Shell
    $WshShell.AppActivate($Excel.Caption) | Out-Null
    Start-Sleep -Milliseconds 500
    try { $Root.SetFocus() } catch { Write-Step "Excel root cannot receive focus; continuing with AppActivate" }
    Start-Sleep -Milliseconds 500

    # Open ribbon search / make ribbon active. This helps UIAutomation materialize add-in controls.
    Start-Sleep -Milliseconds 500
    $WshShell.SendKeys('%')
    Start-Sleep -Milliseconds 800

    Write-Step "Searching for Ganglian ribbon tab"
    $GanglianTab = Find-ElementByNameLike -Root $Root -Patterns @('????2.0', '????', '????', 'Ganglian', 'Mysteel') -TimeoutSeconds 8
    if ($GanglianTab) {
        Write-Step "Ganglian tab/control found: $($GanglianTab.Current.Name). Clicking it."
        Invoke-Element -Element $GanglianTab | Out-Null
        Start-Sleep -Seconds 1
    } else {
        Write-Step "Ganglian tab not found by UIAutomation; continuing."
    }

    if ($LoginClickX -gt 0 -and $LoginClickY -gt 0) {
        Invoke-ScreenClick -X $LoginClickX -Y $LoginClickY -Label "login button" | Out-Null
        Start-Sleep -Seconds 5
    }

    Write-Step "Searching for login button"
    $LoginElement = Find-ElementByNameLike -Root $Root -Patterns @('??', '??', 'Login', 'Sign in') -TimeoutSeconds 8
    if ($LoginElement) {
        Write-Step "Login button found: $($LoginElement.Current.Name). Clicking it."
        if (-not (Invoke-Element -Element $LoginElement)) {
            throw "Login button found but click failed: $($LoginElement.Current.Name)"
        }
        Start-Sleep -Seconds 8
        try {
            $null = $Workbook.Name
        } catch {
            Write-Step "Workbook closed after login. Reopening."
            try { $Excel.Quit() } catch {}
            Start-Sleep -Seconds 3
            $Excel = New-Object -ComObject Excel.Application
            $Excel.Visible = $true
            $Excel.DisplayAlerts = $false
            $Excel.AskToUpdateLinks = $false
            $Workbook = $Excel.Workbooks.Open($ExcelFullPath, 0, $false)
            if ($Workbook.ReadOnly) {
                throw "Workbook reopened as read-only after login. Close other Excel instances/users editing this file, or check file permissions: $ExcelFullPath"
            }
            try { $Excel.WindowState = -4137 } catch {}
            Start-Sleep -Seconds $OpenWaitSeconds
            $Root = Get-ExcelRootElement -WindowHandle $Excel.Hwnd
            try { $Root.SetFocus() } catch { Write-Step "Excel root cannot receive focus after reopen; continuing with AppActivate" }
            Start-Sleep -Milliseconds 500
        }
    } else {
        Write-Step "Login button not visible; assume already logged in."
    }

    if ($UpdateClickX -gt 0 -and $UpdateClickY -gt 0) {
        Write-Step "Using configured update button coordinate"
        $UpdateElement = $null
        Invoke-ScreenClick -X $UpdateClickX -Y $UpdateClickY -Label "update-all-pages button" | Out-Null
    } else {
        Write-Step "Searching for update-all-pages button"
        $UpdateElement = Find-ElementByNameLike -Root $Root -Patterns @('?????', '?????', '?????', '?????', 'Update All', 'Refresh All') -TimeoutSeconds 25
    }
    if (-not $UpdateElement -and -not ($UpdateClickX -gt 0 -and $UpdateClickY -gt 0)) {
        $DiagnosticsPath = Join-Path (Split-Path -Parent $ExcelFullPath) "artifacts\ganglian_excel_controls.txt"
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $DiagnosticsPath) | Out-Null
        Export-ControlNames -Root $Root -Path $DiagnosticsPath
        Write-Step "Control diagnostics exported: $DiagnosticsPath"
        throw "Cannot find update-all-pages button. Use coordinate mode: run set_ganglian_click_config.ps1 first, or rerun with -UpdateClickX/-UpdateClickY."
    } elseif ($UpdateElement) {
        Write-Step "Update button found: $($UpdateElement.Current.Name). Clicking it."
        if (-not (Invoke-Element -Element $UpdateElement)) {
            throw "Update button found but click failed: $($UpdateElement.Current.Name)"
        }
    }

    Write-Step "Waiting for refresh to finish: $RefreshWaitSeconds seconds"
    Start-Sleep -Seconds $RefreshWaitSeconds

    try {
        $Workbook.Save()
        Write-Step "Workbook saved"
    } catch {
        throw "Workbook save failed after refresh: $($_.Exception.Message)"
    }

    $AfterStamp = Get-WorkbookStamp -Path $ExcelFullPath
    Write-Step "After stamp: $($AfterStamp.LastWriteTime), length=$($AfterStamp.Length)"
    if ($AfterStamp.LastWriteTime -le $BeforeStamp.LastWriteTime -and $AfterStamp.Length -eq $BeforeStamp.Length) {
        throw "Workbook timestamp/size did not change after refresh; update may not have actually run."
    }

    Write-Step "Ganglian Excel plugin refresh finished successfully"
} finally {
    if ($Workbook) { try { $Workbook.Close($true) } catch {} }
    if ($Excel) { try { $Excel.Quit() } catch {} }
    Release-ComObject $Workbook
    Release-ComObject $Excel
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}
