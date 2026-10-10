"""Действующие права: значения из каталога плюс переопределения из админки.

Каталог (`authz/catalog.py`) задаёт права «из коробки». Суперадмин может их
переопределить в вебе — строки `rbac_role_permissions` (роль, действие,
разрешено/запрещено) и свои роли `rbac_roles`. Этот модуль собирает итог:

    роли действия = {роль | переопределение(роль, действие),
                            а если его нет — роль ∈ default_roles}

Кэш в процессе: раз в `_CHECK_INTERVAL` секунд сверяем `rbac_state.version`,
и только при новой версии перечитываем таблицы. Изменение из админки
доходит до API, бота и охраны за несколько секунд без рестарта.

Отказоустойчивость: если таблиц нет или база ни разу не прочиталась, действуют
права из каталога — прежнее поведение, а не «всё разрешено». Если база была
прочитана, а потом временно недоступна, действует последнее прочитанное
состояние: снятое в админке право не возвращается из-за сбоя чтения. Ошибка
пишется в лог один раз до следующего успешного чтения.
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
    #: Посчитанные роли действий для ЭТОГО состояния. Кэш живёт в самом
    #: снимке: значение, посчитанное по старому состоянию, не может попасть
    #: в кэш нового, даже если снимок сменился посреди проверки в другом потоке.
    cache: dict[str, frozenset[str]] = field(default_factory=dict, compare=False, repr=False)


class _ReadError(Exception):
    """База не прочиталась (в отличие от «таблиц прав ещё нет»)."""


_lock = threading.Lock()
_snapshot: Optional[Snapshot] = None
_checked_at = 0.0
_failing = False


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


def _load(current: Optional[Snapshot]) -> Optional[Snapshot]:
    """Свежее состояние; None — переопределений нет (нет строки версии).

    Ошибку чтения не прячет — поднимает `_ReadError`, чтобы вызывающий
    оставил последнее известное состояние.
    """
    try:
        from uk_management_bot.database.session import SessionLocal

        session = SessionLocal()
        try:
            version = _read_version(session)
            if version is None:
                return None
            if current is not None and current.version == version:
                return current
            return _read_snapshot(session, version)
        finally:
            session.close()
    except Exception as exc:  # noqa: BLE001 — любая ошибка чтения
        raise _ReadError(str(exc)) from exc


def current_snapshot() -> Optional[Snapshot]:
    """Состояние прав, не старше `_CHECK_INTERVAL` секунд."""
    global _snapshot, _checked_at, _failing
    now = time.monotonic()
    with _lock:
        if now - _checked_at < _CHECK_INTERVAL:
            return _snapshot
        _checked_at = now
        current = _snapshot
    try:
        fresh = _load(current)
    except _ReadError as exc:
        with _lock:
            if not _failing:
                fallback = f"версия {_snapshot.version}" if _snapshot else "права из каталога"
                logger.warning("RBAC: таблицы прав не читаются, действует %s: %s", fallback, exc)
            _failing = True
            return _snapshot
    with _lock:
        _snapshot = fresh
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
    cached = snapshot.cache.get(action.key)
    if cached is None:
        cached = resolve(action, snapshot)
        snapshot.cache[action.key] = cached
    return cached


def invalidate() -> None:
    """Перечитать версию при следующей проверке (после записи в админке).

    Само состояние не сбрасывается: если перечитать не выйдет, останется
    последнее известное, а не права из каталога.
    """
    global _checked_at
    with _lock:
        _checked_at = 0.0


def reset_for_tests() -> None:
    """Забыть прочитанное состояние целиком (только для тестов)."""
    global _checked_at, _snapshot, _failing
    with _lock:
        _checked_at = 0.0
        _snapshot = None
        _failing = False
