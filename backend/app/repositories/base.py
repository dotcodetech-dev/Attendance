"""Base for repositories. All data access goes through repositories."""

from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy.orm import Session

from app.database import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Base repository holding a session. Subclasses implement entity-specific queries."""

    def __init__(self, session: Session, model: type[ModelT]) -> None:
        self._session = session
        self._model = model

    @property
    def session(self) -> Session:
        return self._session
