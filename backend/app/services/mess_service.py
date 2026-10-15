"""
Mess Token Print system: configurable meal windows, time-based token generation
(one per employee per meal per day), thermal-receipt payload, and token log.
"""
from __future__ import annotations

import base64
import io
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import Employee, MasterSetting, MessMeal, MessToken

ENABLED_KEY = "MessTokenEnabled"
DEVICE_KEY = "MessDeviceId"       # which device's punches auto-generate tokens (blank = none)
AUTOPRINT_KEY = "MessAutoPrint"   # Y/N — kiosk auto-prints new tokens


def _get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(MasterSetting).filter(MasterSetting.Name == key).first()
    return row.Value if (row and row.Value is not None) else default


def _set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(MasterSetting).filter(MasterSetting.Name == key).first()
    if row is None:
        row = MasterSetting(Name=key)
        db.add(row)
    row.Value = value


# ---- enable flag (mastersettings) ----
def get_enabled(db: Session) -> bool:
    return _get_setting(db, ENABLED_KEY, "N") == "Y"


def set_enabled(db: Session, enabled: bool) -> None:
    _set_setting(db, ENABLED_KEY, "Y" if enabled else "N")
    db.commit()


def get_mess_device_id(db: Session) -> Optional[int]:
    v = _get_setting(db, DEVICE_KEY, "")
    return int(v) if v.isdigit() else None


def get_auto_print(db: Session) -> bool:
    return _get_setting(db, AUTOPRINT_KEY, "N") == "Y"


# ---- meals ----
def list_meals(db: Session) -> list[MessMeal]:
    return db.query(MessMeal).order_by(MessMeal.SortOrder, MessMeal.MessMealId).all()


def _hhmm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def active_meal(db: Session, now: datetime) -> Optional[MessMeal]:
    """Return the meal whose configured window contains `now` (local wall-clock)."""
    cur = now.hour * 60 + now.minute
    for meal in list_meals(db):
        if (meal.IsActive or "Y") != "Y":
            continue
        try:
            start, end = _hhmm(meal.StartTime), _hhmm(meal.EndTime)
        except (ValueError, AttributeError):
            continue
        if start <= end:
            if start <= cur <= end:
                return meal
        else:  # window crosses midnight
            if cur >= start or cur <= end:
                return meal
    return None


# ---- QR ----
def _qr_data_url(payload: str) -> Optional[str]:
    try:
        import qrcode
        img = qrcode.make(payload)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def _org(db: Session) -> dict:
    from app.api.v1.settings import get_organization_settings
    return get_organization_settings(db)


def _token_payload(t: MessToken) -> dict:
    org = None  # filled by caller
    return {
        "MessTokenId": t.MessTokenId,
        "EmployeeCode": t.EmployeeCode,
        "EmployeeName": t.EmployeeName,
        "MealType": t.MealType,
        "TokenNumber": t.TokenNumber,
        "TokenLabel": f"{t.MealType[:1].upper()}-{t.TokenNumber:03d}",
        "TokenDate": t.TokenDate.isoformat(),
        "CreatedAt": t.CreatedAt.isoformat() if t.CreatedAt else None,
        "PrintStatus": t.PrintStatus,
        "ReprintCount": t.ReprintCount,
        "LastReprintAt": t.LastReprintAt.isoformat() if t.LastReprintAt else None,
    }


def generate_token(db: Session, employee_code: str) -> dict:
    """Issue (or return existing) mess token for the current active meal."""
    if not get_enabled(db):
        return {"ok": False, "message": "Mess token printing is disabled in Settings."}

    employee_code = (employee_code or "").strip()
    if not employee_code:
        return {"ok": False, "message": "Employee code is required."}
    emp = db.query(Employee).filter(Employee.EmployeeCode == employee_code).first()
    if not emp:
        return {"ok": False, "message": f"Employee '{employee_code}' not found."}

    now = datetime.now()  # local wall-clock
    meal = active_meal(db, now)
    if meal is None:
        return {"ok": False, "message": "No active meal at the current time. Check meal timings in Settings."}

    today = now.date()
    existing = (
        db.query(MessToken)
        .filter(MessToken.EmployeeCode == employee_code)
        .filter(MessToken.MealType == meal.MealType)
        .filter(MessToken.TokenDate == today)
        .first()
    )
    org = _org(db)
    if existing is not None:
        data = _token_payload(existing)
        data.update({"ok": True, "already_generated": True,
                     "message": "Token already generated for this meal.",
                     "organization": org,
                     "qr": _qr_data_url(f"MESS|{today.isoformat()}|{meal.MealType}|{employee_code}|{existing.TokenNumber}")})
        return data

    # Next sequential number for this meal + day.
    count = (
        db.query(MessToken)
        .filter(MessToken.MealType == meal.MealType)
        .filter(MessToken.TokenDate == today)
        .count()
    )
    token = MessToken(
        EmployeeCode=employee_code,
        EmployeeName=emp.EmployeeName,
        MealType=meal.MealType,
        TokenNumber=count + 1,
        TokenDate=today,
        CreatedAt=datetime.utcnow(),
        PrintStatus="Printed",
        ReprintCount=0,
    )
    db.add(token)
    db.commit()
    db.refresh(token)

    data = _token_payload(token)
    data.update({"ok": True, "already_generated": False, "message": "Token generated.",
                 "organization": org,
                 "qr": _qr_data_url(f"MESS|{today.isoformat()}|{meal.MealType}|{employee_code}|{token.TokenNumber}")})
    return data


def reprint(db: Session, token_id: int) -> Optional[dict]:
    t = db.query(MessToken).filter(MessToken.MessTokenId == token_id).first()
    if t is None:
        return None
    t.ReprintCount = (t.ReprintCount or 0) + 1
    t.LastReprintAt = datetime.utcnow()
    db.commit()
    db.refresh(t)
    data = _token_payload(t)
    data.update({"ok": True, "organization": _org(db),
                 "qr": _qr_data_url(f"MESS|{t.TokenDate.isoformat()}|{t.MealType}|{t.EmployeeCode}|{t.TokenNumber}")})
    return data


def generate_token_for_punch(db: Session, employee_code: str, punch_dt: datetime) -> Optional[MessToken]:
    """Auto-issue a token for a punch at the mess device. Uses the PUNCH time to
    pick the meal, dedupes one-per-employee-per-meal-per-day. Caller commits.
    Returns the new MessToken, or None if not applicable / already exists."""
    if not get_enabled(db):
        return None
    code = (employee_code or "").strip()
    if not code:
        return None
    meal = active_meal(db, punch_dt)
    if meal is None:
        return None
    day = punch_dt.date()
    exists = (
        db.query(MessToken)
        .filter(MessToken.EmployeeCode == code, MessToken.MealType == meal.MealType, MessToken.TokenDate == day)
        .first()
    )
    if exists is not None:
        return None
    emp = db.query(Employee).filter(Employee.EmployeeCode == code).first()
    count = db.query(MessToken).filter(MessToken.MealType == meal.MealType, MessToken.TokenDate == day).count()
    token = MessToken(
        EmployeeCode=code,
        EmployeeName=emp.EmployeeName if emp else code,
        MealType=meal.MealType,
        TokenNumber=count + 1,
        TokenDate=day,
        CreatedAt=datetime.utcnow(),
        PrintStatus="Auto",
        ReprintCount=0,
    )
    db.add(token)
    return token


def process_punches_for_mess(db: Session, device_id: int, punches: list[dict], today_only: bool = True) -> int:
    """Given punches [{EmployeeCode, LogDate(datetime)}] just ingested from `device_id`,
    auto-generate mess tokens if that device is the configured mess device.
    Returns the number of tokens created."""
    if not get_enabled(db):
        return 0
    mess_dev = get_mess_device_id(db)
    if mess_dev is None or mess_dev != device_id:
        return 0
    today = datetime.now().date()
    created = 0
    for p in punches:
        dt = p.get("LogDate")
        if not isinstance(dt, datetime):
            continue
        if today_only and dt.date() != today:
            continue
        if generate_token_for_punch(db, p.get("EmployeeCode"), dt) is not None:
            created += 1
    if created:
        db.commit()
    return created


def kiosk_feed(db: Session, since_id: int = 0, limit: int = 20) -> list[dict]:
    """New tokens with MessTokenId > since_id (for the kiosk auto-print display)."""
    org = _org(db)
    rows = (
        db.query(MessToken)
        .filter(MessToken.MessTokenId > since_id)
        .filter(MessToken.TokenDate == datetime.now().date())
        .order_by(MessToken.MessTokenId.asc())
        .limit(limit)
        .all()
    )
    out = []
    for t in rows:
        d = _token_payload(t)
        d["organization"] = org
        d["qr"] = _qr_data_url(f"MESS|{t.TokenDate.isoformat()}|{t.MealType}|{t.EmployeeCode}|{t.TokenNumber}")
        out.append(d)
    return out


def list_tokens(db: Session, on_date: Optional[date], meal: Optional[str], employee_code: Optional[str]) -> list[dict]:
    q = db.query(MessToken)
    if on_date:
        q = q.filter(MessToken.TokenDate == on_date)
    if meal:
        q = q.filter(MessToken.MealType == meal)
    if employee_code:
        q = q.filter(MessToken.EmployeeCode == employee_code)
    rows = q.order_by(MessToken.TokenDate.desc(), MessToken.MessTokenId.desc()).limit(2000).all()
    return [_token_payload(t) for t in rows]
