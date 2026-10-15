# Aveon Camera Service - Start face-recognition attendance service
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = $null
if (Test-Path "venv\Scripts\python.exe") {
    $python = "venv\Scripts\python.exe"
    Write-Host "Using venv: venv\Scripts\python.exe" -ForegroundColor Cyan
} else {
    Write-Host "ERROR: venv not found. From Aveon/camera_service run:" -ForegroundColor Red
    Write-Host "  python -m venv venv" -ForegroundColor Yellow
    Write-Host "  venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Checking uvicorn and app..." -ForegroundColor Gray
try {
    & $python -c "import uvicorn; from app.main import app; print('OK')"
} catch {
    Write-Host "ERROR: Could not import app. Run from Aveon/camera_service folder." -ForegroundColor Red
    Write-Host "If venv is new, run: venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
    & $python -c "import uvicorn; from app.main import app" 2>&1
    exit 1
}

Write-Host ""
Write-Host "Starting camera service at http://localhost:8100" -ForegroundColor Green
Write-Host "  Health:  http://localhost:8100/health" -ForegroundColor Cyan
Write-Host "  Status:  http://localhost:8100/status" -ForegroundColor Cyan
Write-Host "Face detections and punches are logged below. Press Ctrl+C to stop." -ForegroundColor Gray
Write-Host ""
& $python -m uvicorn app.main:app --host 0.0.0.0 --port 8100
