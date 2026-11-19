"""Единственная точка смены статуса задания уборки.

Вызывающий держит блокировку строки задания (``SELECT … FOR UPDATE``); здесь —
таблица допустимых переходов, счётчик ``version`` и запись в журнал.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.cleaning import CleaningTask, CleaningTaskEvent

# (из, в) — см. раздел 4 плана. Всё, чего здесь нет, запрещено.
ALLOWED: frozenset[tuple[str, str]] = frozenset({
    ("planned", "in_progress"),      # первое активированное фото
    ("in_progress", "accepted"),     # автоприёмка при закрытии последнего слота
    ("in_progress", "review"),       # есть причина или выпала выборка
    ("accepted", "review"),          # жалоба / менеджер открыл повторно
    ("review", "accepted"),          # решение менеджера
    ("review", "rejected"),
    ("review", "in_progress"),       # вернул на досъёмку
    ("planned", "missed"),           # закрытие дня
    ("in_progress", "expired"),
    ("missed", "accepted"),          # ручной зачёт с комментарием
    ("expired", "accepted"),
    ("rejected", "accepted"),
})


class TransitionError(Exception):
    def __init__(self, from_status: str, to_status: str):
        super().__init__(f"{from_status} -> {to_status}")
        self.from_status, self.to_status = from_status, to_status


def log_event(db: AsyncSession, task: CleaningTask, kind: str, *, actor_id: Optional[int] = None,
              from_status: Optional[str] = None, to_status: Optional[str] = None,
              reason: Optional[str] = None, rules_version: Optional[int] = None,
              payload: Optional[dict[str, Any]] = None) -> None:
    db.add(CleaningTaskEvent(
        task_id=task.id, actor_id=actor_id, kind=kind, from_status=from_status, to_status=to_status,
        reason=reason, rules_version=rules_version, payload=payload,
    ))


async def move(db: AsyncSession, task: CleaningTask, to_status: str, *, kind: str,
               actor_id: Optional[int] = None, reason: Optional[str] = None,
               rules_version: Optional[int] = None, payload: Optional[dict[str, Any]] = None) -> None:
    """Перевести задание в ``to_status`` и записать событие; запрещённый переход — ошибка."""
    from_status = task.status
    if (from_status, to_status) not in ALLOWED:
        raise TransitionError(from_status, to_status)
    task.status = to_status
    task.version = (task.version or 1) + 1
    log_event(db, task, kind, actor_id=actor_id, from_status=from_status, to_status=to_status,
              reason=reason, rules_version=rules_version, payload=payload)
    await db.flush()
