from __future__ import annotations
from datetime import datetime
import re
from typing import Optional


# ZK verify modes -> DeviceLog.VerificationType (2-char column). Same codes the
# SDK ingest path stores, so pushed and fetched punches look identical.
VERIFY_MODE = {0: "PW", 1: "FP", 2: "PN", 3: "PW", 4: "CD", 15: "FA"}

# ADMS attendance state -> Direction. 0 Check-In, 1 Check-Out, 2 Break-Out,
# 3 Break-In, 4 OT-In, 5 OT-Out.
STATUS_DIRECTION = {0: "IN", 1: "OUT", 2: "OUT", 3: "IN", 4: "IN", 5: "OUT"}


def parse_attlog_lines(payload: str) -> list[dict]:
    """
    Parse a POST /iclock/cdata?table=ATTLOG body. Each record is one line of
    tab-separated fields in push-protocol order:
        PIN <TAB> time <TAB> status <TAB> verify <TAB> workcode <TAB> reserved...
    Note status (in/out state) comes BEFORE verify (authentication method).
    """
    records: list[dict] = []
    for raw_line in payload.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split("\t")]
        if len(parts) < 2:
            continue

        employee_code = parts[0]
        timestamp_text = parts[1]
        status_raw = parts[2] if len(parts) > 2 else None
        verify_raw = parts[3] if len(parts) > 3 else None
        work_code = parts[4] if len(parts) > 4 else None

        log_date = _parse_datetime(timestamp_text)
        if log_date is None or not employee_code:
            continue

        direction = None
        if status_raw is not None and status_raw.isdigit():
            direction = STATUS_DIRECTION.get(int(status_raw))

        verify_type = None
        if verify_raw is not None and verify_raw.isdigit():
            verify_type = VERIFY_MODE.get(int(verify_raw), verify_raw[:2])
        elif verify_raw:
            verify_type = verify_raw[:2]

        records.append(
            {
                "EmployeeCode": employee_code,
                "LogDate": log_date,
                "VerificationType": verify_type,
                "Direction": direction,
                "WorkCode": (work_code if work_code and work_code != "0" else None),
            }
        )
    return records


def _parse_datetime(value: str) -> Optional[datetime]:
    formats = ["%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def parse_operlog_lines(payload: str, default_kind: Optional[str] = None) -> list[dict]:
    """
    Parse a POST /iclock/cdata?table=OPERLOG body. Devices push enrolled data
    as lines whose first token names the record type, followed by tab-separated
    key=value pairs (the first pair rides on the same token as the type):
        USER PIN=1\tName=John\tPri=0\tPasswd=\tCard=123\t...
        FP PIN=1\tFID=0\tSize=1656\tValid=1\tTMP=<base64>
        FACE PIN=1\tFID=50\tSIZE=2496\tVALID=1\tTMP=<base64>
        USERPIC PIN=1\tFileName=1.jpg\tSize=...\tContent=<base64>
        BIOPHOTO PIN=1\tFileName=1.jpg\tType=2\tSize=...\tContent=<base64>
    OPLOG (operation record) lines are ignored.
    default_kind: the table the upload is for (e.g. BIOPHOTO), used when a row starts straight with its fields
    ("pin=1\tfilename=1.jpg\tcontent=...") instead of the table name.
    Returns [{kind, pin, fields}] with field keys upper-cased.
    """
    records: list[dict] = []
    for raw_line in payload.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        head = line.split("\t", 1)[0]
        if default_kind and "=" in head.split(" ", 1)[0]:
            kind, remainder = default_kind, line
        elif " " in line:
            kind, remainder = line.split(" ", 1)
        else:
            continue
        kind = kind.strip().upper()
        # Newer firmwares name the tables USERINFO / FINGERTMP / BIODATA (Type 1 = finger, 9 = face).
        kind = {"USERINFO": "USER", "FINGERTMP": "FP"}.get(kind, kind)
        if kind not in {"USER", "FP", "FACE", "BIODATA", "USERPIC", "BIOPHOTO"}:
            continue
        fields: dict[str, str] = {}
        for part in remainder.split("\t"):
            if "=" in part:
                key, value = part.split("=", 1)
                fields[key.strip().upper()] = value.strip()
        pin = fields.get("PIN", "").strip()
        if not pin:
            continue
        records.append({"kind": kind, "pin": pin, "fields": fields})
    return records


def parse_photo_lines(payload: str) -> list[dict]:
    records: list[dict] = []
    for raw_line in payload.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Key-value style payloads: PIN=1001\tPHOTO=<base64>\tTIME=...
        if "=" in line:
            tokens = re.split(r"[\t,]", line)
            kv: dict[str, str] = {}
            for token in tokens:
                if "=" not in token:
                    continue
                key, value = token.split("=", 1)
                kv[key.strip().upper()] = value.strip()

            employee_code = (
                kv.get("EMPLOYEECODE")
                or kv.get("USERID")
                or kv.get("PIN")
                or kv.get("ENROLLNUMBER")
                or ""
            ).strip()
            photo_data = (
                kv.get("PHOTO")
                or kv.get("PHOTODATA")
                or kv.get("IMAGE")
                or kv.get("BASE64")
                or kv.get("ATTPHOTO")
                or ""
            ).strip()
            mime = (kv.get("MIME") or kv.get("PHOTOMIMETYPE") or "image/jpeg").strip()
            log_date = _parse_datetime((kv.get("TIME") or kv.get("LOGDATE") or "").strip())

            cleaned = _clean_base64(photo_data)
            if employee_code and cleaned:
                records.append(
                    {
                        "EmployeeCode": employee_code,
                        "PhotoData": cleaned,
                        "PhotoMimeType": mime,
                        "LogDate": log_date,
                    }
                )
            continue

        # Tab-separated fallback: EmployeeCode<TAB>Timestamp?<TAB>PhotoBase64
        parts = [part.strip() for part in line.split("\t")]
        if len(parts) < 2:
            continue
        employee_code = parts[0]
        if not employee_code:
            continue
        if len(parts) >= 3:
            maybe_time = _parse_datetime(parts[1])
            photo_raw = parts[2]
        else:
            maybe_time = None
            photo_raw = parts[1]
        cleaned = _clean_base64(photo_raw)
        if cleaned:
            records.append(
                {
                    "EmployeeCode": employee_code,
                    "PhotoData": cleaned,
                    "PhotoMimeType": "image/jpeg",
                    "LogDate": maybe_time,
                }
            )
    return records


def _clean_base64(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if text.startswith("data:"):
        marker = ";base64,"
        idx = text.find(marker)
        if idx >= 0:
            text = text[idx + len(marker) :]
    return text.strip()
