# Aveon Client Installation Manual

## 1. Purpose

This manual explains how to install and run the Aveon Biometric Device Management software on a client Windows machine.

---

## 2. System Requirements

- OS: Windows 10 / Windows 11 / Windows Server
- RAM: 8 GB minimum (16 GB recommended)
- CPU: Intel i5 or above (or equivalent)
- Disk: 20 GB free space minimum
- Network: LAN access to biometric devices

### Required Software

- Python 3.9+ (added to PATH)
- Node.js 18+ (includes npm)
- Microsoft SQL Server (Express/Standard/Enterprise)
- ODBC Driver 18 for SQL Server
- Biometric SDK installed and COM registered (`zkemkeeper`) on the server machine

---

## 3. Package Contents

Deployment package includes:

- `backend/`
- `frontend/`
- `database/schema.sql`
- `install-and-start.cmd` (single-click installer)
- `install-and-start.ps1`
- `scripts/install-client.ps1`
- `scripts/start-client.ps1`
- `scripts/register-services.ps1`

---

## 4. Database Setup

1. Open SQL Server Management Studio (SSMS).
2. Create a new database (example: `AIFace`).
3. Open and execute:
   - `database/schema.sql`
4. Confirm tables are created and admin user is inserted.

---

## 5. Configuration

## 5.1 Backend Environment

Edit `backend/.env`:

```env
APP_ENV=production
APP_DEBUG=false
SECRET_KEY=replace_with_strong_secret
API_V1_PREFIX=/api/v1

ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123

SQLSERVER_SERVER=localhost
SQLSERVER_DATABASE=AIFace
SQLSERVER_USER=sa
SQLSERVER_PASSWORD=your_sql_password
SQLSERVER_DRIVER=ODBC Driver 18 for SQL Server
SQLSERVER_ENCRYPT=no

CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
WEBHOOK_URL=
```

## 5.2 Frontend Environment

Edit `frontend/.env`:

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_BRAND_LOGO_URL=/branding/logo.png
```

To use custom logo:

1. Copy logo image to: `frontend/public/branding/logo.png`
2. Or set another path in `VITE_BRAND_LOGO_URL`.

---

## 6. Installation Methods

## Method A: Single-Click Installation (Recommended)

1. Right-click `install-and-start.cmd`
2. Select **Run as Administrator**

This automatically:

- installs backend dependencies
- installs frontend dependencies
- builds frontend
- starts backend (port 8000) and frontend (port 5173)

## Method B: Manual Installation

From package root:

```powershell
.\scripts\install-client.ps1
.\scripts\start-client.ps1
```

---

## 7. Access URLs

- Frontend: `http://localhost:5173`
- Backend health check: `http://localhost:8000/health`

Default login:

- Username: `admin`
- Password: `admin123`

Change admin password after first login.

---

## 8. Service Mode (Auto-start after Reboot)

Use NSSM (Non-Sucking Service Manager).

1. Install NSSM.
2. Run:

```powershell
.\scripts\register-services.ps1
```

This creates and starts:

- `AveonBackend`
- `AveonFrontend`

---

## 9. Firewall and Network

Allow inbound ports if remote users access the app:

- 5173 (frontend)
- 8000 (backend)

If same machine only, localhost access is enough.

---

## 10. Device Connection Checklist

For each device:

1. Confirm device and server are on same network.
2. Set correct server URL on device (iClock mode if used):
   - `http://<server-ip>:8000/iclock`
3. In app, add device with correct IP address.
4. Use **Test SDK** and **Connect**.
5. Verify device users can be loaded.

---

## 11. Troubleshooting

## Backend not starting

- Check Python installation and PATH
- Verify SQL credentials in `backend/.env`
- Ensure ODBC Driver 18 is installed

## Frontend blank page

- Confirm `VITE_API_BASE_URL` is correct
- Rebuild frontend: `npm run build`

## Device actions fail

- Check SDK installed and `zkemkeeper` COM registration
- Confirm device IP/port (default 4370)
- Ensure no firewall blocks device communication

## Login fails

- Verify backend is running
- Check admin credentials in DB and `.env`

---

## 12. Post-Installation Handover

After successful installation:

- Share application URL with client
- Provide user accounts and passwords
- Run basic validation:
  - Add device
  - Connect device
  - Load users
  - Enroll test user
  - Verify attendance log

---

## 13. Backup and Maintenance

- Take daily SQL backup
- Keep package version and changelog
- Rotate admin password periodically
- Apply updates using latest deployment package
