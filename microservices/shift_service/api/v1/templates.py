# Shift Templates API Router for Shift Service
# UK Management Bot - Shift Service

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.shifts import SpecializationType
from schemas.shifts import ShiftTemplateCreate, ShiftTemplateResponse
from schemas.common import PaginationParams, PaginatedResponse
from services.template_service import TemplateService
from middleware.auth_middleware import get_current_user

router = APIRouter()


@router.post("/", response_model=ShiftTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    template_data: ShiftTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new shift template

    Requires: template:create permission
    """
    template_service = TemplateService(db)
    template = await template_service.create_template(template_data, current_user["user_id"])
    return template


@router.get("/", response_model=PaginatedResponse[ShiftTemplateResponse])
async def list_templates(
    pagination: PaginationParams = Depends(),
    specialization: Optional[SpecializationType] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List shift templates with filtering

    Requires: template:read permission
    """
    template_service = TemplateService(db)
    filters = {
        "specialization": specialization,
        "is_active": is_active
    }
    templates = await template_service.list_templates(pagination, filters)
    return templates


@router.get("/{template_id}", response_model=ShiftTemplateResponse)
async def get_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get a specific template by ID

    Requires: template:read permission
    """
    template_service = TemplateService(db)
    template = await template_service.get_template(template_id)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )

    return template


@router.put("/{template_id}", response_model=ShiftTemplateResponse)
async def update_template(
    template_id: UUID,
    template_data: ShiftTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update a template

    Requires: template:update permission
    """
    template_service = TemplateService(db)
    template = await template_service.update_template(template_id, template_data, current_user["user_id"])

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )

    return template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a template

    Requires: template:delete permission
    """
    template_service = TemplateService(db)
    success = await template_service.delete_template(template_id, current_user["user_id"])

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )


@router.post("/{template_id}/generate-shifts", response_model=dict)
async def generate_shifts_from_template(
    template_id: UUID,
    days_ahead: int = Query(30, ge=1, le=90, description="Days to generate ahead"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Generate shifts from template for specified period

    Requires: shift:create permission
    """
    template_service = TemplateService(db)
    result = await template_service.generate_shifts_from_template(
        template_id, days_ahead, current_user["user_id"]
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )

    return result