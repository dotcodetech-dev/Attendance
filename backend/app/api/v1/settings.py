"""Organisation branding / address settings (stored in mastersettings key/value)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import get_current_user
from app.database import get_db
from app.models.entities import MasterSetting
from app.schemas.organization import OrganizationOut, OrganizationUpdate

router = APIRouter()

# Setting keys -> defaults (brand comes from BRAND_NAME in .env; the client
# overrides everything here from Configuration -> Organization).
_ORG_KEYS = {
    "OrgName": settings.brand_name,
    "OrgSubtitle": "Attendance Management System",
    "OrgAddress": "",
    "OrgPhone": "",
    "OrgEmail": "",
    "OrgLogo": "",
}


def _read_all(db: Session) -> dict:
    rows = {r.Name: r.Value for r in db.query(MasterSetting).filter(MasterSetting.Name.in_(list(_ORG_KEYS))).all()}
    return {k: (rows.get(k) if rows.get(k) not in (None, "") else default) for k, default in _ORG_KEYS.items()}


def get_organization_settings(db: Session) -> dict:
    """Shared helper so reports can stamp the org header."""
    return _read_all(db)


@router.get("/organization", response_model=OrganizationOut)
def get_organization(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    return OrganizationOut(**_read_all(db))


@router.put("/organization", response_model=OrganizationOut)
def update_organization(
    payload: OrganizationUpdate,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key not in _ORG_KEYS:
            continue
        row = db.query(MasterSetting).filter(MasterSetting.Name == key).first()
        if row is None:
            row = MasterSetting(Name=key)
            db.add(row)
        row.Value = value or ""
    db.commit()
    return OrganizationOut(**_read_all(db))


@router.get("/features")
def get_features(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Which optional modules are switched on (Module Configuration). Drives the sidebar."""
    from app.core.feature_flags import student_leaves_enabled, student_module_enabled
    from app.services import mess_service

    return {
        "student_attendance": student_module_enabled(db),
        "student_leaves": student_leaves_enabled(db),
        "mess_tokens": mess_service.get_enabled(db),
    }
