"""Singleton-конфиг мониторинга отключений — клон services/auto_manager/config.

``complex_context`` — свободное описание комплекса для LLM (адреса, район,
махалля, ориентиры): это и есть «страница настроек» вместо хардкода адресов.
``keywords`` (ресурс: вода, газ, свет…) и ``event_keywords`` (событие: отключение,
авария…) — детерминированный префильтр: LLM зовём, только если в тексте есть оба.
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
# A11-CODE-02/06: каждый источник — подписка реального Telegram-аккаунта, каждое
# ключевое слово расширяет поток в платный LLM. Слово короче 3 символов как
# подстрока совпадает почти с любым текстом.
MAX_SOURCES = 30
MAX_KEYWORDS = 100
MIN_KEYWORD_LEN = 3
_SOURCE_RE = re.compile(r"^(?:https?://)?(?:t\.me/|telegram\.me/)?@?([A-Za-z][A-Za-z0-9_]{3,31})/?$")

DEFAULT_CONFIG: dict = {
    "sources": [],
    "complex_context": "",
    "keywords": [
        "отключ", "электр", "свет", "вод", "газ", "отопл", "авари", "плановые работы",
        "elektr", "svet", "chiroq", "suv", "gaz", "issiqlik", "o'chir", "ochir", "avariya",
    ],
    # Без слова-события подстрока ресурса ловит «водителей», «газопроводов» —
    # ≈40% отсеянных на profk уходило в LLM впустую. Пустой список = только keywords.
    "event_keywords": [
        "отключ", "авари", "плановые работы", "плановых работ", "ремонт", "прекращ",
        "ограничен", "перебо", "не будет", "o'chir", "ochir", "avariya", "ta'mir",
        "to'xtat", "toxtat", "uzilish", "vaqtincha", "cheklan",
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


def _validate_sources(raw: object, limits: bool) -> list[dict]:
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
    if limits and len(out) > MAX_SOURCES:
        raise ValueError(f"sources: не больше {MAX_SOURCES} источников, получено {len(out)}")
    return out


_APOSTROPHES = str.maketrans({c: "'" for c in "’‘ʻʼ`"})


def normalize_word(text: str) -> str:
    """Нижний регистр + один апостроф: узбекский пишут через ' ’ ʻ ʼ ‘ `."""
    return text.lower().translate(_APOSTROPHES)


def _validate_keywords(raw: object, limits: bool, field: str = "keywords") -> list[str]:
    if raw is None:
        return list(DEFAULT_CONFIG[field])
    if not isinstance(raw, list):
        raise ValueError(f"{field}: ожидается список строк, получено {raw!r}")
    out: list[str] = []
    for word in raw:
        if not isinstance(word, str):
            raise ValueError(f"{field}[]: ожидается строка, получено {word!r}")
        lowered = normalize_word(word.strip())
        if limits and lowered and len(lowered) < MIN_KEYWORD_LEN:
            raise ValueError(f"{field}[]: не короче {MIN_KEYWORD_LEN} символов, получено {word!r}")
        if lowered and lowered not in out:
            out.append(lowered)
    if limits and len(out) > MAX_KEYWORDS:
        raise ValueError(f"{field}: не больше {MAX_KEYWORDS} слов, получено {len(out)}")
    return out


def validate_config(raw: dict, *, limits: bool = True) -> dict:
    """Чистая валидация + нормализация; ValueError на невалидном поле.

    ``limits`` — лимиты A11 (источники ≤ MAX_SOURCES, слова ≤ MAX_KEYWORDS,
    слово ≥ MIN_KEYWORD_LEN): строго при ЗАПИСИ; при чтении сохранённого
    (``load_config``, схема ответа API) — без них, чтобы конфиг, сохранённый до
    введения лимитов, не превращался молча в дефолт с пустыми источниками.
    """
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
        "sources": _validate_sources(raw.get("sources"), limits),
        "complex_context": context,
        "keywords": _validate_keywords(raw.get("keywords"), limits),
        "event_keywords": _validate_keywords(raw.get("event_keywords"), limits, "event_keywords"),
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
        return validate_config(data, limits=False)
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
        return validate_config(data, limits=False)
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


async def update_config_audited(db: AsyncSession, data: dict, *, actor_id: int) -> tuple[dict, dict]:
    """A11-CODE-05: сохранить из API — строка и ``audit_logs`` одной транзакцией → (before, after)."""
    from uk_management_bot.services.config_audit import update_singleton_audited

    return await update_singleton_audited(
        db, NewsWatchConfig, data, validate=validate_config, defaults=DEFAULT_CONFIG,
        actor_id=actor_id, action="news_watch_config_updated",
    )


# ───────────────────────── предполётная проверка (деплой) ─────────────────────────

def check_stored_config_sync(db: Session) -> str | None:
    """Совместим ли СОХРАНЁННЫЙ конфиг с текущими правилами валидации.

    ``load_config`` при невалидных данных молча отдаёт дефолт (пустые источники,
    выключенная автопубликация) — новые правила (A11: лимиты источников/слов)
    без этой проверки тихо обнулили бы настройку на проде. None — совместим
    (или строки ещё нет), иначе текст ошибки валидации.
    """
    row = db.query(NewsWatchConfig).filter(NewsWatchConfig.id == CONFIG_ROW_ID).first()
    if row is None or not row.data:
        return None
    try:
        validate_config(row.data)
    except ValueError as e:
        return str(e)
    return None


def main(argv: list[str] | None = None, *, session_factory=None) -> int:
    """``python -m uk_management_bot.services.news_watch.config --check-stored`` → 0/1."""
    import argparse

    parser = argparse.ArgumentParser(prog="news_watch.config")
    parser.add_argument("--check-stored", action="store_true", required=True,
                        help="проверить сохранённый news_watch_config новыми правилами")
    parser.parse_args(argv)
    if session_factory is None:
        from uk_management_bot.database.session import SessionLocal

        session_factory = SessionLocal
    with session_factory() as db:
        problem = check_stored_config_sync(db)
    if problem:
        logger.error("news_watch_config несовместим с новыми правилами: %s — деплой остановить, "
                     "исправить конфиг в дашборде («Отключения»)", problem)
        return 1
    logger.info("news_watch_config: совместим")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
