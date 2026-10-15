@echo off
rem Pull attendance from all reachable eSSL devices over the SDK (TCP 4370).
rem Run every 10 min by scheduled task "AveonFetchAttendance". Logs to fetch.log.
cd /d "%~dp0"
echo [%date% %time%] fetch start >> fetch.log
.venv\Scripts\python.exe scripts\fetch_all_attendance.py >> fetch.log 2>&1
echo [%date% %time%] fetch done (exit %errorlevel%) >> fetch.log
