param(
    [string]$ExcelPath = "",
    [switch]$SetLogin,
    [switch]$SetUpdate,
    [int]$CountdownSeconds = 8
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms

if (-not $ExcelPath) {
    $ExcelPath = Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")) "????????.xlsx"
}
$ExcelFullPath = (Resolve-Path -LiteralPath $ExcelPath).Path
$ArtifactDir = Join-Path (Split-Path -Parent $ExcelFullPath) "artifacts"
New-Item -ItemType Directory -Force -Path $ArtifactDir | Out-Null
$ConfigPath = Join-Path $ArtifactDir "ganglian_click_config.json"

$Config = [ordered]@{}
if (Test-Path -LiteralPath $ConfigPath) {
    try {
        $Existing = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($Property in $Existing.PSObject.Properties) { $Config[$Property.Name] = $Property.Value }
    } catch {}
}

function Capture-Point {
    param([string]$Label)
    Write-Host "Move mouse to [$Label] button. Capturing in $CountdownSeconds seconds..."
    for ($i = $CountdownSeconds; $i -ge 1; $i--) {
        $p = [System.Windows.Forms.Cursor]::Position
        Write-Host ("{0}s  current X={1} Y={2}" -f $i, $p.X, $p.Y)
        Start-Sleep -Seconds 1
    }
    $Point = [System.Windows.Forms.Cursor]::Position
    Write-Host "Captured [$Label]: X=$($Point.X) Y=$($Point.Y)"
    return $Point
}

if (-not $SetLogin -and -not $SetUpdate) {
    $SetUpdate = $true
}
if ($SetLogin) {
    $Point = Capture-Point -Label "login"
    $Config['login_click_x'] = $Point.X
    $Config['login_click_y'] = $Point.Y
}
if ($SetUpdate) {
    $Point = Capture-Point -Label "update all pages"
    $Config['update_click_x'] = $Point.X
    $Config['update_click_y'] = $Point.Y
}
$Config['excel_path'] = $ExcelFullPath
$Config['updated_at'] = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
$Config | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
Write-Host "Saved click config: $ConfigPath"
Get-Content -LiteralPath $ConfigPath -Encoding UTF8
