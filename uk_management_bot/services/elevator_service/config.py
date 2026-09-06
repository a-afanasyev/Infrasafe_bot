"""Конфиг модуля «Лифты»: строка ``elevators_config`` id=1 ← дефолты.

Паттерн ``api/board_config/service.py:load_board_config``: нет строки / БД
недоступна / битые данные → дефолты, публичные потребители не падают.
Неизвестные ключи сохранённого конфига логируются (один warning на чтение)
и отбрасываются ``merge_config``. Commit — у вызывающего.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.database.models.elevators_config import ElevatorsConfig

from ._core import ElevatorValidationError
from .reminder_rules import merge_config, unknown_config_keys

logger = logging.getLogger(__name__)

CONFIG_ROW_ID = 1


def _defaults() -> dict[str, Any]:
    return merge_config(None, None)


def resolve_stored_config(stored: Mapping[str, Any] | None) -> dict[str, Any]:
    """Сохранённые данные → полный валидный конфиг (терпимо: мусор → дефолты + warning)."""
    if not stored:
        return _defaults()
    unknown = unknown_config_keys(stored)
    if unknown:
        logger.warning("elevators_config: неизвестные ключи отброшены: %s", ", ".join(unknown))
    try:
        return merge_config(stored, None)
    except ElevatorValidationError as exc:
        logger.warning("elevators_config.data невалиден, отдаю дефолты: %s", exc)
        return _defaults()


def load_config_sync(db: Session) -> dict[str, Any]:
    """Конфиг модуля для бота; при недоступности таблицы — дефолты.

    После ``OperationalError``/``ProgrammingError`` транзакция сессии
    сломана (PG: «current transaction is aborted») — откатываем, чтобы
    вызывающий мог продолжить работу в той же сессии.
    """
    try:
        row = db.get(ElevatorsConfig, CONFIG_ROW_ID)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("elevators_config недоступен, отдаю дефолты: %s", exc)
        db.rollback()
        return _defaults()
    return resolve_stored_config(row.data if row is not None else None)


async def load_config_async(db: AsyncSession) -> dict[str, Any]:
    """Async-зеркало ``load_config_sync`` (с ``rollback`` после ошибки БД)."""
    try:
        row = await db.get(ElevatorsConfig, CONFIG_ROW_ID)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("elevators_config недоступен, отдаю дефолты: %s", exc)
        await db.rollback()
        return _defaults()
    return resolve_stored_config(row.data if row is not None else None)


async def save_config_async(
    db: AsyncSession, patch: Mapping[str, Any], *, actor_user_id: int | None
) -> dict[str, Any]:
    """``merge_config(stored, patch)`` + upsert строки id=1; возвращает итоговый конфиг.

    Патч строгий (неизвестные ключи → ``ElevatorValidationError``); сохранённая
    часть терпимая — мусор старых версий при первом сохранении вычищается.
    """
    row = (
        await db.execute(
            select(ElevatorsConfig).where(ElevatorsConfig.id == CONFIG_ROW_ID).with_for_update()
        )
    ).scalar_one_or_none()
    stored = row.data if row is not None and row.data else None
    merged = merge_config(stored, patch)
    if row is None:
        db.add(ElevatorsConfig(id=CONFIG_ROW_ID, data=merged, updated_by=actor_user_id))
    else:
        row.data = merged
        row.updated_by = actor_user_id
    await db.flush()
    return merged
