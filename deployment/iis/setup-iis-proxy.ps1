<#
.SYNOPSIS
  Create/refresh an IIS reverse-proxy site that fronts Aveon on port 80 and
  forwards to the uvicorn backend on 127.0.0.1:8000.

.DESCRIPTION
  Because this machine's IIS routes by host header, this adds a NEW site bound
  to its own hostname on port 80. It does NOT touch the existing 'iclock'
  (eBioServerNew) site or any other site.

  Prerequisites (see README.md) — install first, or this script will warn:
    * IIS URL Rewrite 2.1 module
    * Application Request Routing (ARR) 3.0 module

  Run in an ELEVATED PowerShell (Run as Administrator):
    .\setup-iis-proxy.ps1 -HostName aveon.aveoniclock.com

.PARAMETER HostName
  The host header the devices will use, e.g. aveon.aveoniclock.com.
  This name must resolve (public DNS for remote devices) to this server's IP.

.PARAMETER SiteName
  IIS site name to create/update. Default: AveonProxy.

.PARAMETER BackendPort
  Local uvicorn port to forward to. Default: 8000.
#>
param(
    [Parameter(Mandatory = $true)] [string] $HostName,
    [string] $SiteName = "AveonProxy",
    [int]    $BackendPort = 8000
)

$ErrorActionPreference = "Stop"
Import-Module WebAdministration -ErrorAction Stop

# 1. Verify prerequisite modules.
$rewrite = Test-Path "C:\Windows\System32\inetsrv\rewrite.dll"
$arr     = Test-Path "C:\Program Files\IIS\Application Request Routing\requestRouter.dll"
if (-not $rewrite) { Write-Warning "URL Rewrite module NOT found. Install it before the proxy will work (see README.md)." }
if (-not $arr)     { Write-Warning "ARR module NOT found. Install it before the proxy will work (see README.md)." }

# 2. Enable ARR proxy at the server level (idempotent).
if ($arr) {
    try {
        Set-WebConfigurationProperty -PSPath "MACHINE/WEBROOT/APPHOST" `
            -Filter "system.webServer/proxy" -Name "enabled" -Value "True"
        Write-Host "ARR proxy enabled at server level." -ForegroundColor Green
    } catch {
        Write-Warning "Could not enable ARR proxy automatically: $($_.Exception.Message)"
    }
}

# 3. Physical folder: frontend/dist (IIS serves static files directly from here).
#    The web.config is copied there so IIS picks it up; API routes are proxied to uvicorn.
$scriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = (Get-Item (Join-Path $scriptDir "..\..")).FullName
$proxyRoot   = Join-Path $projectRoot "frontend\dist"

if (-not (Test-Path $proxyRoot)) {
    throw "frontend/dist not found at '$proxyRoot'. Run 'npm run build' inside frontend/ first."
}

# Copy web.config into dist so IIS picks it up.
$webConfigSrc = Join-Path $scriptDir "web.config"
Copy-Item -Force $webConfigSrc (Join-Path $proxyRoot "web.config")
Write-Host "Copied web.config to $proxyRoot" -ForegroundColor Cyan

# 4. Create or update the site.
$existing = Get-Website -Name $SiteName -ErrorAction SilentlyContinue
if ($null -eq $existing) {
    New-Website -Name $SiteName -PhysicalPath $proxyRoot -Port 80 -HostHeader $HostName | Out-Null
    Write-Host "Created site '$SiteName' bound to http://${HostName}:80 -> 127.0.0.1:$BackendPort" -ForegroundColor Green
} else {
    Set-ItemProperty "IIS:\Sites\$SiteName" -Name physicalPath -Value $proxyRoot
    # Ensure the host-header binding exists.
    $hasBinding = (Get-WebBinding -Name $SiteName -ErrorAction SilentlyContinue |
                   Where-Object { $_.bindingInformation -eq "*:80:$HostName" })
    if (-not $hasBinding) {
        New-WebBinding -Name $SiteName -Protocol http -Port 80 -HostHeader $HostName
    }
    Write-Host "Updated site '$SiteName' -> http://${HostName}:80 -> 127.0.0.1:$BackendPort" -ForegroundColor Green
}

# 5. If the backend forwards to a non-default port, patch the rewrite target.
if ($BackendPort -ne 8000) {
    $cfg = Join-Path $proxyRoot "web.config"
    (Get-Content $cfg) -replace "127\.0\.0\.1:8000", "127.0.0.1:$BackendPort" | Set-Content $cfg -Encoding UTF8
    Write-Host "Rewrote backend target to 127.0.0.1:$BackendPort in web.config." -ForegroundColor Green
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Make sure the Aveon backend is running on 127.0.0.1:$BackendPort (uvicorn)."
Write-Host "  2. Point DNS for '$HostName' at this server's public IP (remote devices)."
Write-Host "  3. On each device: Cloud Server = $HostName, Port = 80, path /iclock."
Write-Host "  4. Test from another machine:  http://$HostName/health   ->  {""status"":""ok""}"
