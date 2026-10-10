"""Действующие права: значения из каталога плюс переопределения из админки.

Каталог (`authz/catalog.py`) задаёт права «из коробки». Суперадмин может их
переопределить в вебе — строки `rbac_role_permissions` (роль, действие,
разрешено/запрещено) и свои роли `rbac_roles`. Этот модуль собирает итог:

    роли действия = {роль | переопределение(роль, действие),
                            а если его нет — роль ∈ default_roles}

Кэш в процессе: раз в `_CHECK_INTERVAL` секунд сверяем `rbac_state.version`,
и только при новой версии перечитываем таблицы. Изменение из админки
доходит до API, бота и охраны за несколько секунд без рестарта.

Отказоустойчивость: если таблиц нет или база недоступна, действуют права из
каталога — это прежнее поведение, а не «всё разрешено». Ошибка пишется в лог
один раз до следующего успешного чтения.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Mapping, Optional

logger = logging.getLogger(__name__)

_CHECK_INTERVAL = 5.0


@dataclass(frozen=True)
class Snapshot:
    """Прочитанное из базы состояние прав."""

    version: int
    #: (роль, действие) → разрешено ли.
    overrides: Mapping[tuple[str, str], bool] = field(default_factory=dict)
    #: Роли, заведённые в админке (системные + свои).
    roles: frozenset[str] = frozenset()


_lock = threading.Lock()
_snapshot: Optional[Snapshot] = None
_checked_at = 0.0
_failing = False
_effective_cache: dict[str, frozenset[str]] = {}


def _read_version(session) -> Optional[int]:
    from uk_management_bot.database.models.rbac import RbacState

    row = session.get(RbacState, 1)
    return int(row.version) if row is not None else None


def _read_snapshot(session, version: int) -> Snapshot:
    from uk_management_bot.database.models.rbac import RbacRole, RbacRolePermission

    overrides = {
        (p.role_key, p.action_key): bool(p.allowed)
        for p in session.query(RbacRolePermission).all()
    }
    roles = frozenset(key for (key,) in session.query(RbacRole.key).all())
    return Snapshot(version=version, overrides=overrides, roles=roles)


def _load() -> Optional[Snapshot]:
    """Свежее состояние из базы или None, если читать нечего/нельзя."""
    global _failing
    try:
        from uk_management_bot.database.session import SessionLocal

        session = SessionLocal()
        try:
            version = _read_version(session)
            if version is None:
                return None
            current = _snapshot
            if current is not None and current.version == version:
                return current
            return _read_snapshot(session, version)
        finally:
            session.close()
    except Exception as exc:  # noqa: BLE001 — любая ошибка = права из каталога
        if not _failing:
            logger.warning("RBAC: переопределения прав недоступны, действуют права из каталога: %s", exc)
        _failing = True
        return None


def current_snapshot() -> Optional[Snapshot]:
    """Состояние прав, не старше `_CHECK_INTERVAL` секунд."""
    global _snapshot, _checked_at, _failing, _effective_cache
    now = time.monotonic()
    with _lock:
        if now - _checked_at < _CHECK_INTERVAL:
            return _snapshot
        _checked_at = now
    fresh = _load()
    with _lock:
        if fresh is not _snapshot:
            _snapshot = fresh
            _effective_cache = {}
        if fresh is not None:
            _failing = False
        return _snapshot


def resolve(action, snapshot: Optional[Snapshot]) -> frozenset[str]:
    """Роли действия при заданном состоянии (чистая функция, без базы)."""
    if action.superadmin_only:
        return frozenset()
    if snapshot is None:
        return action.default_roles
    candidates = set(action.default_roles) | set(snapshot.roles)
    return frozenset(
        role for role in candidates
        if snapshot.overrides.get((role, action.key), role in action.default_roles)
    )


def effective_roles(action) -> frozenset[str]:
    """Действующие роли действия с учётом админки."""
    snapshot = current_snapshot()
    if snapshot is None:
        return resolve(action, None)
    cached = _effective_cache.get(action.key)
    if cached is None:
        cached = resolve(action, snapshot)
        _effective_cache[action.key] = cached
    return cached


def invalidate() -> None:
    """Сбросить кэш: следующая проверка перечитает базу (после записи в админке)."""
    global _checked_at, _snapshot, _effective_cache
    with _lock:
        _checked_at = 0.0
        _snapshot = None
        _effective_cache = {}
