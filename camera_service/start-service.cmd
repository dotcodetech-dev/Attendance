@echo off
rem Aveon camera face-attendance service - launched by scheduled task "AveonCamera"
rem (boot + logon) and revived by "AveonWatchdog" whenever /health fails.
cd /d D:\ESSL\ESSL_SW\Aveon\camera_service
echo [%date% %time%] starting camera service >> service.log
venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8100 >> service.log 2>&1
echo [%date% %time%] camera service exited with code %errorlevel% >> service.log
