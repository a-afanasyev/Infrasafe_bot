"""Общая валидация + load/save singleton-конфига «автоматического менеджера».

`validate_config` — чистая функция (без I/O), переиспользуемая и Pydantic-
схемой API (в валидаторе), и ботом (сырой dict из шедулера/хендлера) — должна
вести себя идентично в обоих местах.

Sync-варианты (`load_config_sync`/`save_config_sync`, `Session`) — для бота
(шедулер-job, хендлер меню). Async-варианты (`load_config`/`save_config`,
`AsyncSession`) — для FastAPI-роутера дашборда. Паттерн load/save — клон
board_config (api/board_config/service.py, router.py): толерантность к
отсутствующей строке/таблице (fallback на дефолт), upsert по id=CONFIG_ROW_ID.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.database.models.auto_manager_config import AutoManagerConfig

logger = logging.getLogger(__name__)

CONFIG_ROW_ID = 1

DEFAULT_CONFIG: dict = {
    "enabled": False,
    "mode": "rule",
    "window_start": "20:00",
    "window_end": "08:00",
    "timezone": "Asia/Tashkent",
    "max_requests_per_run": 10,
}

# Строгий HH:MM: два ровно разряда часов и минут. Сам по себе пропускает
# "99:99" (не валидное время) — поэтому дополнительно нужен strptime ниже.
_TIME_RE = re.compile(r"\d{2}:\d{2}")
_VALID_MODES = {"rule", "ai"}


def _validate_time(value: object, field_name: str) -> str:
    """Строгий HH:MM: regex (2+2 цифры) И strptime (реальное время).

    Regex один пропустил бы "99:99" (2 цифры на 2 цифры, но не время).
    strptime один пропустил бы "1:2"/"1:02" (%H/%M не требуют ведущего нуля
    при парсинге) — оба условия обязательны.
    """
    if not isinstance(value, str) or not _TIME_RE.fullmatch(value):
        raise ValueError(f"{field_name}: ожидается строгий формат HH:MM, получено {value!r}")
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError as e:
        raise ValueError(f"{field_name}: невалидное время {value!r}") from e
    return value


def validate_config(raw: dict) -> dict:
    """Чистая валидация + нормализация конфига авто-менеджера.

    Мёрджит `raw` поверх `DEFAULT_CONFIG` (отсутствующие ключи → дефолт), затем
    валидирует каждое поле. Без I/O — вызывается и из Pydantic-схемы API, и из
    сырого dict-пути бота; обязана вести себя идентично в обоих местах.

    Raises:
        ValueError: конкретное поле не прошло валидацию.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"config: ожидается dict, получено {type(raw).__name__}")

    cfg = {**DEFAULT_CONFIG, **raw}

    if not isinstance(cfg["enabled"], bool):
        raise ValueError(f"enabled: ожидается bool, получено {cfg['enabled']!r}")

    if not isinstance(cfg["mode"], str) or cfg["mode"] not in _VALID_MODES:
        raise ValueError(f"mode: ожидается 'rule' или 'ai', получено {cfg['mode']!r}")

    _validate_time(cfg["window_start"], "window_start")
    _validate_time(cfg["window_end"], "window_end")

    if not isinstance(cfg["timezone"], str):
        raise ValueError(f"timezone: ожидается строка, получено {cfg['timezone']!r}")
    try:
        ZoneInfo(cfg["timezone"])
    except ZoneInfoNotFoundError as e:
        raise ValueError(f"timezone: неизвестная IANA-зона {cfg['timezone']!r}") from e

    max_requests = cfg["max_requests_per_run"]
    # bool — подкласс int в Python, исключаем явно (True/False не число заявок).
    if isinstance(max_requests, bool) or not isinstance(max_requests, int):
        raise ValueError(f"max_requests_per_run: ожидается int, получено {max_requests!r}")
    if not (1 <= max_requests <= 50):
        raise ValueError(f"max_requests_per_run: ожидается 1..50, получено {max_requests!r}")

    return cfg


def is_window_active(cfg: dict, now_utc: datetime) -> bool:
    """Активно ли окно авто-менеджера в момент `now_utc` (tz-aware, UTC).

    `cfg` — уже валидированный dict (см. validate_config). Конвертирует
    `now_utc` в `cfg["timezone"]`, берёт time() и сравнивает с window_start/end:
      * start == end        → всегда активно (24/7, явное продуктовое решение).
      * start < end          → активно при start <= t < end (окно в пределах суток).
      * start > end          → активно при t >= start или t < end (окно через полночь).
    """
    tz = ZoneInfo(cfg["timezone"])
    local_time = now_utc.astimezone(tz).time()

    start = datetime.strptime(cfg["window_start"], "%H:%M").time()
    end = datetime.strptime(cfg["window_end"], "%H:%M").time()

    if start == end:
        return True
    if start < end:
        return start <= local_time < end
    return local_time >= start or local_time < end


# ─────────────────────── Sync (бот: шедулер-job, хендлер меню) ───────────────────────

def load_config_sync(db: Session) -> dict:
    """Загрузить конфиг (id=CONFIG_ROW_ID) или отдать дефолт.

    Толерантен к отсутствующей строке (ещё не сохраняли) и к отсутствующей
    таблице (миграция не накатана) — не должен падать вызывающему коду.
    """
    data = DEFAULT_CONFIG
    try:
        row = db.query(AutoManagerConfig).filter(AutoManagerConfig.id == CONFIG_ROW_ID).first()
        if row is not None and row.data:
            data = row.data
    except (OperationalError, ProgrammingError) as e:
        logger.warning("auto_manager_config недоступен, отдаю дефолт: %s", e)

    try:
        return validate_config(data)
    except ValueError as e:
        # Битая/легаси строка в БД не должна ронять шедулер/хендлер — дефолт.
        logger.warning("auto_manager_config.data не проходит валидацию, отдаю дефолт: %s", e)
        return validate_config(DEFAULT_CONFIG)


def save_config_sync(db: Session, data: dict, updated_by: int | None = None) -> dict:
    """Валидировать и сохранить конфиг (upsert по id=CONFIG_ROW_ID)."""
    validated = validate_config(data)

    row = db.query(AutoManagerConfig).filter(AutoManagerConfig.id == CONFIG_ROW_ID).first()
    if row is None:
        db.add(AutoManagerConfig(id=CONFIG_ROW_ID, data=validated, updated_by=updated_by))
    else:
        row.data = validated
        row.updated_by = updated_by
    db.commit()

    return validated


# ───────────────────────── Async (API дашборда) ─────────────────────────

async def load_config(db: AsyncSession) -> dict:
    """Асинхронный аналог load_config_sync — тот же fallback-контракт."""
    data = DEFAULT_CONFIG
    try:
        result = await db.execute(
            select(AutoManagerConfig).where(AutoManagerConfig.id == CONFIG_ROW_ID)
        )
        row = result.scalar_one_or_none()
        if row is not None and row.data:
            data = row.data
    except (OperationalError, ProgrammingError) as e:
        logger.warning("auto_manager_config недоступен, отдаю дефолт: %s", e)

    try:
        return validate_config(data)
    except ValueError as e:
        logger.warning("auto_manager_config.data не проходит валидацию, отдаю дефолт: %s", e)
        return validate_config(DEFAULT_CONFIG)


async def save_config(db: AsyncSession, data: dict, updated_by: int | None = None) -> dict:
    """Асинхронный аналог save_config_sync — тот же upsert-по-id контракт."""
    validated = validate_config(data)

    result = await db.execute(
        select(AutoManagerConfig).where(AutoManagerConfig.id == CONFIG_ROW_ID)
    )
    row = result.scalar_one_or_none()
    if row is None:
        db.add(AutoManagerConfig(id=CONFIG_ROW_ID, data=validated, updated_by=updated_by))
    else:
        row.data = validated
        row.updated_by = updated_by
    await db.commit()

    return validated
