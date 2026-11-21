"""Подземный паркинг двора в заявке (бот): кнопка, перевод, сохранение, адрес в отчёте о работах."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models import Apartment, Building, UserApartment, Yard
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.handlers.requests.create import save_request_sync
from uk_management_bot.services.work_reports.addressing import derive_public_address
from uk_management_bot.keyboards.requests import build_request_address_inline_keyboard
from uk_management_bot.services.request_address import PARKING_SUFFIX
from uk_management_bot.utils.address_helpers import localize_address

ADDRESSES = {
    "apartments": [], "buildings": [],
    "yards": [{"id": 7, "label": "Двор А"}],
    "parkings": [{"id": 7, "label": f"Двор А{PARKING_SUFFIX}"}],
}


def _buttons(language: str) -> dict[str, str]:
    keyboard = build_request_address_inline_keyboard(ADDRESSES, language=language)
    return {b.callback_data: b.text for row in keyboard.inline_keyboard for b in row}


def test_parking_button_carries_yard_id_and_parking_level():
    buttons = _buttons("ru")
    assert buttons["addr:parking:7"] == "🅿️ Двор А, подземный паркинг"
    assert "addr:yard:7" in buttons


def test_parking_label_is_translated_for_uzbek():
    assert _buttons("uz")["addr:parking:7"] == "🅿️ Двор А, yer osti avtoturargohi"
    assert localize_address("Двор А, подземный паркинг", "ru") == "Двор А, подземный паркинг"


def test_no_parking_button_without_flag():
    keyboard = build_request_address_inline_keyboard({**ADDRESSES, "parkings": []}, language="ru")
    assert not any((b.callback_data or "").startswith("addr:parking") for row in keyboard.inline_keyboard for b in row)


@pytest.fixture()
def db(monkeypatch):
    import uk_management_bot.services.dispatch as dispatch_mod

    monkeypatch.setattr(dispatch_mod, "auto_dispatch_new_request_sync", MagicMock())
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _resident(db, *, parking: bool) -> Yard:
    yard = Yard(name="Двор А", is_active=True, has_underground_parking=parking)
    building = Building(address="ул. Тестовая, 12", yard=yard, is_active=True)
    apt = Apartment(apartment_number="7", building=building, is_active=True)
    user = User(telegram_id=111, roles='["applicant"]', active_role="applicant",
                status="approved", phone="+998901112233", language="ru")
    db.add_all([yard, building, apt, user])
    db.commit()
    db.add(UserApartment(user_id=user.id, apartment_id=apt.id, status="approved", is_primary=True))
    db.commit()
    return yard


def _data(yard: Yard) -> dict:
    return {"category": "plumbing", "urgency": "low", "address_type": "parking",
            "address_id": yard.id, "description": "Течёт труба", "media_files": []}


def test_bot_saves_parking_request_as_yard_level_with_parking_address(db):
    """FSM хранит выбранный уровень "parking": повторный резолв при сохранении не теряет паркинг."""
    yard = _resident(db, parking=True)
    saved = save_request_sync(_data(yard), 111, db, source="bot", role="applicant")
    assert saved is not None
    req = db.query(Request).filter(Request.request_number == saved[0]).one()
    assert (req.address_type, req.yard_id, req.address) == ("yard", yard.id, "Двор А, подземный паркинг")
    assert derive_public_address(req) == "Двор А, подземный паркинг"


def test_bot_refuses_parking_request_when_yard_has_no_parking(db):
    yard = _resident(db, parking=False)
    assert save_request_sync(_data(yard), 111, db, source="bot", role="applicant") is None
    assert db.query(Request).count() == 0


def test_work_report_address_of_plain_yard_request_has_no_parking():
    yard = SimpleNamespace(name="Двор А")
    request = SimpleNamespace(address_type="yard", yard_obj=yard, address="Двор А")
    assert derive_public_address(request) == "Двор А"
