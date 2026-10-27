"""Логика админки ролей: чтение прав, правка ролей, роли сотрудников.

Права читаются здесь напрямую из таблиц (не из кэша `authz/store`), чтобы
страница сразу показывала только что сохранённое. Каждая запись начинается с
`begin_change` (`rbac_state.version += 1` под блокировкой строки — другие
процессы перечитают права, параллельные правки идут по очереди) и кончается
`commit_change` (коммит + перечитать права в этом процессе).
"""
from __future__ import annotations

import json
from typing import Iterable, Optional

from fastapi import HTTPException, status
from sqlalchemy import case, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.authz import store
from uk_management_bot.authz.catalog import ACTIONS, SYSTEM_ROLES, is_menu_mode
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.rbac import RbacRole, RbacRolePermission, RbacState
from uk_management_bot.database.models.user import User
from uk_management_bot.database.roles_type import roles_contain
from uk_management_bot.utils.auth_helpers import parse_roles_safe

#: Область действия для группировки на странице — по префиксу ключа. Код
#: области, а не название: подпись переводит фронт (`rbac.areas.<код>`).
AREAS: tuple[tuple[str, str], ...] = (
    ("requests.", "requests"), ("dashboard.", "dashboard"), ("callcenter.", "dashboard"),
    ("feedback.", "dashboard"), ("group_intake.", "dashboard"), ("board.", "dashboard"),
    ("auto_manager.", "dashboard"), ("work_reports.", "modules"), ("payments.", "modules"),
    ("resources.", "modules"), ("materials.", "modules"), ("elevators.", "modules"),
    ("staff.", "staff"), ("shifts.", "staff"),
    ("shift_transfers.", "staff"), ("addresses.", "addresses"),
    ("residents.", "addresses"), ("apartments.", "addresses"),
    ("access.", "access"), ("admin_panel.", "bot"), ("management.", "bot"),
    ("execution.", "bot"), ("rbac.", "rbac"),
)

EDITABLE_ACTIONS: frozenset[str] = frozenset(k for k, a in ACTIONS.items() if not a.superadmin_only)


def area_of(key: str) -> str:
    return next((code for prefix, code in AREAS if key.startswith(prefix)), "other")


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


async def users_count_by_role(db: AsyncSession, role_keys: Iterable[str]) -> dict[str, int]:
    """Число не удалённых пользователей с каждой ролью — одним запросом в базе.

    `roles_contain` компилируется в jsonb `@>` на PostgreSQL (GIN-индекс
    ix_users_roles_gin) и в точный LIKE на sqlite.
    """
    keys = sorted(set(role_keys))
    if not keys:
        return {}
    columns = [func.coalesce(func.sum(case((roles_contain(User.roles, key), 1), else_=0)), 0) for key in keys]
    row = (await db.execute(
        select(*columns).where(User.status != "deleted", User.deleted_at.is_(None))
    )).one()
    return {key: int(count) for key, count in zip(keys, row)}


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
    """Записать права роли: строки только там, где они расходятся с каталогом.

    Совпадающее с правами «из коробки» не хранится — иначе роль «замёрзла» бы,
    и будущая правка `default_roles` в коде к ней бы не применилась. Для своей
    роли «из коробки» нет ничего, поэтому хранятся только разрешения.
    """
    await drop_permissions(db, role_key)
    defaults = default_actions(role_key)
    db.add_all(
        RbacRolePermission(role_key=role_key, action_key=key, allowed=key in actions)
        for key in sorted(EDITABLE_ACTIONS)
        if (key in actions) != (key in defaults)
    )


async def begin_change(db: AsyncSession) -> None:
    """Начать запись в админке: поднять версию прав первым же запросом.

    UPDATE строки `rbac_state` держит её блокировку до коммита, поэтому две
    одновременные правки (две вкладки) идут по очереди, а не падают на
    дубле ключа при «удалить строки → вставить заново».
    """
    result = await db.execute(
        update(RbacState).where(RbacState.id == 1).values(version=RbacState.version + 1)
    )
    if result.rowcount == 0:
        db.add(RbacState(id=1, version=1))
        await db.flush()
    await purge_orphans(db)


async def purge_orphans(db: AsyncSession) -> None:
    """Удалить переопределения действий, которых больше нет в каталоге."""
    await db.execute(delete(RbacRolePermission).where(RbacRolePermission.action_key.not_in(list(ACTIONS))))


def audit(db: AsyncSession, actor: User, action: str, details: dict) -> None:
    db.add(AuditLog(user_id=actor.id, telegram_user_id=actor.telegram_id, action=action, details=details))


async def commit_change(db: AsyncSession) -> None:
    """Закрыть запись: коммит и перечитать права в этом процессе сразу."""
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
    """Записать роли пользователю; режим меню — только системная роль.

    Прежний режим сохраняется, если роль осталась. Иначе — первая системная
    роль из списка (своя роль режимом меню не становится: меню бота строится
    по системным ролям).
    """
    unique = list(dict.fromkeys(roles))
    user.roles = json.dumps(unique)
    modes = [r for r in unique if is_menu_mode(r)]
    if user.active_role not in modes:
        system = [r for r in unique if r in SYSTEM_ROLES]
        user.active_role = (modes or system or unique)[0]
    return user.active_role
