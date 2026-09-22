"""Simple per-user message throttling middleware.

KNOWN CONSTRAINT (SEC-09): throttling state (``_last_message``, ``_albums``)
lives in process memory, so the per-user rate limit holds only with a SINGLE bot
worker. Running multiple bot workers would give each its own counter and
multiply the effective limit. The bot is deployed single-worker on purpose — see
docs/development/known-constraints.md before scaling out.
"""
import time
from dataclasses import dataclass, replace
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

_EVICTION_THRESHOLD = 10_000

# A9-P1-1: альбом (media_group_id) Telegram присылает N апдейтами за
# миллисекунды — троттлинг «по сообщению» съедал все части, кроме первой.
# Троттлим «по альбому»: старт нового альбома подчиняется rate_limit и открывает
# окно; части ТОГО ЖЕ альбома проходят без троттлинга, но не больше лимита
# Telegram на альбом и только в коротком окне. media_group_id задаёт клиент
# (юзербот шлёт sendMultiMedia в цикле), поэтому полный пропуск снял бы антифлуд.
_ALBUM_MAX_ITEMS = 10
_ALBUM_WINDOW_SECONDS = 5.0
# Старт НОВОГО альбома реже обычного rate_limit: иначе худший случай —
# 10 частей каждые rate_limit (20 msg/s при 0,5 с). Второй альбом быстрее
# чем через 2 с человек не шлёт.
_ALBUM_MIN_START_INTERVAL = 2.0


@dataclass(frozen=True)
class _AlbumWindow:
    group_id: str
    started_at: float
    count: int


class ThrottlingMiddleware(BaseMiddleware):
    """Drop messages from users who exceed rate_limit (seconds between messages).

    An album (``media_group_id``) counts as one message: see A9-P1-1 above.
    """

    def __init__(self, rate_limit: float = 0.5):
        self.rate_limit = rate_limit
        self._album_start_interval = max(rate_limit, _ALBUM_MIN_START_INTERVAL)
        self._last_message: Dict[int, float] = {}
        self._albums: Dict[int, _AlbumWindow] = {}

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        user_id = event.from_user.id if event.from_user else 0
        now = time.monotonic()
        group_id = event.media_group_id

        album = self._albums.get(user_id)
        if group_id and album is not None and album.group_id == group_id:
            if (now - album.started_at > _ALBUM_WINDOW_SECONDS
                    or album.count >= _ALBUM_MAX_ITEMS):
                return None
            self._albums[user_id] = replace(album, count=album.count + 1)
            return await handler(event, data)

        # Обычное сообщение или старт нового альбома — общий rate_limit.
        last = self._last_message.get(user_id, 0.0)
        if now - last < self.rate_limit:
            return None
        if (group_id and album is not None
                and now - album.started_at < self._album_start_interval):
            return None

        self._last_message[user_id] = now
        if group_id:
            self._albums[user_id] = _AlbumWindow(group_id, now, 1)

        # Evict stale entries to prevent unbounded memory growth
        if len(self._last_message) > _EVICTION_THRESHOLD:
            self._evict(now)

        return await handler(event, data)

    def _evict(self, now: float) -> None:
        cutoff = now - self.rate_limit
        self._last_message = {
            k: v for k, v in self._last_message.items() if v >= cutoff
        }
        # Истёкшее окно альбома уже ничего не пропускает и не сдерживает
        # старт следующего альбома.
        album_cutoff = now - max(_ALBUM_WINDOW_SECONDS, self._album_start_interval)
        self._albums = {
            k: v for k, v in self._albums.items() if v.started_at >= album_cutoff
        }
