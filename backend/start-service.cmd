@echo off
rem Aveon backend API - launched by scheduled task "AveonBackend" (boot + logon)
rem and revived by "AveonWatchdog" whenever /health fails. Runs uvicorn in the
rem foreground; the watchdog is the single authority on liveness.
cd /d "%~dp0"
echo [%date% %time%] starting backend >> service.log
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> service.log 2>&1
echo [%date% %time%] backend exited with code %errorlevel% >> service.log
