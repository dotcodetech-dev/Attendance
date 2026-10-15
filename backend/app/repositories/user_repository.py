"""Data access for User (auth)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, User)

    def get_by_username(self, login_name: str) -> User | None:
        return (
            self._session.query(User)
            .filter(User.LoginName == login_name)
            .first()
        )

    def get_by_id(self, user_id: int) -> User | None:
        return (
            self._session.query(User)
            .filter(User.UserId == user_id)
            .first()
        )

    def create(self, login_name: str, hashed_password: str, role_name: str | None = "Employee",
               employee_code: str | None = None) -> User:
        user = User(
            LoginName=login_name.strip(),
            LoginPassword=hashed_password,
            RoleName=role_name,
            EmployeeCode=(employee_code or None),
        )
        self._session.add(user)
        self._session.commit()
        self._session.refresh(user)
        return user

    def update_password(self, login_name: str, hashed_password: str) -> User | None:
        user = self.get_by_username(login_name)
        if not user:
            return None
        user.LoginPassword = hashed_password
        self._session.commit()
        self._session.refresh(user)
        return user
