"""Подписчик резидентских уведомлений: access:resident_notify → Telegram (§16.2, §11).

SUBSCRIBE-сторона канала ``access:resident_notify``. Access-сервис (uk-access-api)
публикует PD-safe сообщение, адресованное конкретному жителю, когда менеджер
рассматривает заявку. Этот модуль — фоновая задача бота: слушает Redis pub/sub,
резолвит получателя (``users.id`` → ``telegram_id`` + язык) и шлёт ему
локализованное Telegram-сообщение.

Контракт сообщения переиспользуется из
``access_control.services.resident_notify`` (канал, kinds, ``ResidentNotification``).

Кросс-процессность: бот и access-api — РАЗНЫЕ контейнеры/процессы, поэтому
доставка работает ТОЛЬКО через Redis (``ACCESS_EVENT_BROKER=redis``). In-process
брокер пилота не пересекает границу процесса — подписчик в этом режиме не
запускается (best-effort, лог-warning, бот работает без уведомлений).

URL Redis берём из ``settings.REDIS_PUBSUB_URL_RESOLVED`` — ТОТ ЖЕ, что использует
publish-сторона (``resident_notify._build_broker`` → ``RedisBroker`` на
``REDIS_PUBSUB_URL_RESOLVED``). Использовать ``REDIS_URL`` (db 0) нельзя: publisher
публикует в db 1, и сообщения бы не дошли.

PD-safe (§11): в логи не попадает полный номер/код/ПД — только вид/статус и
числовой id получателя (сообщение адресовано ему же). Best-effort: неизвестный
адресат, блокировка бота, обрыв Redis — логируются и не роняют цикл.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

from access_control.services.resident_notify import (
    ACCESS_RESIDENT_NOTIFY_CHANNEL,
    KIND_VEHICLE_REQUEST_RESOLVED,
    ResidentNotification,
)
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import SessionLocal
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

# Бэкофф переподключения к Redis (сек): старт и потолок.
_RECONNECT_BACKOFF_START = 1.0
_RECONNECT_BACKOFF_MAX = 30.0
# Таймаут чтения сообщения (сек): позволяет периодически проверять stop_event.
_READ_TIMEOUT = 1.0


def parse_payload(raw: str | bytes) -> dict | None:
    """Безопасно распарсить сырое сообщение канала в dict.

    Невалидный JSON или не-объект (list/число) → ``None`` без исключения.
    """
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except Exception:  # noqa: BLE001
            return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def build_notification_text(
    notification: ResidentNotification, language: str
) -> str | None:
    """Собрать локализованный текст уведомления по виду+статусу.

    Возвращает ``None`` для неизвестного вида/статуса (нечего слать).
    Комментарий менеджера (если есть) дописывается отдельной строкой.
    """
    if notification.kind != KIND_VEHICLE_REQUEST_RESOLVED:
        return None

    status = (notification.status or "").strip().lower()
    if status == "approved":
        base = get_text(
            "access_control.notify.vehicle_request_resolved.approved",
            language=language,
        )
    elif status == "rejected":
        base = get_text(
            "access_control.notify.vehicle_request_resolved.rejected",
            language=language,
        )
    else:
        return None

    comment = (notification.comment or "").strip()
    if comment:
        base += get_text(
            "access_control.notify.comment", language=language, comment=comment
        )
    return base


def _resolve_recipient(db, recipient_user_id: int) -> User | None:
    """Найти получателя по ``users.id`` (НЕ telegram_id). ``None`` если нет."""
    return db.query(User).filter(User.id == recipient_user_id).first()


async def handle_payload(bot, db, payload: dict) -> None:
    """Обработать одно сообщение канала: резолв адресата + доставка (best-effort).

    Чистая, тестируемая единица: цикл-обёртка только подаёт сюда payload и db.
    Любой сбой логируется без ПД и не пробрасывается — цикл должен жить дальше.
    """
    try:
        notification = ResidentNotification.from_payload(payload)
    except Exception:  # noqa: BLE001 — кривой payload не должен ронять цикл
        logger.warning("resident notify: bad payload skipped")
        return

    recipient_id = notification.recipient_user_id
    if not recipient_id:
        logger.warning("resident notify: missing recipient_user_id, skipped")
        return

    user = _resolve_recipient(db, recipient_id)
    if user is None or not getattr(user, "telegram_id", None):
        logger.info(
            "resident notify: recipient id=%s not found / no telegram_id, skipped",
            recipient_id,
        )
        return

    language = getattr(user, "language", None) or "ru"
    text = build_notification_text(notification, language)
    if not text:
        logger.info(
            "resident notify: no text for kind=%s status=%s, skipped",
            notification.kind,
            notification.status,
        )
        return

    try:
        await bot.send_message(user.telegram_id, text)
        logger.info(
            "resident notify delivered: kind=%s status=%s recipient_id=%s",
            notification.kind,
            notification.status,
            recipient_id,
        )
    except Exception:  # noqa: BLE001 — блокировка бота/сетевой сбой не критичны
        logger.warning(
            "resident notify: delivery failed (recipient_id=%s, kind=%s) — skipped",
            recipient_id,
            notification.kind,
        )


async def run_resident_notify_subscriber(
    bot, *, stop_event: asyncio.Event | None = None
) -> None:
    """Фоновый цикл: подписка на канал + переподключение при обрыве Redis.

    Тонкая обёртка над ``handle_payload``: читает сообщения, парсит, для каждого
    открывает короткую сессию БД и делегирует доставку. Любой сетевой сбой →
    переподключение с экспоненциальным бэкоффом; ``stop_event`` корректно
    завершает цикл (для shutdown).
    """
    import redis.asyncio as aioredis

    url = settings.REDIS_PUBSUB_URL_RESOLVED
    backoff = _RECONNECT_BACKOFF_START

    while stop_event is None or not stop_event.is_set():
        client = None
        pubsub = None
        try:
            client = aioredis.from_url(url)
            pubsub = client.pubsub()
            await pubsub.subscribe(ACCESS_RESIDENT_NOTIFY_CHANNEL)
            logger.info(
                "resident notify subscriber listening on channel '%s'",
                ACCESS_RESIDENT_NOTIFY_CHANNEL,
            )
            backoff = _RECONNECT_BACKOFF_START

            while stop_event is None or not stop_event.is_set():
                raw = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=_READ_TIMEOUT
                )
                if raw is None or raw.get("type") != "message":
                    continue
                payload = parse_payload(raw["data"])
                if payload is None:
                    logger.warning("resident notify: unparseable message skipped")
                    continue
                db = SessionLocal()
                try:
                    await handle_payload(bot, db, payload)
                finally:
                    db.close()
        except asyncio.CancelledError:
            logger.info("resident notify subscriber cancelled")
            raise
        except Exception:  # noqa: BLE001 — обрыв Redis → переподключение
            logger.warning(
                "resident notify subscriber: redis error, reconnecting in %.0fs",
                backoff,
            )
            try:
                await asyncio.sleep(backoff)
            except asyncio.CancelledError:
                raise
            backoff = min(backoff * 2, _RECONNECT_BACKOFF_MAX)
        finally:
            if pubsub is not None:
                try:
                    await pubsub.aclose()
                except Exception:  # noqa: BLE001
                    pass
            if client is not None:
                try:
                    await client.aclose()
                except Exception:  # noqa: BLE001
                    pass


def start_resident_notify_subscriber(bot) -> asyncio.Task | None:
    """Запустить подписчик как фоновую задачу (best-effort).

    Запускается ТОЛЬКО при ``ACCESS_EVENT_BROKER=redis`` (cross-process доставка).
    Иначе/при отсутствии redis.asyncio — лог и ``None`` (бот работает без
    резидентских уведомлений). Возвращает ``asyncio.Task`` для отмены на shutdown.
    """
    broker_kind = os.getenv("ACCESS_EVENT_BROKER", "memory").strip().lower()
    if broker_kind != "redis":
        logger.info(
            "resident notify subscriber disabled (ACCESS_EVENT_BROKER=%s; "
            "redis required for cross-process delivery)",
            broker_kind,
        )
        return None

    try:
        import redis.asyncio  # noqa: F401
    except Exception:  # noqa: BLE001
        logger.warning(
            "resident notify subscriber disabled: redis.asyncio unavailable"
        )
        return None

    task = asyncio.create_task(run_resident_notify_subscriber(bot))
    logger.info("resident notify subscriber started")
    return task
