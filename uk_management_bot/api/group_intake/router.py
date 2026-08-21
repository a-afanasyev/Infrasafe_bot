"""CRUD реестра мониторимых ТГ-групп (Group Intake). Только manager.

- GET    ""      — список групп
- POST   ""      — добавить группу (chat_id обязателен; дубль → 409)
- PATCH  "/{id}" — переключить is_active / поправить title / kind
- DELETE "/{id}" — удалить (в UI предпочтителен toggle — история сохраняется)

Изменения фиксируются: updated_by на строке + audit-строка (кто/что/когда).
⚠️ Прод-edge InfraSafe пускает /uk/api/v2/* по prefix-allowlist — новый префикс
/api/v2/monitored-groups требует добавления на edge (иначе 404 снаружи).
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.api.group_intake.schemas import (
    MonitoredGroupCreate,
    MonitoredGroupListOut,
    MonitoredGroupOut,
    MonitoredGroupUpdate,
)
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.monitored_group import MonitoredGroup
from uk_management_bot.database.models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=MonitoredGroupListOut)
async def list_groups(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
) -> MonitoredGroupListOut:
    rows = (
        (await db.execute(select(MonitoredGroup).order_by(MonitoredGroup.id)))
        .scalars()
        .all()
    )
    total = (
        await db.execute(select(func.count()).select_from(MonitoredGroup))
    ).scalar() or 0
    return MonitoredGroupListOut(
        items=[MonitoredGroupOut.model_validate(r) for r in rows], total=total
    )


@router.post("", response_model=MonitoredGroupOut, status_code=201)
@limiter.limit("30/minute")
async def create_group(
    request: Request,
    body: MonitoredGroupCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
) -> MonitoredGroupOut:
    existing = (
        await db.execute(
            select(MonitoredGroup.id).where(MonitoredGroup.chat_id == body.chat_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Group already registered")

    group = MonitoredGroup(
        chat_id=body.chat_id,
        title=body.title,
        kind=body.kind,
        is_active=True,
        created_by=user.id,
        updated_by=user.id,
    )
    db.add(group)
    db.add(
        AuditLog(
            user_id=user.id,
            telegram_user_id=user.telegram_id,
            action="monitored_group.created",
            details={"chat_id": body.chat_id, "kind": body.kind, "title": body.title},
        )
    )
    await db.commit()
    await db.refresh(group)
    logger.info("Group Intake: группа %s добавлена менеджером %s", body.chat_id, user.id)
    return MonitoredGroupOut.model_validate(group)


@router.patch("/{group_id}", response_model=MonitoredGroupOut)
@limiter.limit("30/minute")
async def update_group(
    request: Request,
    group_id: int,
    body: MonitoredGroupUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
) -> MonitoredGroupOut:
    group = (
        await db.execute(select(MonitoredGroup).where(MonitoredGroup.id == group_id))
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")

    changes: dict = {}
    if body.is_active is not None and body.is_active != group.is_active:
        changes["is_active"] = {"old": group.is_active, "new": body.is_active}
        group.is_active = body.is_active
    if body.title is not None and body.title != group.title:
        changes["title"] = {"old": group.title, "new": body.title}
        group.title = body.title
    if body.kind is not None and body.kind != group.kind:
        changes["kind"] = {"old": group.kind, "new": body.kind}
        group.kind = body.kind

    if changes:
        group.updated_by = user.id
        db.add(
            AuditLog(
                user_id=user.id,
                telegram_user_id=user.telegram_id,
                action="monitored_group.updated",
                details={"group_id": group.id, "chat_id": group.chat_id, **changes},
            )
        )
        await db.commit()
        await db.refresh(group)
    return MonitoredGroupOut.model_validate(group)


@router.delete("/{group_id}", status_code=204)
@limiter.limit("30/minute")
async def delete_group(
    request: Request,
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
) -> None:
    group = (
        await db.execute(select(MonitoredGroup).where(MonitoredGroup.id == group_id))
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")

    db.add(
        AuditLog(
            user_id=user.id,
            telegram_user_id=user.telegram_id,
            action="monitored_group.deleted",
            details={
                "group_id": group.id,
                "chat_id": group.chat_id,
                "kind": group.kind,
                "title": group.title,
            },
        )
    )
    await db.delete(group)
    await db.commit()
    logger.info("Group Intake: группа %s удалена менеджером %s", group.chat_id, user.id)
