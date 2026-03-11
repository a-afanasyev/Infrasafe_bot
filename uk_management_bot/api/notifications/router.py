from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uk_management_bot.api.dependencies import get_db, get_current_user
from uk_management_bot.database.models.notification import Notification
from uk_management_bot.database.models.user import User
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

router = APIRouter()


class NotificationOut(BaseModel):
    id: int
    notification_type: str
    title: Optional[str] = None
    content: str
    is_read: bool = False
    request_number_fk: Optional[str] = None
    created_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    return result.scalars().all()


@router.patch("/{notification_id}/read")
async def mark_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
    )
    n = result.scalar_one_or_none()
    if n:
        n.is_read = True
        await db.commit()
    return {"ok": True}
