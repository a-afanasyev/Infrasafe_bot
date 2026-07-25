"""Дисковый кэш превью + ограничитель параллельных скачиваний из Telegram.

Зачем это появилось (инцидент 2026-07-25 на profk): публичная витрина «до/после»
на 30 карточках запрашивает 60 изображений за одну загрузку страницы, каждое —
скачивание оригинала из Telegram (~1 с). Пул соединений media-service
(5 + 10 overflow) выедался целиком, запросы вставали на 30 с и падали в 504, а
страдал и приватный путь: тот же `/{media_id}/file` отдаёт фото в карточках
заявок и TWA.

Решение из трёх частей:
  1. витрина получает ПРЕВЬЮ (≈480px JPEG, десятки КБ), а не оригинал;
  2. превью лежат на диске — повторный просмотр не трогает Telegram вообще;
  3. скачивания ограничены семафором.

Вытеснение — по ЗАЯВКАМ, а не по файлам: каталог на заявку, вытесняется целиком
самая давно не читанная. Лимит совпадает с тем, как витрину смотрят («последние
N выполненных работ»), и не даёт одной заявке с восемью фото вытеснить восемь
других заявок.
"""
import asyncio
import io
import logging
import os
import re
import shutil
import time
from typing import Optional

from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)

# request_number приходит из БД, но кладётся в путь на диске — санитизируем
# по allowlist, чтобы никакой «../» не мог оказаться именем каталога.
_SAFE_BUCKET = re.compile(r"[^A-Za-z0-9_-]")

# Один семафор на процесс (uvicorn запущен без --workers, см. Dockerfile).
_download_semaphore: Optional[asyncio.Semaphore] = None
# Сериализует вытеснение: без него два одновременных промаха могли бы удалять
# каталоги друг у друга из-под ног.
_evict_lock = asyncio.Lock()


def download_semaphore() -> asyncio.Semaphore:
    """Ленивая инициализация: `asyncio.Semaphore` привязывается к текущему
    event loop, а на импорте модуля цикла ещё нет."""
    global _download_semaphore
    if _download_semaphore is None:
        _download_semaphore = asyncio.Semaphore(settings.telegram_download_concurrency)
    return _download_semaphore


def _bucket_name(request_number: Optional[str], media_id: int) -> str:
    """Каталог-владелец превью. Для медиа без заявки (домен контроля доступа)
    бакет свой на файл — вытесняться будет так же, по LRU."""
    if request_number:
        return _SAFE_BUCKET.sub("_", request_number)[:64]
    return f"_m{media_id}"


def _paths(media_id: int, request_number: Optional[str]) -> tuple[str, str]:
    bucket = os.path.join(settings.preview_cache_dir, _bucket_name(request_number, media_id))
    return bucket, os.path.join(bucket, f"{media_id}.jpg")


def make_preview(original: bytes) -> Optional[bytes]:
    """Оригинал → JPEG-превью с ограничением по длинной стороне.

    Возвращает None, если Pillow не смог открыть данные (не изображение, битый
    файл) — вызывающий тогда отдаёт оригинал: лучше тяжёлая картинка, чем её
    отсутствие.
    """
    try:
        with Image.open(io.BytesIO(original)) as img:
            # JPEG не умеет альфу и палитру; RGB — единственный безопасный режим.
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img.thumbnail(
                (settings.preview_max_px, settings.preview_max_px), Image.LANCZOS
            )
            out = io.BytesIO()
            img.save(
                out, format="JPEG", quality=settings.preview_jpeg_quality, optimize=True
            )
            return out.getvalue()
    except Exception as e:
        logger.warning("Не удалось построить превью: %s", e)
        return None


def get(media_id: int, request_number: Optional[str]) -> Optional[bytes]:
    """Прочитать превью из кэша. Попадание «трогает» mtime каталога заявки —
    именно по нему считается давность при вытеснении (то есть LRU по чтению,
    а не FIFO по записи)."""
    bucket, path = _paths(media_id, request_number)
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    try:
        os.utime(bucket, None)
    except OSError:
        pass
    return data


async def put(media_id: int, request_number: Optional[str], preview: bytes) -> None:
    """Записать превью и при необходимости вытеснить давние заявки."""
    bucket, path = _paths(media_id, request_number)
    try:
        os.makedirs(bucket, exist_ok=True)
        # Пишем через временный файл: параллельный читатель не должен увидеть
        # полузаписанный JPEG.
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "wb") as f:
            f.write(preview)
        os.replace(tmp, path)
    except OSError as e:
        logger.warning("Не удалось записать превью %s: %s", path, e)
        return
    await _evict_if_needed()


async def _evict_if_needed() -> None:
    limit = settings.preview_cache_max_requests
    if limit <= 0:
        return
    async with _evict_lock:
        try:
            entries = [
                (os.path.getmtime(p), p)
                for p in (
                    os.path.join(settings.preview_cache_dir, name)
                    for name in os.listdir(settings.preview_cache_dir)
                )
                if os.path.isdir(p)
            ]
        except OSError:
            return
        if len(entries) <= limit:
            return
        entries.sort()  # по возрастанию mtime — сначала самые давние
        for _, path in entries[: len(entries) - limit]:
            shutil.rmtree(path, ignore_errors=True)
        logger.info(
            "Кэш превью: вытеснено %d заявок (лимит %d)",
            len(entries) - limit, limit,
        )


def stats() -> dict:
    """Для диагностики (эндпоинт обслуживания и тесты)."""
    try:
        buckets = [
            name for name in os.listdir(settings.preview_cache_dir)
            if os.path.isdir(os.path.join(settings.preview_cache_dir, name))
        ]
    except OSError:
        buckets = []
    files = 0
    size = 0
    for name in buckets:
        d = os.path.join(settings.preview_cache_dir, name)
        for f in os.listdir(d):
            fp = os.path.join(d, f)
            if os.path.isfile(fp):
                files += 1
                size += os.path.getsize(fp)
    return {
        "requests_cached": len(buckets),
        "files": files,
        "bytes": size,
        "limit_requests": settings.preview_cache_max_requests,
        "max_px": settings.preview_max_px,
        "download_concurrency": settings.telegram_download_concurrency,
        "generated_at": time.time(),
    }
