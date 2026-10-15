# Aveon Backend - Start API server
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = $null
if (Test-Path ".venv\Scripts\python.exe") {
    $python = ".venv\Scripts\python.exe"
    Write-Host "Using venv: .venv\Scripts\python.exe" -ForegroundColor Cyan
} else {
    $python = "python"
    Write-Host "Using system Python" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "Checking uvicorn and app..." -ForegroundColor Gray
try {
    & $python -c "import uvicorn; from app.main import app; print('OK')"
} catch {
    Write-Host "ERROR: Could not import app. Run from Aveon/backend folder." -ForegroundColor Red
    Write-Host "If venv is new, run: .venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
    & $python -c "import uvicorn; from app.main import app" 2>&1
    exit 1
}

Write-Host ""
Write-Host "Starting backend at http://localhost:8000" -ForegroundColor Green
Write-Host "  Health:  http://localhost:8000/health" -ForegroundColor Cyan
Write-Host "  Docs:    http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop." -ForegroundColor Gray
Write-Host ""
& $python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
