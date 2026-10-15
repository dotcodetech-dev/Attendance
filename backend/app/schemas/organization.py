from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class OrganizationOut(BaseModel):
    OrgName: str
    OrgSubtitle: str
    OrgAddress: Optional[str] = None
    OrgPhone: Optional[str] = None
    OrgEmail: Optional[str] = None
    OrgLogo: Optional[str] = None  # data URL (base64) or http URL


class OrganizationUpdate(BaseModel):
    OrgName: Optional[str] = None
    OrgSubtitle: Optional[str] = None
    OrgAddress: Optional[str] = None
    OrgPhone: Optional[str] = None
    OrgEmail: Optional[str] = None
    OrgLogo: Optional[str] = None
