# Aveon Software User Manual

## 1. Overview

Aveon Biometric Device Management software is used to:

- manage biometric devices
- manage employees/users
- enroll biometrics
- transfer biometric data across devices
- send commands to devices
- view attendance logs and dashboard insights

---

## 2. Login

1. Open application URL in browser.
2. Enter username and password.
3. Click **Login to Dashboard**.

If login fails, contact administrator.

---

## 3. Dashboard

Dashboard shows:

- total devices
- online/offline count
- today attendance count
- recent logs

Use dashboard to quickly verify system health.

---

## 4. Device Management

Open **Devices** menu.

## 4.1 Add Device

1. Enter:
   - Device Name
   - Serial Number
   - Device IP Address
   - Direction
2. Click **Add Device**.

## 4.2 Test and Connect

- Click **Test SDK** to verify SDK connectivity.
- Click **Connect/Reconnect** per device.

## 4.3 View Device Users

- Click **Users** to list machine users.

## 4.4 Delete Device User

- Click **Delete** on user row.
- System verifies and refreshes list after delete.

## 4.5 Device User Photo

- Click **Fetch Photo** to pull photo from device/fallback.
- Click **View Photo** to preview stored photo.

---

## 5. Employee Management

Open **Employees** menu.

## 5.1 Field Meaning

- **ID (DB)**: internal auto-generated database ID
- **Code (Device)**: employee code used on device

Note: technical String/Numeric codes are auto-managed by system.

## 5.2 Add Employee

Fill:

- Employee Name
- Device/User Code
- Department (optional)
- Role (optional)
- RFID Number (optional)

Click **Add Employee**.

## 5.3 Edit/Delete Employee

- Use **Edit** to update details.
- Use **Delete** to remove employee.

## 5.4 Import from Device

1. Select a device.
2. Select data types (Face/Finger/RFID/Photo).
3. Click **Import From Device**.

Result:

- users are added/updated in software DB
- available biometrics and photo are stored

## 5.5 Update Software to Device

1. Select device.
2. Select data types to sync.
3. Click **Update Software To Device**.

Result:

- sync commands are queued for device execution.

---

## 6. Biometric Enrollment

Open **Enrollment** menu.

1. Select device.
2. Enter employee ID/code.
3. Select bio type (`FACE` or `FINGER`).
4. (Optional) enable update existing biometric.
5. Click **Enroll**.

Status messages show:

- enrollment start
- progress
- completion confirmation

Use **Verify Completion Now** if needed.

---

## 7. Transfer Biometric Data

Open **Transfer** menu.

1. Select source device.
2. Click **Load Source Users**.
3. Select users.
4. Select target devices.
5. Select data types:
   - Face
   - Finger
   - Card
   - Photo
6. Click **Transfer**.

System queues transfer commands and shows summary.

---

## 8. Commands

Open **Commands** menu.

Use this page to send manual commands such as:

- Clear Logs
- Enroll Face/Fingerprint
- Reset Stamps
- Unlock Door
- Reboot

Command list shows queued and execution status.

---

## 9. Attendance Logs

Open **Attendance Logs** menu.

View:

- Device ID
- Employee code
- Date/Time
- Verification type
- Direction
- Photo availability

Use logs for attendance verification and auditing.

---

## 10. Branding

Logo can be customized by admin:

- Place logo at `frontend/public/branding/logo.png`
- Configure `VITE_BRAND_LOGO_URL` if needed

---

## 11. Best Practices

- Keep device clocks accurate.
- Ensure stable network between server and devices.
- Import users before bulk sync/transfer.
- Review command status after large operations.
- Backup SQL database daily.

---

## 12. Common Issues

## Device Offline

- Check network cable/Wi-Fi
- Verify IP address
- Click **Connect**

## Enrollment Not Confirmed

- Complete biometric capture on machine
- Use **Verify Completion Now**

## Transfer Fails

- Ensure source users loaded
- Ensure targets selected
- Select at least one data type

## Login Error

- Check backend service status
- Confirm credentials with admin

---

## 13. Support Information

For technical support and maintenance:

- Aveon Infotech Private Limited
- Website: [https://www.aveoninfotech.com](https://www.aveoninfotech.com)
