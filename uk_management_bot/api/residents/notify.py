"""Уведомления жителю о решениях менеджера (Т11).

Отправка — через общий модуль API `api/telegram_send.py` (A9-P2-9): один
переиспользуемый клиент, общая таймаут-политика, 403 «бот заблокирован»
проставляет `users.bot_blocked_at`.

**Никогда не поднимает исключение.** Решение менеджера уже зафиксировано в БД;
недоступный Telegram не имеет права превратить успешную операцию в 500.
Все сбои — в лог.

Текст берётся из локалей бота по языку ЖИТЕЛЯ, не менеджера. `parse_mode` не
задаётся сознательно: разнобой бота (где-то HTML, где-то Markdown) сюда не
наследуем, а обычный текст не может сломаться на скобке в адресе.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable
from typing import Protocol

from uk_management_bot.api import telegram_send
from uk_management_bot.utils.http_errors import describe_http_error
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

#: Темп рассылок (A9-P2-8): лимит Telegram — порядка 30 сообщений/с на бота;
#: 25/с оставляет запас боту, который шлёт параллельно. Темп ОБЩИЙ на процесс
#: (см. :class:`_BulkPacer`): API идёт с ``--workers 2``, так что потолок
#: сверху — 2 × 25/с; это осознанно приемлемо (глобальный лимит ~30/с
#: срабатывает на всплеск, а рассылки по лифтам редки).
BULK_SEND_INTERVAL = 1 / 25
#: Сколько раз повторить сообщение после 429 и потолок ожидания retry_after (с).
BULK_MAX_429_RETRIES = 2
BULK_MAX_RETRY_AFTER = 60.0
#: Потолок общего времени одной рассылки (с): дальше — WARNING и остаток не шлём.
BULK_MAX_DURATION = 600.0

#: Тест-хуки: подмена ожидания и часов без патча глобального asyncio/time.
_sleep = asyncio.sleep
_monotonic = time.monotonic


class _BulkPacer:
    """Процессный ограничитель рассылок: все фоновые рассылки идут в ОДНОМ темпе.

    Без него каждая фоновая задача держала бы свои 25/с, и N параллельных
    смен статуса лифта дали бы N × 25/с к Telegram (ревью A9-P2-8). Слот —
    «не раньше ``_next``»; очередь — FIFO ``asyncio.Lock``. 429 сдвигает
    ``_next`` на ``retry_after`` для ВСЕХ рассылок: flood-лимит — на бота.
    Замок привязан к event loop'у (в тестах loop свой на тест).
    """

    def __init__(self) -> None:
        self._lock: asyncio.Lock | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._next = 0.0

    def _get_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._lock is None or self._loop is not loop:
            self._lock, self._loop, self._next = asyncio.Lock(), loop, 0.0
        return self._lock

    async def wait_turn(self) -> None:
        async with self._get_lock():
            now = _monotonic()
            if self._next > now:
                await _sleep(self._next - now)
            self._next = max(_monotonic(), self._next) + BULK_SEND_INTERVAL

    def defer(self, seconds: float) -> None:
        self._next = max(self._next, _monotonic() + seconds)


_PACER = _BulkPacer()


class PlainMessage(Protocol):
    """Адресованное сообщение: ``telegram_id`` + готовый текст (``elevator_service.Message``)."""

    telegram_id: int
    text: str


async def _send(
    chat_id: int, text: str, reply_markup: dict | None = None, *, parse_mode: str | None = None,
) -> bool:
    """Один ``sendMessage``; ``True`` — Telegram принял, иначе ``False`` (в лог).

    Не-2xx (403 «бот заблокирован», 400 «чат не найден») — штатный прод-кейс,
    не исключение: вызывающий по возвращаемому значению считает доставленных.
    Лог отказа и штамп ``bot_blocked_at`` — в ``telegram_send.send_message``.
    """
    result = await telegram_send.send_message(
        chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup,
    )
    return result.ok


async def _safe_send(resident: User, text: str, reply_markup: dict | None = None) -> None:
    try:
        await _send(resident.telegram_id, text, reply_markup)
    except Exception as e:  # noqa: BLE001 — best-effort, наружу не поднимаем
        logger.error("Не удалось уведомить жителя %s: %s", resident.id, describe_http_error(e))


async def _deliver_bulk_one(chat_id: int, text: str, parse_mode: str | None) -> bool:
    """Одно сообщение рассылки в общем темпе; 429 → сдвиг темпа на ``retry_after``."""
    for attempt in range(BULK_MAX_429_RETRIES + 1):
        await _PACER.wait_turn()
        result = await telegram_send.send_message(chat_id, text, parse_mode=parse_mode)
        if result.http_status != 429:
            return result.ok
        if attempt < BULK_MAX_429_RETRIES:
            _PACER.defer(min(result.retry_after or 1.0, BULK_MAX_RETRY_AFTER))
    logger.warning("Рассылка: сообщение %s не доставлено — Telegram 429 после %s повторов",
                   chat_id, BULK_MAX_429_RETRIES)
    return False


async def send_plain_messages(
    messages: Iterable[PlainMessage], *, parse_mode: str | None = "HTML",
) -> int:
    """Разослать готовые сообщения (например, жителям подъезда о лифте); вернуть число ДОСТАВЛЕННЫХ.

    Считаются только принятые Telegram (HTTP 200): отказ 400/403 (бот
    заблокирован жителем) — не доставка. Best-effort: вызывать строго ПОСЛЕ
    commit и вне запроса (A9-P2-8: из ``BackgroundTasks`` — рассылка на подъезд
    длится секунды); сбой одного адресата не останавливает остальных и не
    поднимается наружу (``telegram_send`` не поднимает сетевые исключения и не
    логирует URL с токеном). Темп — общий на процесс (:class:`_BulkPacer`),
    429 — повтор через ``retry_after``; дольше ``BULK_MAX_DURATION`` рассылка
    не идёт (WARNING, остаток не отправляется).
    """
    messages = list(messages)
    started = _monotonic()
    delivered = 0
    for index, message in enumerate(messages):
        if _monotonic() - started > BULK_MAX_DURATION:
            logger.warning(
                "Рассылка прервана по потолку %.0f с: отправлено %s из %s, доставлено %s",
                BULK_MAX_DURATION, index, len(messages), delivered)
            break
        if await _deliver_bulk_one(message.telegram_id, message.text, parse_mode):
            delivered += 1
    return delivered


def _lang(resident: User) -> str:
    return resident.language or "ru"


async def notify_account_approved(resident: User) -> None:
    """Одобрение аккаунта.

    Тот же ключ и та же inline-кнопка, что у бота: текст говорит «нажмите
    кнопку ниже», и без кнопки он был бы враньём.
    """
    lang = _lang(resident)
    await _safe_send(
        resident,
        get_text("user_mgmt.handlers.application_approved_restart", language=lang),
        reply_markup={"inline_keyboard": [[{
            "text": get_text("user_mgmt.handlers.restart_bot_btn", language=lang),
            "callback_data": "restart_bot",
        }]]},
    )


async def notify_apartment_attached(resident: User, address: str) -> None:
    lang = _lang(resident)
    await _safe_send(resident, get_text(
        "web_notifications.apartment_attached", language=lang, address=address,
    ))


async def notify_binding_approved(resident: User, address: str) -> None:
    lang = _lang(resident)
    await _safe_send(resident, get_text(
        "web_notifications.binding_approved", language=lang, address=address,
    ))


async def notify_binding_rejected(resident: User, address: str, comment: str) -> None:
    lang = _lang(resident)
    await _safe_send(resident, get_text(
        "web_notifications.binding_rejected", language=lang,
        address=address, comment=comment,
    ))


async def notify_binding_removed(resident: User, address: str) -> None:
    lang = _lang(resident)
    await _safe_send(resident, get_text(
        "web_notifications.binding_removed", language=lang, address=address,
    ))


async def notify_documents_requested(
    resident: User, *, document_types: list[str], comment: str,
) -> None:
    lang = _lang(resident)
    from uk_management_bot.services.residents.verification_core import (
        format_requested_documents,
    )
    await _safe_send(resident, get_text(
        "web_notifications.documents_requested", language=lang,
        documents=format_requested_documents(document_types, lang), comment=comment,
    ))


async def notify_verification_approved(resident: User) -> None:
    await _safe_send(resident, get_text(
        "web_notifications.verification_approved", language=_lang(resident),
    ))


async def notify_verification_rejected(resident: User, notes: str) -> None:
    await _safe_send(resident, get_text(
        "web_notifications.verification_rejected", language=_lang(resident), notes=notes,
    ))
