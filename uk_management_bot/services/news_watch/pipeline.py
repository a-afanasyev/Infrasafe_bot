"""Конвейер мониторинга отключений: inbox → решение → объявление + рассылка.

``ingest``: дедуп по (source_chat_id, source_message_id) → детерминированный
префильтр по ``keywords`` (нет совпадения → ``ignored``, LLM не зовём) → LLM
(``services/llm``, structured output: релевантна ли новость комплексу по
``complex_context``) → ``pending`` (менеджеру — уведомление) или ``ignored``.
Отказ LLM — ``pending`` без вердикта: новость с ключевыми словами не должна
потеряться молча. ``auto_publish`` при уверенности ≥ порога публикует сразу.

``publish``: объявление на табло (``board_config.announcements``, под FOR
UPDATE в той же транзакции) + outbox рассылки (``broadcast_status=pending``,
воркер — ``services/news_watch/broadcast``). Повторная публикация запрещена;
``retry_broadcast`` — только из ``failed``.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.news_item import (
    BROADCAST_DONE,
    BROADCAST_FAILED,
    BROADCAST_NONE,
    BROADCAST_PENDING,
    NEWS_KINDS,
    NEWS_STATUS_IGNORED,
    NEWS_STATUS_PENDING,
    NEWS_STATUS_PUBLISHED,
    NEWS_STATUS_REJECTED,
    NewsItem,
)
from uk_management_bot.services.llm.client import llm_json_async
from uk_management_bot.services.news_watch.config import load_config

logger = logging.getLogger(__name__)

_TEXT_LIMIT = 3000
_SUMMARY_LIMIT = 500
_MAX_TOKENS = 500
_ICONS = {"power": "⚡", "water": "💧", "gas": "🔥", "heating": "🌡", "internet": "🌐", "other": "📢"}


class NewsWatchError(Exception):
    """Нарушение контракта конвейера (неверный статус, нет новости, флаг выключен)."""


@dataclass(frozen=True)
class Inbound:
    source_chat_id: int
    source_message_id: int
    chat_title: Optional[str]
    text: str
    posted_at: Optional[datetime]


# ───────────── правила ─────────────


def prefilter(text: str, keywords: list[str]) -> bool:
    """Есть ли в тексте хотя бы одно ключевое слово (подстрока, без регистра)."""
    if not text:
        return False
    lowered = text.lower()
    return any(word and word in lowered for word in keywords)


# ───────────── LLM ─────────────


def _schema() -> dict:
    # Плоская схема (structured outputs): словари и диапазоны — в _parse_verdict.
    return {
        "type": "object",
        "properties": {
            "relevant": {"type": "boolean"},
            "kind": {"type": "string"},
            "starts_at": {"type": ["string", "null"]},
            "ends_at": {"type": ["string", "null"]},
            "summary_ru": {"type": "string"},
            "summary_uz": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["relevant", "kind", "starts_at", "ends_at", "summary_ru", "summary_uz", "confidence"],
        "additionalProperties": False,
    }


_BASE_PROMPT = (
    "Ты — диспетчер управляющей компании жилого комплекса. Тебе дают сообщение из "
    "Telegram-канала коммунальной службы или хокимията (русский или узбекский язык, "
    "узбекский бывает кириллицей и латиницей) и описание нашего комплекса. "
    "Определи, касается ли сообщение НАШЕГО комплекса: отключение или ограничение "
    "электричества, воды, газа, отопления, интернета, плановые работы, аварии — "
    "именно по нашим адресам/району/махалле/ориентирам из описания. Общегородские "
    "новости без привязки к нашему району, реклама, поздравления — не касаются.\n"
    "Верни JSON: relevant (true/false); kind — power|water|gas|heating|internet|other; "
    "starts_at/ends_at — ISO 8601 с датой и временем, если они названы, иначе null "
    "(год — текущий, если не указан); summary_ru и summary_uz — одно-два предложения "
    "для жителей на каждом языке: что отключают, где, когда (без ссылок и телефонов); "
    "confidence — уверенность 0..1, что это про наш комплекс."
)


@lru_cache(maxsize=8)
def _system_prompt(complex_context: str) -> str:
    """Стабильный префикс (кэшируется провайдером) + описание комплекса."""
    return f"{_BASE_PROMPT}\n\nОписание нашего комплекса:\n{complex_context or '—'}"


def _parse_iso(raw: object) -> Optional[datetime]:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        value = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _parse_verdict(payload: dict) -> Optional[dict]:
    """Python-валидация ответа модели; битый ответ → None (как отказ LLM)."""
    try:
        relevant = bool(payload["relevant"])
        kind = str(payload["kind"] or "").lower()
        confidence = float(payload["confidence"])
        summary_ru = str(payload.get("summary_ru") or "").strip()[:_SUMMARY_LIMIT]
        summary_uz = str(payload.get("summary_uz") or "").strip()[:_SUMMARY_LIMIT]
    except (KeyError, TypeError, ValueError):
        return None
    if isinstance(payload.get("confidence"), (bool, str)) or not (math.isfinite(confidence) and 0.0 <= confidence <= 1.0):
        return None
    if kind not in NEWS_KINDS:
        return None
    return {
        "relevant": relevant, "kind": kind, "confidence": confidence,
        "summary_ru": summary_ru, "summary_uz": summary_uz,
        "starts_at": _parse_iso(payload.get("starts_at")), "ends_at": _parse_iso(payload.get("ends_at")),
    }


async def classify_async(text: str, complex_context: str) -> Optional[dict]:
    payload = await llm_json_async(
        system=_system_prompt(complex_context),
        user=f"Сообщение:\n{text[:_TEXT_LIMIT]}",  # html-raw: промпт LLM, не Telegram
        schema=_schema(),
        model=settings.NEWS_WATCH_MODEL,
        timeout=settings.NEWS_WATCH_LLM_TIMEOUT,
        max_tokens=_MAX_TOKENS,
        effort=settings.AI_MANAGER_EFFORT,
        tag="news_watch",
    )
    return _parse_verdict(payload) if payload is not None else None


# ───────────── inbox ─────────────


async def ingest(db: AsyncSession, inbound: Inbound) -> tuple[NewsItem, bool]:
    """Принять новость. Возвращает (строка, создана ли сейчас). Коммитит."""
    if not settings.NEWS_WATCH_ENABLED:
        raise NewsWatchError("news-watch выключен")
    existing = (await db.execute(
        select(NewsItem).where(NewsItem.source_chat_id == inbound.source_chat_id,
                               NewsItem.source_message_id == inbound.source_message_id)
    )).scalar_one_or_none()
    if existing is not None:
        return existing, False

    cfg = await load_config(db)
    item = NewsItem(
        source_chat_id=inbound.source_chat_id, source_message_id=inbound.source_message_id,
        chat_title=(inbound.chat_title or "")[:255] or None, raw_text=inbound.text,
        posted_at=inbound.posted_at, status=NEWS_STATUS_IGNORED, broadcast_status=BROADCAST_NONE,
    )
    if prefilter(inbound.text, cfg["keywords"]):
        verdict = await classify_async(inbound.text, cfg["complex_context"])
        if verdict is None:
            item.status = NEWS_STATUS_PENDING  # LLM недоступен — решает человек
        else:
            item.relevant = verdict["relevant"]
            item.kind, item.confidence = verdict["kind"], verdict["confidence"]
            item.summary_ru, item.summary_uz = verdict["summary_ru"], verdict["summary_uz"]
            item.starts_at, item.ends_at = verdict["starts_at"], verdict["ends_at"]
            item.status = NEWS_STATUS_PENDING if verdict["relevant"] else NEWS_STATUS_IGNORED
    db.add(item)
    await db.flush()

    if (item.status == NEWS_STATUS_PENDING and item.relevant and cfg["auto_publish"]
            and (item.confidence or 0.0) >= cfg["min_confidence"]):
        await _publish_item(db, item, user_id=None, cfg=cfg)
    await db.commit()
    await db.refresh(item)

    logger.info("news_watch: item %s from %s → %s (kind=%s conf=%s)",
                item.id, inbound.source_chat_id, item.status, item.kind, item.confidence)
    return item, True


# ───────────── публикация ─────────────


def kind_title(kind: Optional[str], lang: str) -> str:
    from uk_management_bot.utils.helpers import get_text

    return get_text(f"news_watch.kind.{kind if kind in NEWS_KINDS else 'other'}", language=lang)


def announcement_from(item: NewsItem) -> dict:
    """Элемент board_config.announcements (services/board_config/schemas.py)."""
    published = item.published_at or datetime.now(timezone.utc)
    return {
        "id": f"news-{item.id}",
        "icon": _ICONS.get(item.kind or "other", "📢"),
        "important": True,
        "title": {"ru": kind_title(item.kind, "ru"), "uz": kind_title(item.kind, "uz")},
        "text": {"ru": item.summary_ru or item.raw_text[:_SUMMARY_LIMIT],
                 "uz": item.summary_uz or item.raw_text[:_SUMMARY_LIMIT]},
        "published_at": published.replace(tzinfo=None).isoformat(timespec="seconds"),
    }


async def _publish_item(db: AsyncSession, item: NewsItem, *, user_id: Optional[int], cfg: dict) -> None:
    from uk_management_bot.services.board_config.service import append_announcement

    item.status = NEWS_STATUS_PUBLISHED
    item.published_at = datetime.now(timezone.utc)
    item.decided_by = user_id
    wants_broadcast = cfg["broadcast"]["dm"] or cfg["broadcast"]["residents_groups"]
    item.broadcast_status = BROADCAST_PENDING if wants_broadcast else BROADCAST_DONE
    item.broadcast_attempts, item.broadcast_cursor = 0, 0
    await append_announcement(db, announcement_from(item), user_id)


async def _get_item(db: AsyncSession, item_id: int) -> NewsItem:
    item = await db.get(NewsItem, item_id)
    if item is None:
        raise NewsWatchError(f"новость {item_id} не найдена")
    return item


async def publish(db: AsyncSession, item_id: int, *, user_id: int) -> NewsItem:
    item = await _get_item(db, item_id)
    if item.status != NEWS_STATUS_PENDING:
        raise NewsWatchError(f"новость {item_id}: публиковать можно только из pending, сейчас {item.status}")
    await _publish_item(db, item, user_id=user_id, cfg=await load_config(db))
    await db.commit()
    await db.refresh(item)
    return item


async def reject(db: AsyncSession, item_id: int, *, user_id: int) -> NewsItem:
    item = await _get_item(db, item_id)
    if item.status != NEWS_STATUS_PENDING:
        raise NewsWatchError(f"новость {item_id}: отклонить можно только из pending, сейчас {item.status}")
    item.status, item.decided_by = NEWS_STATUS_REJECTED, user_id
    await db.commit()
    await db.refresh(item)
    return item


async def retry_broadcast(db: AsyncSession, item_id: int) -> NewsItem:
    """failed → pending; курсор НЕ сбрасывается (уже получившие не получат дубль)."""
    item = await _get_item(db, item_id)
    if item.status != NEWS_STATUS_PUBLISHED or item.broadcast_status != BROADCAST_FAILED:
        raise NewsWatchError(f"новость {item_id}: повтор рассылки только из failed")
    item.broadcast_status, item.broadcast_attempts, item.broadcast_next_at = BROADCAST_PENDING, 0, None
    await db.commit()
    await db.refresh(item)
    return item
