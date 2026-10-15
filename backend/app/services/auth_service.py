"""Business logic for authentication (3-tier: Application tier)."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.entities import User
from app.repositories.user_repository import UserRepository
from app.services.employee_status import login_block_reason


class AuthService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = UserRepository(session)

    def login(self, username: str, password: str) -> dict[str, str]:
        normalized_username = username.strip()
        is_admin = normalized_username.lower() == settings.admin_username.lower()
        try:
            user = self._repo.get_by_username(normalized_username)
        except SQLAlchemyError as exc:
            # Allow the admin bootstrap password even when the DB is unavailable.
            if is_admin and password == settings.admin_password:
                token = create_access_token(settings.admin_username)
                return {"access_token": token}
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Database unavailable: {exc.__class__.__name__}",
            ) from exc
        # Admin with no DB row yet (fresh install): accept the config bootstrap password.
        # Once the admin changes their password a DB row exists and is checked below instead,
        # so the default admin password stops working.
        if is_admin and not user:
            if password == settings.admin_password:
                token = create_access_token(settings.admin_username)
                return {"access_token": token}
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        if not verify_password(password, user.LoginPassword):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        reason = login_block_reason(self._session, user)
        if reason:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)
        token = create_access_token(user.LoginName)
        return {"access_token": token}

    def create_user(self, login_name: str, password: str, role_name: str | None = "Employee",
                    employee_code: str | None = None) -> User:
        normalized = login_name.strip()
        if not normalized:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Login name is required")
        existing = self._repo.get_by_username(normalized)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
        hashed = get_password_hash(password)
        return self._repo.create(normalized, hashed, role_name or "Employee", (employee_code or "").strip() or None)

    def reset_password(self, login_name: str, new_password: str) -> User:
        normalized = login_name.strip()
        if not normalized:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Login name is required")
        hashed = get_password_hash(new_password)
        user = self._repo.get_by_username(normalized)
        if not user:
            # The built-in admin account is config-only until its password is first changed;
            # create its DB row now so the new password persists and takes effect at login.
            if normalized.lower() == settings.admin_username.lower():
                return self._repo.create(settings.admin_username, hashed, "Admin", None)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        updated = self._repo.update_password(normalized, hashed)
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return updated
