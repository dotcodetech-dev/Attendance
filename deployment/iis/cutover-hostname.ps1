<#
.SYNOPSIS
  MIGRATE cutover: move the live device hostname www.aveoniclock.com from the
  eBioServer 'iclock' site to the Aveon reverse-proxy site.

  After this, remote devices that already point at www.aveoniclock.com:80/iclock
  hit Aveon instead of eBioServer — with NO device reconfiguration.

.WARNING
  This redirects your LIVE device fleet. Any device whose serial number is NOT
  registered in Aveon's database will be unrecognised and its punches lost.
  Verify device coverage first (see -WhatIf output / README). Reversible with
  rollback-hostname.ps1.

  Run elevated. Use -WhatIf to preview without changing anything.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string] $HostName = "www.aveoniclock.com",
    [string] $OldSite  = "iclock",
    [string] $NewSite  = "AveonProxy"
)

$ErrorActionPreference = "Stop"
Import-Module WebAdministration

# Pre-flight: backend must be up, proxy must answer.
$backend = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if (-not $backend) { throw "Aveon backend is NOT listening on 127.0.0.1:8000. Start it before cutover." }

Write-Host "Pre-flight OK: backend on 8000." -ForegroundColor Green
Write-Host "Moving binding *:80:$HostName  from '$OldSite'  to '$NewSite'..." -ForegroundColor Cyan

if ($PSCmdlet.ShouldProcess("$HostName", "move port-80 host binding from $OldSite to $NewSite")) {
    # 1. Remove the host binding from the old (eBioServer) site.
    $old = Get-WebBinding -Name $OldSite -Protocol http -Port 80 -HostHeader $HostName -ErrorAction SilentlyContinue
    if ($old) {
        Remove-WebBinding -Name $OldSite -Protocol http -Port 80 -HostHeader $HostName
        Write-Host "Removed $HostName from '$OldSite'." -ForegroundColor Yellow
    } else {
        Write-Host "No $HostName binding found on '$OldSite' (already moved?)." -ForegroundColor Yellow
    }

    # 2. Add it to the Aveon proxy site.
    $exists = Get-WebBinding -Name $NewSite -Protocol http -Port 80 -HostHeader $HostName -ErrorAction SilentlyContinue
    if (-not $exists) {
        New-WebBinding -Name $NewSite -Protocol http -Port 80 -HostHeader $HostName
    }
    # Only start if not already running (starting a started site throws 0x800710D8).
    if ((Get-Website -Name $NewSite).State -ne 'Started') {
        try { Start-Website -Name $NewSite } catch { Write-Host "  (site already running)" }
    }

    Write-Host "Cutover done. $HostName now serves Aveon." -ForegroundColor Green
    Write-Host "Verify from an external machine: http://$HostName/health  ->  {""status"":""ok""}"
    Write-Host "Roll back any time with: .\rollback-hostname.ps1"
}
