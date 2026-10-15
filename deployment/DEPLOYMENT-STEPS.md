# Aveon — Client Server Deployment (one-click)

```
Devices (ADMS push, port 80) ─┐
Admin browsers (port 80) ─────┼─> IIS site "Aveon" ── static UI (frontend\dist)
                              │        └─ /api /iclock /health ──> uvicorn backend 127.0.0.1:8000 ──> SQL Server
Scheduled tasks (SYSTEM):     │
  AveonBackend      boot+logon, runs the backend
  AveonWatchdog     every 1 min: /health check, restarts a crashed or stuck backend
  AveonAttendanceRecalc  daily 01:00, recalculates attendance
  AveonFetchAttendance   every 10 min, pulls punches from LAN devices over the eSSL SDK (TCP 4370)
```

---

## 1. Build the package (on the development PC)

```powershell
cd D:\ESSL\ESSL_SW\Aveon\deployment
.\build-client-package.ps1 -DownloadPrereqs -CreateZip
```

Output: `deployment\out\AveonSetup.zip` (~790 MB, fully offline).

- `-DownloadPrereqs` is needed only the first time. Installers are cached in `deployment\prereqs\` and must pass a Microsoft/Python signature check.
- `-ExcludeSqlExpress` builds a ~80 MB package for clients that already run SQL Server:
  `.\build-client-package.ps1 -ExcludeSqlExpress -CreateZip -OutputRoot .\out\AveonSetup-NoSQL`

| Package folder | Contents |
|---|---|
| `INSTALL.cmd` / `UNINSTALL.cmd` | one-click install/upgrade, and removal |
| `install.ps1`, `install-config.psd1` | installer, plus optional unattended answers |
| `prereqs\` | VC++ runtime, Python 3.12, ODBC 18, IIS URL Rewrite, ARR, SQL Server Express |
| `wheels\` | every Python package the backend needs (no internet required) |
| `sdk32\` | eSSL 32-bit zkemkeeper SDK |
| `templates\` | scheduled-task XMLs, `backend.env.template` |
| `app\` | backend, prebuilt `frontend\dist` (+ IIS `web.config`), `database\schema.sql`, watchdog |

## 2. Install on the client server

1. Copy `AveonSetup.zip` to the server and extract it, e.g. to `D:\AveonSetup`.
2. *(Optional, for unattended installs)* fill in `install-config.psd1`.
3. **Double-click `INSTALL.cmd`** and accept the UAC prompt. You are asked for:
   - install folder (default `C:\Aveon`)
   - SQL host / database (`Aveon`) / login (`sa`) / password. If the server already
     has several SQL instances you pick one; the login is **tested before anything
     is installed**. If the password is unknown, the installer either creates a
     dedicated login (when your Windows account is a SQL admin) or offers to
     install a separate SQL Express instance named after the product.
   - web admin password (user `admin`)
   - the server IP address that devices will use (auto-detected)

The installer then does the following. Each step detects first and skips anything already done:

| Step | What happens |
|---|---|
| Prerequisites | VC++ runtime (repaired if stale), Python 3.12 (all users), ODBC Driver 18, IIS role, URL Rewrite, ARR (+ proxy enabled). **SQL Server Express** is installed only if the machine has no SQL Server. |
| App files | copied to the install folder; Python venv created from `wheels\` |
| `backend\.env` | written with a random `SECRET_KEY` (first install only) |
| Database | created if missing. `schema.sql` runs **only on an empty DB**, then the compatibility schema adds all remaining tables. Existing data is never dropped. |
| eSSL SDK | 32-bit DLLs copied to `SysWOW64` and `zkemkeeper.dll` registered |
| IIS | site `Aveon` on `*:80` serving `frontend\dist`. Any other site holding port 80 (e.g. Default Web Site) is stopped. |
| Firewall | inbound TCP 80 allowed (rule `Aveon HTTP`) |
| Services | four SYSTEM scheduled tasks registered; backend started |
| Verify | `http://localhost/health` must answer `ok` (IIS → backend → SQL) |

A summary at the end shows the web URL, the device settings and the log locations.
Full log: `install.log` next to `INSTALL.cmd`. If a restart is requested (VC++, IIS or SQL), restart once.

Preview without changing anything:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -DryRun
```

## 3. Upgrade an existing client

Build a new package, extract it on the server, and double-click `INSTALL.cmd` again.
It stops the backend, replaces the app files and Python packages, and applies any
new database columns/tables. It keeps `backend\.env`, the logs and all data, then
re-registers the tasks and restarts the backend.

## 4. Register devices

1. Open `http://<server-ip>/`, log in as `admin`, go to **Devices**, and add each device
   by **serial number** (it must match the device exactly). Enter IP and SDK port 4370 for LAN devices.
2. On each device: **Comm → Cloud Server / ADMS** = `<server-ip>`, port `80`, HTTPS off. Reboot.
3. **Last Seen** should update within ~30 s. For LAN devices, the 10-minute SDK pull
   (`AveonFetchAttendance`) collects punches even if ADMS push is not configured.

Remote devices over the internet: point a DNS name at the site's public IP, forward
TCP 80 to the server, and use that name as the Cloud Server address.

## 5. Day-to-day operations

| Task | How |
|---|---|
| Change settings | edit `C:\Aveon\backend\.env`, then `schtasks /end /tn AveonBackend` and `schtasks /run /tn AveonBackend` |
| Backend log | `C:\Aveon\backend\service.log` |
| Watchdog log | `C:\Aveon\deployment\watchdog.log` (`tick: backend=ok` every minute) |
| SDK pull log | `C:\Aveon\backend\fetch.log` |
| Recalculate attendance now | ESS → My Attendance → *Recalculate month*, or `backend\.venv\Scripts\python.exe backend\scripts\recalc_attendance.py --days 35` |
| CSV/FTP payroll export | set `ATTENDANCE_EXPORT_*` in `.env`; add `--export` to the AveonAttendanceRecalc task arguments |
| Remove services | `UNINSTALL.cmd` (keeps files, DB and prerequisites) |

## 6. Go-live checklist

- [ ] `INSTALL.cmd` finished with "Aveon is installed and running".
- [ ] `http://<server-ip>/` loads from another PC; `admin` login works.
- [ ] Every device serial is registered, and Last Seen updates.
- [ ] Punches appear in Attendance Logs; a manual recalc succeeds.
- [ ] `watchdog.log` shows `backend=ok` ticks.
- [ ] Reboot the server once: the site and backend come back without anyone logging in.
