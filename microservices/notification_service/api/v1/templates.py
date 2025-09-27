# Template management API endpoints
# UK Management Bot - Notification Service

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from models.notification import NotificationType, NotificationChannel
from schemas.notification import (
    NotificationTemplateCreate,
    NotificationTemplateResponse
)
from services.template_service import TemplateService
from database import get_db

router = APIRouter(prefix="/templates", tags=["templates"])

@router.post("/", response_model=NotificationTemplateResponse)
async def create_template(
    template: NotificationTemplateCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new notification template"""
    try:
        service = TemplateService(db)
        result = await service.create_template(template)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create template: {str(e)}")

@router.get("/", response_model=List[NotificationTemplateResponse])
async def get_all_templates(
    db: AsyncSession = Depends(get_db)
):
    """Get all notification templates"""
    try:
        service = TemplateService(db)
        templates = await service.get_all_templates()
        return templates
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve templates: {str(e)}")

@router.get("/type/{notification_type}/channel/{channel}")
async def get_template(
    notification_type: NotificationType,
    channel: NotificationChannel,
    language: str = "ru",
    db: AsyncSession = Depends(get_db)
):
    """Get template for specific notification type and channel"""
    try:
        service = TemplateService(db)
        template = await service.get_template(notification_type, channel, language)

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        return template
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve template: {str(e)}")

@router.put("/{template_id}", response_model=NotificationTemplateResponse)
async def update_template(
    template_id: int,
    template: NotificationTemplateCreate,
    db: AsyncSession = Depends(get_db)
):
    """Update existing template"""
    try:
        service = TemplateService(db)
        result = await service.update_template(template_id, template)

        if not result:
            raise HTTPException(status_code=404, detail="Template not found")

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update template: {str(e)}")

@router.delete("/{template_id}")
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete template"""
    try:
        service = TemplateService(db)
        success = await service.delete_template(template_id)

        if not success:
            raise HTTPException(status_code=404, detail="Template not found")

        return {"message": "Template deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete template: {str(e)}")

@router.post("/render")
async def render_template(
    template_id: int,
    variables: dict,
    db: AsyncSession = Depends(get_db)
):
    """Render template with variables"""
    try:
        service = TemplateService(db)

        # First get the template
        from schemas.notification import NotificationTemplateResponse
        from sqlalchemy import select
        from models.notification import NotificationTemplate

        stmt = select(NotificationTemplate).where(NotificationTemplate.id == template_id)
        result = await db.execute(stmt)
        template_model = result.scalar_one_or_none()

        if not template_model:
            raise HTTPException(status_code=404, detail="Template not found")

        template = NotificationTemplateResponse.from_orm(template_model)

        # Render template
        rendered = await service.render_template(template, variables)
        return rendered

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to render template: {str(e)}")

@router.post("/initialize-defaults")
async def initialize_default_templates(
    db: AsyncSession = Depends(get_db)
):
    """Initialize default notification templates"""
    try:
        service = TemplateService(db)
        await service.initialize_default_templates()
        return {"message": "Default templates initialized successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize default templates: {str(e)}")