from __future__ import annotations
from fastapi import APIRouter

from app.api.v1 import (
    attendance,
    auth,
    biometrics,
    categories,
    commands,
    dashboard,
    devices,
    employees,
    face,
    holidays,
    leave_approvals,
    leave_balance,
    leave_config,
    leaves,
    manual_entries,
    masters,
    mess,
    notifications,
    reports,
    role_config,
    rosters,
    settings as settings_api,
    shifts,
    student_attendance,
    student_leaves,
    student_shifts,
    students,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(devices.router, prefix="/devices", tags=["devices"])
api_router.include_router(employees.router, prefix="/employees", tags=["employees"])
api_router.include_router(biometrics.router, prefix="/biometrics", tags=["biometrics"])
api_router.include_router(face.router, prefix="/face", tags=["face"])
api_router.include_router(commands.router, prefix="/commands", tags=["commands"])
api_router.include_router(attendance.router, prefix="/attendance", tags=["attendance"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(shifts.router, prefix="/shifts", tags=["shifts"])
api_router.include_router(rosters.router, prefix="/rosters", tags=["rosters"])
api_router.include_router(holidays.router, prefix="/holidays", tags=["holidays"])
api_router.include_router(leave_config.router, prefix="/leave-config", tags=["leave-config"])
api_router.include_router(leaves.router, prefix="/leaves", tags=["leaves"])
api_router.include_router(leave_approvals.router, prefix="/leave-approvals", tags=["leave-approvals"])
api_router.include_router(leave_balance.router, prefix="/leave-balance", tags=["leave-balance"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(masters.router, prefix="/masters", tags=["masters"])
api_router.include_router(mess.router, prefix="/mess", tags=["mess"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(students.router, prefix="/students", tags=["students"])
api_router.include_router(student_shifts.router, prefix="/student-shifts", tags=["students"])
api_router.include_router(student_leaves.router, prefix="/student-leaves", tags=["students"])
api_router.include_router(student_attendance.router, prefix="/student-attendance", tags=["students"])
api_router.include_router(settings_api.router, prefix="/settings", tags=["settings"])
api_router.include_router(manual_entries.router, prefix="/manual-entries", tags=["manual-entries"])
api_router.include_router(role_config.router, prefix="/role-config", tags=["role-config"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
