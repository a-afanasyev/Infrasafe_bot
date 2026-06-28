"""Публикация резидентских уведомлений (manager→житель) из access-сервиса (§16.2, §11).

Проверяет PUBLISH-сторону канала ``access:resident_notify``: рассмотрение заявки
менеджером (``management.review_request``) ПОСЛЕ commit публикует адресованное
автору заявки уведомление ``vehicle_request_resolved`` через брокер (тот же
механизм, что ``event_broadcaster``: in-process для тестов, Redis на проде).

Инварианты:
* approve → ``status="approved"``, reject → ``status="rejected"``;
* получатель — ``resident_access_requests.created_by_user_id`` (автор заявки);
* best-effort: сбой брокера НЕ ломает уже зафиксированное рассмотрение (§ best-effort);
* PD-safe (§11): в payload канала нет полного номера авто (только id/статус).

PostgreSQL-only (как и остальные write-тесты домена) + in-process/capture-брокер.
Подписчик-бот — отдельная фаза (здесь не тестируется).
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from access_control.services import management, resident_notify
from access_control.tests.conftest import PilotFixture, seed_user


class _CaptureBroker:
    """Брокер, записывающий опубликованные сообщения (для проверки publish)."""

    def __init__(self) -> None:
        self.published: list = []

    def publish(self, message) -> None:
        self.published.append(message)

    def subscribe(self):  # pragma: no cover - подписчик не тестируется
        raise NotImplementedError


class _BrokenBroker:
    """Брокер, чей ``publish`` всегда падает — проверка best-effort."""

    def publish(self, message) -> None:
        raise RuntimeError("broker down")

    def subscribe(self):  # pragma: no cover
        raise NotImplementedError


@pytest.fixture
def capture_broker():
    """Подменить резидентский брокер capture-брокером на время теста."""
    broker = _CaptureBroker()
    resident_notify.set_resident_broker(broker)
    yield broker
    resident_notify.reset_resident_broker()


def _seed_request(db, pilot: PilotFixture, *, creator_id: int,
                  plate: str = "01A123BC") -> int:
    rid = db.execute(
        text(
            "INSERT INTO resident_access_requests "
            "(apartment_id, created_by_user_id, plate_number_original, "
            " plate_number_normalized, relation_type, status) "
            "VALUES (:a, :c, :po, :pn, 'owner', 'pending') RETURNING id"
        ),
        {"a": pilot.apartment_id, "c": creator_id, "po": plate, "pn": plate},
    ).scalar()
    db.commit()
    return rid


def test_approve_publishes_resident_notification(
    pg_db, pilot: PilotFixture, capture_broker: _CaptureBroker
) -> None:
    """approve → опубликовано vehicle_request_resolved автору заявки, status=approved."""
    creator = seed_user(pg_db, roles="applicant")
    manager = seed_user(pg_db, roles="manager")
    rid = _seed_request(pg_db, pilot, creator_id=creator)

    management.review_request(
        pg_db, request_id=rid, action="approve", actor_user_id=manager,
        zone_id=pilot.zone_id,
    )

    assert len(capture_broker.published) == 1
    msg = capture_broker.published[0]
    payload = msg.to_payload()
    assert payload["kind"] == "vehicle_request_resolved"
    assert payload["recipient_user_id"] == creator
    assert payload["status"] == "approved"
    assert payload["request_id"] == rid


def test_reject_publishes_status_rejected(
    pg_db, pilot: PilotFixture, capture_broker: _CaptureBroker
) -> None:
    """reject → опубликовано уведомление автору со status=rejected."""
    creator = seed_user(pg_db, roles="applicant")
    manager = seed_user(pg_db, roles="manager")
    rid = _seed_request(pg_db, pilot, creator_id=creator)

    management.review_request(
        pg_db, request_id=rid, action="reject", actor_user_id=manager,
        comment="нет места",
    )

    assert len(capture_broker.published) == 1
    payload = capture_broker.published[0].to_payload()
    assert payload["kind"] == "vehicle_request_resolved"
    assert payload["recipient_user_id"] == creator
    assert payload["status"] == "rejected"
    assert payload["request_id"] == rid


def test_broker_failure_does_not_break_review(
    pg_db, pilot: PilotFixture
) -> None:
    """Сбой брокера НЕ ломает рассмотрение: заявка одобрена, исключение проглочено."""
    creator = seed_user(pg_db, roles="applicant")
    manager = seed_user(pg_db, roles="manager")
    rid = _seed_request(pg_db, pilot, creator_id=creator)

    resident_notify.set_resident_broker(_BrokenBroker())
    try:
        outcome = management.review_request(
            pg_db, request_id=rid, action="approve", actor_user_id=manager,
            zone_id=pilot.zone_id,
        )
    finally:
        resident_notify.reset_resident_broker()

    # Операция успешна несмотря на падение publish.
    assert outcome.status == "approved"
    status = pg_db.execute(
        text("SELECT status FROM resident_access_requests WHERE id = :r"),
        {"r": rid},
    ).scalar()
    assert status == "approved"


def test_payload_has_no_full_plate(
    pg_db, pilot: PilotFixture, capture_broker: _CaptureBroker
) -> None:
    """§11: в payload канала нет полного номера авто (только id/статус)."""
    creator = seed_user(pg_db, roles="applicant")
    manager = seed_user(pg_db, roles="manager")
    plate = "01A777ZZ"
    rid = _seed_request(pg_db, pilot, creator_id=creator, plate=plate)

    management.review_request(
        pg_db, request_id=rid, action="approve", actor_user_id=manager,
        zone_id=pilot.zone_id,
    )

    flat = str(capture_broker.published[0].to_payload())
    assert plate not in flat
