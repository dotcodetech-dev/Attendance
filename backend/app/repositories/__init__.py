"""Data access layer (3-tier: Data tier). Repositories encapsulate all DB operations."""

from app.repositories.category_repository import CategoryRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.roster_repository import RosterRepository
from app.repositories.holiday_repository import HolidayRepository
from app.repositories.leave_config_repository import LeaveConfigRepository
from app.repositories.leave_request_repository import LeaveRequestRepository
from app.repositories.manual_entry_repository import ManualEntryRepository
from app.repositories.device_repository import DeviceRepository
from app.repositories.user_repository import UserRepository

__all__ = [
    "CategoryRepository",
    "EmployeeRepository",
    "ShiftRepository",
    "RosterRepository",
    "HolidayRepository",
    "LeaveConfigRepository",
    "LeaveRequestRepository",
    "ManualEntryRepository",
    "DeviceRepository",
    "UserRepository",
]
