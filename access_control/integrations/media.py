"""Тонкий async httpx-клиент к медиа-сервису для access_control (§11, §10.2).

Загрузка фото проезда (номер/обзор) в ОТДЕЛЬНЫЙ канал медиа-сервиса ВНЕ горячего
пути решения (§10.2: ingestion p95 ≤500мс, а загрузка в Telegram медленная —
секунды). Отдача — стримом байтов по ``media://``-ссылке (см. registry ``/photos``).

Контракт медиа-сервиса (готов, см. ``media_service``):
* ``POST {MEDIA_SERVICE_URL}/api/v1/media/upload-access`` — заголовок
  ``X-API-Key``, multipart ``file`` + ``kind`` (plate|overview) + ``ref`` +
  опц. ``uploaded_by`` → 201 ``{media_file:{id, telegram_file_id, ...},
  file_url}``; нет канала access → 503;
* ``GET {MEDIA_SERVICE_URL}/api/v1/media/{media_id}/file`` (``X-API-Key``) — стрим.

Пакет ``media_service`` в access-образ НЕ импортируется (его там нет) — это
самостоятельный httpx-клиент.

Конфиг из окружения: ``MEDIA_SERVICE_URL`` + ``MEDIA_API_KEY``. Хардкод-дефолтов
в коде нет: их отсутствие при ИСПОЛЬЗОВАНИИ → понятная ``MediaConfigError`` (не на
импорте — сервис стартует без MEDIA_*, клиент ленивый). API-ключ и сырой
storage/Telegram-URL фото в логи НЕ пишем (§11).
"""
from __future__ import annotations

import logging
import os
from typing import Any, BinaryIO

import httpx

logger = logging.getLogger(__name__)

# Имена env конфигурации интеграции. Дефолтов в коде нет (как остальные секреты §11).
_BASE_URL_ENV = "MEDIA_SERVICE_URL"
_API_KEY_ENV = "MEDIA_API_KEY"

# Допустимые виды кадра (контракт медиа-сервиса upload-access).
KINDS = ("plate", "overview")

# Таймаут обращения к медиа-сервису, c. Загрузка в Telegram медленная (секунды),
# но это ВНЕ пути решения (§10.2) — латентность здесь не критична, таймаут щедрый.
DEFAULT_TIMEOUT_SECONDS = float(os.getenv("MEDIA_SERVICE_TIMEOUT_SECONDS", "30"))


class MediaConfigError(RuntimeError):
    """``MEDIA_SERVICE_URL``/``MEDIA_API_KEY`` не сконфигурированы (понятная ошибка)."""


class AccessMediaClient:
    """Async httpx-клиент медиа-сервиса для access_control (ленивая конфигурация).

    Значения ``base_url``/``api_key`` берутся из окружения ПРИ ИСПОЛЬЗОВАНИИ, не на
    конструировании — поэтому сервис может стартовать без ``MEDIA_*`` (роуты домена
    остаются живыми, ошибка возникнет только при фактической загрузке/отдаче фото).
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._timeout = timeout

    # --------------------------- конфигурация (ленивая) ---------------------------

    def _resolved_base_url(self) -> str:
        url = self._base_url if self._base_url is not None else os.getenv(_BASE_URL_ENV)
        if not url:
            raise MediaConfigError(
                f"{_BASE_URL_ENV} не задан: интеграция с медиа-сервисом не "
                "сконфигурирована (загрузка/отдача фото проезда недоступна)."
            )
        return url.rstrip("/")

    def _resolved_api_key(self) -> str:
        key = self._api_key if self._api_key is not None else os.getenv(_API_KEY_ENV)
        if not key:
            raise MediaConfigError(
                f"{_API_KEY_ENV} не задан: интеграция с медиа-сервисом не "
                "сконфигурирована (загрузка/отдача фото проезда недоступна)."
            )
        return key

    def _client(self) -> httpx.AsyncClient:
        """Собрать httpx-клиент с base_url ``/api/v1`` и заголовком X-API-Key.

        Ключ уходит только в заголовок и НЕ логируется (§11).
        """
        return httpx.AsyncClient(
            base_url=f"{self._resolved_base_url()}/api/v1",
            headers={"X-API-Key": self._resolved_api_key()},
            timeout=self._timeout,
        )

    # ------------------------------ операции ------------------------------

    async def upload_access_photo(
        self,
        kind: str,
        ref: str,
        file_data: bytes | BinaryIO,
        filename: str,
        content_type: str = "image/jpeg",
        uploaded_by: int | None = None,
    ) -> dict[str, Any]:
        """Загрузить кадр проезда в отдельный канал медиа-сервиса (§10.2, вне пути решения).

        ``kind`` — plate|overview, ``ref`` — домен-нейтральный идентификатор события
        (``f"{controller}|{event_id}"``). Возвращает
        ``{media_id, telegram_file_id, file_url}``. Сетевые ошибки/неуспешный статус
        пробрасываются (``httpx.HTTPError``); PD/ключ в лог не пишем (§11).
        """
        if kind not in KINDS:
            raise ValueError(f"неизвестный kind фото: {kind!r} (допустимы {KINDS})")
        content = file_data.read() if hasattr(file_data, "read") else file_data
        files = [("file", (filename, content, content_type))]
        data: dict[str, str] = {"kind": kind, "ref": ref}
        if uploaded_by is not None:
            data["uploaded_by"] = str(uploaded_by)
        async with self._client() as client:
            resp = await client.post("/media/upload-access", files=files, data=data)
            resp.raise_for_status()
            result = resp.json()
        media_file = result["media_file"]
        return {
            "media_id": media_file["id"],
            "telegram_file_id": media_file.get("telegram_file_id"),
            "file_url": result.get("file_url"),
        }

    async def fetch_file(self, media_id: int | str) -> tuple[bytes, str]:
        """Скачать байты файла из медиа-сервиса по ``media_id`` (стрим для ``/photos``).

        Возвращает ``(content, content_type)``. Сырой URL/ключ не логируем (§11).
        """
        async with self._client() as client:
            resp = await client.get(f"/media/{int(media_id)}/file")
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "application/octet-stream")
            return resp.content, content_type


# Синглтон-клиент. Ленивый: конструируется без MEDIA_* (ошибка только при использовании).
_default_client: AccessMediaClient | None = None


def get_access_media_client() -> AccessMediaClient:
    """FastAPI-зависимость: общий ленивый ``AccessMediaClient``.

    Не читает env на старте — конфигурация резолвится при первой загрузке/отдаче
    фото. Тесты подменяют через ``app.dependency_overrides``.
    """
    global _default_client
    if _default_client is None:
        _default_client = AccessMediaClient()
    return _default_client


def reset_access_media_client(client: AccessMediaClient | None = None) -> None:
    """Сбросить/подменить синглтон медиа-клиента (для тестов изоляции)."""
    global _default_client
    _default_client = client
