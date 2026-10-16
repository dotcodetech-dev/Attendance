from __future__ import annotations
from fastapi import APIRouter, Depends

from app.services.campus_scope import campus_guard, shared_read_only, shared_unless
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

# Campus-role logins (User Roles) only see their institution: this guard checks every device / employee named in
# the URL of these routers; their list endpoints and request bodies apply the same limit themselves.
_CAMPUS = [Depends(campus_guard)]
# Settings shared by every institution: a campus login may read them, only an Admin may change them.
_SHARED = [Depends(shared_read_only)]
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(devices.router, dependencies=_CAMPUS, prefix="/devices", tags=["devices"])
api_router.include_router(employees.router, dependencies=_CAMPUS, prefix="/employees", tags=["employees"])
api_router.include_router(biometrics.router, dependencies=_CAMPUS, prefix="/biometrics", tags=["biometrics"])
api_router.include_router(face.router, dependencies=_CAMPUS, prefix="/face", tags=["face"])
api_router.include_router(commands.router, dependencies=_CAMPUS, prefix="/commands", tags=["commands"])
api_router.include_router(attendance.router, dependencies=_CAMPUS, prefix="/attendance", tags=["attendance"])
api_router.include_router(categories.router, dependencies=_SHARED, prefix="/categories", tags=["categories"])
api_router.include_router(dashboard.router, dependencies=_CAMPUS, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(shifts.router, dependencies=_SHARED, prefix="/shifts", tags=["shifts"])
api_router.include_router(rosters.router, dependencies=_SHARED, prefix="/rosters", tags=["rosters"])
api_router.include_router(holidays.router, dependencies=_SHARED, prefix="/holidays", tags=["holidays"])
api_router.include_router(leave_config.router, dependencies=[Depends(shared_unless("config_leaves"))], prefix="/leave-config", tags=["leave-config"])
api_router.include_router(leaves.router, dependencies=_CAMPUS, prefix="/leaves", tags=["leaves"])
api_router.include_router(leave_approvals.router, dependencies=_SHARED, prefix="/leave-approvals", tags=["leave-approvals"])
api_router.include_router(leave_balance.router, dependencies=_CAMPUS, prefix="/leave-balance", tags=["leave-balance"])
api_router.include_router(reports.router, dependencies=_CAMPUS, prefix="/reports", tags=["reports"])
api_router.include_router(masters.router, dependencies=_SHARED, prefix="/masters", tags=["masters"])
api_router.include_router(mess.router, dependencies=_SHARED, prefix="/mess", tags=["mess"])
api_router.include_router(notifications.router, dependencies=_CAMPUS, prefix="/notifications", tags=["notifications"])
api_router.include_router(students.router, dependencies=_SHARED, prefix="/students", tags=["students"])
api_router.include_router(student_shifts.router, dependencies=_SHARED, prefix="/student-shifts", tags=["students"])
api_router.include_router(student_leaves.router, dependencies=_SHARED, prefix="/student-leaves", tags=["students"])
api_router.include_router(student_attendance.router, dependencies=_SHARED, prefix="/student-attendance", tags=["students"])
api_router.include_router(settings_api.router, dependencies=_SHARED, prefix="/settings", tags=["settings"])
api_router.include_router(manual_entries.router, dependencies=_CAMPUS, prefix="/manual-entries", tags=["manual-entries"])
api_router.include_router(role_config.router, dependencies=_SHARED, prefix="/role-config", tags=["role-config"])
# Logins check rights per endpoint: everyone may change their own password, which a router guard would block.
api_router.include_router(users.router, prefix="/users", tags=["users"])
