"""T7 (ревью): шаг лифта у обходчика в боте — те же общие шаги create_elevator,
свои состояния InspectorRequestStates.elevator_pick/elevator_operational.

Свойства (RED-первыми):
1. Флаг выключен → категория ведёт сразу в description (как раньше).
2. Дом с одним введённым лифтом → автоподстановка (у обходчика нет подъезда —
   только «ровно один в доме»); несколько → клавиатура elv:pick; ни одного →
   сообщение и возврат к категории (клавиатура insp_cat:*).
3. elv:pick: не-обходчик → отказ inspector.only_approved; лифт чужого дома → отказ.
4. elv:op:0 → elevator_operational False, переход в description.
5. inspector_confirm: save_request получает data с elevator_id/operational;
   None → requests.elevator.error_generic (для лифтового потока).
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models import Building, Yard
from uk_management_bot.database.models.elevator import Elevator
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.handlers import inspector_requests as insp
from uk_management_bot.handlers.inspector_requests import InspectorRequestStates
from uk_management_bot.handlers.requests import create_elevator as mod
from uk_management_bot.services.elevator_service import generate_public_code
from uk_management_bot.utils.helpers import get_text

INSPECTOR_TG = 333
APPLICANT_TG = 444


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
def _lang_ru():
    with patch.object(insp, "_lang", AsyncMock(return_value="ru")):
        yield


@pytest.fixture(autouse=True)
def _run_db_on_sqlite(db):
    session = db

    async def _run(unit, *, db=None):
        return unit(db if db is not None else session)

    with patch.object(insp, "run_db", _run), patch.object(mod, "run_db", _run):
        yield


def _elevator(building, entrance, number, *, commissioned=True):
    return Elevator(
        building_id=building.id, entrance_number=entrance, elevator_number=number,
        passport_number=f"P-{entrance}{number}", manufacturer="OTIS",
        serial_number=f"S-{building.id}-{entrance}{number}", public_code=generate_public_code(),
        is_commissioned=commissioned, commissioned_at=date(2020, 1, 1) if commissioned else None,
        current_status="working" if commissioned else None,
    )


@pytest.fixture()
def world(db):
    yard = Yard(name="Двор", is_active=True)
    single = Building(address="ул. Одиночная, 1", yard=yard, is_active=True)
    many = Building(address="ул. Многолифтовая, 2", yard=yard, is_active=True)
    none = Building(address="ул. Пешая, 3", yard=yard, is_active=True)
    inspector = User(telegram_id=INSPECTOR_TG, roles='["inspector"]', active_role="inspector",
                     status="approved", language="ru")
    applicant = User(telegram_id=APPLICANT_TG, roles='["applicant"]', active_role="applicant",
                     status="approved", language="ru")
    db.add_all([yard, single, many, none, inspector, applicant])
    db.commit()
    s11 = _elevator(single, 1, 1)
    s12_raw = _elevator(single, 1, 2, commissioned=False)
    m11, m21 = _elevator(many, 1, 1), _elevator(many, 2, 1)
    db.add_all([s11, s12_raw, m11, m21])
    db.commit()
    return {"single": single, "many": many, "none": none,
            "s11": s11, "s12_raw": s12_raw, "m11": m11, "m21": m21}


class FakeState:
    def __init__(self, data=None, state=None):
        self.data = dict(data or {})
        self.state = state

    async def get_data(self):
        return dict(self.data)

    async def update_data(self, data=None, **kwargs):
        self.data = {**self.data, **(data or {}), **kwargs}
        return dict(self.data)

    async def set_data(self, data):
        self.data = dict(data)

    async def set_state(self, state=None):
        self.state = state

    async def clear(self):
        self.data, self.state = {}, None


def _callback(data: str, tg_id: int = INSPECTOR_TG) -> MagicMock:
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = tg_id
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    cb.bot = MagicMock()
    return cb


def _callbacks(markup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def _answers(cb) -> list[str]:
    return [c.args[0] for c in cb.message.answer.await_args_list]


def _last_markup(cb):
    return cb.message.answer.await_args_list[-1].kwargs.get("reply_markup")


def _building_data(world, key: str) -> dict:
    """Data после выбора дома обходчиком (как кладёт inspector_building_selected)."""
    return {"address_type": "building", "address_id": world[key].id, "address": world[key].address}


async def _pick_category(world, key: str, category: str = "elevator"):
    cb = _callback(f"insp_cat:{category}")
    state = FakeState(_building_data(world, key), InspectorRequestStates.category)
    await insp.inspector_category_selected(cb, state)
    return cb, state


# ── 1. регресс ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_flag_off_goes_to_description(world, monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", False)
    cb, state = await _pick_category(world, "many")
    assert state.state is InspectorRequestStates.description
    assert "elevator_id" not in state.data
    assert get_text("requests.description", language="ru") in _answers(cb)


@pytest.mark.asyncio
async def test_other_category_unchanged(world):
    _, state = await _pick_category(world, "many", category="electricity")
    assert state.state is InspectorRequestStates.description


# ── 2. автоподстановка / выбор / нет лифтов ──────────────────────────────


@pytest.mark.asyncio
async def test_single_commissioned_elevator_in_building_autopicked(world):
    cb, state = await _pick_category(world, "single")
    assert state.state is InspectorRequestStates.elevator_operational
    assert state.data["elevator_id"] == world["s11"].id
    assert state.data["elevator_building_id"] == world["single"].id
    assert {"elv:op:1", "elv:op:0"} <= set(_callbacks(_last_markup(cb)))


@pytest.mark.asyncio
async def test_many_elevators_show_pick_keyboard(world):
    cb, state = await _pick_category(world, "many")
    assert state.state is InspectorRequestStates.elevator_pick
    callbacks = _callbacks(_last_markup(cb))
    assert f"elv:pick:{world['m11'].id}" in callbacks and f"elv:pick:{world['m21'].id}" in callbacks


@pytest.mark.asyncio
async def test_building_without_elevators_returns_to_inspector_category(world):
    cb, state = await _pick_category(world, "none")
    assert state.state is InspectorRequestStates.category
    assert get_text("requests.elevator.none_in_building", language="ru") in _answers(cb)
    assert any(c.startswith("insp_cat:") for c in _callbacks(_last_markup(cb)))
    assert "elevator_id" not in state.data


# ── 3. отказы elv:pick ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pick_by_non_inspector_rejected(world):
    cb = _callback(f"elv:pick:{world['m11'].id}", tg_id=APPLICANT_TG)
    state = FakeState({"category": "elevator", "elevator_building_id": world["many"].id},
                      InspectorRequestStates.elevator_pick)
    await insp.inspector_elevator_pick(cb, state)
    assert "elevator_id" not in state.data
    assert cb.answer.await_args.args[0] == get_text("inspector.only_approved", language="ru")


@pytest.mark.asyncio
async def test_pick_elevator_of_other_building_rejected(world):
    cb = _callback(f"elv:pick:{world['s11'].id}")
    state = FakeState({"category": "elevator", "elevator_building_id": world["many"].id},
                      InspectorRequestStates.elevator_pick)
    await insp.inspector_elevator_pick(cb, state)
    assert "elevator_id" not in state.data
    assert cb.answer.await_args.args[0] == get_text("requests.elevator.invalid_choice", language="ru")


@pytest.mark.asyncio
async def test_pick_ok_moves_to_operational(world):
    cb = _callback(f"elv:pick:{world['m21'].id}")
    state = FakeState({"category": "elevator", "elevator_building_id": world["many"].id},
                      InspectorRequestStates.elevator_pick)
    await insp.inspector_elevator_pick(cb, state)
    assert state.state is InspectorRequestStates.elevator_operational
    assert state.data["elevator_id"] == world["m21"].id
    assert state.data["elevator_entrance"] == 2 and state.data["elevator_number"] == 1


# ── 4. «работает?» ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_operational_no_moves_to_description(world):
    cb = _callback("elv:op:0")
    state = FakeState({"category": "elevator", "elevator_id": world["m11"].id},
                      InspectorRequestStates.elevator_operational)
    await insp.inspector_elevator_operational(cb, state)
    assert state.data["elevator_operational"] is False
    assert state.state is InspectorRequestStates.description
    assert get_text("requests.description", language="ru") in _answers(cb)


# ── 5. сохранение ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_confirm_passes_elevator_fields_to_save(world):
    cb = _callback("insp_confirm_yes")
    data = {**_building_data(world, "many"), "category": "elevator", "description": "Не едет",
            "urgency": "high", "elevator_id": world["m11"].id, "elevator_operational": False}
    state = FakeState(data, InspectorRequestStates.confirm)
    saved = AsyncMock(return_value="260906-001")
    with patch("uk_management_bot.handlers.requests.save_request", saved):
        await insp.inspector_confirm(cb, state)
    passed = saved.await_args.args[0]
    assert passed["elevator_id"] == world["m11"].id and passed["elevator_operational"] is False
    assert saved.await_args.kwargs["source"] == "inspector"


@pytest.mark.asyncio
async def test_confirm_save_failed_shows_elevator_error(world):
    cb = _callback("insp_confirm_yes")
    data = {**_building_data(world, "many"), "category": "elevator",
            "elevator_id": world["m11"].id, "elevator_operational": True}
    state = FakeState(data, InspectorRequestStates.confirm)
    with patch("uk_management_bot.handlers.requests.save_request", AsyncMock(return_value=None)):
        await insp.inspector_confirm(cb, state)
    assert cb.message.edit_text.await_args.args[0] == get_text(
        "requests.elevator.error_generic", language="ru")


@pytest.mark.asyncio
async def test_confirm_save_failed_other_category_generic(world):
    cb = _callback("insp_confirm_yes")
    state = FakeState({**_building_data(world, "many"), "category": "electricity"},
                      InspectorRequestStates.confirm)
    with patch("uk_management_bot.handlers.requests.save_request", AsyncMock(return_value=None)):
        await insp.inspector_confirm(cb, state)
    assert cb.message.edit_text.await_args.args[0] == get_text(
        "errors.request_save_failed", language="ru")


# ── 6. Р18: обходчик — персонал, запрет самообслуживания на него не действует ──


@pytest.mark.asyncio
async def test_inspector_can_pick_elevator_under_works(world, db):
    """Лифт «В ремонте» обходчику не блокируется: прежняя мягкая подсказка + вопрос."""
    world["m21"].current_status = "under_repair"
    db.commit()
    cb = _callback(f"elv:pick:{world['m21'].id}")
    state = FakeState({"category": "elevator", "elevator_building_id": world["many"].id},
                      InspectorRequestStates.elevator_pick)
    await insp.inspector_elevator_pick(cb, state)
    assert state.state is InspectorRequestStates.elevator_operational
    assert state.data["elevator_id"] == world["m21"].id
    texts = "\n".join(_answers(cb))
    assert get_text("elevators.status.under_repair", language="ru") in texts
    assert get_text("requests.elevator.operational_prompt", language="ru") in texts


@pytest.mark.asyncio
async def test_inspector_confirm_passes_staff_escape_hatch(world):
    """save_request получает allow_under_works=True — иначе Р18 отбил бы ремонт."""
    cb = _callback("insp_confirm_yes")
    data = {**_building_data(world, "many"), "category": "elevator", "description": "Не едет",
            "urgency": "high", "elevator_id": world["m21"].id, "elevator_operational": False}
    state = FakeState(data, InspectorRequestStates.confirm)
    saved = AsyncMock(return_value="260906-002")
    with patch("uk_management_bot.handlers.requests.save_request", saved):
        await insp.inspector_confirm(cb, state)
    assert saved.await_args.kwargs["allow_under_works"] is True
