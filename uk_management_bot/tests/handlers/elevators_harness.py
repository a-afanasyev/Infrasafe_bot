"""Общий харнес тестов бота лифтёра (Ф5, T10): мир на sqlite, фейки aiogram.

Не тест-модуль (без ``test_``-префикса): импортируется из
``test_elevators_*.py``. Sync-юниты гоняются на настоящем sqlite через
подменённый ``run_db`` пакета (образец — test_elevator_hint_manager).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from uk_management_bot.database.models import Apartment, Building, UserApartment, Yard
from uk_management_bot.database.models.elevator import Elevator, ElevatorMaintenanceOccurrence
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services.elevator_service import generate_public_code

TECH_TG = 1001          # лифтёр: executor + specialization elevator
ALIAS_TG = 1002         # executor со специализацией-алиасом maintenance
PLAIN_TG = 1003         # executor без специализации
RESIDENT_TG = 1004      # житель подъезда 1 (адресат уведомлений)
MANAGER_TG = 1005       # менеджер без роли executor
SINCE = datetime(2026, 9, 1, 7, 30, tzinfo=timezone.utc)
OPEN_REQUEST_NUMBER = "260901-001"


def make_db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def build_world(db: Session, *, today: date) -> dict:
    """Двор → дом → два лифта (введённый working и невведённый) + пользователи + график."""
    yard = Yard(name="Двор Лифтовый", is_active=True)
    building = Building(address="ул. Лифтовая, 1", yard=yard, is_active=True)
    apt = Apartment(apartment_number="7", building=building, entrance=1, is_active=True)
    tech = User(telegram_id=TECH_TG, roles='["executor"]', active_role="executor",
                status="approved", language="ru", specialization='["elevator"]')
    alias = User(telegram_id=ALIAS_TG, roles='["executor"]', active_role="executor",
                 status="approved", language="ru", specialization="maintenance")
    plain = User(telegram_id=PLAIN_TG, roles='["executor"]', active_role="executor",
                 status="approved", language="ru", specialization='["plumber"]')
    resident = User(telegram_id=RESIDENT_TG, roles='["applicant"]', active_role="applicant",
                    status="approved", language="ru")
    manager = User(telegram_id=MANAGER_TG, roles='["manager"]', active_role="manager",
                   status="approved", language="ru")
    db.add_all([yard, building, apt, tech, alias, plain, resident, manager])
    db.commit()
    db.add(UserApartment(user_id=resident.id, apartment_id=apt.id, status="approved"))
    working = Elevator(
        building_id=building.id, entrance_number=1, elevator_number=1,
        passport_number="P-1", manufacturer="OTIS", serial_number="S-1",
        public_code=generate_public_code(), is_commissioned=True,
        commissioned_at=date(2020, 1, 1), current_status="working", status_since=SINCE,
    )
    raw = Elevator(
        building_id=building.id, entrance_number=2, elevator_number=1,
        passport_number="P-2", manufacturer="OTIS", serial_number="S-2",
        public_code=generate_public_code(), is_commissioned=False,
    )
    db.add_all([working, raw])
    db.commit()
    soon = ElevatorMaintenanceOccurrence(
        elevator_id=working.id, kind="maintenance", due_on=today + timedelta(days=3), state="planned",
    )
    later = ElevatorMaintenanceOccurrence(
        elevator_id=working.id, kind="maintenance", due_on=today + timedelta(days=95), state="planned",
    )
    cert = ElevatorMaintenanceOccurrence(
        elevator_id=working.id, kind="certification", due_on=today + timedelta(days=20), state="planned",
    )
    open_request = Request(
        request_number=OPEN_REQUEST_NUMBER, user_id=tech.id, category="elevator",
        address="ул. Лифтовая, 1", description="скрипит", urgency="low", status="Новая",
        elevator_id=working.id, elevator_operational=True,
    )
    db.add_all([soon, later, cert, open_request])
    db.commit()
    return {
        "yard": yard, "building": building, "working": working, "raw": raw,
        "tech": tech, "alias": alias, "plain": plain, "resident": resident, "manager": manager,
        "soon": soon, "later": later, "cert": cert,
    }


class FakeState:
    """Минимальный FSMContext: данные и состояние в памяти."""

    def __init__(self) -> None:
        self.data: dict = {}
        self.state = None

    async def get_data(self) -> dict:
        return dict(self.data)

    async def update_data(self, **kwargs) -> dict:
        self.data = {**self.data, **kwargs}
        return dict(self.data)

    async def set_state(self, state) -> None:
        self.state = state

    async def get_state(self):
        return self.state

    async def clear(self) -> None:
        self.data, self.state = {}, None


def make_callback(data: str, from_id: int = TECH_TG) -> MagicMock:
    cb = MagicMock()
    cb.data = data
    cb.id = "cb1"
    cb.from_user.id = from_id
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    cb.bot = MagicMock()
    cb.bot.send_message = AsyncMock()
    return cb


def make_message(text: str, from_id: int = TECH_TG) -> MagicMock:
    msg = MagicMock()
    msg.text = text
    msg.from_user.id = from_id
    msg.answer = AsyncMock()
    msg.bot = MagicMock()
    msg.bot.send_message = AsyncMock()
    return msg


def callbacks_of(markup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def texts_of(markup) -> list[str]:
    return [b.text for row in markup.inline_keyboard for b in row]


def run_db_on(session: Session):
    """Подмена ``run_db``: юнит исполняется синхронно на тестовой сессии."""

    async def _run(unit, *, db=None):
        return unit(db if db is not None else session)

    return _run
