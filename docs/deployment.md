# Deployment Guide (Windows)

## Backend

1. Create and activate a virtual environment in `backend/`.
2. Install dependencies:
   `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and update SQL Server credentials.
4. Apply `database/schema.sql` in SQL Server.
5. Start API:
   `uvicorn app.main:app --host 0.0.0.0 --port 8000`

## Frontend

1. Run `npm install` in `frontend/`.
2. Run `npm run build`.
3. Host `frontend/dist` from IIS or serve from FastAPI static files.

## Nightly attendance recalculation (recommended)

Raw punches land in `devicelogs`; the `attendance_processed` table holds the
computed daily attendance that reports read from. Keep it current with a nightly
job (Aveon's equivalent of eTimeTrackLite's WebScheduler.exe).

Register in Windows Task Scheduler:
- **Program:** `<backend>\.venv\Scripts\python.exe`
- **Arguments:** `scripts\recalc_attendance.py --days 35`
- **Start in:** `<backend>` (e.g. `D:\ESSL\ESSL_SW\Aveon\backend`)
- **Trigger:** daily, e.g. 01:00.

The `--days 35` rolling window re-folds recent punches (covering late arrivals
and month boundaries); the job is idempotent, so extra runs are harmless. You can
also recalculate on demand from ESS → My Attendance ("Recalculate month"), or via
`POST /api/v1/attendance/recalculate`. Fast reports/exports read from
`GET /api/v1/attendance/processed`.

The `attendance_processed` table is created automatically on backend startup
(`ensure_compat_schema`), so no manual DB step is needed for existing installs.

### CSV / FTP export (optional, for payroll hand-off)

To push computed attendance to a folder or FTP server for payroll (as
eTimeTrackLite's scheduler did), set the `ATTENDANCE_EXPORT_*` keys in
`backend/.env` (see `.env.example`) and add `--export` to the scheduled command:

    Arguments: scripts\recalc_attendance.py --days 35 --export

That processes the window, then writes `attendance_<from>_<to>.csv` (UTF-8 BOM,
Excel-friendly) to `ATTENDANCE_EXPORT_FOLDER` and/or uploads it to the configured
FTP server. On demand: `POST /api/v1/attendance/export`, or the "Download CSV"
button on ESS → My Attendance (`GET /api/v1/attendance/processed/export.csv`).

## Device URL

Configure device server URLs to:
- `http://<server>:8000/iclock/ping`
- `http://<server>:8000/iclock/cdata`
- `http://<server>:8000/iclock/devicecmd`
- `http://<server>:8000/iclock/getrequest`
- `http://<server>:8000/iclock/fdata`

The server also accepts `.aspx` and `.php` variants of each path (e.g.
`/iclock/cdata.aspx`), because different eSSL firmware builds append different
suffixes. You do not configure these — the device chooses; the server handles
all forms.

## Remote (WAN) face readers — the important case

When the face readers are NOT on the same LAN as the server, only the **push
(ADMS/Cloud Server) channel** works. The direct-SDK features (Test Connection,
Read Users, Fetch Photo via SDK, and the "Push via SDK now" button on Transfer)
rely on a direct TCP 4370 connection from the server to the device and will NOT
reach a remote device behind NAT. For remote fleets, drive everything through
the push channel below.

### 1. Make the server reachable from the internet

Pick ONE:
- **Public IP + port-forward:** forward inbound TCP `8000` on the site router to
  the server. Devices use `http://<public-ip>:8000`.
- **Domain name:** point a DNS A-record at the public IP; devices use
  `http://devices.yourdomain.com:8000`. (eSSL devices speak plain HTTP; if you
  need HTTPS, terminate TLS at a reverse proxy such as IIS/nginx on 443 and
  forward to 8000 — many older firmwares do not support TLS, so plain HTTP on a
  restricted port is common.)
- **VPN / DDNS:** if the devices sit in branch offices, a site-to-site VPN or a
  DDNS hostname works the same way.

Open inbound `8000` in Windows Firewall on the server. The device connects TO
the server, so nothing needs opening at the device site.

### 2. Configure each device (on the device keypad)

`Menu > Comm. > Cloud Server Setting` (also labelled ADMS on some models):
- **Server Address / Server Mode:** the public IP or domain from step 1.
- **Server Port:** `8000`.
- **Enable Domain Name:** on, if you used a domain.
- **HTTPS:** off (unless you set up a TLS proxy).
- Leave the URL path as the default `/iclock`.

Reboot the device. Within ~30s its **Last Ping** on the Devices page should
start updating — that confirms the remote device is reaching the server.

### 3. How syncing works for remote devices

- **Attendance & photos** flow in automatically: the device pushes punches to
  `/iclock/cdata` and capture photos to `/iclock/fdata`; they appear in
  Attendance Logs with no action from you.
- **Transfers / enrollment** are delivered as queued commands the device fetches
  on its next `/iclock/getrequest` poll (every few seconds). Start a transfer as
  usual — for remote devices simply wait; do NOT use "Push via SDK now" (that is
  LAN-only). The job completes as the device acknowledges each command.
- If a transfer to a remote device stays at 0 fetched for ~10 minutes, the job
  auto-fails with a message telling you the device never contacted the server —
  re-check the Cloud Server settings and Last Ping, then use Retry.
