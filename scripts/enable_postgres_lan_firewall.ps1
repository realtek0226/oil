# Run this file in Administrator PowerShell on the database host.
$ErrorActionPreference = "Stop"

$RuleName = "PostgreSQL 5432 LAN Inbound"
$Existing = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue
if (-not $Existing) {
    New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5432 -Profile Any | Out-Null
} else {
    Set-NetFirewallRule -DisplayName $RuleName -Enabled True -Direction Inbound -Action Allow -Profile Any | Out-Null
    Set-NetFirewallPortFilter -AssociatedNetFirewallRule $Existing -Protocol TCP -LocalPort 5432 | Out-Null
}

Get-NetFirewallRule -DisplayName $RuleName | Select-Object DisplayName,Enabled,Direction,Action,Profile | Format-List
Get-NetFirewallPortFilter -AssociatedNetFirewallRule (Get-NetFirewallRule -DisplayName $RuleName) | Format-List
Write-Host "PostgreSQL 5432 inbound firewall rule is enabled for all profiles."
