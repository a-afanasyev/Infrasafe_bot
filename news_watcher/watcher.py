"""Чистая логика юзербота: источники, offsets, доставка в API с повтором.

Без Telethon — тестируется в основном наборе (tests/services). ``main.py``
подключает это к Telegram.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import httpx

logger = logging.getLogger("news_watcher")

INBOX_PATH = "/api/v2/news-watch/inbox"
SOURCES_PATH = "/api/v2/news-watch/sources"
POST_ATTEMPTS = 4
BACKOFF_BASE = 2.0
TEXT_LIMIT = 20000


@dataclass(frozen=True)
class Settings:
    api_url: str
    service_token: str
    api_id: int
    api_hash: str
    session: str
    offsets_path: str = "/data/offsets.json"
    refresh_seconds: int = 300

    @classmethod
    def from_env(cls, env: Optional[dict] = None) -> "Settings":
        env = os.environ if env is None else env
        missing = [k for k in ("NEWS_WATCH_API_URL", "NEWS_WATCH_SERVICE_TOKEN", "TG_API_ID",
                               "TG_API_HASH", "NEWS_WATCH_TG_SESSION") if not env.get(k)]
        if missing:
            raise RuntimeError(f"news_watcher: не заданы {missing} (Doppler)")
        return cls(
            api_url=env["NEWS_WATCH_API_URL"].rstrip("/"),
            service_token=env["NEWS_WATCH_SERVICE_TOKEN"],
            api_id=int(env["TG_API_ID"]),
            api_hash=env["TG_API_HASH"],
            session=env["NEWS_WATCH_TG_SESSION"],
            offsets_path=env.get("NEWS_WATCH_OFFSETS_PATH", "/data/offsets.json"),
            refresh_seconds=int(env.get("NEWS_WATCH_REFRESH_SECONDS", "300")),
        )


def diff_sources(current: set[str], wanted: set[str]) -> tuple[set[str], set[str]]:
    """(подписаться, отписаться) — оба множества в виде ``@name``."""
    return wanted - current, current - wanted


def inbound_payload(chat_id: int, message_id: int, chat_title: Optional[str], text: str,
                    posted_at: Optional[datetime]) -> dict:
    return {
        "source_chat_id": int(chat_id),
        "source_message_id": int(message_id),
        "chat_title": (chat_title or "")[:255] or None,
        "text": text[:TEXT_LIMIT],
        "posted_at": posted_at.isoformat() if posted_at else None,
    }


class Offsets:
    """Последний обработанный message_id на источник — JSON в томе контейнера."""

    def __init__(self, path: str):
        self._path = Path(path)
        self._data: dict[str, int] = {}
        try:
            self._data = {str(k): int(v) for k, v in json.loads(self._path.read_text()).items()}
        except (OSError, ValueError, AttributeError):
            self._data = {}

    def is_new(self, chat_id: int, message_id: int) -> bool:
        return int(message_id) > self._data.get(str(chat_id), 0)

    def mark(self, chat_id: int, message_id: int) -> None:
        key = str(chat_id)
        if int(message_id) <= self._data.get(key, 0):
            return
        self._data = {**self._data, key: int(message_id)}
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data))
            tmp.replace(self._path)
        except OSError as e:
            logger.warning("offsets not saved: %s", type(e).__name__)


class ApiClient:
    """HTTP к API UK с service-token. ``sleep`` — seam для тестов."""

    def __init__(self, settings: Settings, client: Optional[httpx.AsyncClient] = None,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self._base = settings.api_url
        self._headers = {"X-Service-Token": settings.service_token}
        self._client = client or httpx.AsyncClient(timeout=15.0)
        self._sleep = sleep

    async def fetch_sources(self) -> list[str]:
        resp = await self._client.get(self._base + SOURCES_PATH, headers=self._headers)
        resp.raise_for_status()
        return [s["chat"] for s in resp.json().get("sources", []) if isinstance(s, dict) and s.get("chat")]

    async def post_inbox(self, payload: dict) -> bool:
        """True — принято (или дубль); False — отдано после всех попыток.
        4xx (кроме 429) не повторяем: тот же запрос упадёт так же."""
        for attempt in range(1, POST_ATTEMPTS + 1):
            try:
                resp = await self._client.post(self._base + INBOX_PATH, json=payload, headers=self._headers)
            except httpx.HTTPError as e:
                logger.warning("inbox post attempt %s: %s", attempt, type(e).__name__)
                resp = None
            if resp is not None:
                if 200 <= resp.status_code < 300:
                    return True
                if resp.status_code == 409 or (400 <= resp.status_code < 500 and resp.status_code != 429):
                    logger.warning("inbox rejected %s: %s", resp.status_code, resp.text[:200])
                    return False
            if attempt < POST_ATTEMPTS:
                await self._sleep(BACKOFF_BASE ** attempt)
        return False

    async def aclose(self) -> None:
        await self._client.aclose()


async def handle_message(api: ApiClient, offsets: Offsets, *, chat_id: int, message_id: int,
                         chat_title: Optional[str], text: str, posted_at: Optional[datetime]) -> bool:
    """Одно сообщение источника → inbox. Offset сдвигается только после приёма."""
    if not text or not text.strip() or not offsets.is_new(chat_id, message_id):
        return False
    accepted = await api.post_inbox(inbound_payload(chat_id, message_id, chat_title, text, posted_at))
    if accepted:
        offsets.mark(chat_id, message_id)
    return accepted


def normalize_handle(value: Any) -> Optional[str]:
    """username Telegram-сущности → ``@name`` в нижнем регистре."""
    if not value:
        return None
    return "@" + str(value).lstrip("@").lower()
