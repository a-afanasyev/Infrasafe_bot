"""Групповой приём, категория «лифт» (Ф4b, T9): фаза выбора лифта после «Да».

Хендлер зовётся напрямую (канон AUD3-37: БД через ``_db``-seam на sqlite);
Redis-pending подменён dict-фейком (реально сохранённый payload и TTL видны
ассертам), save_request — AsyncMock. Контракты: флаг/категория — no-op; один
лифт в подъезде автора → сразу «работает?»; несколько → кнопки
``gint:elv:{id}``; двор → выбор дома ``gint:bld:{n}``; дом без лифтов —
сообщение, заявки нет; отвечает только автор; единый дедлайн (таймер, TTL,
ленивая проверка); «нет» → save_request с elevator_operational=False.
"""
import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import uk_management_bot.handlers.group_intake as gi
import uk_management_bot.handlers.group_intake_elevator as gie
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models import (
    Apartment,
    Building,
    MonitoredGroup,
    UserApartment,
    Yard,
)
from uk_management_bot.database.models.elevator import Elevator
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services.elevator_service import generate_public_code

CHAT_ID = -100700
PROMPT_ID = 777
AUTHOR_ID = 111
STRANGER_ID = 999
START = 1_800_000_000.0  # фиксированное «сейчас» для дедлайна
KEY = (CHAT_ID, PROMPT_ID)

REAL_SCHEDULE = gie.schedule_elevator_timeout


# ───────────────────────── фикстуры ─────────────────────────


class FakePending:
    """Dict-backed Redis-pending: get/pop/store с записью TTL каждого store."""

    def __init__(self):
        self.store: dict = {}
        self.stores: list = []  # (chat_id, message_id, payload, ttl)
        self.pops = 0
        self.store_ok = True

    def seed(self, candidate, key=KEY):
        self.store[key] = dict(candidate)

    async def get_candidate(self, chat_id, message_id):
        candidate = self.store.get((chat_id, message_id))
        return dict(candidate) if candidate is not None else None

    async def pop_candidate(self, chat_id, message_id):
        self.pops += 1
        return self.store.pop((chat_id, message_id), None)

    async def store_candidate(self, chat_id, message_id, payload, *, ttl=3600):
        if not self.store_ok:
            return False
        self.stores.append((chat_id, message_id, dict(payload), ttl))
        self.store[(chat_id, message_id)] = {"v": 1, **payload}
        return True

    @property
    def last(self):
        return self.stores[-1][2]

    @property
    def last_ttl(self):
        return self.stores[-1][3]


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
def env(monkeypatch):
    monkeypatch.setattr(settings, "GROUP_INTAKE_ENABLED", True)
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", True)
    monkeypatch.setattr(settings, "BOT_USERNAME", "test_bot")
    fake = FakePending()
    mocks = SimpleNamespace(
        pending=fake,
        save_request=AsyncMock(return_value="260906-001"),
        schedule_timeout=MagicMock(),
        clock=SimpleNamespace(now=START),
    )
    monkeypatch.setattr(gi.pending, "get_candidate", fake.get_candidate)
    monkeypatch.setattr(gi.pending, "pop_candidate", fake.pop_candidate)
    monkeypatch.setattr(gi.pending, "store_candidate", fake.store_candidate)
    monkeypatch.setattr(
        "uk_management_bot.handlers.requests.create.save_request", mocks.save_request
    )
    monkeypatch.setattr(gie, "schedule_elevator_timeout", mocks.schedule_timeout)
    monkeypatch.setattr(gie, "_now", lambda: mocks.clock.now)
    gie._timeout_tasks.clear()
    return mocks


def _elevator(building, entrance, number, *, commissioned=True, status="working"):
    return Elevator(
        building_id=building.id, entrance_number=entrance, elevator_number=number,
        passport_number=f"P-{entrance}{number}", manufacturer="OTIS",
        serial_number=f"S-{building.id}-{entrance}{number}", public_code=generate_public_code(),
        is_commissioned=commissioned,
        commissioned_at=date(2020, 1, 1) if commissioned else None,
        current_status=status if commissioned else None,
    )


@pytest.fixture()
def world(db):
    """Двор с тремя домами: A — три лифта (подъезд 1: один; подъезд 2: два),
    B — без лифтов, C — один лифт. Автор — approved applicant с телефоном."""
    yard = Yard(name="Двор Лифтовый", is_active=True)
    a = Building(address="ул. Лифтовая, 1", yard=yard, is_active=True)
    b = Building(address="ул. Пешая, 2", yard=yard, is_active=True)
    c = Building(address="ул. Лифтовая, 3", yard=yard, is_active=True)
    apt_e1 = Apartment(apartment_number="7", building=a, entrance=1, is_active=True)
    apt_e2 = Apartment(apartment_number="70", building=a, entrance=2, is_active=True)
    apt_noent = Apartment(apartment_number="9", building=a, is_active=True)
    apt_b = Apartment(apartment_number="1", building=b, entrance=1, is_active=True)
    apt_c = Apartment(apartment_number="5", building=c, entrance=1, is_active=True)
    user = User(telegram_id=AUTHOR_ID, roles='["applicant"]', active_role="applicant",
                status="approved", phone="+998901112233", language="ru")
    db.add_all([yard, a, b, c, apt_e1, apt_e2, apt_noent, apt_b, apt_c, user,
                MonitoredGroup(chat_id=CHAT_ID, title="Дом", kind="residents", is_active=True)])
    db.commit()
    lifts = [
        _elevator(a, 1, 1), _elevator(a, 2, 1), _elevator(a, 2, 2),
        _elevator(a, 2, 3, commissioned=False), _elevator(c, 1, 1, status="under_repair"),
    ]
    db.add_all(lifts)
    db.commit()
    return SimpleNamespace(
        yard=yard, a=a, b=b, c=c, apt_e1=apt_e1, apt_e2=apt_e2, apt_noent=apt_noent,
        apt_b=apt_b, apt_c=apt_c, user=user,
        lift_a11=lifts[0], lift_a21=lifts[1], lift_a22=lifts[2], lift_raw=lifts[3],
        lift_c=lifts[4],
    )


def approve(db, world, *apartments):
    for index, apartment in enumerate(apartments):
        db.add(UserApartment(
            user_id=world.user.id, apartment_id=apartment.id, status="approved",
            is_primary=index == 0,
        ))
    db.commit()


def make_candidate(address, **overrides):
    candidate = {
        "v": 1,
        "kind": "residents",
        "author_id": AUTHOR_ID,
        "source_message_id": 42,
        "text": "Лифт застрял между этажами",
        "truncated": False,
        "category": "elevator",
        "category_source": "llm",
        "urgency": "high",
        "confidence": 0.9,
        "location_scope": "building",
        "photo_file_id": None,
        "selected_address": address,
        "lang": "ru",
    }
    candidate.update(overrides)
    return candidate


def phased(address, phase, **fields):
    """Кандидат уже в фазе лифта с живым дедлайном."""
    return make_candidate(
        address, phase=phase, phase_deadline=START + gie.ELEVATOR_ANSWER_TIMEOUT, **fields
    )


def apartment_address(apartment):
    return {"type": "apartment", "id": apartment.id,
            "label_public": "дом, ваша квартира", "label_full": "дом, кв."}


def yard_address(yard):
    return {"type": "yard", "id": yard.id, "label_public": yard.name, "label_full": yard.name}


def building_address(building):
    return {"type": "building", "id": building.id,
            "label_public": building.address, "label_full": building.address}


def make_callback(action="yes", from_id=AUTHOR_ID):
    return SimpleNamespace(
        data=f"gint:{action}",
        from_user=SimpleNamespace(id=from_id, language_code="ru"),
        message=SimpleNamespace(
            chat=SimpleNamespace(id=CHAT_ID, type="supergroup"),
            message_id=PROMPT_ID,
            edit_text=AsyncMock(),
        ),
        answer=AsyncMock(),
    )


def make_bot():
    return SimpleNamespace(edit_message_text=AsyncMock())


async def run_cb(callback, db, bot=None):
    await gi.group_intake_callback(callback, bot=bot or make_bot(), _db=db)


async def press(action, db, from_id=AUTHOR_ID, bot=None):
    callback = make_callback(action, from_id=from_id)
    await run_cb(callback, db, bot)
    return callback


def buttons(callback):
    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def button_texts(callback):
    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    return [b.text for row in markup.inline_keyboard for b in row]


def edited_text(callback):
    return callback.message.edit_text.await_args.args[0]


# ───────────────────────── регресс: путь не меняется ─────────────────────────


async def test_other_category_saves_immediately(env, db, world):
    approve(db, world, world.apt_e1)
    env.pending.seed(make_candidate(apartment_address(world.apt_e1), category="electricity"))
    await press("yes", db)

    env.save_request.assert_awaited_once()
    assert env.pending.stores == []
    assert "elevator_id" not in env.save_request.await_args.args[0]


async def test_flag_off_saves_immediately(monkeypatch, env, db, world):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", False)
    approve(db, world, world.apt_e1)
    env.pending.seed(make_candidate(apartment_address(world.apt_e1)))
    await press("yes", db)

    env.save_request.assert_awaited_once()
    assert env.pending.stores == []
    env.schedule_timeout.assert_not_called()


# ───────────────────────── «Да» → фаза лифта ─────────────────────────


async def test_single_elevator_in_author_entrance_asks_operational(env, db, world):
    approve(db, world, world.apt_e1)
    env.pending.seed(make_candidate(apartment_address(world.apt_e1)))
    callback = await press("yes", db)

    env.save_request.assert_not_awaited()
    payload = env.pending.last
    assert payload["phase"] == gie.PHASE_OPERATIONAL
    assert payload["elevator_id"] == world.lift_a11.id
    assert payload["elevator_building_id"] == world.a.id
    assert payload["elevator_entrance"] == 1 and payload["elevator_number"] == 1
    assert payload["phase_deadline"] == int(START) + gie.ELEVATOR_ANSWER_TIMEOUT
    assert "v" not in payload
    assert env.pending.last_ttl == gie.ELEVATOR_PHASE_TTL
    assert "работает" in edited_text(callback)
    assert buttons(callback) == ["gint:op:1", "gint:op:0"]
    env.schedule_timeout.assert_called_once()


async def test_many_elevators_offer_pick_buttons(env, db, world):
    approve(db, world, world.apt_noent)
    env.pending.seed(make_candidate(apartment_address(world.apt_noent)))
    callback = await press("yes", db)

    payload = env.pending.last
    assert payload["phase"] == gie.PHASE_PICK
    assert payload["elevator_building_id"] == world.a.id
    # только введённые в эксплуатацию (lift_raw не предлагается)
    assert buttons(callback) == [
        f"gint:elv:{world.lift_a11.id}",
        f"gint:elv:{world.lift_a21.id}",
        f"gint:elv:{world.lift_a22.id}",
    ]
    assert "Подъезд 2 · лифт 2" in button_texts(callback)
    env.schedule_timeout.assert_called_once()


async def test_entrance_with_two_elevators_offers_pick(env, db, world):
    approve(db, world, world.apt_e2)
    env.pending.seed(make_candidate(apartment_address(world.apt_e2)))
    await press("yes", db)
    assert env.pending.last["phase"] == gie.PHASE_PICK


async def test_building_without_elevators_edits_and_creates_nothing(env, db, world):
    approve(db, world, world.apt_b)
    env.pending.seed(make_candidate(apartment_address(world.apt_b)))
    callback = await press("yes", db)

    env.save_request.assert_not_awaited()
    assert env.pending.stores == [] and env.pending.store == {}
    env.schedule_timeout.assert_not_called()
    assert "не заведены" in edited_text(callback)
    assert "reply_markup" not in callback.message.edit_text.await_args.kwargs


async def test_yard_level_with_several_buildings_asks_building(env, db, world):
    approve(db, world, world.apt_e1, world.apt_c)
    env.pending.seed(make_candidate(yard_address(world.yard), location_scope="yard"))
    callback = await press("yes", db)

    env.save_request.assert_not_awaited()
    payload = env.pending.last
    assert payload["phase"] == gie.PHASE_BUILDING
    assert [o["id"] for o in payload["building_options"]] == [world.apt_e1.id, world.apt_c.id]
    assert payload["selected_address"] == yard_address(world.yard)
    assert buttons(callback) == ["gint:bld:0", "gint:bld:1"]
    assert "дом" in edited_text(callback).lower()
    assert "нет в списке" not in edited_text(callback)


async def test_yard_level_with_single_building_resolves_it(env, db, world):
    approve(db, world, world.apt_c)
    env.pending.seed(make_candidate(yard_address(world.yard), location_scope="yard"))
    callback = await press("yes", db)

    payload = env.pending.last
    assert payload["phase"] == gie.PHASE_OPERATIONAL
    assert payload["selected_address"]["type"] == "apartment"
    assert payload["selected_address"]["id"] == world.apt_c.id
    assert payload["elevator_id"] == world.lift_c.id
    # мягкая подсказка о ремонте/ТО
    assert "работы" in edited_text(callback) and "В ремонте" in edited_text(callback)


async def test_store_failure_after_yes_shows_expired(env, db, world):
    approve(db, world, world.apt_e1)
    env.pending.seed(make_candidate(apartment_address(world.apt_e1)))
    env.pending.store_ok = False
    callback = await press("yes", db)
    assert "устарело" in edited_text(callback)
    env.schedule_timeout.assert_not_called()


# ───────────────────────── двор: staff и кап списка ─────────────────────────


def test_staff_yard_lists_directory_buildings(db, world):
    """Staff: дома двора из справочника, тип building, по адресу."""
    step = gie.load_group_elevator_step_sync(
        db, {"kind": "staff", "selected_address": yard_address(world.yard)}, None
    )
    assert step.verdict == "building"
    assert [(o["type"], o["id"]) for o in step.building_options] == [
        ("building", world.a.id), ("building", world.c.id), ("building", world.b.id),
    ]


def test_staff_yard_respects_cap(db, world, monkeypatch):
    monkeypatch.setattr(gie, "_MAX_BUILDING_OPTIONS", 2)
    step = gie.load_group_elevator_step_sync(
        db, {"kind": "staff", "selected_address": yard_address(world.yard)}, None
    )
    assert len(step.building_options) == 2


def test_resident_yard_without_user_id_has_no_options(db, world):
    step = gie.load_group_elevator_step_sync(
        db, make_candidate(yard_address(world.yard)), None
    )
    assert step.verdict == "building" and step.building_options == ()


async def test_capped_building_list_adds_text_hint(env, db, world, monkeypatch):
    monkeypatch.setattr(gie, "_MAX_BUILDING_OPTIONS", 2)
    options = (building_address(world.a), building_address(world.c))
    step = gie.GroupElevatorStep("building", yard_address(world.yard), building_options=options)
    callback = make_callback()
    waiting = await gie._apply_step(callback, make_candidate(yard_address(world.yard)), step, "ru")
    assert waiting is True
    assert "нет в списке" in edited_text(callback)
    assert buttons(callback) == ["gint:bld:0", "gint:bld:1"]


# ───────────────────────── кнопка дома ─────────────────────────


def building_options(world):
    return [
        {"type": "apartment", "id": world.apt_e1.id, "label_public": "ул. Лифтовая, 1",
         "label_full": "ул. Лифтовая, 1"},
        {"type": "apartment", "id": world.apt_c.id, "label_public": "ул. Лифтовая, 3",
         "label_full": "ул. Лифтовая, 3"},
    ]


async def test_building_pick_updates_address_and_continues(env, db, world):
    approve(db, world, world.apt_e1, world.apt_c)
    env.pending.seed(phased(yard_address(world.yard), gie.PHASE_BUILDING,
                            building_options=building_options(world)))
    callback = await press("bld:1", db)

    callback.answer.assert_awaited_once_with()
    payload = env.pending.last
    assert payload["selected_address"]["id"] == world.apt_c.id
    assert payload["phase"] == gie.PHASE_OPERATIONAL
    assert payload["building_options"] is None
    env.schedule_timeout.assert_not_called()  # таймер поставлен на «Да», не переставляется


@pytest.mark.parametrize("action", ["bld:7", "bld:-1", "bld:x"])
async def test_building_pick_invalid_index_is_noop(env, db, world, action):
    env.pending.seed(phased(yard_address(world.yard), gie.PHASE_BUILDING,
                            building_options=building_options(world)))
    callback = await press(action, db)
    assert env.pending.stores == []
    callback.message.edit_text.assert_not_awaited()


async def test_building_pick_in_wrong_phase_is_noop(env, db, world):
    env.pending.seed(phased(apartment_address(world.apt_e1), gie.PHASE_PICK,
                            elevator_building_id=world.a.id,
                            building_options=building_options(world)))
    await press("bld:0", db)
    assert env.pending.stores == []


# ───────────────────────── кнопка лифта ─────────────────────────


def pick_candidate(world, **overrides):
    return phased(apartment_address(world.apt_noent), gie.PHASE_PICK,
                  elevator_building_id=world.a.id, **overrides)


async def test_elevator_pick_stores_and_asks_operational(env, db, world):
    env.pending.seed(pick_candidate(world))
    callback = await press(f"elv:{world.lift_a22.id}", db)

    callback.answer.assert_awaited_once_with()
    payload = env.pending.last
    assert payload["phase"] == gie.PHASE_OPERATIONAL
    assert payload["elevator_id"] == world.lift_a22.id
    assert payload["elevator_entrance"] == 2 and payload["elevator_number"] == 2
    assert "работает" in edited_text(callback)
    assert buttons(callback) == ["gint:op:1", "gint:op:0"]


@pytest.mark.parametrize("bad", ["lift_c", "lift_raw", "missing"])
async def test_elevator_pick_rejects_foreign_raw_and_unknown(env, db, world, bad):
    """Лифт другого дома / не введённый / несуществующий — отклонён сервером."""
    bad_id = getattr(world, bad).id if bad != "missing" else 999999
    env.pending.seed(pick_candidate(world))
    callback = await press(f"elv:{bad_id}", db)
    assert env.pending.stores == []
    callback.message.edit_text.assert_not_awaited()


async def test_elevator_pick_garbage_is_noop(env, db, world):
    env.pending.seed(pick_candidate(world))
    await press("elv:abc", db)
    assert env.pending.stores == []


async def test_elevator_pick_in_wrong_phase_is_noop(env, db, world):
    env.pending.seed(phased(apartment_address(world.apt_e1), gie.PHASE_OPERATIONAL,
                            elevator_building_id=world.a.id, elevator_id=world.lift_a11.id))
    await press(f"elv:{world.lift_a22.id}", db)
    assert env.pending.stores == []


# ───────────────────────── только автор ─────────────────────────


async def test_stranger_pressing_elevator_button_gets_alert(env, db, world):
    env.pending.seed(pick_candidate(world))
    callback = await press(f"elv:{world.lift_a11.id}", db, from_id=STRANGER_ID)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert") is True
    assert "автор" in callback.answer.await_args.args[0]
    assert env.pending.stores == [] and env.pending.pops == 0


async def test_staff_colleague_cannot_answer_operational(env, db, world):
    """В staff-группе коллега подтверждает «Да», но про лифт отвечает автор."""
    db.add(User(telegram_id=STRANGER_ID, roles='["manager"]', active_role="manager",
                status="approved", phone="+998901112299", language="ru"))
    db.commit()
    env.pending.seed(phased(building_address(world.a), gie.PHASE_OPERATIONAL, kind="staff",
                            elevator_building_id=world.a.id, elevator_id=world.lift_a11.id))
    callback = await press("op:1", db, from_id=STRANGER_ID)

    assert callback.answer.await_args.kwargs.get("show_alert") is True
    assert env.pending.pops == 0
    env.save_request.assert_not_awaited()


# ───────────────────────── crafted addr/cat/yes в фазе лифта ─────────────────────────


def staff_phase_candidate(world):
    return phased(building_address(world.a), gie.PHASE_PICK, kind="staff",
                  elevator_building_id=world.a.id,
                  address_options=[building_address(world.a), building_address(world.c)])


async def test_crafted_cat_in_elevator_phase_is_noop(env, db, world):
    env.pending.seed(staff_phase_candidate(world))
    for action in ("cat", "cat:plumbing", "cat:back"):
        callback = await press(action, db)
        callback.message.edit_text.assert_not_awaited()
    assert env.pending.stores == []
    assert env.pending.store[KEY]["phase"] == gie.PHASE_PICK


async def test_crafted_addr_in_elevator_phase_is_noop(env, db, world):
    env.pending.seed(staff_phase_candidate(world))
    callback = await press("addr:1", db)
    callback.message.edit_text.assert_not_awaited()
    assert env.pending.stores == []
    assert env.pending.store[KEY]["phase"] == gie.PHASE_PICK


async def test_crafted_yes_in_elevator_phase_is_noop(env, db, world):
    env.pending.seed(operational_candidate(world))
    callback = await press("yes", db)
    assert env.pending.pops == 0
    env.save_request.assert_not_awaited()
    callback.message.edit_text.assert_not_awaited()


# ───────────────────────── «работает?» → заявка ─────────────────────────


def operational_candidate(world, **overrides):
    return phased(apartment_address(world.apt_e1), gie.PHASE_OPERATIONAL,
                  elevator_building_id=world.a.id, elevator_id=world.lift_a11.id,
                  elevator_entrance=1, elevator_number=1, **overrides)


async def test_operational_no_creates_request_with_elevator_fields(env, db, world):
    approve(db, world, world.apt_e1)
    env.pending.seed(operational_candidate(world))
    callback = await press("op:0", db)

    callback.answer.assert_awaited_once_with()
    assert env.pending.pops == 1 and env.pending.store == {}
    env.save_request.assert_awaited_once()
    data, owner_tg_id = env.save_request.await_args.args[:2]
    assert owner_tg_id == AUTHOR_ID
    assert env.save_request.await_args.kwargs["role"] == "applicant"
    assert data["elevator_id"] == world.lift_a11.id
    assert data["elevator_operational"] is False
    assert data["category"] == "elevator"
    assert data["address_type"] == "apartment" and data["address_id"] == world.apt_e1.id
    assert "260906-001" in edited_text(callback)


async def test_operational_yes_passes_true(env, db, world):
    approve(db, world, world.apt_e1)
    env.pending.seed(operational_candidate(world))
    await press("op:1", db)
    assert env.save_request.await_args.args[0]["elevator_operational"] is True


async def test_operational_double_press_second_is_expired(env, db, world):
    approve(db, world, world.apt_e1)
    env.pending.seed(operational_candidate(world))
    first = await press("op:1", db)
    second = await press("op:1", db)  # кандидат уже снят GETDEL первого нажатия
    env.save_request.assert_awaited_once()
    assert "260906-001" in edited_text(first)
    second.answer.assert_awaited_once()
    assert second.answer.await_args.kwargs.get("show_alert") is True
    second.message.edit_text.assert_not_awaited()


async def test_operational_getdel_race_shows_expired(env, db, world, monkeypatch):
    """GET увидел кандидата, GETDEL уже пуст (параллельное нажатие/таймер)."""
    approve(db, world, world.apt_e1)
    env.pending.seed(operational_candidate(world))
    monkeypatch.setattr(gi.pending, "pop_candidate", AsyncMock(return_value=None))
    callback = await press("op:1", db)
    env.save_request.assert_not_awaited()
    assert "устарело" in edited_text(callback)


async def test_operational_garbage_and_wrong_phase_are_noop(env, db, world):
    env.pending.seed(operational_candidate(world))
    await press("op:2", db)
    env.pending.seed(pick_candidate(world))
    await press("op:1", db)
    assert env.pending.pops == 0
    env.save_request.assert_not_awaited()


# ───────────────────────── единый дедлайн ─────────────────────────


async def test_step_at_minute_29_does_not_extend_window(env, db, world):
    approve(db, world, world.apt_noent, world.apt_c)
    env.pending.seed(make_candidate(yard_address(world.yard), location_scope="yard"))
    await press("yes", db)
    assert env.pending.last_ttl == gie.ELEVATOR_ANSWER_TIMEOUT + gie.TTL_GRACE

    env.clock.now = START + 29 * 60
    await press("bld:0", db)  # дом A → выбор лифта
    assert env.pending.last["phase"] == gie.PHASE_PICK
    assert env.pending.last["phase_deadline"] == int(START) + gie.ELEVATOR_ANSWER_TIMEOUT
    assert env.pending.last_ttl == 60 + gie.TTL_GRACE

    env.clock.now = START + 29 * 60 + 30
    await press(f"elv:{world.lift_a22.id}", db)
    assert env.pending.last["phase"] == gie.PHASE_OPERATIONAL
    assert env.pending.last_ttl == 30 + gie.TTL_GRACE


async def test_press_after_deadline_is_expired_without_request(env, db, world):
    approve(db, world, world.apt_e1)
    env.pending.seed(operational_candidate(world))
    env.clock.now = START + gie.ELEVATOR_ANSWER_TIMEOUT + 1  # запись ещё жива за счёт grace
    callback = await press("op:0", db)

    env.save_request.assert_not_awaited()
    assert "устарело" in edited_text(callback)
    assert env.pending.store == {}  # кандидат снят


async def test_elevator_pick_after_deadline_is_expired(env, db, world):
    env.pending.seed(pick_candidate(world))
    env.clock.now = START + gie.ELEVATOR_ANSWER_TIMEOUT + 1
    callback = await press(f"elv:{world.lift_a22.id}", db)
    assert "устарело" in edited_text(callback)
    assert env.pending.stores == [] and env.pending.store == {}


# ───────────────────────── таймер ─────────────────────────


async def test_timeout_pops_candidate_and_edits_message(monkeypatch, env, world):
    monkeypatch.setattr(gie, "ELEVATOR_ANSWER_TIMEOUT", 0)
    env.pending.seed(operational_candidate(world))
    bot = make_bot()
    await gie._expire_elevator_prompt(bot, CHAT_ID, PROMPT_ID, "ru")

    assert env.pending.pops == 1 and env.pending.store == {}
    bot.edit_message_text.assert_awaited_once()
    kwargs = bot.edit_message_text.await_args.kwargs
    assert kwargs["chat_id"] == CHAT_ID and kwargs["message_id"] == PROMPT_ID
    assert "не оформлена" in kwargs["text"]
    assert "https://t.me/test_bot" in kwargs["text"]


async def test_timeout_after_answer_does_nothing(monkeypatch, env, world):
    monkeypatch.setattr(gie, "ELEVATOR_ANSWER_TIMEOUT", 0)
    bot = make_bot()  # кандидата нет — заявка создана
    await gie._expire_elevator_prompt(bot, CHAT_ID, PROMPT_ID, "ru")
    assert env.pending.pops == 0
    bot.edit_message_text.assert_not_awaited()


async def test_timeout_ignores_candidate_outside_elevator_phase(monkeypatch, env, world):
    monkeypatch.setattr(gie, "ELEVATOR_ANSWER_TIMEOUT", 0)
    env.pending.seed(make_candidate(apartment_address(world.apt_e1)))
    bot = make_bot()
    await gie._expire_elevator_prompt(bot, CHAT_ID, PROMPT_ID, "ru")
    assert env.pending.pops == 0
    bot.edit_message_text.assert_not_awaited()


async def test_schedule_creates_one_shot_task_in_registry(monkeypatch, env, world):
    monkeypatch.setattr(gie, "ELEVATOR_ANSWER_TIMEOUT", 0)
    task = REAL_SCHEDULE(make_bot(), CHAT_ID, PROMPT_ID, "ru")
    assert gie._timeout_tasks[KEY] is task
    await task
    assert task.exception() is None
    assert KEY not in gie._timeout_tasks  # done-callback вычистил запись


async def test_answer_cancels_timer(monkeypatch, env, db, world):
    monkeypatch.setattr(gie, "schedule_elevator_timeout", REAL_SCHEDULE)
    approve(db, world, world.apt_e1)
    env.pending.seed(make_candidate(apartment_address(world.apt_e1)))
    await press("yes", db)  # auto → «работает?», таймер поставлен
    task = gie._timeout_tasks[KEY]
    assert not task.done()

    await press("op:1", db)
    await asyncio.sleep(0)
    env.save_request.assert_awaited_once()
    assert task.cancelled()
    assert KEY not in gie._timeout_tasks


async def test_no_elevators_after_building_pick_cancels_timer(monkeypatch, env, db, world):
    monkeypatch.setattr(gie, "schedule_elevator_timeout", REAL_SCHEDULE)
    approve(db, world, world.apt_b, world.apt_c)
    env.pending.seed(make_candidate(yard_address(world.yard), location_scope="yard"))
    await press("yes", db)
    task = gie._timeout_tasks[KEY]

    callback = await press("bld:1", db)  # «ул. Пешая, 2» — дом без лифтов
    await asyncio.sleep(0)
    assert "не заведены" in edited_text(callback)
    assert task.cancelled() and env.pending.store == {}


def test_phase_ttl_constants_consistent():
    assert gie.ELEVATOR_PHASE_TTL == gie.ELEVATOR_ANSWER_TIMEOUT + gie.TTL_GRACE


# ───────────────────────── сквозной сценарий ─────────────────────────


async def test_end_to_end_yes_building_elevator_operational_save(env, db, world):
    """«Да» → дом → лифт → «не работает» → save_request с полями лифта;
    каждый шаг читает РЕАЛЬНО сохранённый payload, TTL не растёт."""
    approve(db, world, world.apt_noent, world.apt_c)
    env.pending.seed(make_candidate(yard_address(world.yard), location_scope="yard"))

    step1 = await press("yes", db)
    assert buttons(step1) == ["gint:bld:0", "gint:bld:1"]
    ttl_yes = env.pending.last_ttl
    env.schedule_timeout.assert_called_once()

    env.clock.now = START + 60
    step2 = await press("bld:0", db)  # ул. Лифтовая, 1 → три лифта
    assert env.pending.last["phase"] == gie.PHASE_PICK
    assert env.pending.last["selected_address"]["id"] == world.apt_noent.id
    assert buttons(step2)[0] == f"gint:elv:{world.lift_a11.id}"
    assert env.pending.last_ttl < ttl_yes

    env.clock.now = START + 120
    step3 = await press(f"elv:{world.lift_a21.id}", db)
    assert env.pending.last["phase"] == gie.PHASE_OPERATIONAL
    assert buttons(step3) == ["gint:op:1", "gint:op:0"]
    assert env.pending.last_ttl == ttl_yes - 120

    env.clock.now = START + 180
    step4 = await press("op:0", db)
    env.save_request.assert_awaited_once()
    data, owner_tg_id = env.save_request.await_args.args[:2]
    assert owner_tg_id == AUTHOR_ID
    assert data["elevator_id"] == world.lift_a21.id
    assert data["elevator_operational"] is False
    assert data["address_type"] == "apartment" and data["address_id"] == world.apt_noent.id
    assert data["source_chat_id"] == CHAT_ID
    assert "260906-001" in edited_text(step4)
    assert env.pending.store == {}
    env.schedule_timeout.assert_called_once()  # один таймер на весь поток
