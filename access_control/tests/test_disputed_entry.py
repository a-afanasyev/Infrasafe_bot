"""Подтверждение спорного въезда жителем (§6.4, §9.4, §16.2). PostgreSQL-only.

СОВЕЩАТЕЛЬНЫЙ сигнал жителя (решение CTO): подтверждение/опровержение спорного
въезда фиксируется в ``access_entry_confirmations`` и показывается оператору, но
НЕ открывает шлагбаум и НЕ меняет решение — финальное решение (manual_open/deny/
expiry) остаётся за оператором (§4.2, §9.4, §9.5).

Покрывает:
* notify-hook ingestion: pending_review по номеру зарегистрированного авто →
  публикуется ``disputed_entry`` жителю(ям) квартиры (in-process capture-брокер);
  номер без резидента → уведомления нет; best-effort (сбой publish не ломает
  ingestion);
* POST /my/entries/{decision_id}/confirm: житель квартиры → запись confirm/deny;
  чужой житель → 403; повтор → upsert (последний ответ); НЕ открывает шлагбаум,
  решение остаётся pending_review; RBAC (applicant; без auth 401; manager 403);
* GET /events/{id} → массив resident_confirmations виден оператору.
"""
from __future__ import annotations

import types

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from access_control.app.main import create_app
from access_control.services import resident_notify
from access_control.services.ingestion import AnprIngestInput, ingest_anpr
from access_control.tests.conftest import (
    PilotFixture,
    _seed_apartment,
    seed_permanent_vehicle,
    seed_user,
    utcnow,
)
from uk_management_bot.api.dependencies import get_current_user

PLATE = "01A777BC"
PLATE_OTHER = "01B888CD"
LOW_CONFIDENCE = 0.50  # ниже DEFAULT_CONFIDENCE_THRESHOLD (0.70) → manual_review


# ------------------------------ auth / client ------------------------------


def _fake_user(uid: int, role: str = "applicant", status: str = "approved"):
    import json

    return lambda: types.SimpleNamespace(
        id=uid, roles=json.dumps([role]), active_role=role, status=status
    )


def _client(uid: int, role: str = "applicant", status: str = "approved") -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, role, status)
    return TestClient(app)


# ------------------------------ capture broker ------------------------------


class _CaptureBroker:
    def __init__(self) -> None:
        self.published: list = []

    def publish(self, message) -> None:
        self.published.append(message)

    def subscribe(self):  # pragma: no cover
        raise NotImplementedError


class _BrokenBroker:
    def publish(self, message) -> None:
        raise RuntimeError("broker down")

    def subscribe(self):  # pragma: no cover
        raise NotImplementedError


@pytest.fixture
def capture_broker():
    broker = _CaptureBroker()
    resident_notify.set_resident_broker(broker)
    yield broker
    resident_notify.reset_resident_broker()


# ------------------------------ seed helpers ------------------------------


def _link_user_apartment(db, user_id: int, apartment_id: int, status: str = "approved") -> None:
    db.execute(
        text(
            "INSERT INTO user_apartments (user_id, apartment_id, status, is_owner, is_primary) "
            "VALUES (:u, :a, :s, false, true)"
        ),
        {"u": user_id, "a": apartment_id, "s": status},
    )
    db.commit()


def _ingest_manual_review(
    db, pilot: PilotFixture, *, plate: str = PLATE, event_id: str,
    confidence: float = LOW_CONFIDENCE,
):
    return ingest_anpr(
        db,
        AnprIngestInput(
            controller_id=pilot.controller_id,
            event_id=event_id,
            zone_id=pilot.zone_id,
            gate_id=pilot.gate_id,
            camera_id=pilot.camera_id,
            barrier_id=pilot.barrier_id,
            plate_number_original=plate,
            direction="entry",
            confidence=confidence,
            captured_at=utcnow(),
        ),
    )


# ------------------------------ router wiring ------------------------------


def test_confirm_route_registered() -> None:
    paths = {route.path for route in create_app().routes}
    assert "/api/v1/access/my/entries/{decision_id}/confirm" in paths


# ------------------------------ notify-hook ------------------------------


def test_pending_review_notifies_resident(
    pg_db, pilot: PilotFixture, capture_broker: _CaptureBroker
) -> None:
    """pending_review по номеру зарегистрированного авто → disputed_entry жителю."""
    resident = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, resident, pilot.apartment_id)
    seed_permanent_vehicle(pg_db, pilot, normalized=PLATE)

    result = _ingest_manual_review(pg_db, pilot, plate=PLATE, event_id="mr-notify-1")
    assert result.status == "pending_review"

    assert len(capture_broker.published) == 1
    payload = capture_broker.published[0].to_payload()
    assert payload["kind"] == "disputed_entry"
    assert payload["recipient_user_id"] == resident
    assert payload["decision_id"] == result.decision_id
    assert payload["status"] == "pending_review"
    assert payload["camera_event_id"] is not None
    # PD-safe (§11): полный номер в канал не попадает, только маскированный хвост.
    assert PLATE not in str(payload)
    assert payload["plate_masked"]


def test_no_resident_no_notification(
    pg_db, pilot: PilotFixture, capture_broker: _CaptureBroker
) -> None:
    """Номер не сопоставлен с резидентом → уведомления нет (нет адресата)."""
    result = _ingest_manual_review(pg_db, pilot, plate=PLATE, event_id="mr-notify-2")
    assert result.status == "pending_review"
    assert capture_broker.published == []


def test_notify_best_effort_does_not_break_ingest(
    pg_db, pilot: PilotFixture
) -> None:
    """Сбой publish НЕ ломает ingestion: решение зафиксировано как pending_review."""
    resident = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, resident, pilot.apartment_id)
    seed_permanent_vehicle(pg_db, pilot, normalized=PLATE)

    resident_notify.set_resident_broker(_BrokenBroker())
    try:
        result = _ingest_manual_review(pg_db, pilot, plate=PLATE, event_id="mr-notify-3")
    finally:
        resident_notify.reset_resident_broker()

    assert result.status == "pending_review"
    status = pg_db.execute(
        text("SELECT status FROM access_decisions WHERE id = :d"),
        {"d": result.decision_id},
    ).scalar()
    assert status == "pending_review"


# ------------------------------ POST confirm ------------------------------


def test_resident_confirms_entry(pg_db, pilot: PilotFixture) -> None:
    """Житель квартиры → запись confirm создана, решение не тронуто."""
    resident = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, resident, pilot.apartment_id)
    seed_permanent_vehicle(pg_db, pilot, normalized=PLATE)
    result = _ingest_manual_review(pg_db, pilot, plate=PLATE, event_id="mr-conf-1")

    resp = _client(resident).post(
        f"/api/v1/access/my/entries/{result.decision_id}/confirm",
        json={"response": "confirm"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["response"] == "confirm"
    assert body["decision_id"] == result.decision_id

    row = pg_db.execute(
        text(
            "SELECT response, user_id FROM access_entry_confirmations "
            "WHERE decision_id = :d"
        ),
        {"d": result.decision_id},
    ).mappings().all()
    assert len(row) == 1
    assert row[0]["response"] == "confirm"
    assert row[0]["user_id"] == resident


def test_resident_deny_entry(pg_db, pilot: PilotFixture) -> None:
    """Житель может опровергнуть въезд (deny)."""
    resident = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, resident, pilot.apartment_id)
    seed_permanent_vehicle(pg_db, pilot, normalized=PLATE)
    result = _ingest_manual_review(pg_db, pilot, plate=PLATE, event_id="mr-conf-deny")

    resp = _client(resident).post(
        f"/api/v1/access/my/entries/{result.decision_id}/confirm",
        json={"response": "deny"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["response"] == "deny"


def test_foreign_resident_403(pg_db, pilot: PilotFixture) -> None:
    """Чужой житель (не его авто/квартира) → 403."""
    # Спорный въезд по авто pilot.apartment_id.
    seed_permanent_vehicle(pg_db, pilot, normalized=PLATE)
    result = _ingest_manual_review(pg_db, pilot, plate=PLATE, event_id="mr-conf-foreign")

    # Чужой житель: другая квартира + своё (другое) авто.
    other = seed_user(pg_db, roles="applicant")
    other_apt = _seed_apartment(pg_db)
    pg_db.commit()
    _link_user_apartment(pg_db, other, other_apt)

    resp = _client(other).post(
        f"/api/v1/access/my/entries/{result.decision_id}/confirm",
        json={"response": "confirm"},
    )
    assert resp.status_code == 403


def test_repeat_confirm_upserts_last_answer(pg_db, pilot: PilotFixture) -> None:
    """Повтор → upsert: остаётся ОДНА строка с последним ответом."""
    resident = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, resident, pilot.apartment_id)
    seed_permanent_vehicle(pg_db, pilot, normalized=PLATE)
    result = _ingest_manual_review(pg_db, pilot, plate=PLATE, event_id="mr-conf-upsert")
    client = _client(resident)

    r1 = client.post(
        f"/api/v1/access/my/entries/{result.decision_id}/confirm",
        json={"response": "confirm"},
    )
    assert r1.status_code == 200
    r2 = client.post(
        f"/api/v1/access/my/entries/{result.decision_id}/confirm",
        json={"response": "deny"},
    )
    assert r2.status_code == 200

    rows = pg_db.execute(
        text(
            "SELECT response FROM access_entry_confirmations WHERE decision_id = :d"
        ),
        {"d": result.decision_id},
    ).scalars().all()
    assert rows == ["deny"]


def test_confirm_does_not_open_barrier(pg_db, pilot: PilotFixture) -> None:
    """Подтверждение совещательно: команды открытия нет, решение pending_review."""
    resident = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, resident, pilot.apartment_id)
    seed_permanent_vehicle(pg_db, pilot, normalized=PLATE)
    result = _ingest_manual_review(pg_db, pilot, plate=PLATE, event_id="mr-conf-nobar")

    _client(resident).post(
        f"/api/v1/access/my/entries/{result.decision_id}/confirm",
        json={"response": "confirm"},
    )

    cmds = pg_db.execute(
        text("SELECT count(*) FROM barrier_commands WHERE decision_id = :d"),
        {"d": result.decision_id},
    ).scalar()
    assert cmds == 0
    status = pg_db.execute(
        text(
            "SELECT status FROM access_decisions WHERE id = (SELECT max(id) "
            "FROM access_decisions WHERE camera_event_id = "
            "(SELECT camera_event_id FROM access_decisions WHERE id = :d))"
        ),
        {"d": result.decision_id},
    ).scalar()
    assert status == "pending_review"


def test_confirm_unknown_decision_404(pg_db, pilot: PilotFixture) -> None:
    resident = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, resident, pilot.apartment_id)
    resp = _client(resident).post(
        "/api/v1/access/my/entries/999999/confirm", json={"response": "confirm"}
    )
    assert resp.status_code == 404


# ------------------------------ RBAC ------------------------------


def test_confirm_requires_auth_401(pg_db, pilot: PilotFixture) -> None:
    seed_permanent_vehicle(pg_db, pilot, normalized=PLATE)
    result = _ingest_manual_review(pg_db, pilot, plate=PLATE, event_id="mr-conf-401")
    resp = TestClient(create_app()).post(
        f"/api/v1/access/my/entries/{result.decision_id}/confirm",
        json={"response": "confirm"},
    )
    assert resp.status_code == 401


def test_confirm_manager_403(pg_db, pilot: PilotFixture) -> None:
    seed_permanent_vehicle(pg_db, pilot, normalized=PLATE)
    result = _ingest_manual_review(pg_db, pilot, plate=PLATE, event_id="mr-conf-mgr")
    uid = seed_user(pg_db, roles="manager")
    resp = _client(uid, "manager").post(
        f"/api/v1/access/my/entries/{result.decision_id}/confirm",
        json={"response": "confirm"},
    )
    assert resp.status_code == 403


def test_confirm_invalid_response_422(pg_db, pilot: PilotFixture) -> None:
    resident = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, resident, pilot.apartment_id)
    seed_permanent_vehicle(pg_db, pilot, normalized=PLATE)
    result = _ingest_manual_review(pg_db, pilot, plate=PLATE, event_id="mr-conf-422")
    resp = _client(resident).post(
        f"/api/v1/access/my/entries/{result.decision_id}/confirm",
        json={"response": "maybe"},
    )
    assert resp.status_code == 422


# ------------------------------ operator visibility ------------------------------


def test_event_detail_shows_resident_confirmations(pg_db, pilot: PilotFixture) -> None:
    """GET /events/{id} → resident_confirmations виден оператору на manual_review."""
    resident = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, resident, pilot.apartment_id)
    seed_permanent_vehicle(pg_db, pilot, normalized=PLATE)
    result = _ingest_manual_review(pg_db, pilot, plate=PLATE, event_id="mr-detail-1")

    _client(resident).post(
        f"/api/v1/access/my/entries/{result.decision_id}/confirm",
        json={"response": "confirm"},
    )

    operator = seed_user(pg_db, roles="security_operator")
    camera_event_id = pg_db.execute(
        text("SELECT camera_event_id FROM access_decisions WHERE id = :d"),
        {"d": result.decision_id},
    ).scalar()
    resp = _client(operator, "security_operator").get(
        f"/api/v1/access/events/{camera_event_id}"
    )
    assert resp.status_code == 200, resp.text
    confirmations = resp.json()["resident_confirmations"]
    assert len(confirmations) == 1
    assert confirmations[0]["user_id"] == resident
    assert confirmations[0]["response"] == "confirm"
    assert "created_at" in confirmations[0]
