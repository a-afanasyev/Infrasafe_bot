"""A10-INF-05: след входа в дашборд в `audit_logs`.

Роли, инвайты и админ-действия аудировались, а сам вход (пароль+OTP, Telegram
Widget) — нет: расследовать перебор или компрометацию аккаунта по БД было нельзя,
только по stdout. Запись best-effort: сбой аудита не должен ломать вход.
Для неуспешного входа user_id нет — пишем хэш логина, не сам email.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.user import User

logger = logging.getLogger(__name__)

LOGIN_OK = "auth.login_ok"
LOGIN_FAILED = "auth.login_failed"


def _login_hash(login: str) -> str:
    return hashlib.sha256(login.strip().lower().encode()).hexdigest()[:16]


async def audit_login(
    db: AsyncSession,
    *,
    ok: bool,
    method: str,
    ip: Optional[str],
    user: Optional[User] = None,
    login: Optional[str] = None,
) -> None:
    details: dict = {"method": method}
    if login is not None:
        details["login_hash"] = _login_hash(login)
    try:
        db.add(
            AuditLog(
                user_id=user.id if user else None,
                telegram_user_id=user.telegram_id if user else None,
                action=LOGIN_OK if ok else LOGIN_FAILED,
                details=details,
                ip_address=(ip or "")[:45] or None,
            )
        )
        await db.commit()
    except Exception as exc:  # noqa: BLE001 — аудит не должен ломать вход
        logger.error("login audit failed: %s", exc)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
