"""Ручное освобождение presence-сессии оператором (§8.3, §10.3).

Сценарий: «машина уехала, но выездной камеры нет» — оператор/менеджер закрывает
открытую сессию вручную, освобождая место. Под per-barrier-независимый поток (не
конкурирует с приёмом по конкретному авто): закрытие атомарно
``UPDATE ... WHERE status='open'``, аудит append-only (§9.7).

Идемпотентность: повторное закрытие уже закрытой сессии возвращает СОХРАНЁННЫЙ
результат (``replayed=True``), без второго аудита/перехода.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy.orm import Session

from access_control.domain.enums import PresenceStatus
from access_control.repositories import audit_repo, presence_repo


class PresenceSessionNotFound(Exception):
    """Запрошенная presence-сессия не существует (404)."""


@dataclass(frozen=True)
class PresenceCloseResult:
    """Результат ручного закрытия сессии."""

    session_id: int
    status: str
    closed_by_user_id: int | None
    replayed: bool


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def close_presence_session(
    db: Session,
    *,
    session_id: int,
    operator_user_id: int,
    close_reason: str,
    ip_address: str | None = None,
    now: dt.datetime | None = None,
) -> PresenceCloseResult:
    """Закрыть открытую presence-сессию вручную (§8.3). Идемпотентно.

    Открытую → закрывает (``closed``, ``closed_by_user_id``, ``close_reason``) +
    аудит ``access.presence_close``. Уже закрытую → сохранённый результат
    (``replayed=True``). Несуществующую → ``PresenceSessionNotFound``.
    """
    now = now or _utcnow()
    session = presence_repo.get_session(db, session_id)
    if session is None:
        db.rollback()
        raise PresenceSessionNotFound(f"presence session {session_id} not found")

    # Уже закрыта → идемпотентный сохранённый результат (без второго аудита).
    if session.status != PresenceStatus.OPEN.value:
        db.commit()
        return PresenceCloseResult(
            session_id=session.id,
            status=session.status,
            closed_by_user_id=session.closed_by_user_id,
            replayed=True,
        )

    closed_id = presence_repo.close_session_manual(
        db,
        session_id=session_id,
        closed_by_user_id=operator_user_id,
        # Колонка close_reason — VARCHAR(32); полный текст идёт в audit.reason.
        close_reason=close_reason[:32],
        exited_at=now,
    )
    if closed_id is None:
        # Гонка: между чтением и UPDATE кто-то закрыл — вернуть текущее состояние.
        db.rollback()
        session = presence_repo.get_session(db, session_id)
        return PresenceCloseResult(
            session_id=session_id,
            status=session.status if session else PresenceStatus.CLOSED.value,
            closed_by_user_id=session.closed_by_user_id if session else None,
            replayed=True,
        )

    audit_repo.insert(
        db,
        actor_user_id=operator_user_id,
        action="access.presence_close",
        entity_type="vehicle_presence_session",
        entity_id=session_id,
        barrier_id=None,
        source="operator_presence_close",
        reason=close_reason,
        ip_address=ip_address,
    )
    db.commit()
    return PresenceCloseResult(
        session_id=session_id,
        status=PresenceStatus.CLOSED.value,
        closed_by_user_id=operator_user_id,
        replayed=False,
    )
