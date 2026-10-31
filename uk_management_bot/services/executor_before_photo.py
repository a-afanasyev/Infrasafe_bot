"""Фото «до работ» исполнителя: одно фото за вызов → media-service, статус не меняется.

Решение владельца (2026-10-31): необязательно (не блокирует «Готово»), снимать
можно в любом незакрытом статусе назначенному исполнителю, до 4 фото на заявку,
видит и житель. Единственный путь загрузки категории ``before_photo`` — общий
`/api/v2/media/upload` её не принимает (там нет лимита и идемпотентности).
Зовут: API (`POST /api/v2/requests/{n}/before-photo`, оба режима TWA) и бот.

Порядок:

1. ключ и фото проверяются локально (`validate_completion_photo`);
2. запись попытки (Redis, `OP_BEFORE`): уже ``done`` → прежний результат ДО
   проверки лимита — повтор 4-го фото после потерянного ответа = тот же 201;
3. лок на заявку (свой, «Готово» его не ждёт), повторное чтение записи;
4. права (канон `can_upload_completion_async`) и статус: закрытая → отказ;
5. лимит по списку media-service; загрузка; запись ``done``.

Redis недоступен → отказ ``idempotency_unavailable`` (fail-closed, см.
`completion_idempotency`): естественной идемпотентности здесь нет.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.integrations import get_media_client
from uk_management_bot.services import completion_idempotency as idem
from uk_management_bot.services.executor_completion import (
    CompletionRefused,
    parse_idempotency_key,
    upload_executor_photo,
    validate_completion_photo,
)
from uk_management_bot.services.request_access import can_upload_completion_async
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_APPROVED,
    REQUEST_STATUS_CANCELLED,
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_EXECUTED,
)
from uk_management_bot.utils.request_workflow import normalize_status

logger = logging.getLogger(__name__)

BEFORE_CATEGORY = "before_photo"
# = MAX_MEDIA_PER_SIDE отчётов о работах: больше в отчёт всё равно не попадёт.
BEFORE_PHOTO_LIMIT = 4
# Работа сдана или заявка снята — «до» уже не снимают. Шире TERMINAL_STATUSES
# workflow: «Выполнена» туда не входит (её можно вернуть), но работа уже сделана.
CLOSED_STATUSES = frozenset({
    REQUEST_STATUS_EXECUTED, REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_APPROVED, REQUEST_STATUS_CANCELLED,
})


@dataclass(frozen=True)
class BeforePhotoResult:
    media_id: int
    count: int


async def _count(request_number: str) -> int:
    client = get_media_client()
    if client is None:
        raise CompletionRefused("media_unavailable", 503)
    try:
        items = await client.get_request_media(request_number, category=BEFORE_CATEGORY) or []
    except Exception as exc:  # noqa: BLE001 — сеть/таймаут = сервис недоступен
        logger.warning("before %s: список фото не получен: %s", request_number, type(exc).__name__)
        raise CompletionRefused("media_unavailable", 503) from None
    return sum(1 for i in items if isinstance(i, dict) and i.get("status", "active") == "active")


async def _check_access(session_factory, request_number: str, executor_id: int) -> None:
    async with session_factory() as db:
        request = await db.get(Request, request_number)
        if request is None:
            raise CompletionRefused("not_found", 404)
        user = await db.get(User, executor_id)
        if user is None or not await can_upload_completion_async(db, user, request):
            raise CompletionRefused("not_assigned", 403)
        if normalize_status(request) in CLOSED_STATUSES:
            raise CompletionRefused("invalid_status", 409)


async def _load(executor_id: int, request_number: str, key: str):
    try:
        return await idem.load(executor_id, request_number, key, op=idem.OP_BEFORE, strict=True)
    except idem.IdempotencyUnavailable:
        raise CompletionRefused("idempotency_unavailable", 503) from None


async def upload_before_photo(session_factory, request_number: str, executor_id: int,
                              photo_bytes: bytes, idempotency_key: str) -> BeforePhotoResult:
    """Приложить фото «до» (см. докстринг модуля)."""
    key = parse_idempotency_key(idempotency_key)
    mime = validate_completion_photo(photo_bytes)

    record = await _load(executor_id, request_number, key)
    if record is not None and record.state == idem.STATE_DONE and record.media_id:
        return BeforePhotoResult(record.media_id, await _count(request_number))

    lock = await idem.acquire_lock(request_number, op=idem.OP_BEFORE)
    if lock.degraded:
        raise CompletionRefused("idempotency_unavailable", 503)
    if not lock.acquired:
        raise CompletionRefused("in_progress", 409)
    try:
        record = await _load(executor_id, request_number, key)
        if record is not None and record.state == idem.STATE_DONE and record.media_id:
            return BeforePhotoResult(record.media_id, await _count(request_number))

        await _check_access(session_factory, request_number, executor_id)
        count = await _count(request_number)
        if count >= BEFORE_PHOTO_LIMIT:
            raise CompletionRefused("before_limit", 409)

        media_id = await upload_executor_photo(
            request_number, executor_id, photo_bytes, mime,
            category=BEFORE_CATEGORY, name_suffix="before")
        await idem.save(executor_id, request_number, key, idem.STATE_DONE, media_id, op=idem.OP_BEFORE)
        return BeforePhotoResult(media_id, count + 1)
    finally:
        await idem.release_lock(lock)
