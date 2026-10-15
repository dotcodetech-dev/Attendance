from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


class DeviceCommandCreate(BaseModel):
    DeviceId: int
    command: str
    title: Optional[str] = None
    type: Optional[str] = "manual"
    payload: Optional[str] = None


class DeviceCommandOut(BaseModel):
    DeviceCommandId: int
    DeviceId: int
    Title: Optional[str]
    DeviceCommand: Optional[str]
    Status: Optional[str]

    class Config:
        from_attributes = True


class TransferRequest(BaseModel):
    source_device_id: Optional[int] = None
    employee_ids: list[int] = Field(default_factory=list)
    employee_codes: list[str] = Field(default_factory=list)
    target_device_ids: list[int]
    include_face: bool = True
    include_finger: bool = True
    include_card: bool = True
    include_photo: bool = False
    allow_create_missing_employees: bool = True
    batch_size: int = 500                  # users per batch (max 1000)
    sequential_biometrics: bool = True     # face fully done before finger starts


class TransferJobOut(BaseModel):
    job_id: int
    status: str
    phase: Optional[str]
    total_users: int
    batch_size: int
    total_batches: int
    include_face: bool
    include_finger: bool
    include_card: bool
    include_photo: bool
    sequential_biometrics: bool
    face_queued: int
    face_executed: int
    face_failed: int
    finger_queued: int
    finger_executed: int
    finger_failed: int
    total_commands: int
    pending_commands: int
    sent_commands: int
    executed_commands: int
    failed_commands: int
    created_at: Optional[str]
    completed_at: Optional[str]
    error_message: Optional[str]
