"""Видеоинструкции жителя: «как зарегистрироваться» и «как подать заявку».

Ролики лежат в ``uk_management_bot/assets/tutorials`` (копии
``docs/manuals/video``, ``docs/`` в образ не попадает). Первая отправка
заливает файл, Telegram возвращает file_id — дальше шлём по нему (кэш в
Redis, ключ меняется вместе с размером файла).

Сбои только в лог: ролик не должен ломать онбординг и меню. Автоматические
показы (``send_tutorial_once``, счётчик свободного текста) без Redis НЕ шлют:
иначе /start и /menu одобренного жителя слали бы ролик каждый раз. Кнопки
«Помощи» (``send_tutorial``) работают и без Redis.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile

from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "tutorials"
KINDS = ("registration", "request")

_DAY = 24 * 60 * 60
REGISTRATION_ONCE_TTL = 30 * _DAY
REQUEST_ONCE_TTL = 365 * _DAY
#: Решение владельца 2026-11-04: больше 3 свободных сообщений за сутки →
#: ролик «как подать заявку», не чаще раза в 7 дней.
FREE_TEXT_WINDOW = _DAY
FREE_TEXT_THRESHOLD = 3
FREE_TEXT_OFFER_TTL = 7 * _DAY
#: Сек-ревью 2026-11-04: кнопку «Помощи» можно жать скриптом — не чаще раза в 10 с.
HELP_COOLDOWN = 10


def video_path(kind: str, language: Optional[str]) -> Path:
    """uz и uz_cyrl — узбекский ролик (латиница), остальное — русский."""
    lang = "uz" if (language or "").startswith("uz") else "ru"
    return ASSETS_DIR / f"{kind}_{lang}.mp4"


def file_id_cache_key(path: Path) -> str:
    """Ключ file_id в Redis; меняется вместе с файлом. OSError — файла нет.

    Общий с API (кнопка «Видео о регистрации» в «Жителях»): токен бота один,
    значит и file_id один."""
    return f"tutorial:fid:{path.stem}:{path.stat().st_size}"


async def _get_redis():
    from uk_management_bot.services.redis_pubsub import get_pubsub_redis

    return await get_pubsub_redis()


async def _redis_or_none():
    try:
        return await _get_redis()
    except Exception as exc:  # noqa: BLE001 — см. докстринг модуля
        logger.warning("tutorial: Redis недоступен: %s", type(exc).__name__)
        return None


async def _cached_file_id(redis, key: str) -> Optional[str]:
    if redis is None:
        return None
    try:
        return await redis.get(key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("tutorial: не прочитать file_id из Redis: %s", type(exc).__name__)
        return None


async def _remember_file_id(redis, key: str, msg) -> None:
    video = getattr(msg, "video", None)
    if redis is None or video is None:
        return
    try:
        await redis.set(key, video.file_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("tutorial: не сохранить file_id в Redis: %s", type(exc).__name__)


async def send_tutorial(bot, chat_id: int, kind: str, language: Optional[str],
                        *, caption_key: Optional[str] = None) -> bool:
    """Отправить ролик; True — доставлен."""
    path = video_path(kind, language)
    caption = get_text(caption_key or f"tutorial.{kind}.caption", language=language)
    try:
        key = file_id_cache_key(path)
    except OSError as exc:
        logger.error("tutorial: нет файла ролика %s: %s", path.name, type(exc).__name__)
        return False
    redis = await _redis_or_none()
    try:
        file_id = await _cached_file_id(redis, key)
        if file_id:
            try:
                await bot.send_video(chat_id, file_id, caption=caption, supports_streaming=True)
                return True
            except TelegramBadRequest:
                logger.warning("tutorial: file_id %s не принят, заливаю файл заново", path.stem)
        msg = await bot.send_video(chat_id, FSInputFile(path), caption=caption, supports_streaming=True)
    except Exception as exc:  # noqa: BLE001 — сырой текст ошибки Bot API в лог не пишем
        logger.warning("tutorial: ролик %s не доставлен %s: %s", path.stem, chat_id, type(exc).__name__)
        return False
    await _remember_file_id(redis, key, msg)
    return True


async def send_tutorial_once(bot, user_id: int, kind: str, language: Optional[str], *, ttl: int,
                             flag: Optional[str] = None, caption_key: Optional[str] = None) -> bool:
    """Ролик не чаще раза в ``ttl`` секунд для пары (flag|kind, user_id)."""
    # ponytail: флаг «показан» в Redis, а не в БД — при потере Redis ролик придёт
    # повторно; колонка users.*_video_sent_at, если повтор станет проблемой.
    redis = await _redis_or_none()
    if redis is None:
        return False
    flag_key = f"tutorial:sent:{flag or kind}:{user_id}"
    try:
        if not await redis.set(flag_key, "1", nx=True, ex=ttl):
            return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("tutorial: флаг показа не поставлен: %s", type(exc).__name__)
        return False
    if await send_tutorial(bot, user_id, kind, language, caption_key=caption_key):
        return True
    # Не доставили (сеть, бот заблокирован) — снимаем флаг, иначе ролик не придёт до конца ttl.
    try:
        await redis.delete(flag_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("tutorial: флаг показа не снят: %s", type(exc).__name__)
    return False


async def count_free_text(user_id: int) -> int:
    """Свободные сообщения пользователя за окно FREE_TEXT_WINDOW (0 — Redis недоступен)."""
    redis = await _redis_or_none()
    if redis is None:
        return 0
    key = f"tutorial:free:{user_id}"
    try:
        # Срок ставится вместе с созданием ключа (SET NX EX), INCR его сохраняет:
        # отдельный EXPIRE после INCR мог не выполниться — счётчик жил бы вечно.
        await redis.set(key, 0, nx=True, ex=FREE_TEXT_WINDOW)
        return int(await redis.incr(key))
    except Exception as exc:  # noqa: BLE001
        logger.warning("tutorial: счётчик свободного текста недоступен: %s", type(exc).__name__)
        return 0


async def help_cooldown_passed(user_id: int, kind: str) -> bool:
    """Кнопка «Помощи» — один и тот же ролик не чаще раза в HELP_COOLDOWN секунд
    (оба ролика подряд можно). Без Redis — пропускаем."""
    redis = await _redis_or_none()
    if redis is None:
        return True
    try:
        return bool(await redis.set(f"tutorial:cd:{kind}:{user_id}", "1", nx=True, ex=HELP_COOLDOWN))
    except Exception as exc:  # noqa: BLE001
        logger.warning("tutorial: кулдаун кнопки недоступен: %s", type(exc).__name__)
        return True


#: Ссылки на фоновые задачи: без них asyncio может собрать задачу сборщиком мусора.
_BACKGROUND: set = set()


def schedule(coro) -> None:
    """Ролик — после ответа пользователю, в фоне: /start и меню не ждут Redis и
    загрузку файла. Корутины модуля сами глотают ошибки (см. докстринг)."""
    task = asyncio.get_running_loop().create_task(coro)
    _BACKGROUND.add(task)
    task.add_done_callback(_BACKGROUND.discard)


async def offer_after_free_text(bot, user_id: int, language: Optional[str]) -> bool:
    """После FREE_TEXT_THRESHOLD свободных сообщений за сутки — ролик «как подать заявку»."""
    if await count_free_text(user_id) <= FREE_TEXT_THRESHOLD:
        return False
    return await send_tutorial_once(bot, user_id, "request", language, ttl=FREE_TEXT_OFFER_TTL,
                                    flag="free_text", caption_key="tutorial.free_text_offer")
