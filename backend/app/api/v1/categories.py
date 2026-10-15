"""Presentation tier: Category API delegates to CategoryService."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database import get_db
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate
from app.services.category_service import CategoryService

router = APIRouter()


def _get_category_service(db: Session = Depends(get_db)) -> CategoryService:
    return CategoryService(db)


@router.get("", response_model=List[CategoryOut])
def list_categories(
    service: CategoryService = Depends(_get_category_service),
    _user=Depends(get_current_user),
) -> List[CategoryOut]:
    return service.list_all()


@router.get("/{category_id}", response_model=CategoryOut)
def get_category(
    category_id: int,
    service: CategoryService = Depends(_get_category_service),
    _user=Depends(get_current_user),
) -> CategoryOut:
    return service.get_by_id(category_id)


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(
    payload: CategoryCreate,
    service: CategoryService = Depends(_get_category_service),
    _user=Depends(get_current_user),
) -> CategoryOut:
    return service.create(payload)


@router.put("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int,
    payload: CategoryUpdate,
    service: CategoryService = Depends(_get_category_service),
    _user=Depends(get_current_user),
) -> CategoryOut:
    return service.update(category_id, payload)


@router.delete("/{category_id}")
def delete_category(
    category_id: int,
    service: CategoryService = Depends(_get_category_service),
    _user=Depends(get_current_user),
) -> dict[str, bool]:
    return service.delete(category_id)
