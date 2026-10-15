<#
.SYNOPSIS
  Roll the device hostname back to eBioServer. Reverses cutover-hostname.ps1:
  moves *:80:www.aveoniclock.com from the Aveon proxy back to the 'iclock' site.

  Run elevated.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string] $HostName = "www.aveoniclock.com",
    [string] $OldSite  = "iclock",
    [string] $NewSite  = "AveonProxy"
)

$ErrorActionPreference = "Stop"
Import-Module WebAdministration

if ($PSCmdlet.ShouldProcess("$HostName", "move port-80 host binding from $NewSite back to $OldSite")) {
    $onProxy = Get-WebBinding -Name $NewSite -Protocol http -Port 80 -HostHeader $HostName -ErrorAction SilentlyContinue
    if ($onProxy) {
        Remove-WebBinding -Name $NewSite -Protocol http -Port 80 -HostHeader $HostName
        Write-Host "Removed $HostName from '$NewSite'." -ForegroundColor Yellow
    }
    $onOld = Get-WebBinding -Name $OldSite -Protocol http -Port 80 -HostHeader $HostName -ErrorAction SilentlyContinue
    if (-not $onOld) {
        New-WebBinding -Name $OldSite -Protocol http -Port 80 -HostHeader $HostName
    }
    # Only start if not already running (starting a started site throws 0x800710D8).
    if ((Get-Website -Name $OldSite).State -ne 'Started') {
        try { Start-Website -Name $OldSite } catch { Write-Host "  (site already running)" }
    }
    Write-Host "Rolled back. $HostName serves eBioServer ('$OldSite') again." -ForegroundColor Green
}
