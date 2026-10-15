# Rebuild the Aveon frontend for the IIS-served site (port 80).
# Run this after any frontend change, then hard-refresh the browser (Ctrl+Shift+R).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Building frontend..." -ForegroundColor Cyan
npm run build
if ($LASTEXITCODE -ne 0) {
    Write-Host "Build FAILED - the live site was not changed." -ForegroundColor Red
    exit 1
}
Write-Host ""
Write-Host "Build complete. dist/ updated - IIS serves it immediately." -ForegroundColor Green
Write-Host "Now hard-refresh the browser: Ctrl+Shift+R" -ForegroundColor Yellow
