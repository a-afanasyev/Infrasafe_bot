"""Singleton-конфиг мониторинга отключений — клон services/auto_manager/config.

``complex_context`` — свободное описание комплекса для LLM (адреса, район,
махалля, ориентиры): это и есть «страница настроек» вместо хардкода адресов.
``keywords`` — детерминированный префильтр: нет совпадения → LLM не зовём.
``sources`` — каналы/группы (@username или ссылка t.me), на которые
подписывается юзербот (получает список через GET /news-watch/sources).
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.database.models.news_item import NewsWatchConfig

logger = logging.getLogger(__name__)

CONFIG_ROW_ID = 1
_CONTEXT_MAX_LEN = 2000
_SOURCE_RE = re.compile(r"^(?:https?://)?(?:t\.me/|telegram\.me/)?@?([A-Za-z][A-Za-z0-9_]{3,31})/?$")

DEFAULT_CONFIG: dict = {
    "sources": [],
    "complex_context": "",
    "keywords": [
        "отключ", "электр", "свет", "вод", "газ", "отопл", "авари", "плановые работы",
        "elektr", "svet", "chiroq", "suv", "gaz", "issiqlik", "o'chir", "ochir", "avariya",
    ],
    "auto_publish": False,
    "min_confidence": 0.8,
    "broadcast": {"dm": True, "residents_groups": True},
}


def normalize_source_chat(raw: object) -> str:
    """``@Name`` / ``t.me/Name`` / ``https://t.me/Name`` → ``@name``."""
    if not isinstance(raw, str):
        raise ValueError(f"sources[].chat: ожидается строка, получено {raw!r}")
    match = _SOURCE_RE.match(raw.strip())
    if not match:
        raise ValueError(f"sources[].chat: ожидается @username или ссылка t.me, получено {raw!r}")
    return "@" + match.group(1).lower()


def _validate_sources(raw: object) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"sources: ожидается список, получено {raw!r}")
    out: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or "chat" not in item:
            raise ValueError(f"sources[]: ожидается {{chat, title?}}, получено {item!r}")
        unknown = sorted(set(item) - {"chat", "title"})
        if unknown:
            raise ValueError(f"sources[]: неизвестные ключи {unknown}")
        chat = normalize_source_chat(item["chat"])
        title = item.get("title") or ""
        if not isinstance(title, str):
            raise ValueError(f"sources[].title: ожидается строка, получено {title!r}")
        if chat in seen:
            continue
        seen.add(chat)
        out.append({"chat": chat, "title": title.strip()[:255]})
    return out


def _validate_keywords(raw: object) -> list[str]:
    if raw is None:
        return list(DEFAULT_CONFIG["keywords"])
    if not isinstance(raw, list):
        raise ValueError(f"keywords: ожидается список строк, получено {raw!r}")
    out: list[str] = []
    for word in raw:
        if not isinstance(word, str):
            raise ValueError(f"keywords[]: ожидается строка, получено {word!r}")
        lowered = word.strip().lower()
        if lowered and lowered not in out:
            out.append(lowered)
    return out


def validate_config(raw: dict) -> dict:
    """Чистая валидация + нормализация; ValueError на невалидном поле."""
    if not isinstance(raw, dict):
        raise ValueError(f"config: ожидается dict, получено {type(raw).__name__}")
    unknown = sorted(set(raw) - set(DEFAULT_CONFIG))
    if unknown:
        raise ValueError(f"config: неизвестные ключи {unknown}")
    cfg = {**DEFAULT_CONFIG, **raw}

    context = cfg["complex_context"]
    if not isinstance(context, str):
        raise ValueError(f"complex_context: ожидается строка, получено {context!r}")
    context = context.strip()
    if len(context) > _CONTEXT_MAX_LEN:
        raise ValueError(f"complex_context: не длиннее {_CONTEXT_MAX_LEN} символов")

    threshold = cfg["min_confidence"]
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0.0 <= threshold <= 1.0:
        raise ValueError(f"min_confidence: ожидается число 0..1, получено {threshold!r}")
    if not isinstance(cfg["auto_publish"], bool):
        raise ValueError(f"auto_publish: ожидается bool, получено {cfg['auto_publish']!r}")

    broadcast_raw = cfg["broadcast"] if cfg["broadcast"] is not None else {}
    if not isinstance(broadcast_raw, dict):
        raise ValueError(f"broadcast: ожидается dict, получено {broadcast_raw!r}")
    unknown = sorted(set(broadcast_raw) - set(DEFAULT_CONFIG["broadcast"]))
    if unknown:
        raise ValueError(f"broadcast: неизвестные ключи {unknown}")
    broadcast = {**DEFAULT_CONFIG["broadcast"], **broadcast_raw}
    for key, value in broadcast.items():
        if not isinstance(value, bool):
            raise ValueError(f"broadcast.{key}: ожидается bool, получено {value!r}")

    return {
        "sources": _validate_sources(raw.get("sources")),
        "complex_context": context,
        "keywords": _validate_keywords(raw.get("keywords")),
        "auto_publish": cfg["auto_publish"],
        "min_confidence": float(threshold),
        "broadcast": broadcast,
    }


# ───────────────────────── sync (воркер/тесты) ─────────────────────────

def load_config_sync(db: Session) -> dict:
    data = DEFAULT_CONFIG
    try:
        row = db.query(NewsWatchConfig).filter(NewsWatchConfig.id == CONFIG_ROW_ID).first()
        if row is not None and row.data:
            data = row.data
    except (OperationalError, ProgrammingError) as e:
        logger.warning("news_watch_config недоступен, отдаю дефолт: %s", e)
    try:
        return validate_config(data)
    except ValueError as e:
        logger.warning("news_watch_config.data не проходит валидацию, отдаю дефолт: %s", e)
        return validate_config(DEFAULT_CONFIG)


def save_config_sync(db: Session, data: dict, updated_by: int | None = None) -> dict:
    validated = validate_config(data)
    row = db.query(NewsWatchConfig).filter(NewsWatchConfig.id == CONFIG_ROW_ID).first()
    if row is None:
        db.add(NewsWatchConfig(id=CONFIG_ROW_ID, data=validated, updated_by=updated_by))
    else:
        row.data = validated
        row.updated_by = updated_by
    db.commit()
    return validated


# ───────────────────────── async (API) ─────────────────────────

async def load_config(db: AsyncSession) -> dict:
    data = DEFAULT_CONFIG
    try:
        result = await db.execute(select(NewsWatchConfig).where(NewsWatchConfig.id == CONFIG_ROW_ID))
        row = result.scalar_one_or_none()
        if row is not None and row.data:
            data = row.data
    except (OperationalError, ProgrammingError) as e:
        logger.warning("news_watch_config недоступен, отдаю дефолт: %s", e)
    try:
        return validate_config(data)
    except ValueError as e:
        logger.warning("news_watch_config.data не проходит валидацию, отдаю дефолт: %s", e)
        return validate_config(DEFAULT_CONFIG)


async def save_config(db: AsyncSession, data: dict, updated_by: int | None = None) -> dict:
    validated = validate_config(data)
    result = await db.execute(select(NewsWatchConfig).where(NewsWatchConfig.id == CONFIG_ROW_ID))
    row = result.scalar_one_or_none()
    if row is None:
        db.add(NewsWatchConfig(id=CONFIG_ROW_ID, data=validated, updated_by=updated_by))
    else:
        row.data = validated
        row.updated_by = updated_by
    await db.commit()
    return validated
