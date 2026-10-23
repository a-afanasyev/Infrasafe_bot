"""A10-API-01: след выдачи менеджерских прав из дашборда.

Решение владельца 2026-10-24: менеджер по-прежнему может выпустить инвайт на
роль manager и активировать pending-менеджера (второй путь к роли помимо
админки RBAC), но каждое такое действие пишется в `audit_logs` и уходит
уведомлением суперадминам — иначе украденная сессия менеджера заводила бы
«своего» менеджера без следа.

Живёт в service-слое: роутер `api/shifts/router/` не делает ORM напрямую
(гейт `test_shifts_router_inventory.py`), а имя роли сравнивается здесь через
константу, не литералом в хендлере (ратчет `test_rbac_baseline.py`).
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.admin_notify import notify_superadmins
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.auth_helpers import get_user_roles

logger = logging.getLogger(__name__)

ACTION_INVITE = "staff.manager_invite_created"
ACTION_ACTIVATED = "staff.manager_activated"

#: Роль, выдача которой из дашборда считается привилегированной.
PRIVILEGED_ROLE = "manager"


def is_manager_role(role: str) -> bool:
    return role == PRIVILEGED_ROLE


def has_manager_role(user: User) -> bool:
    return PRIVILEGED_ROLE in get_user_roles(user)


async def record_manager_grant(
    db: AsyncSession, *, actor: User, action: str, details: dict, text: str
) -> None:
    """Записать аудит (коммит) и best-effort уведомить суперадминов."""
    db.add(
        AuditLog(
            user_id=actor.id,
            telegram_user_id=actor.telegram_id,
            action=action,
            details={"actor_telegram_id": actor.telegram_id, **details},
        )
    )
    await db.commit()
    try:
        await notify_superadmins(text)
    except Exception as exc:  # noqa: BLE001 — уведомление не должно ломать действие
        logger.error("manager grant notification failed: %s", exc)
