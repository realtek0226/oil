param(
    [int]$Seconds = 10
)
Add-Type -AssemblyName System.Windows.Forms
Write-Host "Move mouse to the target button. Printing cursor position for $Seconds seconds..."
$End = (Get-Date).AddSeconds($Seconds)
while ((Get-Date) -lt $End) {
    $p = [System.Windows.Forms.Cursor]::Position
    Write-Host ("{0} X={1} Y={2}" -f (Get-Date -Format "HH:mm:ss"), $p.X, $p.Y)
    Start-Sleep -Milliseconds 500
}
