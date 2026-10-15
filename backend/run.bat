@echo off
cd /d "%~dp0"
echo ============================================
echo   Aveon Backend - http://localhost:8000
echo ============================================
echo.

set PYTHON=
if exist ".venv\Scripts\python.exe" (
  set PYTHON=.venv\Scripts\python.exe
  echo Using venv: .venv\Scripts\python.exe
) else (
  where python >nul 2>&1
  if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10+ and create venv:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
  )
  set PYTHON=python
  echo Using system Python
)
echo.

echo Checking uvicorn and app...
"%PYTHON%" -c "import uvicorn; from app.main import app; print('OK')" 2>nul
if errorlevel 1 (
  echo ERROR: Could not import app. Run from Aveon/backend folder.
  echo If venv is new, run: .venv\Scripts\pip install -r requirements.txt
  echo.
  "%PYTHON%" -c "import uvicorn; from app.main import app" 2>&1
  pause
  exit /b 1
)
echo.
echo Starting server. Health: http://localhost:8000/health
echo Press Ctrl+C to stop.
echo.
"%PYTHON%" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
pause
