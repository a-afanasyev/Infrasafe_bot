"""Публикация резидентских уведомлений (manager→житель) из access-сервиса (§16.2, §11).

PUBLISH-сторона канала ``access:resident_notify``: когда менеджер рассматривает
заявку жителя (или, в будущем, происходит иное адресное событие), access-сервис
публикует в брокер PD-safe сообщение, АДРЕСОВАННОЕ конкретному жителю. Подписчик
(Telegram-бот) — отдельная фаза: он сам решает локализацию и доставку.

Механизм/конфиг переиспользует ``event_broadcaster`` (§9.6):

* ``InProcessBroker`` (по умолчанию, пилот в одном процессе);
* ``RedisBroker`` (флаг ``ACCESS_EVENT_BROKER=redis``) — Redis pub/sub на
  ОТДЕЛЬНОМ канале ``access:resident_notify`` (не смешивается с ``access:events``
  WS-панели охраны).

PD-safe (§11): сообщение адресовано самому жителю, поэтому его id/статус допустимы,
но в канал НЕ кладётся полный номер авто — только маскированный хвост (``plate_masked``)
и идентификаторы. Полный номер/код/фото в канал не попадают.

Best-effort: ошибка публикации НЕ должна ломать основную операцию (рассмотрение
заявки уже зафиксировано в БД) — исключение проглатывается с логом без ПД.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import logging
import os
import threading

from access_control.services.event_broadcaster import (
    EventBroker,
    InProcessBroker,
    RedisBroker,
)

logger = logging.getLogger(__name__)

# Канал Redis pub/sub для адресных резидентских уведомлений (отдельный от WS-панели).
ACCESS_RESIDENT_NOTIFY_CHANNEL = "access:resident_notify"

# Виды резидентских уведомлений (контракт для бота-подписчика).
KIND_VEHICLE_REQUEST_RESOLVED = "vehicle_request_resolved"
# Спорный въезд (manual_review) по номеру авто жителя — просьба подтвердить (§9.4).
KIND_DISPUTED_ENTRY = "disputed_entry"


@dataclasses.dataclass(frozen=True)
class ResidentNotification:
    """Иммутабельное PD-safe уведомление, адресованное конкретному жителю (§16.2, §11).

    Намеренно БЕЗ полного номера/фото: только вид, получатель, идентификаторы,
    статус, опц. маскированный номер/зона/комментарий и время.
    """

    kind: str
    recipient_user_id: int
    request_id: int | None = None
    pass_id: int | None = None
    decision_id: int | None = None
    camera_event_id: int | None = None
    status: str | None = None
    plate_masked: str | None = None
    zone: int | None = None
    comment: str | None = None
    created_at: str | None = None

    def to_payload(self) -> dict:
        """Сериализуемый dict для публикации в канал. ``kind`` — тип уведомления."""
        return {
            "kind": self.kind,
            "recipient_user_id": self.recipient_user_id,
            "request_id": self.request_id,
            "pass_id": self.pass_id,
            "decision_id": self.decision_id,
            "camera_event_id": self.camera_event_id,
            "status": self.status,
            "plate_masked": self.plate_masked,
            "zone": self.zone,
            "comment": self.comment,
            "created_at": self.created_at,
        }

    @classmethod
    def from_payload(cls, payload: dict) -> "ResidentNotification":
        return cls(
            kind=payload.get("kind", ""),
            recipient_user_id=payload.get("recipient_user_id"),
            request_id=payload.get("request_id"),
            pass_id=payload.get("pass_id"),
            decision_id=payload.get("decision_id"),
            camera_event_id=payload.get("camera_event_id"),
            status=payload.get("status"),
            plate_masked=payload.get("plate_masked"),
            zone=payload.get("zone"),
            comment=payload.get("comment"),
            created_at=payload.get("created_at"),
        )


# ───────────────────────── singleton/фабрика брокера ──────────────────────────

_broker: EventBroker | None = None
_broker_lock = threading.Lock()


def get_resident_broker() -> EventBroker:
    """Процессный singleton брокера резидентских уведомлений (создаётся по конфигу)."""
    global _broker
    if _broker is None:
        with _broker_lock:
            if _broker is None:
                _broker = _build_broker()
    return _broker


def _build_broker() -> EventBroker:
    kind = os.getenv("ACCESS_EVENT_BROKER", "memory").strip().lower()
    if kind == "redis":
        from uk_management_bot.config.settings import settings

        url = settings.REDIS_PUBSUB_URL_RESOLVED
        logger.info("resident notify broker: redis (%s)", url)
        return RedisBroker(url, channel=ACCESS_RESIDENT_NOTIFY_CHANNEL)
    logger.info("resident notify broker: in-process (single-worker pilot)")
    return InProcessBroker()


def set_resident_broker(broker: EventBroker | None) -> None:
    """Подменить singleton брокера (для тестов/DI)."""
    global _broker
    with _broker_lock:
        _broker = broker


def reset_resident_broker() -> None:
    """Сбросить singleton: чистый in-process брокер без подписчиков (тесты)."""
    set_resident_broker(InProcessBroker())


# ───────────────────────── публичная публикация ──────────────────────────────


def publish_resident_notification(
    kind: str,
    recipient_user_id: int,
    payload: dict | None = None,
) -> None:
    """Опубликовать адресное резидентское уведомление в канал (best-effort, §16.2, §11).

    ``payload`` — опц. dict с дополнительными PD-safe полями: ``request_id``,
    ``pass_id``, ``status``, ``plate_masked``, ``zone``, ``comment``, ``created_at``.
    Полный номер авто в payload класть НЕЛЬЗЯ (§11) — только маскированный хвост.

    Best-effort: любая ошибка (сборка сообщения, сбой брокера) проглатывается с
    логом без ПД — основная операция уже зафиксирована и не должна падать.
    """
    payload = payload or {}
    try:
        notification = ResidentNotification(
            kind=kind,
            recipient_user_id=recipient_user_id,
            request_id=payload.get("request_id"),
            pass_id=payload.get("pass_id"),
            decision_id=payload.get("decision_id"),
            camera_event_id=payload.get("camera_event_id"),
            status=payload.get("status"),
            plate_masked=payload.get("plate_masked"),
            zone=payload.get("zone"),
            comment=payload.get("comment"),
            created_at=payload.get("created_at")
            or dt.datetime.now(dt.timezone.utc).isoformat(),
        )
        get_resident_broker().publish(notification)
    except Exception:  # noqa: BLE001 — уведомление не критично для основной операции
        logger.exception(
            "resident notification publish failed (operation unaffected, kind=%s)",
            kind,
        )
