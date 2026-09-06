"""T7 (Ф4a-2): FSM жителя — шаг выбора лифта и «работает?» после адреса.

Свойства (RED-первыми):
1. Флаг выключен / категория не «лифт» → адрес ведёт сразу в description (регресс).
2. Квартира с подъездом и единственным лифтом в нём → автоподстановка, сразу
   вопрос «работает?»; несколько лифтов → клавиатура ``elv:pick:{id}``.
3. Дом без введённых лифтов → сообщение и возврат к выбору категории (Р11).
4. Двор → «укажите дом», адресный шаг остаётся.
5. ``elv:op:0`` → ``elevator_operational is False``, переход в description.
6. Чужой/невведённый лифт в ``elv:pick`` → отказ; не-applicant → отказ.
7. Сводка confirm несёт строку лифта; None от save_request → локализованная
   ошибка лифта, а не общий текст.

Sync-юниты гоняются на настоящем sqlite через подменённый ``run_db``
(образец — test_save_request_elevator / test_request_change_category).
"""
from __future__ import annotations

import copy
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models import Apartment, Building, UserApartment, Yard
from uk_management_bot.database.models.board_config import BoardConfig
from uk_management_bot.database.models.elevator import Elevator
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.handlers.requests import create, create_callbacks
from uk_management_bot.handlers.requests import create_elevator as mod
from uk_management_bot.handlers.requests import create_elevator_resident as resident
from uk_management_bot.handlers.requests.shared import RequestStates
from uk_management_bot.services.elevator_service import generate_public_code
from uk_management_bot.utils.helpers import get_text, load_locale

TG_ID = 111
STRANGER_TG_ID = 222
SINCE = datetime(2026, 9, 1, 7, 30, tzinfo=timezone.utc)


# ── харнесс ──────────────────────────────────────────────────────────────


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
    with patch.object(create, "_get_user_language", AsyncMock(return_value="ru")), \
         patch.object(resident, "_get_user_language", AsyncMock(return_value="ru")), \
         patch.object(create_callbacks, "_get_user_language", AsyncMock(return_value="ru")):
        yield


@pytest.fixture(autouse=True)
def _run_db_on_sqlite(db):
    session = db

    async def _run(unit, *, db=None):
        return unit(db if db is not None else session)

    with patch.object(create, "run_db", _run), patch.object(mod, "run_db", _run), \
         patch.object(resident, "run_db", _run), patch.object(create_callbacks, "run_db", _run):
        yield


def _elevator(building, entrance, number, *, commissioned=True, status="working", since=None):
    return Elevator(
        building_id=building.id, entrance_number=entrance, elevator_number=number,
        passport_number=f"P-{entrance}{number}", manufacturer="OTIS",
        serial_number=f"S-{building.id}-{entrance}{number}", public_code=generate_public_code(),
        is_commissioned=commissioned,
        commissioned_at=date(2020, 1, 1) if commissioned else None,
        current_status=status if commissioned else None, status_since=since,
    )


@pytest.fixture()
def world(db):
    yard = Yard(name="Двор", is_active=True)
    with_lifts = Building(address="ул. Лифтовая, 1", yard=yard, is_active=True)
    no_lifts = Building(address="ул. Пешая, 2", yard=yard, is_active=True)
    apt_single = Apartment(apartment_number="7", building=with_lifts, entrance=1, is_active=True)
    apt_many = Apartment(apartment_number="70", building=with_lifts, entrance=2, is_active=True)
    apt_no_entrance = Apartment(apartment_number="9", building=with_lifts, is_active=True)
    apt_no_lifts = Apartment(apartment_number="1", building=no_lifts, entrance=1, is_active=True)
    user = User(telegram_id=TG_ID, roles='["applicant"]', active_role="applicant",
                status="approved", phone="+998901112233", language="ru")
    stranger = User(telegram_id=STRANGER_TG_ID, roles='["executor"]', active_role="executor",
                    status="approved", phone="+998901112234", language="ru")
    db.add_all([yard, with_lifts, no_lifts, apt_single, apt_many, apt_no_entrance,
                apt_no_lifts, user, stranger])
    db.commit()
    for apt in (apt_single, apt_many, apt_no_entrance, apt_no_lifts):
        db.add(UserApartment(user_id=user.id, apartment_id=apt.id, status="approved"))
    e11 = _elevator(with_lifts, 1, 1)
    e12_raw = _elevator(with_lifts, 1, 2, commissioned=False)
    e21 = _elevator(with_lifts, 2, 1, status="under_repair", since=SINCE)
    e22 = _elevator(with_lifts, 2, 2)
    other = Building(address="ул. Чужая, 9", yard=yard, is_active=True)
    db.add_all([e11, e12_raw, e21, e22, other])
    db.commit()
    foreign = _elevator(other, 1, 1)
    db.add(foreign)
    db.commit()
    return {
        "yard": yard, "with_lifts": with_lifts, "no_lifts": no_lifts,
        "apt_single": apt_single, "apt_many": apt_many, "apt_no_entrance": apt_no_entrance,
        "apt_no_lifts": apt_no_lifts, "user": user,
        "e11": e11, "e12_raw": e12_raw, "e21": e21, "e22": e22, "foreign": foreign,
    }


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

    async def get_state(self):
        return self.state

    async def clear(self):
        self.data, self.state = {}, None


def _callback(data: str, tg_id: int = TG_ID) -> MagicMock:
    cb = MagicMock()
    cb.data = data
    cb.id = "cb1"
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


async def _pick_address(world, key: str, category: str = "elevator", atype: str = "apartment"):
    address_id = world[key].id
    cb = _callback(f"addr:{atype}:{address_id}")
    state = FakeState({"category": category}, RequestStates.address)
    await create.handle_address_selection(cb, state)
    return cb, state


# ── 1. регресс: без флага / не лифт ──────────────────────────────────────


@pytest.mark.asyncio
async def test_flag_off_address_goes_straight_to_description(world, monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", False)
    cb, state = await _pick_address(world, "apt_single")
    assert state.state is RequestStates.description
    assert "elevator_id" not in state.data
    assert get_text("requests.description", language="ru") in _answers(cb)


@pytest.mark.asyncio
async def test_other_category_unchanged_with_flag_on(world):
    _, state = await _pick_address(world, "apt_single", category="electricity")
    assert state.state is RequestStates.description
    assert "elevator_id" not in state.data


# ── 2. автоподстановка / клавиатура выбора ───────────────────────────────


@pytest.mark.asyncio
async def test_single_elevator_in_entrance_autopicked_and_asks_operational(world):
    """Подъезд 1: лифт №1 введён, №2 — нет → ровно один пригодный → без вопроса."""
    cb, state = await _pick_address(world, "apt_single")
    assert state.state is RequestStates.elevator_operational
    assert state.data["elevator_id"] == world["e11"].id
    assert state.data["elevator_building_id"] == world["with_lifts"].id
    assert {"elv:op:1", "elv:op:0"} <= set(_callbacks(_last_markup(cb)))
    assert get_text("requests.elevator.operational_prompt", language="ru") in _answers(cb)


@pytest.mark.asyncio
async def test_many_elevators_show_pick_keyboard(world):
    cb, state = await _pick_address(world, "apt_many")
    assert state.state is RequestStates.elevator_pick
    assert "elevator_id" not in state.data
    callbacks = _callbacks(_last_markup(cb))
    # Все введённые лифты дома, невведённый e12 — нет.
    assert f"elv:pick:{world['e11'].id}" in callbacks
    assert f"elv:pick:{world['e21'].id}" in callbacks
    assert f"elv:pick:{world['e22'].id}" in callbacks
    assert f"elv:pick:{world['e12_raw'].id}" not in callbacks
    texts = [b.text for row in _last_markup(cb).inline_keyboard for b in row]
    assert get_text("requests.elevator.pick_button", language="ru",
                    entrance=2, elevator=1) in texts


@pytest.mark.asyncio
async def test_apartment_without_entrance_shows_pick_keyboard(world):
    _, state = await _pick_address(world, "apt_no_entrance")
    assert state.state is RequestStates.elevator_pick


@pytest.mark.asyncio
async def test_building_level_address_shows_pick_keyboard(world):
    _, state = await _pick_address(world, "with_lifts", atype="building")
    assert state.state is RequestStates.elevator_pick
    assert state.data["elevator_building_id"] == world["with_lifts"].id


# ── 3. дом без лифтов → Р11: сообщение и возврат к категории ─────────────


@pytest.mark.asyncio
async def test_building_without_elevators_returns_to_category(world):
    cb, state = await _pick_address(world, "apt_no_lifts")
    assert state.state is RequestStates.category
    assert "elevator_id" not in state.data
    assert get_text("requests.elevator.none_in_building", language="ru") in _answers(cb)


def _stored_board_config(phone: str) -> dict:
    """Строка board_config в РЕАЛЬНОЙ форме (contacts.dispatch_phone), через схему API."""
    from uk_management_bot.api.board_config.defaults import DEFAULT_BOARD_CONFIG
    from uk_management_bot.api.board_config.schemas import StoredBoardConfigData

    raw = copy.deepcopy(DEFAULT_BOARD_CONFIG)
    raw["contacts"]["dispatch_phone"] = phone
    return StoredBoardConfigData.model_validate(raw).model_dump()


@pytest.mark.asyncio
async def test_building_without_elevators_mentions_dispatch_phone(world, db):
    db.add(BoardConfig(id=1, data=_stored_board_config("+998 71 200-00-00")))
    db.commit()
    cb, state = await _pick_address(world, "apt_no_lifts")
    assert state.state is RequestStates.category
    expected = get_text("requests.elevator.none_in_building_phone", language="ru",
                        phone="+998 71 200-00-00")
    assert expected in _answers(cb)


@pytest.mark.asyncio
async def test_dispatch_phone_is_html_escaped(world, db):
    db.add(BoardConfig(id=1, data=_stored_board_config("<b>+998</b>")))
    db.commit()
    cb, _ = await _pick_address(world, "apt_no_lifts")
    texts = "\n".join(_answers(cb))
    assert "&lt;b&gt;+998&lt;/b&gt;" in texts and "<b>+998</b>" not in texts


@pytest.mark.asyncio
async def test_default_board_config_phone_is_shown_as_stored(world, db):
    """Сид миграции хранит дефолт целиком — читаем ровно то, что лежит в contacts."""
    from uk_management_bot.api.board_config.defaults import DEFAULT_BOARD_CONFIG

    db.add(BoardConfig(id=1, data=copy.deepcopy(DEFAULT_BOARD_CONFIG)))
    db.commit()
    cb, _ = await _pick_address(world, "apt_no_lifts")
    assert DEFAULT_BOARD_CONFIG["contacts"]["dispatch_phone"] in "\n".join(_answers(cb))


# ── 4. двор → укажите дом ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_yard_address_asks_for_building(world):
    cb, state = await _pick_address(world, "yard", atype="yard")
    assert state.state is RequestStates.address
    assert get_text("requests.elevator.need_building", language="ru") in _answers(cb)
    # клавиатура адресов переотправлена
    assert any(c.startswith("addr:") for c in _callbacks(_last_markup(cb)))


# ── 5. «работает?» ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_operational_no_saves_false_and_moves_to_description(world):
    cb = _callback("elv:op:0")
    state = FakeState({"category": "elevator", "elevator_id": world["e11"].id},
                      RequestStates.elevator_operational)
    await resident.handle_elevator_operational(cb, state)
    assert state.data["elevator_operational"] is False
    assert state.state is RequestStates.description
    assert get_text("requests.description", language="ru") in _answers(cb)


@pytest.mark.asyncio
async def test_operational_yes_saves_true(world):
    cb = _callback("elv:op:1")
    state = FakeState({"category": "elevator", "elevator_id": world["e11"].id},
                      RequestStates.elevator_operational)
    await resident.handle_elevator_operational(cb, state)
    assert state.data["elevator_operational"] is True


@pytest.mark.asyncio
async def test_pick_under_repair_shows_soft_hint_before_question(world):
    cb = _callback(f"elv:pick:{world['e21'].id}")
    state = FakeState({"category": "elevator", "elevator_building_id": world["with_lifts"].id},
                      RequestStates.elevator_pick)
    await resident.handle_elevator_pick(cb, state)
    assert state.state is RequestStates.elevator_operational
    assert state.data["elevator_id"] == world["e21"].id
    hint = [t for t in _answers(cb) if get_text("elevators.status.under_repair", language="ru") in t]
    assert hint, "подсказка о работах по лифту не показана"
    assert "01.09.2026" in hint[0]


# ── 6. отказы elv:pick ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pick_foreign_elevator_rejected(world):
    cb = _callback(f"elv:pick:{world['foreign'].id}")
    state = FakeState({"category": "elevator", "elevator_building_id": world["with_lifts"].id},
                      RequestStates.elevator_pick)
    await resident.handle_elevator_pick(cb, state)
    assert state.state is RequestStates.elevator_pick
    assert "elevator_id" not in state.data
    cb.answer.assert_awaited()
    assert cb.answer.await_args.args[0] == get_text("requests.elevator.invalid_choice", language="ru")


@pytest.mark.asyncio
async def test_pick_uncommissioned_elevator_rejected(world):
    cb = _callback(f"elv:pick:{world['e12_raw'].id}")
    state = FakeState({"category": "elevator", "elevator_building_id": world["with_lifts"].id},
                      RequestStates.elevator_pick)
    await resident.handle_elevator_pick(cb, state)
    assert "elevator_id" not in state.data


@pytest.mark.asyncio
async def test_pick_by_non_applicant_rejected(world):
    cb = _callback(f"elv:pick:{world['e11'].id}", tg_id=STRANGER_TG_ID)
    state = FakeState({"category": "elevator", "elevator_building_id": world["with_lifts"].id},
                      RequestStates.elevator_pick)
    await resident.handle_elevator_pick(cb, state)
    assert "elevator_id" not in state.data
    assert cb.answer.await_args.args[0] == get_text("requests.applicant_only", language="ru")


@pytest.mark.asyncio
async def test_pick_garbage_id_rejected_without_db(world):
    cb = _callback("elv:pick:abc")
    state = FakeState({"category": "elevator", "elevator_building_id": world["with_lifts"].id},
                      RequestStates.elevator_pick)
    await resident.handle_elevator_pick(cb, state)
    assert "elevator_id" not in state.data
    cb.answer.assert_awaited()


# ── 7. сводка и ошибка сохранения ────────────────────────────────────────


@pytest.mark.asyncio
async def test_confirmation_summary_has_elevator_line(world):
    message = MagicMock()
    message.answer = AsyncMock()
    message.from_user.id = TG_ID
    state = FakeState({
        "category": "elevator", "address": "ул. Лифтовая, 1, кв. 7", "description": "Не едет",
        "urgency": "high", "media_files": [], "elevator_id": world["e11"].id,
        "elevator_entrance": 1, "elevator_number": 1, "elevator_operational": False,
    })
    await create.show_confirmation(message, state)
    text = message.answer.await_args.args[0]
    line = get_text("requests.elevator.summary_line", language="ru", entrance=1, elevator=1,
                    operational=get_text("requests.elevator.operational_no", language="ru"))
    assert line in text
    # строка лифта стоит внутри сводки, до финального призыва подтвердить
    assert text.index(line) < text.rindex("\n\n")


@pytest.mark.asyncio
async def test_summary_without_elevator_unchanged():
    message = MagicMock()
    message.answer = AsyncMock()
    message.from_user.id = TG_ID
    state = FakeState({"category": "electricity", "address": "a", "description": "d",
                       "urgency": "low", "media_files": []})
    await create.show_confirmation(message, state)
    assert "🛗" not in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_confirm_save_failed_shows_elevator_error(world):
    cb = _callback("confirm_yes")
    state = FakeState({"category": "elevator", "urgency": "low", "elevator_id": world["e11"].id,
                       "elevator_operational": True})
    with patch.object(create_callbacks, "save_request", AsyncMock(return_value=None)), \
         patch.object(create_callbacks, "get_user_contextual_keyboard", AsyncMock(return_value=None)):
        await create_callbacks.handle_confirmation(cb, state)
    expected = get_text("requests.elevator.error_generic", language="ru")
    assert expected in _answers(cb)
    assert cb.answer.await_args.args[0] == expected


@pytest.mark.asyncio
async def test_confirm_save_failed_other_category_keeps_generic_error(world):
    cb = _callback("confirm_yes")
    state = FakeState({"category": "electricity", "urgency": "low"})
    with patch.object(create_callbacks, "save_request", AsyncMock(return_value=None)), \
         patch.object(create_callbacks, "get_user_contextual_keyboard", AsyncMock(return_value=None)):
        await create_callbacks.handle_confirmation(cb, state)
    assert get_text("errors.request_save_failed", language="ru") in _answers(cb)


# ── брошенный лифтовой поток не протекает в новую заявку ─────────────────


@pytest.mark.asyncio
async def test_stale_elevator_keys_cleared_on_restart_and_recategory(world, db):
    """Брошенная лифтовая заявка → новая заявка другой категории → в save_request_sync
    уходит elevator_id=None (иначе Р11 «лифт указан не для лифта» валил бы сохранение)."""
    stale = {
        "category": "elevator", "elevator_id": world["e11"].id, "elevator_operational": False,
        "elevator_entrance": 1, "elevator_number": 1, "elevator_building_id": world["with_lifts"].id,
    }
    # 1) повторный вход «Создать заявку»
    message = MagicMock()
    message.text = "x"
    message.from_user.id = TG_ID
    message.answer = AsyncMock()
    state = FakeState(stale, RequestStates.confirm)
    with patch.object(create, "_load_applicant_gate", lambda s, tg: "ok"):
        await create.start_request_creation(message, state)
    assert not any(k in state.data for k in mod.ELEVATOR_DATA_KEYS)
    assert state.state is RequestStates.category

    # 2) повторный выбор категории поверх хвоста
    state = FakeState(stale, RequestStates.category)
    cb = _callback("category_electricity")
    await create_callbacks.handle_category_selection(cb, state)
    assert state.data["category"] == "electricity"
    assert not any(k in state.data for k in mod.ELEVATOR_DATA_KEYS)

    # 3) итоговые data доходят до save_request_sync без лифта
    data = {**state.data, "address_type": "apartment", "address_id": world["apt_single"].id,
            "description": "Нет света", "urgency": "low", "media_files": []}
    with patch("uk_management_bot.services.dispatch.auto_dispatch_new_request_sync", MagicMock()):
        saved = create.save_request_sync(data, TG_ID, db, source="bot", role="applicant")
    assert saved is not None
    from uk_management_bot.database.models.request import Request

    req = db.query(Request).filter(Request.request_number == saved[0]).one()
    assert req.elevator_id is None and req.elevator_operational is None


# ── локали: ключи есть в обоих языках ────────────────────────────────────


def _lookup(locale: dict, dotted: str):
    """Ключ ровно в ЭТОЙ локали (get_text молча падает на ru — фолбэк спрятал бы дыру)."""
    node = locale
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


@pytest.mark.parametrize("lang", ["ru", "uz"])
def test_locale_keys_present(lang):
    keys = [
        "requests.elevator.pick_prompt", "requests.elevator.pick_button",
        "requests.elevator.picked", "requests.elevator.need_building",
        "requests.elevator.none_in_building", "requests.elevator.none_in_building_phone",
        "requests.elevator.works_hint", "requests.elevator.operational_prompt",
        "requests.elevator.operational_yes_button", "requests.elevator.operational_no_button",
        "requests.elevator.operational_yes", "requests.elevator.operational_no",
        "requests.elevator.operational_saved", "requests.elevator.summary_line",
        "requests.elevator.use_buttons", "requests.elevator.invalid_choice",
        "requests.elevator.error_generic",
        "elevators.status.working", "elevators.status.not_working",
        "elevators.status.under_repair", "elevators.status.maintenance",
    ]
    locale = load_locale(lang)
    for key in keys:
        assert _lookup(locale, key) is not None, (lang, key)
