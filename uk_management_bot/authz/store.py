"""Действующие права: значения из каталога плюс переопределения из админки.

Каталог (`authz/catalog.py`) задаёт права «из коробки». Суперадмин может их
переопределить в вебе — строки `rbac_role_permissions` (роль, действие,
разрешено/запрещено) и свои роли `rbac_roles`. Этот модуль собирает итог:

    роли действия = {роль | переопределение(роль, действие),
                            а если его нет — роль ∈ default_roles}

Кэш в процессе: раз в `_CHECK_INTERVAL` секунд сверяем `rbac_state.version`,
и только при новой версии перечитываем таблицы. Изменение из админки
доходит до API, бота и охраны за несколько секунд без рестарта.

Проверки прав зовутся из async-кода (FastAPI, aiogram), а чтение синхронное.
Под нагрузкой проверки берут состояние из памяти, а сверку версии делает
фоновый поток — медленная база не останавливает event loop. Синхронно база
читается, только когда состояние старше `_MAX_STALE`: первая проверка
процесса, первая проверка после простоя и проверка сразу после записи в
админке. Иначе первое действие после простоя прошло бы по уже снятому праву
(фоновая сверка лишь начиналась бы на нём).

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

from sqlalchemy import text

logger = logging.getLogger(__name__)

_CHECK_INTERVAL = 5.0
#: Старше — проверка не отдаёт устаревшее, а перечитывает базу сама.
_MAX_STALE = 3 * _CHECK_INTERVAL
#: Потолок одного запроса чтения прав в PostgreSQL.
_STATEMENT_TIMEOUT = "3s"


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
#: Первое чтение процесса уже было (удачное или нет) — дальше только в фоне.
_first_done = False
#: Идущее фоновое обновление (одно на процесс).
_refresh_thread: Optional[threading.Thread] = None


def _read_version(session) -> Optional[int]:
    from uk_management_bot.database.models.rbac import RbacState

    row = session.get(RbacState, 1)
    return int(row.version) if row is not None else None


def _read_snapshot(session, version: int) -> Snapshot:
    from uk_management_bot.authz.catalog import ACTIONS
    from uk_management_bot.database.models.rbac import RbacRole, RbacRolePermission

    # Строки по действиям, которых больше нет в каталоге, не читаем: если ключ
    # когда-нибудь займёт новое действие, старое переопределение не оживёт.
    # Сами строки удаляет первая же запись в админке (`purge_orphans`).
    overrides = {
        (p.role_key, p.action_key): bool(p.allowed)
        for p in session.query(RbacRolePermission).all()
        if p.action_key in ACTIONS
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
            if session.get_bind().dialect.name == "postgresql":
                session.execute(text(f"SET LOCAL statement_timeout = '{_STATEMENT_TIMEOUT}'"))
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


def _refresh() -> None:
    """Перечитать состояние; при ошибке оставить последнее известное."""
    global _snapshot, _failing
    with _lock:
        current = _snapshot
    try:
        fresh = _load(current)
    except _ReadError as exc:
        with _lock:
            if not _failing:
                fallback = f"версия {_snapshot.version}" if _snapshot else "права из каталога"
                logger.warning("RBAC: таблицы прав не читаются, действует %s: %s", fallback, exc)
            _failing = True
        return
    with _lock:
        _snapshot = fresh
        _failing = False


def _refresh_in_background() -> None:
    try:
        _refresh()
    except Exception:  # noqa: BLE001 — поток не должен умирать молча
        logger.exception("RBAC: фоновое обновление прав упало")


def current_snapshot() -> Optional[Snapshot]:
    """Состояние прав: не старше `_MAX_STALE` секунд, обычно — `_CHECK_INTERVAL`.

    * Первая проверка процесса, проверка после простоя дольше `_MAX_STALE` и
      после `invalidate()` читают базу сами — по устаревшему не отвечают.
    * Состояние старше `_CHECK_INTERVAL`, но моложе `_MAX_STALE` (процесс
      под нагрузкой) отдаётся сразу, а сверка версии идёт в фоновом потоке.
    """
    global _checked_at, _first_done, _refresh_thread
    now = time.monotonic()
    with _lock:
        age = now - _checked_at
        busy = _refresh_thread is not None and _refresh_thread.is_alive()
        sync = not _first_done or (age >= _MAX_STALE and not busy)
        if sync:
            _first_done = True
            _checked_at = now
        elif age >= _CHECK_INTERVAL and not busy:
            _checked_at = now
            _refresh_thread = threading.Thread(target=_refresh_in_background, name="rbac-refresh", daemon=True)
            _refresh_thread.start()
        if not sync:
            return _snapshot
    _refresh()
    with _lock:
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
    """Перечитать версию при следующей проверке (после записи в админке) — сразу,
    синхронно: процесс, записавший правку, не отвечает по старым правам.

    Само состояние не сбрасывается: если перечитать не выйдет, останется
    последнее известное, а не права из каталога.
    """
    global _checked_at
    with _lock:
        # -inf, а не 0: time.monotonic() может быть меньше `_MAX_STALE`.
        _checked_at = float("-inf")


def wait_for_refresh(timeout: float = 5.0) -> None:
    """Дождаться идущего фонового обновления (для тестов)."""
    thread = _refresh_thread
    if thread is not None:
        thread.join(timeout)


def reset_for_tests() -> None:
    """Забыть прочитанное состояние целиком (только для тестов)."""
    global _checked_at, _snapshot, _failing, _first_done
    wait_for_refresh()
    with _lock:
        _checked_at = 0.0
        _snapshot = None
        _failing = False
        _first_done = False
