from __future__ import annotations
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DeviceBase(BaseModel):
    DeviceName: str
    SerialNumber: str
    DeviceIPAddress: Optional[str] = None
    DeviceDirection: Optional[str] = None
    Timezone: Optional[str] = None
    ActivationCode: Optional[str] = None
    DeviceType: Optional[str] = None
    IsAttendanceDevice: Optional[str] = None
    LocationId: Optional[int] = None
    CommKey: Optional[int] = None


class DeviceCreate(DeviceBase):
    pass


class DeviceUpdate(BaseModel):
    DeviceName: Optional[str] = None
    DeviceIPAddress: Optional[str] = None
    DeviceDirection: Optional[str] = None
    Timezone: Optional[str] = None
    ActivationCode: Optional[str] = None
    DeviceType: Optional[str] = None
    IsAttendanceDevice: Optional[str] = None
    LocationId: Optional[int] = None
    CommKey: Optional[int] = None


class DeviceOut(DeviceBase):
    DeviceId: int
    LastPing: Optional[datetime] = None
    TransactionStamp: Optional[str] = None
    OpStamp: Optional[str] = None
    DeviceStatus: Optional[str] = None

    class Config:
        from_attributes = True


class DeviceConnectionTestRequest(BaseModel):
    DeviceIPAddress: str
    Port: int = 4370
    CommKey: Optional[int] = None


class DeviceConnectionTestResponse(BaseModel):
    connected: bool
    reachable: Optional[bool] = None  # True/False from the TCP pre-check; None if not probed
    error_code: Optional[int] = None
    message: Optional[str] = None
    prog_id: Optional[str] = None


class DeviceUserOut(BaseModel):
    EmployeeId: int
    EmployeeCode: str
    EmployeeName: str
    Role: Optional[str] = None
    Status: Optional[str] = None
    SyncDate: Optional[str] = None


class DeviceMachineUserOut(BaseModel):
    EmployeeCode: str
    EmployeeName: Optional[str] = None
    Role: Optional[str] = None
    Enabled: Optional[bool] = None
    Source: Optional[str] = None      # "sdk" = read live from the reader, "push" = from what it pushed to us
    SyncDate: Optional[str] = None
    # What this server holds for the person (templates a reader has sent), not a live count from the reader.
    FaceCount: Optional[int] = None
    FingerCount: Optional[int] = None
    HasPhoto: Optional[bool] = None
    HasFacePhoto: Optional[bool] = None   # BIOPHOTO from an AI-face reader: enough to transfer the face to another AI reader


class DeviceMachineUserDeleteResponse(BaseModel):
    DeviceId: int
    EmployeeCode: str
    connected: bool
    deleted: bool
    error_code: Optional[int] = None
    message: Optional[str] = None
    prog_id: Optional[str] = None


class DevicePhotoPullAttempt(BaseModel):
    method: Optional[str] = None
    detail: Optional[str] = None


class DeviceMachineUserPhotoPullResponse(BaseModel):
    DeviceId: int
    EmployeeCode: str
    connected: bool
    photo_found: bool
    stored: bool
    source: Optional[str] = None
    photo_mime_type: Optional[str] = None
    error_code: Optional[int] = None
    message: Optional[str] = None
    prog_id: Optional[str] = None
    method_used: Optional[str] = None
    attempts: list[DevicePhotoPullAttempt] = Field(default_factory=list)
    available_photo_methods: Optional[str] = None


class DeviceEmployeeImportRequest(BaseModel):
    include_face: bool = True
    include_finger: bool = True
    include_card: bool = True
    include_photo: bool = True
    port: int = 4370


class DeviceEmployeeImportResponse(BaseModel):
    DeviceId: int
    imported: int
    updated: int
    biometric_upserts: int
    photos_upserts: int
    total_device_users: int
    message: Optional[str] = None


class DeviceEmployeeSyncRequest(BaseModel):
    employee_codes: list[str] = Field(default_factory=list)
    include_face: bool = True
    include_finger: bool = True
    include_card: bool = True
    include_photo: bool = True
    queue_only: bool = True


class DeviceEmployeeSyncResponse(BaseModel):
    DeviceId: int
    synced_users: int
    queued_commands: int
    message: Optional[str] = None


class DeviceConnectResponse(BaseModel):
    DeviceId: int
    DeviceStatus: str
    LastPing: Optional[datetime] = None
    connected: bool
    error_code: Optional[int] = None
    message: Optional[str] = None
    prog_id: Optional[str] = None


class DeviceEnrollRequest(BaseModel):
    EmployeeRef: str
    BioType: str = "FINGER"
    AllowUpdate: bool = False
    Port: int = 4370


class DeviceEnrollResponse(BaseModel):
    DeviceId: int
    DeviceStatus: str
    LastPing: Optional[datetime] = None
    EmployeeRef: str
    BioType: str
    already_exists: bool
    connected: bool
    enrollment_started: bool
    error_code: Optional[int] = None
    message: Optional[str] = None
    prog_id: Optional[str] = None
    method_used: Optional[str] = None


class DeviceEnrollStatusResponse(BaseModel):
    DeviceId: int
    EmployeeRef: str
    BioType: str
    connected: bool
    completed: bool
    detected_by: Optional[str] = None
    error_code: Optional[int] = None
    message: Optional[str] = None
    prog_id: Optional[str] = None
