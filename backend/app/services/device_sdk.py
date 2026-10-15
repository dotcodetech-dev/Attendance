from __future__ import annotations

import json
import os
import re
import socket
import subprocess
from typing import Any

# The eSSL zkemkeeper SDK only works reliably as a 32-bit COM server, so every
# bridge script must run under 32-bit PowerShell (the 64-bit DLL build crashes
# with AccessViolationException inside Connect_Net).
_PS32 = r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe"
POWERSHELL = _PS32 if os.path.exists(_PS32) else "powershell"

# Guidance appended when a reader can't be reached / logged into over the SDK:
# these devices can stream attendance over Cloud/ADMS push instead (no port 4370).
_PUSH_HINT = (
    "If this reader only supports Cloud/ADMS push, point its Cloud Server / ADMS "
    "setting at this server's address (port 80) - attendance then arrives "
    "automatically with no SDK needed."
)


def _with_comm_key(script: str, comm_key: int | None) -> str:
    """Readers with a Comm Key (Menu > Comm > Security) reject Connect_Net unless
    SetCommPassword(key) is called first. Inject it before every Connect_Net."""
    try:
        key = int(comm_key or 0)
    except (TypeError, ValueError):
        key = 0
    if key <= 0:
        return script
    return re.sub(r"(\$\w+)\.Connect_Net\(", lambda m: f"$null = {m.group(1)}.SetCommPassword({key}); {m.group(1)}.Connect_Net(", script)


def _tcp_reachable(ip: str, port: int, timeout: float = 4.0) -> bool:
    """Fast TCP check so we can tell 'device off the network' from 'SDK/login error'."""
    if not ip:
        return False
    try:
        with socket.create_connection((ip, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def test_device_connection(device_ip: str, port: int = 4370, timeout_seconds: int = 30, comm_key: int | None = None) -> dict[str, Any]:
    # Layer 1 — is the device even reachable on the network? A fast TCP probe
    # avoids a slow, opaque 30s SDK timeout when the real problem is a wrong IP,
    # a powered-off reader, or a firewall/VLAN blocking port 4370.
    if not _tcp_reachable(device_ip, port):
        return {
            "connected": False,
            "reachable": False,
            "error_code": -10,
            "message": (
                f"Device not reachable at {device_ip}:{port}. Check that the IP is correct, "
                f"the reader is powered on and on the same network as the server, and that "
                f"TCP port {port} is not blocked by a firewall or VLAN. " + _PUSH_HINT
            ),
            "prog_id": None,
        }

    script = r"""
$ErrorActionPreference = "Stop"
$ip = $env:SDK_DEVICE_IP
$port = [int]$env:SDK_DEVICE_PORT
$progIds = @("zkemkeeper.CZKEM", "zkemkeeper.CZKEM.1", "zkemkeeper.ZKEM")

foreach ($progId in $progIds) {
    try {
        $zk = New-Object -ComObject $progId
    } catch {
        continue
    }

    try {
        $connected = $zk.Connect_Net($ip, $port)
        if ($connected) {
            try { $zk.Disconnect() | Out-Null } catch {}
            [PSCustomObject]@{
                connected = $true
                error_code = 0
                message = "Connected successfully via SDK"
                prog_id = $progId
            } | ConvertTo-Json -Compress
            exit 0
        }
        else {
            $errCode = 0
            try { $zk.GetLastError([ref]$errCode) | Out-Null } catch {}
            [PSCustomObject]@{
                connected = $false
                error_code = $errCode
                message = "SDK connection failed"
                prog_id = $progId
            } | ConvertTo-Json -Compress
            exit 0
        }
    }
    catch {
        continue
    }
}

[PSCustomObject]@{
    connected = $false
    error_code = -1
    message = "SDK unavailable. Use HTTP device configuration instead (go to device settings and enable Cloud Server push)."
    prog_id = $null
} | ConvertTo-Json -Compress
"""

    env = os.environ.copy()
    env["SDK_DEVICE_IP"] = device_ip
    env["SDK_DEVICE_PORT"] = str(port)

    try:
        proc = subprocess.run(
            [POWERSHELL, "-NoProfile", "-Command", _with_comm_key(script, comm_key)],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {
            "connected": False,
            "error_code": -2,
            "message": "SDK connection test timed out",
            "prog_id": None,
        }

    output = (proc.stdout or "").strip()
    if not output:
        return {
            "connected": False,
            "error_code": -3,
            "message": (proc.stderr or "No response from SDK bridge").strip(),
            "prog_id": None,
        }

    # PowerShell may emit extra lines; parse the last JSON-looking line.
    line = output.splitlines()[-1].strip()
    try:
        data = json.loads(line)
        connected = bool(data.get("connected", False))
        message = data.get("message")
        if not connected:
            # Layer 2 — the device answered on the port but the SDK could not log in.
            # Almost always a Comm Key/password set on the reader, or push-only firmware.
            err = data.get("error_code")
            message = (
                f"Reached {device_ip}:{port} but the SDK could not log in"
                f"{f' (error {err})' if err not in (None, 0) else ''}. This usually means a "
                f"Comm Key is set on the reader (Menu > Comm > Security > Comm Key). Enter the same "
                f"Comm Key in this device's settings (Edit > Comm Key) or set it to 0 on the reader. " + _PUSH_HINT
            )
        return {
            "connected": connected,
            "reachable": True,
            "error_code": data.get("error_code"),
            "message": message,
            "prog_id": data.get("prog_id"),
        }
    except json.JSONDecodeError:
        return {
            "connected": False,
            "error_code": -4,
            "message": f"Unexpected SDK bridge output: {line}",
            "prog_id": None,
        }


def read_device_users(
    device_ip: str,
    port: int = 4370,
    timeout_seconds: int = 25,
    include_biometrics: bool = False, comm_key: int | None = None) -> dict[str, Any]:
    script = r"""
$ErrorActionPreference = "Stop"
$ip = $env:SDK_DEVICE_IP
$port = [int]$env:SDK_DEVICE_PORT
$includeBiometrics = $env:SDK_INCLUDE_BIOMETRICS -eq "1"
$machineNumber = 1
$progIds = @("zkemkeeper.CZKEM", "zkemkeeper.CZKEM.1", "zkemkeeper.ZKEM")

foreach ($progId in $progIds) {
    try {
        $zk = New-Object -ComObject $progId
        $connected = $zk.Connect_Net($ip, $port)
        if (-not $connected) {
            $errCode = 0
            try { $zk.GetLastError([ref]$errCode) | Out-Null } catch {}
            [PSCustomObject]@{
                connected = $false
                error_code = $errCode
                message = "SDK connection failed"
                prog_id = $progId
                users = @()
            } | ConvertTo-Json -Compress -Depth 6
            exit 0
        }

        try { $zk.EnableDevice($machineNumber, $false) | Out-Null } catch {}
        try { $zk.ReadAllUserID($machineNumber) | Out-Null } catch {}

        $users = @()
        $enroll = ""
        $name = ""
        $password = ""
        $privilege = 0
        $enabled = $false

        while ($zk.SSR_GetAllUserInfo($machineNumber, [ref]$enroll, [ref]$name, [ref]$password, [ref]$privilege, [ref]$enabled)) {
            if (-not [string]::IsNullOrWhiteSpace($enroll)) {
                $rfid = ""
                try {
                    $tmpCard = ""
                    if ($zk.GetStrCardNumber([ref]$tmpCard)) { $rfid = "$tmpCard" }
                } catch {}

                $faceTemplate = ""
                $faceLen = 0
                $hasFace = $false
                $fingerTemplate = ""
                $fingerLen = 0
                $fingerFlag = 0
                $hasFinger = $false

                if ($includeBiometrics) {
                    try {
                        if ($zk.GetUserFaceStr($machineNumber, $enroll, 50, [ref]$faceTemplate, [ref]$faceLen)) {
                            if ($faceLen -gt 0 -or -not [string]::IsNullOrWhiteSpace($faceTemplate)) {
                                $hasFace = $true
                            }
                        }
                    } catch {}

                    for ($idx = 0; $idx -lt 10; $idx++) {
                        try {
                            $tmpFinger = ""
                            $tmpLen = 0
                            $tmpFlag = 0
                            if ($zk.GetUserTmpExStr($machineNumber, $enroll, $idx, [ref]$tmpFlag, [ref]$tmpFinger, [ref]$tmpLen)) {
                                if ($tmpLen -gt 0 -or -not [string]::IsNullOrWhiteSpace($tmpFinger)) {
                                    $hasFinger = $true
                                    if ([string]::IsNullOrWhiteSpace($fingerTemplate)) {
                                        $fingerTemplate = $tmpFinger
                                        $fingerLen = $tmpLen
                                        $fingerFlag = $tmpFlag
                                    }
                                }
                            }
                        } catch {}
                    }
                }

                $users += [PSCustomObject]@{
                    EmployeeCode = "$enroll"
                    EmployeeName = "$name"
                    Role = "$privilege"
                    Enabled = [bool]$enabled
                    RFIDNumber = "$rfid"
                    Department = $null
                    HasFace = [bool]$hasFace
                    HasFinger = [bool]$hasFinger
                    FaceTemplate = $(if ($hasFace) { "$faceTemplate" } else { $null })
                    FingerTemplate = $(if ($hasFinger) { "$fingerTemplate" } else { $null })
                    FingerFlag = $(if ($hasFinger) { $fingerFlag } else { $null })
                }
            }
        }

        try { $zk.EnableDevice($machineNumber, $true) | Out-Null } catch {}
        try { $zk.Disconnect() | Out-Null } catch {}

        [PSCustomObject]@{
            connected = $true
            error_code = 0
            message = "Users read from device"
            prog_id = $progId
            users = $users
        } | ConvertTo-Json -Compress -Depth 6
        exit 0
    }
    catch {
        continue
    }
}

[PSCustomObject]@{
    connected = $false
    error_code = -1
    message = "zkemkeeper COM SDK not registered. Install device SDK / regsvr32 first."
    prog_id = $null
    users = @()
} | ConvertTo-Json -Compress -Depth 6
"""

    env = os.environ.copy()
    env["SDK_DEVICE_IP"] = device_ip
    env["SDK_DEVICE_PORT"] = str(port)
    env["SDK_INCLUDE_BIOMETRICS"] = "1" if include_biometrics else "0"

    try:
        proc = subprocess.run(
            [POWERSHELL, "-NoProfile", "-Command", _with_comm_key(script, comm_key)],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {
            "connected": False,
            "error_code": -2,
            "message": "Read users from SDK timed out",
            "prog_id": None,
            "users": [],
        }

    output = (proc.stdout or "").strip()
    if not output:
        return {
            "connected": False,
            "error_code": -3,
            "message": (proc.stderr or "No response from SDK bridge").strip(),
            "prog_id": None,
            "users": [],
        }

    line = output.splitlines()[-1].strip()
    try:
        data = json.loads(line)
        users = data.get("users") or []
        if not isinstance(users, list):
            users = []
        return {
            "connected": bool(data.get("connected", False)),
            "error_code": data.get("error_code"),
            "message": data.get("message"),
            "prog_id": data.get("prog_id"),
            "users": users,
        }
    except json.JSONDecodeError:
        return {
            "connected": False,
            "error_code": -4,
            "message": f"Unexpected SDK bridge output: {line}",
            "prog_id": None,
            "users": [],
        }


def delete_device_user(device_ip: str, employee_ref: str, port: int = 4370, timeout_seconds: int = 25, comm_key: int | None = None) -> dict[str, Any]:
    script = r"""
$ErrorActionPreference = "Stop"
$ip = $env:SDK_DEVICE_IP
$port = [int]$env:SDK_DEVICE_PORT
$userId = $env:SDK_USER_ID
$machineNumber = 1
$progIds = @("zkemkeeper.CZKEM", "zkemkeeper.CZKEM.1", "zkemkeeper.ZKEM")

function Test-UserExists {
    param($zkObj, $machine, $uid)
    $found = $false
    try { $zkObj.ReadAllUserID($machine) | Out-Null } catch {}
    $enroll = ""
    $name = ""
    $password = ""
    $privilege = 0
    $enabled = $false
    while ($zkObj.SSR_GetAllUserInfo($machine, [ref]$enroll, [ref]$name, [ref]$password, [ref]$privilege, [ref]$enabled)) {
        if ("$enroll" -eq "$uid") {
            $found = $true
            break
        }
    }
    return $found
}

foreach ($progId in $progIds) {
    try {
        $zk = New-Object -ComObject $progId
        $connected = $zk.Connect_Net($ip, $port)
        if (-not $connected) {
            $errCode = 0
            try { $zk.GetLastError([ref]$errCode) | Out-Null } catch {}
            [PSCustomObject]@{
                connected = $false
                deleted = $false
                error_code = $errCode
                message = "SDK connection failed"
                prog_id = $progId
            } | ConvertTo-Json -Compress
            exit 0
        }

        try { $zk.EnableDevice($machineNumber, $false) | Out-Null } catch {}

        $existedBefore = Test-UserExists -zkObj $zk -machine $machineNumber -uid $userId
        $deleteInvoked = $false

        for ($idx = 0; $idx -lt 10; $idx++) {
            try { if ($zk.SSR_DeleteEnrollData($machineNumber, $userId, $idx)) { $deleteInvoked = $true } } catch {}
            try { if ($zk.DeleteEnrollData($machineNumber, $userId, $idx)) { $deleteInvoked = $true } } catch {}
        }

        foreach ($specialIdx in @(10, 11, 12, 13, 14, 15, 50)) {
            try { if ($zk.SSR_DeleteEnrollData($machineNumber, $userId, $specialIdx)) { $deleteInvoked = $true } } catch {}
            try { if ($zk.DeleteEnrollData($machineNumber, $userId, $specialIdx)) { $deleteInvoked = $true } } catch {}
        }

        try { if ($zk.DeleteUserInfoEx($machineNumber, $userId)) { $deleteInvoked = $true } } catch {}
        try { if ($zk.SSR_DeleteUserInfo($machineNumber, $userId)) { $deleteInvoked = $true } } catch {}

        $numericUserId = 0
        if ([int]::TryParse($userId, [ref]$numericUserId)) {
            try { if ($zk.DeleteUserInfo($machineNumber, $numericUserId)) { $deleteInvoked = $true } } catch {}
        }

        try { $zk.RefreshData($machineNumber) | Out-Null } catch {}
        $existsAfter = Test-UserExists -zkObj $zk -machine $machineNumber -uid $userId
        $deleted = -not $existsAfter

        $msg = ""
        if ($deleted -and $existedBefore) {
            $msg = "User deleted from device."
        }
        elseif ($deleted -and -not $existedBefore) {
            $msg = "User is already not present on device."
        }
        else {
            $msg = "Unable to delete user from device."
        }

        $errCode = 0
        if (-not $deleted) {
            try { $zk.GetLastError([ref]$errCode) | Out-Null } catch {}
        }

        try { $zk.EnableDevice($machineNumber, $true) | Out-Null } catch {}
        try { $zk.Disconnect() | Out-Null } catch {}

        [PSCustomObject]@{
            connected = $true
            deleted = [bool]$deleted
            error_code = $errCode
            message = $msg
            prog_id = $progId
        } | ConvertTo-Json -Compress
        exit 0
    }
    catch {
        continue
    }
}

[PSCustomObject]@{
    connected = $false
    deleted = $false
    error_code = -1
    message = "zkemkeeper COM SDK not registered. Install device SDK / regsvr32 first."
    prog_id = $null
} | ConvertTo-Json -Compress
"""

    env = os.environ.copy()
    env["SDK_DEVICE_IP"] = device_ip
    env["SDK_DEVICE_PORT"] = str(port)
    env["SDK_USER_ID"] = employee_ref

    try:
        proc = subprocess.run(
            [POWERSHELL, "-NoProfile", "-Command", _with_comm_key(script, comm_key)],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {
            "connected": False,
            "deleted": False,
            "error_code": -2,
            "message": "Delete user request timed out",
            "prog_id": None,
        }

    output = (proc.stdout or "").strip()
    if not output:
        return {
            "connected": False,
            "deleted": False,
            "error_code": -3,
            "message": (proc.stderr or "No response from SDK bridge").strip(),
            "prog_id": None,
        }

    line = output.splitlines()[-1].strip()
    try:
        data = json.loads(line)
        return {
            "connected": bool(data.get("connected", False)),
            "deleted": bool(data.get("deleted", False)),
            "error_code": data.get("error_code"),
            "message": data.get("message"),
            "prog_id": data.get("prog_id"),
        }
    except json.JSONDecodeError:
        return {
            "connected": False,
            "deleted": False,
            "error_code": -4,
            "message": f"Unexpected SDK bridge output: {line}",
            "prog_id": None,
        }


def read_device_user_photo(
    device_ip: str,
    employee_ref: str,
    port: int = 4370,
    timeout_seconds: int = 30, comm_key: int | None = None) -> dict[str, Any]:
    script = r"""
$ErrorActionPreference = "Stop"
$ip = $env:SDK_DEVICE_IP
$port = [int]$env:SDK_DEVICE_PORT
$userId = $env:SDK_USER_ID
$machineNumber = 1
$progIds = @("zkemkeeper.CZKEM", "zkemkeeper.CZKEM.1", "zkemkeeper.ZKEM")
$progIdErrors = @()

foreach ($progId in $progIds) {
    $zk = $null
    try {
        $zk = New-Object -ComObject $progId
    } catch {
        $progIdErrors += "${progId}: $($_.Exception.Message)"
        continue
    }

    $connected = $false
    try {
        $connected = $zk.Connect_Net($ip, $port)
    } catch {
        $progIdErrors += "${progId}: Connect_Net: $($_.Exception.Message)"
        continue
    }

    if (-not $connected) {
        $errCode = 0
        try { $zk.GetLastError([ref]$errCode) | Out-Null } catch {}
        [PSCustomObject]@{
            connected = $false
            photo_found = $false
            error_code = $errCode
            message = "SDK connection failed"
            prog_id = $progId
            photo_data = $null
            photo_mime_type = $null
            method_used = $null
            attempts = @()
            available_photo_methods = $null
        } | ConvertTo-Json -Compress -Depth 6
        exit 0
    }

    $attempts = @()

    # Enumerate photo/face-related methods the registered SDK actually exposes
    # (often empty for raw __ComObject without a type library â€” that itself is a useful signal).
    $availableMethods = $null
    try {
        $names = $zk | Get-Member -MemberType Method -ErrorAction Stop |
            Where-Object { $_.Name -match "Photo|Face" } |
            Select-Object -ExpandProperty Name
        if ($names) { $availableMethods = (($names | Sort-Object -Unique) -join ",") }
    } catch {}

    # Some SDK builds require buffering photos before individual reads.
    try {
        $zk.ReadAllUserPhoto($machineNumber) | Out-Null
        $attempts += @{ method = "ReadAllUserPhoto"; detail = "ok" }
    } catch {
        $attempts += @{ method = "ReadAllUserPhoto"; detail = $_.Exception.Message }
    }

    $photoData = ""
    $photoLen = 0
    $methodUsed = ""
    $photoFound = $false

    try {
        if ($zk.GetUserFacePhotoByName($machineNumber, $userId, [ref]$photoData)) {
            $photoFound = $true
            $methodUsed = "GetUserFacePhotoByName(3)"
            $attempts += @{ method = "GetUserFacePhotoByName(3)"; detail = "ok" }
        } else {
            $attempts += @{ method = "GetUserFacePhotoByName(3)"; detail = "returned false" }
        }
    } catch {
        $attempts += @{ method = "GetUserFacePhotoByName(3)"; detail = $_.Exception.Message }
    }

    if (-not $photoFound) {
        try {
            if ($zk.GetUserFacePhotoByName($machineNumber, $userId, [ref]$photoData, [ref]$photoLen)) {
                $photoFound = $true
                $methodUsed = "GetUserFacePhotoByName(4)"
                $attempts += @{ method = "GetUserFacePhotoByName(4)"; detail = "ok" }
            } else {
                $attempts += @{ method = "GetUserFacePhotoByName(4)"; detail = "returned false" }
            }
        } catch {
            $attempts += @{ method = "GetUserFacePhotoByName(4)"; detail = $_.Exception.Message }
        }
    }

    if (-not $photoFound) {
        try {
            if ($zk.GetUserFacePhoto($machineNumber, $userId, [ref]$photoData)) {
                $photoFound = $true
                $methodUsed = "GetUserFacePhoto(3)"
                $attempts += @{ method = "GetUserFacePhoto(3)"; detail = "ok" }
            } else {
                $attempts += @{ method = "GetUserFacePhoto(3)"; detail = "returned false" }
            }
        } catch {
            $attempts += @{ method = "GetUserFacePhoto(3)"; detail = $_.Exception.Message }
        }
    }

    if (-not $photoFound) {
        try {
            if ($zk.GetUserPhoto($machineNumber, $userId, [ref]$photoData)) {
                $photoFound = $true
                $methodUsed = "GetUserPhoto(3)"
                $attempts += @{ method = "GetUserPhoto(3)"; detail = "ok" }
            } else {
                $attempts += @{ method = "GetUserPhoto(3)"; detail = "returned false" }
            }
        } catch {
            $attempts += @{ method = "GetUserPhoto(3)"; detail = $_.Exception.Message }
        }
    }

    if (-not $photoFound) {
        try {
            if ($zk.GetUserPhoto($machineNumber, $userId, [ref]$photoLen, [ref]$photoData)) {
                $photoFound = $true
                $methodUsed = "GetUserPhoto(4)"
                $attempts += @{ method = "GetUserPhoto(4)"; detail = "ok" }
            } else {
                $attempts += @{ method = "GetUserPhoto(4)"; detail = "returned false" }
            }
        } catch {
            $attempts += @{ method = "GetUserPhoto(4)"; detail = $_.Exception.Message }
        }
    }

    $photoMime = "image/jpeg"
    $base64 = ""
    if ($photoFound -and -not [string]::IsNullOrWhiteSpace($photoData)) {
        if (Test-Path -LiteralPath $photoData) {
            try {
                $bytes = [System.IO.File]::ReadAllBytes($photoData)
                $base64 = [Convert]::ToBase64String($bytes)
            } catch {
                $base64 = ""
            }
        } else {
            $base64 = "$photoData"
        }
    }

    $message = ""
    if ($photoFound -and -not [string]::IsNullOrWhiteSpace($base64)) {
        $message = "Photo fetched from device"
    }
    else {
        $photoFound = $false
        $message = "Photo API not supported or no photo enrolled for this user on this device."
        $base64 = $null
    }

    try { $zk.Disconnect() | Out-Null } catch {}
    [PSCustomObject]@{
        connected = $true
        photo_found = [bool]$photoFound
        error_code = 0
        message = $message
        prog_id = $progId
        photo_data = $base64
        photo_mime_type = $photoMime
        method_used = $methodUsed
        attempts = @($attempts)
        available_photo_methods = $availableMethods
    } | ConvertTo-Json -Compress -Depth 6
    exit 0
}

$notRegisteredMessage = "zkemkeeper COM SDK not registered. Install device SDK / regsvr32 first."
if ($progIdErrors.Count -gt 0) {
    $notRegisteredMessage = "zkemkeeper COM SDK unavailable: " + ($progIdErrors -join " | ")
}
[PSCustomObject]@{
    connected = $false
    photo_found = $false
    error_code = -1
    message = $notRegisteredMessage
    prog_id = $null
    photo_data = $null
    photo_mime_type = $null
    method_used = $null
    attempts = @()
    available_photo_methods = $null
} | ConvertTo-Json -Compress -Depth 6
"""

    env = os.environ.copy()
    env["SDK_DEVICE_IP"] = device_ip
    env["SDK_DEVICE_PORT"] = str(port)
    env["SDK_USER_ID"] = employee_ref

    try:
        proc = subprocess.run(
            [POWERSHELL, "-NoProfile", "-Command", _with_comm_key(script, comm_key)],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {
            "connected": False,
            "photo_found": False,
            "error_code": -2,
            "message": "Read user photo request timed out",
            "prog_id": None,
            "photo_data": None,
            "photo_mime_type": None,
            "method_used": None,
            "attempts": [],
            "available_photo_methods": None,
        }

    output = (proc.stdout or "").strip()
    if not output:
        return {
            "connected": False,
            "photo_found": False,
            "error_code": -3,
            "message": (proc.stderr or "No response from SDK bridge").strip(),
            "prog_id": None,
            "photo_data": None,
            "photo_mime_type": None,
            "method_used": None,
            "attempts": [],
            "available_photo_methods": None,
        }

    line = output.splitlines()[-1].strip()
    try:
        data = json.loads(line)
        # ConvertTo-Json collapses a single-element array to a bare object.
        attempts = data.get("attempts") or []
        if isinstance(attempts, dict):
            attempts = [attempts]
        return {
            "connected": bool(data.get("connected", False)),
            "photo_found": bool(data.get("photo_found", False)),
            "error_code": data.get("error_code"),
            "message": data.get("message"),
            "prog_id": data.get("prog_id"),
            "photo_data": data.get("photo_data"),
            "photo_mime_type": data.get("photo_mime_type"),
            "method_used": data.get("method_used"),
            "attempts": attempts,
            "available_photo_methods": data.get("available_photo_methods"),
        }
    except json.JSONDecodeError:
        return {
            "connected": False,
            "photo_found": False,
            "error_code": -4,
            "message": f"Unexpected SDK bridge output: {line}",
            "prog_id": None,
            "photo_data": None,
            "photo_mime_type": None,
            "method_used": None,
            "attempts": [],
            "available_photo_methods": None,
        }


def trigger_device_enrollment(
    device_ip: str,
    employee_ref: str,
    bio_type: str,
    port: int = 4370,
    timeout_seconds: int = 20, comm_key: int | None = None) -> dict[str, Any]:
    script = r"""
$ErrorActionPreference = "Stop"
$ip = $env:SDK_DEVICE_IP
$port = [int]$env:SDK_DEVICE_PORT
$userId = $env:SDK_USER_ID
$bioType = $env:SDK_BIO_TYPE
$machineNumber = 1
$progIds = @("zkemkeeper.CZKEM", "zkemkeeper.CZKEM.1", "zkemkeeper.ZKEM")

foreach ($progId in $progIds) {
    try {
        $zk = New-Object -ComObject $progId
        $connected = $zk.Connect_Net($ip, $port)
        if (-not $connected) {
            $errCode = 0
            try { $zk.GetLastError([ref]$errCode) | Out-Null } catch {}
            [PSCustomObject]@{
                connected = $false
                enrollment_started = $false
                error_code = $errCode
                message = "SDK connection failed"
                prog_id = $progId
                method_used = $null
            } | ConvertTo-Json -Compress
            exit 0
        }

        # Ensure user exists before starting biometric registration.
        try { $zk.SSR_SetUserInfo($machineNumber, $userId, $userId, "", 0, $true) | Out-Null } catch {
            try { $zk.SetUserInfo($machineNumber, [int]$userId, $userId, "", 0, $true) | Out-Null } catch {}
        }

        $started = $false
        $methodUsed = ""
        $numericUserId = 0
        $hasNumericUserId = [int]::TryParse($userId, [ref]$numericUserId)

        if ($bioType -eq "FACE") {
            try { if ($zk.StartEnrollEx($userId, 50, 0)) { $started = $true; $methodUsed = "StartEnrollEx(50)" } } catch {}
            if (-not $started -and $hasNumericUserId) { try { if ($zk.StartEnrollEx($numericUserId, 50, 0)) { $started = $true; $methodUsed = "StartEnrollEx(int,50)" } } catch {} }
            if (-not $started) { try { if ($zk.StartEnroll($userId, 50)) { $started = $true; $methodUsed = "StartEnroll(50)" } } catch {} }
            if (-not $started -and $hasNumericUserId) { try { if ($zk.StartEnroll($numericUserId, 50)) { $started = $true; $methodUsed = "StartEnroll(int,50)" } } catch {} }
            if (-not $started) { try { if ($zk.StartEnroll($userId)) { $started = $true; $methodUsed = "StartEnroll" } } catch {} }
            if (-not $started -and $hasNumericUserId) { try { if ($zk.StartEnroll($numericUserId)) { $started = $true; $methodUsed = "StartEnroll(int)" } } catch {} }
        }
        else {
            try { if ($zk.StartEnrollEx($userId, 0, 0)) { $started = $true; $methodUsed = "StartEnrollEx(0)" } } catch {}
            if (-not $started) { try { if ($zk.StartEnrollEx($userId, 1, 0)) { $started = $true; $methodUsed = "StartEnrollEx(1)" } } catch {} }
            if (-not $started -and $hasNumericUserId) { try { if ($zk.StartEnrollEx($numericUserId, 0, 0)) { $started = $true; $methodUsed = "StartEnrollEx(int,0)" } } catch {} }
            if (-not $started -and $hasNumericUserId) { try { if ($zk.StartEnrollEx($numericUserId, 1, 0)) { $started = $true; $methodUsed = "StartEnrollEx(int,1)" } } catch {} }
            if (-not $started) { try { if ($zk.StartEnroll($userId, 0)) { $started = $true; $methodUsed = "StartEnroll(0)" } } catch {} }
            if (-not $started) { try { if ($zk.StartEnroll($userId, 1)) { $started = $true; $methodUsed = "StartEnroll(1)" } } catch {} }
            if (-not $started -and $hasNumericUserId) { try { if ($zk.StartEnroll($numericUserId, 0)) { $started = $true; $methodUsed = "StartEnroll(int,0)" } } catch {} }
            if (-not $started -and $hasNumericUserId) { try { if ($zk.StartEnroll($numericUserId, 1)) { $started = $true; $methodUsed = "StartEnroll(int,1)" } } catch {} }
            if (-not $started) { try { if ($zk.StartEnroll($userId)) { $started = $true; $methodUsed = "StartEnroll" } } catch {} }
            if (-not $started -and $hasNumericUserId) { try { if ($zk.StartEnroll($numericUserId)) { $started = $true; $methodUsed = "StartEnroll(int)" } } catch {} }
        }

        $errCode = 0
        if (-not $started) {
            try { $zk.GetLastError([ref]$errCode) | Out-Null } catch {}
        }
        else {
            # Give device a moment to switch into capture UI before disconnect.
            Start-Sleep -Milliseconds 600
        }

        try { $zk.Disconnect() | Out-Null } catch {}

        [PSCustomObject]@{
            connected = $true
            enrollment_started = $started
            error_code = $errCode
            message = $(if ($started) { "Enrollment started. Please complete capture on the device." } else { "Unable to start enrollment on the device." })
            prog_id = $progId
            method_used = $methodUsed
        } | ConvertTo-Json -Compress
        exit 0
    }
    catch {
        continue
    }
}

[PSCustomObject]@{
    connected = $false
    enrollment_started = $false
    error_code = -1
    message = "zkemkeeper COM SDK not registered. Install device SDK / regsvr32 first."
    prog_id = $null
    method_used = $null
} | ConvertTo-Json -Compress
"""

    env = os.environ.copy()
    env["SDK_DEVICE_IP"] = device_ip
    env["SDK_DEVICE_PORT"] = str(port)
    env["SDK_USER_ID"] = employee_ref
    env["SDK_BIO_TYPE"] = bio_type.upper()

    try:
        proc = subprocess.run(
            [POWERSHELL, "-NoProfile", "-Command", _with_comm_key(script, comm_key)],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {
            "connected": False,
            "enrollment_started": False,
            "error_code": -2,
            "message": "Enrollment request timed out",
            "prog_id": None,
            "method_used": None,
        }

    output = (proc.stdout or "").strip()
    if not output:
        return {
            "connected": False,
            "enrollment_started": False,
            "error_code": -3,
            "message": (proc.stderr or "No response from SDK bridge").strip(),
            "prog_id": None,
            "method_used": None,
        }

    line = output.splitlines()[-1].strip()
    try:
        data = json.loads(line)
        return {
            "connected": bool(data.get("connected", False)),
            "enrollment_started": bool(data.get("enrollment_started", False)),
            "error_code": data.get("error_code"),
            "message": data.get("message"),
            "prog_id": data.get("prog_id"),
            "method_used": data.get("method_used"),
        }
    except json.JSONDecodeError:
        return {
            "connected": False,
            "enrollment_started": False,
            "error_code": -4,
            "message": f"Unexpected SDK bridge output: {line}",
            "prog_id": None,
            "method_used": None,
        }


def check_enrollment_status(
    device_ip: str,
    employee_ref: str,
    bio_type: str,
    port: int = 4370,
    timeout_seconds: int = 15, comm_key: int | None = None) -> dict[str, Any]:
    script = r"""
$ErrorActionPreference = "Stop"
$ip = $env:SDK_DEVICE_IP
$port = [int]$env:SDK_DEVICE_PORT
$userId = $env:SDK_USER_ID
$bioType = $env:SDK_BIO_TYPE
$machineNumber = 1
$progIds = @("zkemkeeper.CZKEM", "zkemkeeper.CZKEM.1", "zkemkeeper.ZKEM")

foreach ($progId in $progIds) {
    try {
        $zk = New-Object -ComObject $progId
        $connected = $zk.Connect_Net($ip, $port)
        if (-not $connected) {
            $errCode = 0
            try { $zk.GetLastError([ref]$errCode) | Out-Null } catch {}
            [PSCustomObject]@{
                connected = $false
                completed = $false
                error_code = $errCode
                message = "SDK connection failed"
                prog_id = $progId
            } | ConvertTo-Json -Compress
            exit 0
        }

        $completed = $false
        if ($bioType -eq "FACE") {
            $faceData = ""
            $length = 0
            try {
                if ($zk.GetUserFaceStr($machineNumber, $userId, 50, [ref]$faceData, [ref]$length)) {
                    if ($length -gt 0 -or -not [string]::IsNullOrWhiteSpace($faceData)) {
                        $completed = $true
                    }
                }
            } catch {}
        }
        else {
            $flag = 0
            $tmp = ""
            $len = 0
            for ($idx = 0; $idx -lt 10; $idx++) {
                try {
                    if ($zk.GetUserTmpExStr($machineNumber, $userId, $idx, [ref]$flag, [ref]$tmp, [ref]$len)) {
                        if ($len -gt 0 -or -not [string]::IsNullOrWhiteSpace($tmp)) {
                            $completed = $true
                            break
                        }
                    }
                } catch {}
            }
        }

        try { $zk.Disconnect() | Out-Null } catch {}
        [PSCustomObject]@{
            connected = $true
            completed = $completed
            error_code = 0
            message = $(if ($completed) { "Enrollment completed on device." } else { "Enrollment still pending on device." })
            prog_id = $progId
        } | ConvertTo-Json -Compress
        exit 0
    }
    catch {
        continue
    }
}

[PSCustomObject]@{
    connected = $false
    completed = $false
    error_code = -1
    message = "zkemkeeper COM SDK not registered. Install device SDK / regsvr32 first."
    prog_id = $null
} | ConvertTo-Json -Compress
"""

    env = os.environ.copy()
    env["SDK_DEVICE_IP"] = device_ip
    env["SDK_DEVICE_PORT"] = str(port)
    env["SDK_USER_ID"] = employee_ref
    env["SDK_BIO_TYPE"] = bio_type.upper()

    try:
        proc = subprocess.run(
            [POWERSHELL, "-NoProfile", "-Command", _with_comm_key(script, comm_key)],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {
            "connected": False,
            "completed": False,
            "error_code": -2,
            "message": "Enrollment status check timed out",
            "prog_id": None,
        }

    output = (proc.stdout or "").strip()
    if not output:
        return {
            "connected": False,
            "completed": False,
            "error_code": -3,
            "message": (proc.stderr or "No response from SDK bridge").strip(),
            "prog_id": None,
        }

    line = output.splitlines()[-1].strip()
    try:
        data = json.loads(line)
        return {
            "connected": bool(data.get("connected", False)),
            "completed": bool(data.get("completed", False)),
            "error_code": data.get("error_code"),
            "message": data.get("message"),
            "prog_id": data.get("prog_id"),
        }
    except json.JSONDecodeError:
        return {
            "connected": False,
            "completed": False,
            "error_code": -4,
            "message": f"Unexpected SDK bridge output: {line}",
            "prog_id": None,
        }


def push_operations_via_sdk(
    device_ip: str,
    operations: list[dict[str, Any]],
    port: int = 4370,
    timeout_seconds: int | None = None, comm_key: int | None = None) -> dict[str, Any]:
    """
    Write users/cards/biometric templates directly to a device over TCP 4370
    using the zkemkeeper COM SDK â€” the fallback transfer path when the device
    is not configured to poll this server's /iclock push endpoints.

    Each operation: {"id": int, "kind": "user"|"face"|"fp",
                     "code": str, "name": str, "card": str,
                     "tmp": str, "len": int}
    Returns {"connected": bool, "message": str, "prog_id": str,
             "results": [{"id", "ok", "error"}]}.
    """
    import tempfile

    script = r"""
$ErrorActionPreference = "Stop"
$ip = $env:SDK_DEVICE_IP
$port = [int]$env:SDK_DEVICE_PORT
$opsPath = $env:SDK_OPS_FILE
$machineNumber = 1

# Assign first, then wrap: @(pipeline) would nest the parsed array in
# another array on PowerShell 5.1, while @($var) leaves an array as-is.
$parsed = Get-Content -Raw -LiteralPath $opsPath | ConvertFrom-Json
$ops = @($parsed)

$zk = $null
$progUsed = $null
foreach ($progId in @("zkemkeeper.CZKEM", "zkemkeeper.CZKEM.1", "zkemkeeper.ZKEM")) {
    try { $zk = New-Object -ComObject $progId; $progUsed = $progId; break } catch {}
}
if (-not $zk) {
    @{ connected = $false; message = "zkemkeeper COM SDK not registered."; prog_id = $null; results = @() } |
        ConvertTo-Json -Compress -Depth 6
    exit 0
}

if (-not $zk.Connect_Net($ip, $port)) {
    $errCode = 0
    try { $zk.GetLastError([ref]$errCode) | Out-Null } catch {}
    @{ connected = $false; message = "SDK connection failed (error $errCode)"; prog_id = $progUsed; results = @() } |
        ConvertTo-Json -Compress -Depth 6
    exit 0
}

try { $zk.EnableDevice($machineNumber, $false) | Out-Null } catch {}

$results = @()
foreach ($op in $ops) {
    $ok = $false
    $err = ""
    try {
        switch ([string]$op.kind) {
            "user" {
                $card = [string]$op.card
                if ($card) {
                    try { $zk.SetStrCardNumber($card) | Out-Null } catch {
                        try { $zk.CardNumber = $card } catch {}
                    }
                }
                $ok = $zk.SSR_SetUserInfo($machineNumber, [string]$op.code, [string]$op.name, "", 0, $true)
            }
            "face" {
                $ok = $zk.SetUserFaceStr($machineNumber, [string]$op.code, 50, [string]$op.tmp, [int]$op.len)
            }
            "fp" {
                $ok = $zk.SetUserTmpExStr($machineNumber, [string]$op.code, 0, 1, [string]$op.tmp)
            }
            default { $err = "Unknown op kind: $($op.kind)" }
        }
        if (-not $ok -and -not $err) {
            $e = 0
            try { $zk.GetLastError([ref]$e) | Out-Null } catch {}
            $err = "SDK returned false (device error $e)"
        }
    } catch {
        $err = $_.Exception.Message
    }
    $results += @{ id = [int]$op.id; ok = [bool]$ok; error = $err }
}

try { $zk.RefreshData($machineNumber) | Out-Null } catch {}
try { $zk.EnableDevice($machineNumber, $true) | Out-Null } catch {}
try { $zk.Disconnect() | Out-Null } catch {}

@{ connected = $true; message = "done"; prog_id = $progUsed; results = @($results) } |
    ConvertTo-Json -Compress -Depth 6
"""

    if timeout_seconds is None:
        timeout_seconds = min(600, 60 + 3 * len(operations))

    ops_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    try:
        json.dump(operations, ops_file)
        ops_file.close()

        env = os.environ.copy()
        env["SDK_DEVICE_IP"] = device_ip
        env["SDK_DEVICE_PORT"] = str(port)
        env["SDK_OPS_FILE"] = ops_file.name

        try:
            proc = subprocess.run(
                [POWERSHELL, "-NoProfile", "-Command", _with_comm_key(script, comm_key)],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return {"connected": False, "message": "SDK push timed out", "prog_id": None, "results": []}

        output = (proc.stdout or "").strip()
        if not output:
            return {
                "connected": False,
                "message": (proc.stderr or "No response from SDK bridge").strip(),
                "prog_id": None,
                "results": [],
            }
        line = output.splitlines()[-1].strip()
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return {"connected": False, "message": f"Unexpected SDK bridge output: {line}", "prog_id": None, "results": []}

        results = data.get("results") or []
        if isinstance(results, dict):  # ConvertTo-Json single-element collapse
            results = [results]
        return {
            "connected": bool(data.get("connected", False)),
            "message": data.get("message"),
            "prog_id": data.get("prog_id"),
            "results": results,
        }
    finally:
        try:
            os.unlink(ops_file.name)
        except OSError:
            pass


def read_device_attendance(
    device_ip: str,
    port: int = 4370,
    timeout_seconds: int = 240, comm_key: int | None = None) -> dict[str, Any]:
    """
    Pull attendance (punch) records from a device over TCP 4370 via the
    zkemkeeper SDK â€” the manual fallback when the device is not pushing ATTLOG.
    Uses ReadGeneralLogData + SSR_GetGeneralLogData (the modern string-PIN API).
    Returns {connected, message, prog_id, count, records:[{EmployeeCode, LogDate,
    VerifyMode, InOutMode, WorkCode}]}.
    """
    script = r"""
$ErrorActionPreference = "Stop"
$ip = $env:SDK_DEVICE_IP
$port = [int]$env:SDK_DEVICE_PORT
$machineNumber = 1
$progIds = @("zkemkeeper.CZKEM", "zkemkeeper.CZKEM.1", "zkemkeeper.ZKEM")

foreach ($progId in $progIds) {
    $zk = $null
    try { $zk = New-Object -ComObject $progId } catch { continue }

    $connected = $false
    try { $connected = $zk.Connect_Net($ip, $port) } catch { $connected = $false }
    if (-not $connected) {
        $errCode = 0
        try { $zk.GetLastError([ref]$errCode) | Out-Null } catch {}
        [PSCustomObject]@{ connected=$false; error_code=$errCode; message="SDK connection failed"; prog_id=$progId; count=0; records=@() } | ConvertTo-Json -Compress -Depth 6
        exit 0
    }

    try { $zk.EnableDevice($machineNumber, $false) | Out-Null } catch {}

    $records = New-Object System.Collections.ArrayList
    $readOk = $false
    try { $readOk = $zk.ReadGeneralLogData($machineNumber) } catch { $readOk = $false }

    $enroll = ""; $verify = 0; $inout = 0; $yy = 0; $mm = 0; $dd = 0; $hh = 0; $mi = 0; $ss = 0; $wc = 0
    $guard = 0
    while ($guard -lt 200000 -and $zk.SSR_GetGeneralLogData($machineNumber, [ref]$enroll, [ref]$verify, [ref]$inout, [ref]$yy, [ref]$mm, [ref]$dd, [ref]$hh, [ref]$mi, [ref]$ss, [ref]$wc)) {
        if (-not [string]::IsNullOrWhiteSpace($enroll)) {
            [void]$records.Add([PSCustomObject]@{
                EmployeeCode = "$enroll"
                LogDate = ("{0:0000}-{1:00}-{2:00} {3:00}:{4:00}:{5:00}" -f [int]$yy,[int]$mm,[int]$dd,[int]$hh,[int]$mi,[int]$ss)
                VerifyMode = [int]$verify
                InOutMode = [int]$inout
                WorkCode = [int]$wc
            })
        }
        $guard++
    }

    try { $zk.EnableDevice($machineNumber, $true) | Out-Null } catch {}
    try { $zk.Disconnect() | Out-Null } catch {}

    [PSCustomObject]@{ connected=$true; error_code=0; message="Attendance read from device"; prog_id=$progId; count=$records.Count; records=@($records) } | ConvertTo-Json -Compress -Depth 6
    exit 0
}

[PSCustomObject]@{ connected=$false; error_code=-1; message="zkemkeeper COM SDK not registered. Install device SDK / regsvr32 first."; prog_id=$null; count=0; records=@() } | ConvertTo-Json -Compress -Depth 6
"""

    env = os.environ.copy()
    env["SDK_DEVICE_IP"] = device_ip
    env["SDK_DEVICE_PORT"] = str(port)

    try:
        proc = subprocess.run(
            [POWERSHELL, "-NoProfile", "-Command", _with_comm_key(script, comm_key)],
            check=False, capture_output=True, text=True, timeout=timeout_seconds, env=env,
        )
    except subprocess.TimeoutExpired:
        return {"connected": False, "message": "Attendance read timed out", "prog_id": None, "count": 0, "records": []}

    output = (proc.stdout or "").strip()
    if not output:
        return {"connected": False, "message": (proc.stderr or "No response from SDK bridge").strip(), "prog_id": None, "count": 0, "records": []}
    line = output.splitlines()[-1].strip()
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return {"connected": False, "message": f"Unexpected SDK bridge output: {line[:200]}", "prog_id": None, "count": 0, "records": []}

    records = data.get("records") or []
    if isinstance(records, dict):  # ConvertTo-Json single-element collapse
        records = [records]
    return {
        "connected": bool(data.get("connected", False)),
        "message": data.get("message"),
        "prog_id": data.get("prog_id"),
        "count": int(data.get("count") or 0),
        "records": records,
    }

