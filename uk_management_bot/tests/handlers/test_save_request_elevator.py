"""Р11 в sync-конструкторе бота (T6, Ф4a-1): ``create_request_record`` +
протаскивание ``data["elevator_id"]``/``data["elevator_operational"]`` через
настоящий ``save_request_sync`` на sqlite (образец — test_group_intake_provenance).
"""
from __future__ import annotations

import logging
from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models import Apartment, Building, UserApartment, Yard
from uk_management_bot.database.models.elevator import Elevator
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.handlers.requests.create import save_request_sync
from uk_management_bot.services.elevator_service import (
    ElevatorValidationError,
    generate_public_code,
)
from uk_management_bot.services.request_handler_service import RequestHandlerService

TELEGRAM_ID = 111


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", True)


@pytest.fixture(autouse=True)
def _no_dispatch(monkeypatch):
    import uk_management_bot.services.dispatch as dispatch_mod

    monkeypatch.setattr(dispatch_mod, "auto_dispatch_new_request_sync", MagicMock())


@pytest.fixture()
def world(db):
    yard = Yard(name="Двор Тестовый", is_active=True)
    building = Building(address="ул. Тестовая, 12", yard=yard, is_active=True)
    apt = Apartment(apartment_number="7", building=building, is_active=True)
    user = User(
        telegram_id=TELEGRAM_ID, roles='["applicant"]', active_role="applicant",
        status="approved", phone="+998901112233", language="ru",
    )
    db.add_all([yard, building, apt, user])
    db.commit()
    db.add(UserApartment(user_id=user.id, apartment_id=apt.id, status="approved", is_primary=True))
    ok = Elevator(building_id=building.id, entrance_number=1, elevator_number=1,
                  passport_number="P-1", manufacturer="OTIS", serial_number="S-1",
                  public_code=generate_public_code(), is_commissioned=True,
                  commissioned_at=date(2020, 1, 1), current_status="working")
    raw = Elevator(building_id=building.id, entrance_number=1, elevator_number=2,
                   passport_number="P-2", manufacturer="OTIS", serial_number="S-2",
                   public_code=generate_public_code(), is_commissioned=False)
    other = Building(address="ул. Чужая, 9", yard=yard, is_active=True)
    db.add(other)
    db.commit()
    foreign = Elevator(building_id=other.id, entrance_number=1, elevator_number=1,
                       passport_number="P-9", manufacturer="OTIS", serial_number="S-9",
                       public_code=generate_public_code(), is_commissioned=True,
                       commissioned_at=date(2020, 1, 1), current_status="working")
    db.add_all([ok, raw, foreign])
    db.commit()
    return {"user": user, "apt": apt, "building": building, "ok": ok, "raw": raw, "foreign": foreign}


def _record(service: RequestHandlerService, number: str, *, category: str, user_id: int,
            building_id: int | None = None, apartment_id: int | None = None, **extra):
    """Заявка уровня дома (building_id) / квартиры (apartment_id) — как отдаёт резолвер."""
    address_type = "apartment" if apartment_id is not None else ("building" if building_id else None)
    return service.create_request_record(
        request_number=number, category=category, address="a", description="d",
        urgency="high", apartment_id=apartment_id, building_id=building_id, yard_id=None,
        address_type=address_type, media_files=[], user_id=user_id, source="bot", **extra,
    )


# ── create_request_record ────────────────────────────────────────────

def test_elevator_category_without_fields_raises(db, world):
    service = RequestHandlerService(db)
    with pytest.raises(ElevatorValidationError):
        _record(service, "260905-001", category="elevator", user_id=world["user"].id)
    db.rollback()
    assert db.query(Request).count() == 0


def test_elevator_category_with_fields_persisted(db, world):
    service = RequestHandlerService(db)
    _record(service, "260905-002", category="elevator", user_id=world["user"].id,
            building_id=world["building"].id,
            elevator_id=world["ok"].id, elevator_operational=False)
    service.commit()
    req = db.query(Request).filter_by(request_number="260905-002").one()
    assert req.elevator_id == world["ok"].id and req.elevator_operational is False


def test_building_derived_from_apartment(db, world):
    """Уровень квартиры: building_id из резолвера None — дом выводится из квартиры."""
    service = RequestHandlerService(db)
    _record(service, "260905-012", category="elevator", user_id=world["user"].id,
            apartment_id=world["apt"].id, elevator_id=world["ok"].id, elevator_operational=True)
    service.commit()
    req = db.query(Request).filter_by(request_number="260905-012").one()
    assert req.elevator_id == world["ok"].id and req.building_id is None


def test_elevator_of_other_building_raises(db, world):
    """Security T6: лифт чужого дома к своей квартире не привязать."""
    service = RequestHandlerService(db)
    with pytest.raises(ElevatorValidationError, match="другому дому"):
        _record(service, "260905-013", category="elevator", user_id=world["user"].id,
                apartment_id=world["apt"].id, elevator_id=world["foreign"].id,
                elevator_operational=False)


def test_elevator_without_building_raises(db, world):
    """Без дома и квартиры (двор/legacy) лифт привязать нельзя."""
    service = RequestHandlerService(db)
    with pytest.raises(ElevatorValidationError, match="нужен дом или квартира"):
        _record(service, "260905-014", category="elevator", user_id=world["user"].id,
                elevator_id=world["ok"].id, elevator_operational=False)


def test_uncommissioned_elevator_raises(db, world):
    service = RequestHandlerService(db)
    with pytest.raises(ElevatorValidationError, match="не введён"):
        _record(service, "260905-003", category="elevator", user_id=world["user"].id,
                building_id=world["building"].id,
                elevator_id=world["raw"].id, elevator_operational=True)


def test_other_category_without_elevator_unchanged(db, world):
    service = RequestHandlerService(db)
    _record(service, "260905-004", category="electricity", user_id=world["user"].id)
    service.commit()
    req = db.query(Request).filter_by(request_number="260905-004").one()
    assert req.elevator_id is None and req.elevator_operational is None


def test_flag_off_ignores_fields(db, world, monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", False)
    service = RequestHandlerService(db)
    _record(service, "260905-005", category="elevator", user_id=world["user"].id)
    _record(service, "260905-006", category="elevator", user_id=world["user"].id,
            elevator_id=world["raw"].id, elevator_operational=True)
    service.commit()
    for number in ("260905-005", "260905-006"):
        req = db.query(Request).filter_by(request_number=number).one()
        assert req.elevator_id is None and req.elevator_operational is None


# ── save_request_sync: маппинг ключей data ───────────────────────────

def _data(world, **extra):
    data = {
        "category": "elevator", "urgency": "high", "address_type": "apartment",
        "address_id": world["apt"].id, "description": "Лифт не едет", "media_files": [],
    }
    data.update(extra)
    return data


def test_save_request_sync_passes_elevator_fields(db, world):
    saved = save_request_sync(
        _data(world, elevator_id=world["ok"].id, elevator_operational=False),
        TELEGRAM_ID, db, source="bot", role="applicant",
    )
    assert saved is not None
    req = db.query(Request).filter(Request.request_number == saved[0]).one()
    assert req.elevator_id == world["ok"].id and req.elevator_operational is False


def test_save_request_sync_elevator_without_fields_not_saved(db, world, caplog):
    """Без FSM-шага (T7) данных нет → инвариант не даёт записать заявку (None).

    Отказ Р11 — ожидаемая валидация: WARNING без traceback, а не ERROR общего
    `except Exception` (образец — ветка AddressResolutionError).
    """
    with caplog.at_level(logging.WARNING):
        saved = save_request_sync(_data(world), TELEGRAM_ID, db, source="bot", role="applicant")
    assert saved is None
    assert db.query(Request).count() == 0
    rejected = [r for r in caplog.records if "Лифт отклонён" in r.getMessage()]
    assert len(rejected) == 1
    assert rejected[0].levelno == logging.WARNING and rejected[0].exc_info is None
    assert "elevator_id" in rejected[0].getMessage()
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
