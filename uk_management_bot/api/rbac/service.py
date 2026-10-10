"""Логика админки ролей: чтение прав, правка ролей, роли сотрудников.

Права читаются здесь напрямую из таблиц (не из кэша `authz/store`), чтобы
страница сразу показывала только что сохранённое. После каждой записи —
`rbac_state.version += 1` (другие процессы перечитают права) и сброс кэша
этого процесса.
"""
from __future__ import annotations

import json
from typing import Iterable, Optional

from fastapi import HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.authz import store
from uk_management_bot.authz.catalog import ACTIONS, SYSTEM_ROLES
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.rbac import RbacRole, RbacRolePermission, RbacState
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.auth_helpers import parse_roles_safe

#: Область действия для группировки на странице — по префиксу ключа.
AREAS: tuple[tuple[str, str], ...] = (
    ("requests.", "Заявки"), ("dashboard.", "Дашборд"), ("callcenter.", "Дашборд"),
    ("feedback.", "Дашборд"), ("group_intake.", "Дашборд"), ("board.", "Дашборд"),
    ("auto_manager.", "Дашборд"), ("work_reports.", "Модули"), ("payments.", "Модули"),
    ("resources.", "Модули"), ("materials.", "Модули"), ("elevators.", "Модули"),
    ("staff.", "Персонал и смены"), ("shifts.", "Персонал и смены"),
    ("shift_transfers.", "Персонал и смены"), ("addresses.", "Адреса и жители"),
    ("residents.", "Адреса и жители"), ("apartments.", "Адреса и жители"),
    ("access.", "Охрана"), ("admin_panel.", "Бот"), ("management.", "Бот"),
    ("execution.", "Бот"), ("rbac.", "Роли и права"),
)

EDITABLE_ACTIONS: frozenset[str] = frozenset(k for k, a in ACTIONS.items() if not a.superadmin_only)


def area_of(key: str) -> str:
    return next((title for prefix, title in AREAS if key.startswith(prefix)), "Прочее")


async def read_snapshot(db: AsyncSession) -> store.Snapshot:
    """Свежее состояние прав из базы (без кэша процесса)."""
    rows = (await db.execute(select(RbacRolePermission))).scalars().all()
    keys = (await db.execute(select(RbacRole.key))).scalars().all()
    version = (await db.execute(select(RbacState.version).where(RbacState.id == 1))).scalar()
    return store.Snapshot(
        version=int(version or 0),
        overrides={(r.role_key, r.action_key): bool(r.allowed) for r in rows},
        roles=frozenset(keys),
    )


def role_actions(role_key: str, snapshot: store.Snapshot) -> set[str]:
    return {key for key, action in ACTIONS.items() if role_key in store.resolve(action, snapshot)}


def default_actions(role_key: str) -> set[str]:
    return {key for key, action in ACTIONS.items() if role_key in action.default_roles}


async def users_count_by_role(db: AsyncSession) -> dict[str, int]:
    counts: dict[str, int] = {}
    rows = (await db.execute(
        select(User.roles).where(User.status != "deleted", User.deleted_at.is_(None))
    )).scalars().all()
    for raw in rows:
        for role in set(parse_roles_safe(raw)):
            counts[role] = counts.get(role, 0) + 1
    return counts


def validate_actions(actions: Iterable[str]) -> set[str]:
    chosen = set(actions)
    unknown = chosen - set(ACTIONS)
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Неизвестные действия: {sorted(unknown)}")
    locked = chosen - EDITABLE_ACTIONS
    if locked:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Эти действия ролям не выдаются: {sorted(locked)}")
    return chosen


async def drop_permissions(db: AsyncSession, role_key: str) -> None:
    await db.execute(delete(RbacRolePermission).where(RbacRolePermission.role_key == role_key))


async def write_permissions(db: AsyncSession, role_key: str, actions: set[str]) -> None:
    """Записать полный набор прав роли: явное «да/нет» по каждому действию."""
    await drop_permissions(db, role_key)
    db.add_all(
        RbacRolePermission(role_key=role_key, action_key=key, allowed=key in actions)
        for key in sorted(EDITABLE_ACTIONS)
    )


async def bump_version(db: AsyncSession) -> None:
    result = await db.execute(
        update(RbacState).where(RbacState.id == 1).values(version=RbacState.version + 1)
    )
    if result.rowcount == 0:
        db.add(RbacState(id=1, version=1))


def audit(db: AsyncSession, actor: User, action: str, details: dict) -> None:
    db.add(AuditLog(user_id=actor.id, telegram_user_id=actor.telegram_id, action=action, details=details))


async def commit_change(db: AsyncSession) -> None:
    await bump_version(db)
    await db.commit()
    store.invalidate()


async def get_role(db: AsyncSession, key: str) -> RbacRole:
    role = await db.get(RbacRole, key)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Роль не найдена")
    return role


async def known_role_keys(db: AsyncSession) -> set[str]:
    return set((await db.execute(select(RbacRole.key))).scalars().all()) | set(SYSTEM_ROLES)


def user_roles_list(user: User) -> list[str]:
    return parse_roles_safe(user.roles)


def apply_user_roles(user: User, roles: list[str]) -> Optional[str]:
    """Записать роли пользователю; режим меню — на первую роль, если прежней нет."""
    unique = list(dict.fromkeys(roles))
    user.roles = json.dumps(unique)
    if user.active_role not in unique:
        user.active_role = unique[0]
    return user.active_role
