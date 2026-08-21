"""Provenance группового источника — сквозь НАСТОЯЩИЙ save_request_sync.

Мок save_request в callback-тестах по построению не ловит рассинхрон ключей
data ↔ create_request_record (урок PR #477: мок CommandOutcome не поймал бы
классовую ошибку). Здесь путь создания проходит целиком на sqlite: валидация →
re-резолв адреса → номер → INSERT c source_chat_id/source_message_id → outbox →
commit.
"""
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models import (
    Apartment,
    Building,
    UserApartment,
    Yard,
)
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.handlers.requests.create import save_request_sync

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


@pytest.fixture()
def apartment(db):
    yard = Yard(name="Двор Тестовый", is_active=True)
    building = Building(address="ул. Тестовая, 12", yard=yard, is_active=True)
    apt = Apartment(apartment_number="7", building=building, is_active=True)
    user = User(
        telegram_id=TELEGRAM_ID, roles='["applicant"]', active_role="applicant",
        status="approved", phone="+998901112233", language="ru",
    )
    db.add_all([yard, building, apt, user])
    db.commit()
    db.add(UserApartment(user_id=user.id, apartment_id=apt.id,
                         status="approved", is_primary=True))
    db.commit()
    return apt


@pytest.fixture(autouse=True)
def _no_dispatch(monkeypatch):
    # авто-dispatch открывает СВОЮ сессию через глобальную фабрику — в
    # sqlite-юните ему делать нечего (best-effort и в проде)
    import uk_management_bot.services.dispatch as dispatch_mod

    monkeypatch.setattr(
        dispatch_mod, "auto_dispatch_new_request_sync", MagicMock()
    )


def _data(apartment, **extra):
    data = {
        "category": "electricity",
        "urgency": "medium",
        "address_type": "apartment",
        "address_id": apartment.id,
        "description": "В подъезде не горит свет уже второй день",
        "media_files": [],
    }
    data.update(extra)
    return data


def test_group_source_persists_provenance(db, apartment):
    saved = save_request_sync(
        _data(apartment, source_chat_id=-100500, source_message_id=42),
        TELEGRAM_ID, db, source="group", role="applicant",
    )
    assert saved is not None
    number, _owner_id, _media = saved
    request = db.query(Request).filter(Request.request_number == number).one()
    assert request.source == "group"
    assert request.source_chat_id == -100500
    assert request.source_message_id == 42
    # адрес пришёл из резолвера, а не из клиента
    assert request.address_type == "apartment"
    assert request.apartment_id == apartment.id


def test_bot_source_leaves_provenance_null(db, apartment):
    saved = save_request_sync(
        _data(apartment), TELEGRAM_ID, db, source="bot", role="applicant"
    )
    assert saved is not None
    number = saved[0]
    request = db.query(Request).filter(Request.request_number == number).one()
    assert request.source_chat_id is None
    assert request.source_message_id is None
