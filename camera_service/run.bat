@echo off
cd /d "%~dp0"
echo ============================================
echo   Aveon Camera Service - http://localhost:8100
echo ============================================
echo.

set PYTHON=
if exist "venv\Scripts\python.exe" (
  set PYTHON=venv\Scripts\python.exe
  echo Using venv: venv\Scripts\python.exe
) else (
  echo ERROR: venv not found. From Aveon/camera_service run:
  echo   python -m venv venv
  echo   venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)
echo.

echo Checking uvicorn and app...
"%PYTHON%" -c "import uvicorn; from app.main import app; print('OK')" 2>nul
if errorlevel 1 (
  echo ERROR: Could not import app. Run from Aveon/camera_service folder.
  echo If venv is new, run: venv\Scripts\pip install -r requirements.txt
  echo.
  "%PYTHON%" -c "import uvicorn; from app.main import app" 2>&1
  pause
  exit /b 1
)
echo.
echo Starting camera service. Status: http://localhost:8100/status
echo Face detections and punches are logged below. Press Ctrl+C to stop.
echo.
"%PYTHON%" -m uvicorn app.main:app --host 0.0.0.0 --port 8100
pause
