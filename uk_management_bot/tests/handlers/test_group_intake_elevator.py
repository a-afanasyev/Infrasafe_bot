"""Групповой приём, категория «лифт» (Ф4b, T9): фаза выбора лифта после «Да».

Хендлер зовётся напрямую (канон AUD3-37: БД через ``_db``-seam на sqlite),
Redis-pending и save_request — AsyncMock. Контракты: флаг/категория —
no-op; один лифт в подъезде автора → сразу «работает?»; несколько → кнопки
``gint:elv:{id}``; двор → выбор дома ``gint:bld:{n}``; дом без лифтов —
сообщение, заявки нет; отвечает только автор; таймаут — заявки нет,
сообщение отредактировано; «нет» → save_request с elevator_operational=False.
"""
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


# ───────────────────────── фикстуры ─────────────────────────


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
    mocks = SimpleNamespace(
        get_candidate=AsyncMock(return_value=None),
        pop_candidate=AsyncMock(return_value=None),
        store_candidate=AsyncMock(return_value=True),
        save_request=AsyncMock(return_value="260906-001"),
        schedule_timeout=MagicMock(),
    )
    monkeypatch.setattr(gi.pending, "get_candidate", mocks.get_candidate)
    monkeypatch.setattr(gi.pending, "pop_candidate", mocks.pop_candidate)
    monkeypatch.setattr(gi.pending, "store_candidate", mocks.store_candidate)
    monkeypatch.setattr(
        "uk_management_bot.handlers.requests.create.save_request", mocks.save_request
    )
    monkeypatch.setattr(gie, "schedule_elevator_timeout", mocks.schedule_timeout)
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


def approve(db, world, *apartments, primary_first=True):
    for index, apartment in enumerate(apartments):
        db.add(UserApartment(
            user_id=world.user.id, apartment_id=apartment.id, status="approved",
            is_primary=primary_first and index == 0,
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


def apartment_address(apartment):
    return {"type": "apartment", "id": apartment.id,
            "label_public": "дом, ваша квартира", "label_full": "дом, кв."}


def yard_address(yard):
    return {"type": "yard", "id": yard.id, "label_public": yard.name, "label_full": yard.name}


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


def stored(env):
    return env.store_candidate.await_args.args[2]


def buttons(callback):
    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def edited_text(callback):
    return callback.message.edit_text.await_args.args[0]


# ───────────────────────── регресс: путь не меняется ─────────────────────────


async def test_other_category_saves_immediately(env, db, world):
    approve(db, world, world.apt_e1)
    candidate = make_candidate(apartment_address(world.apt_e1), category="electricity")
    env.get_candidate.return_value = candidate
    env.pop_candidate.return_value = candidate
    await run_cb(make_callback("yes"), db)

    env.save_request.assert_awaited_once()
    env.store_candidate.assert_not_awaited()
    data = env.save_request.await_args.args[0]
    assert "elevator_id" not in data


async def test_flag_off_saves_immediately(monkeypatch, env, db, world):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", False)
    approve(db, world, world.apt_e1)
    candidate = make_candidate(apartment_address(world.apt_e1))
    env.get_candidate.return_value = candidate
    env.pop_candidate.return_value = candidate
    await run_cb(make_callback("yes"), db)

    env.save_request.assert_awaited_once()
    env.store_candidate.assert_not_awaited()
    env.schedule_timeout.assert_not_called()


# ───────────────────────── «Да» → фаза лифта ─────────────────────────


async def test_single_elevator_in_author_entrance_asks_operational(env, db, world):
    approve(db, world, world.apt_e1)
    candidate = make_candidate(apartment_address(world.apt_e1))
    env.get_candidate.return_value = candidate
    env.pop_candidate.return_value = candidate
    callback = make_callback("yes")
    await run_cb(callback, db)

    env.save_request.assert_not_awaited()
    payload = stored(env)
    assert payload["phase"] == gie.PHASE_OPERATIONAL
    assert payload["elevator_id"] == world.lift_a11.id
    assert payload["elevator_building_id"] == world.a.id
    assert payload["elevator_entrance"] == 1 and payload["elevator_number"] == 1
    assert "v" not in payload
    assert "работает" in edited_text(callback)
    assert buttons(callback) == ["gint:op:1", "gint:op:0"]
    env.schedule_timeout.assert_called_once()


async def test_many_elevators_offer_pick_buttons(env, db, world):
    approve(db, world, world.apt_noent)
    candidate = make_candidate(apartment_address(world.apt_noent))
    env.get_candidate.return_value = candidate
    env.pop_candidate.return_value = candidate
    callback = make_callback("yes")
    await run_cb(callback, db)

    payload = stored(env)
    assert payload["phase"] == gie.PHASE_PICK
    assert payload["elevator_building_id"] == world.a.id
    # только введённые в эксплуатацию (lift_raw не предлагается)
    assert buttons(callback) == [
        f"gint:elv:{world.lift_a11.id}",
        f"gint:elv:{world.lift_a21.id}",
        f"gint:elv:{world.lift_a22.id}",
    ]
    assert "Подъезд 2 · лифт 2" in [
        b.text for row in callback.message.edit_text.await_args.kwargs["reply_markup"].inline_keyboard
        for b in row
    ]
    env.schedule_timeout.assert_called_once()


async def test_entrance_with_two_elevators_offers_pick(env, db, world):
    approve(db, world, world.apt_e2)
    candidate = make_candidate(apartment_address(world.apt_e2))
    env.get_candidate.return_value = candidate
    env.pop_candidate.return_value = candidate
    callback = make_callback("yes")
    await run_cb(callback, db)
    assert stored(env)["phase"] == gie.PHASE_PICK


async def test_building_without_elevators_edits_and_creates_nothing(env, db, world):
    approve(db, world, world.apt_b)
    candidate = make_candidate(apartment_address(world.apt_b))
    env.get_candidate.return_value = candidate
    env.pop_candidate.return_value = candidate
    callback = make_callback("yes")
    await run_cb(callback, db)

    env.save_request.assert_not_awaited()
    env.store_candidate.assert_not_awaited()
    env.schedule_timeout.assert_not_called()
    assert "не заведены" in edited_text(callback)
    assert "reply_markup" not in callback.message.edit_text.await_args.kwargs


async def test_yard_level_with_several_buildings_asks_building(env, db, world):
    approve(db, world, world.apt_e1, world.apt_c)
    candidate = make_candidate(yard_address(world.yard), location_scope="yard")
    env.get_candidate.return_value = candidate
    env.pop_candidate.return_value = candidate
    callback = make_callback("yes")
    await run_cb(callback, db)

    env.save_request.assert_not_awaited()
    payload = stored(env)
    assert payload["phase"] == gie.PHASE_BUILDING
    assert [o["id"] for o in payload["building_options"]] == [world.apt_e1.id, world.apt_c.id]
    assert payload["selected_address"] == yard_address(world.yard)
    assert buttons(callback) == ["gint:bld:0", "gint:bld:1"]
    assert "дом" in edited_text(callback).lower()


async def test_yard_level_with_single_building_resolves_it(env, db, world):
    approve(db, world, world.apt_c)
    candidate = make_candidate(yard_address(world.yard), location_scope="yard")
    env.get_candidate.return_value = candidate
    env.pop_candidate.return_value = candidate
    callback = make_callback("yes")
    await run_cb(callback, db)

    payload = stored(env)
    assert payload["phase"] == gie.PHASE_OPERATIONAL
    assert payload["selected_address"]["type"] == "apartment"
    assert payload["selected_address"]["id"] == world.apt_c.id
    assert payload["elevator_id"] == world.lift_c.id
    # мягкая подсказка о ремонте/ТО
    assert "работы" in edited_text(callback) and "В ремонте" in edited_text(callback)


async def test_store_failure_after_yes_shows_expired(env, db, world):
    approve(db, world, world.apt_e1)
    candidate = make_candidate(apartment_address(world.apt_e1))
    env.get_candidate.return_value = candidate
    env.pop_candidate.return_value = candidate
    env.store_candidate.return_value = False
    callback = make_callback("yes")
    await run_cb(callback, db)
    assert "устарело" in edited_text(callback)
    env.schedule_timeout.assert_not_called()


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
    env.get_candidate.return_value = make_candidate(
        yard_address(world.yard), phase=gie.PHASE_BUILDING,
        building_options=building_options(world),
    )
    callback = make_callback("bld:1")
    await run_cb(callback, db)

    callback.answer.assert_awaited_once_with()
    payload = stored(env)
    assert payload["selected_address"]["id"] == world.apt_c.id
    assert payload["phase"] == gie.PHASE_OPERATIONAL
    assert payload["building_options"] is None
    env.schedule_timeout.assert_not_called()  # таймер поставлен на «Да», не переставляется


@pytest.mark.parametrize("action", ["bld:7", "bld:-1", "bld:x"])
async def test_building_pick_invalid_index_is_noop(env, db, world, action):
    env.get_candidate.return_value = make_candidate(
        yard_address(world.yard), phase=gie.PHASE_BUILDING,
        building_options=building_options(world),
    )
    callback = make_callback(action)
    await run_cb(callback, db)
    env.store_candidate.assert_not_awaited()
    callback.message.edit_text.assert_not_awaited()


async def test_building_pick_in_wrong_phase_is_noop(env, db, world):
    env.get_candidate.return_value = make_candidate(
        apartment_address(world.apt_e1), phase=gie.PHASE_PICK,
        elevator_building_id=world.a.id, building_options=building_options(world),
    )
    callback = make_callback("bld:0")
    await run_cb(callback, db)
    env.store_candidate.assert_not_awaited()


# ───────────────────────── кнопка лифта ─────────────────────────


def pick_candidate(world, **overrides):
    return make_candidate(
        apartment_address(world.apt_noent), phase=gie.PHASE_PICK,
        elevator_building_id=world.a.id, **overrides,
    )


async def test_elevator_pick_stores_and_asks_operational(env, db, world):
    env.get_candidate.return_value = pick_candidate(world)
    callback = make_callback(f"elv:{world.lift_a22.id}")
    await run_cb(callback, db)

    callback.answer.assert_awaited_once_with()
    payload = stored(env)
    assert payload["phase"] == gie.PHASE_OPERATIONAL
    assert payload["elevator_id"] == world.lift_a22.id
    assert payload["elevator_entrance"] == 2 and payload["elevator_number"] == 2
    assert "работает" in edited_text(callback)
    assert buttons(callback) == ["gint:op:1", "gint:op:0"]


async def test_elevator_pick_rejects_foreign_building_and_raw(env, db, world):
    for bad_id in (world.lift_c.id, world.lift_raw.id, 999999):
        env.store_candidate.reset_mock()
        env.get_candidate.return_value = pick_candidate(world)
        callback = make_callback(f"elv:{bad_id}")
        await run_cb(callback, db)
        env.store_candidate.assert_not_awaited()
        callback.message.edit_text.assert_not_awaited()


async def test_elevator_pick_garbage_is_noop(env, db, world):
    env.get_candidate.return_value = pick_candidate(world)
    callback = make_callback("elv:abc")
    await run_cb(callback, db)
    env.store_candidate.assert_not_awaited()


async def test_elevator_pick_in_wrong_phase_is_noop(env, db, world):
    env.get_candidate.return_value = make_candidate(
        apartment_address(world.apt_e1), phase=gie.PHASE_OPERATIONAL,
        elevator_building_id=world.a.id, elevator_id=world.lift_a11.id,
    )
    callback = make_callback(f"elv:{world.lift_a22.id}")
    await run_cb(callback, db)
    env.store_candidate.assert_not_awaited()


# ───────────────────────── только автор ─────────────────────────


async def test_stranger_pressing_elevator_button_gets_alert(env, db, world):
    env.get_candidate.return_value = pick_candidate(world)
    callback = make_callback(f"elv:{world.lift_a11.id}", from_id=STRANGER_ID)
    await run_cb(callback, db)

    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert") is True
    assert "автор" in callback.answer.await_args.args[0]
    env.store_candidate.assert_not_awaited()
    env.pop_candidate.assert_not_awaited()


async def test_staff_colleague_cannot_answer_operational(env, db, world):
    """В staff-группе коллега подтверждает «Да», но про лифт отвечает автор."""
    db.add(User(telegram_id=STRANGER_ID, roles='["manager"]', active_role="manager",
                status="approved", phone="+998901112299", language="ru"))
    db.commit()
    env.get_candidate.return_value = make_candidate(
        {"type": "building", "id": world.a.id, "label_public": "ул. Лифтовая, 1",
         "label_full": "ул. Лифтовая, 1"},
        kind="staff", phase=gie.PHASE_OPERATIONAL,
        elevator_building_id=world.a.id, elevator_id=world.lift_a11.id,
    )
    callback = make_callback("op:1", from_id=STRANGER_ID)
    await run_cb(callback, db)

    assert callback.answer.await_args.kwargs.get("show_alert") is True
    env.pop_candidate.assert_not_awaited()
    env.save_request.assert_not_awaited()


# ───────────────────────── «работает?» → заявка ─────────────────────────


def operational_candidate(world, **overrides):
    return make_candidate(
        apartment_address(world.apt_e1), phase=gie.PHASE_OPERATIONAL,
        elevator_building_id=world.a.id, elevator_id=world.lift_a11.id,
        elevator_entrance=1, elevator_number=1, **overrides,
    )


async def test_operational_no_creates_request_with_elevator_fields(env, db, world):
    approve(db, world, world.apt_e1)
    candidate = operational_candidate(world)
    env.get_candidate.return_value = candidate
    env.pop_candidate.return_value = candidate
    callback = make_callback("op:0")
    await run_cb(callback, db)

    callback.answer.assert_awaited_once_with()
    env.pop_candidate.assert_awaited_once()
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
    candidate = operational_candidate(world)
    env.get_candidate.return_value = candidate
    env.pop_candidate.return_value = candidate
    await run_cb(make_callback("op:1"), db)
    assert env.save_request.await_args.args[0]["elevator_operational"] is True


async def test_operational_double_press_second_is_expired(env, db, world):
    approve(db, world, world.apt_e1)
    env.get_candidate.return_value = operational_candidate(world)
    env.pop_candidate.return_value = None
    callback = make_callback("op:1")
    await run_cb(callback, db)
    env.save_request.assert_not_awaited()
    assert "устарело" in edited_text(callback)


async def test_operational_garbage_and_wrong_phase_are_noop(env, db, world):
    env.get_candidate.return_value = operational_candidate(world)
    await run_cb(make_callback("op:2"), db)
    env.get_candidate.return_value = pick_candidate(world)
    await run_cb(make_callback("op:1"), db)
    env.pop_candidate.assert_not_awaited()
    env.save_request.assert_not_awaited()


async def test_crafted_yes_in_elevator_phase_is_noop(env, db, world):
    env.get_candidate.return_value = operational_candidate(world)
    callback = make_callback("yes")
    await run_cb(callback, db)
    env.pop_candidate.assert_not_awaited()
    env.save_request.assert_not_awaited()
    callback.message.edit_text.assert_not_awaited()


# ───────────────────────── таймаут ─────────────────────────


async def test_timeout_pops_candidate_and_edits_message(monkeypatch, env, world):
    monkeypatch.setattr(gie, "ELEVATOR_ANSWER_TIMEOUT", 0)
    env.get_candidate.return_value = operational_candidate(world)
    env.pop_candidate.return_value = operational_candidate(world)
    bot = make_bot()
    await gie._expire_elevator_prompt(bot, CHAT_ID, PROMPT_ID, "ru")

    env.pop_candidate.assert_awaited_once_with(CHAT_ID, PROMPT_ID)
    bot.edit_message_text.assert_awaited_once()
    kwargs = bot.edit_message_text.await_args.kwargs
    assert kwargs["chat_id"] == CHAT_ID and kwargs["message_id"] == PROMPT_ID
    assert "не оформлена" in kwargs["text"]
    assert "https://t.me/test_bot" in kwargs["text"]


async def test_timeout_after_answer_does_nothing(monkeypatch, env, world):
    monkeypatch.setattr(gie, "ELEVATOR_ANSWER_TIMEOUT", 0)
    env.get_candidate.return_value = None  # заявка создана — кандидат снят
    bot = make_bot()
    await gie._expire_elevator_prompt(bot, CHAT_ID, PROMPT_ID, "ru")
    env.pop_candidate.assert_not_awaited()
    bot.edit_message_text.assert_not_awaited()


async def test_timeout_ignores_candidate_outside_elevator_phase(monkeypatch, env, world):
    monkeypatch.setattr(gie, "ELEVATOR_ANSWER_TIMEOUT", 0)
    env.get_candidate.return_value = make_candidate(apartment_address(world.apt_e1))
    bot = make_bot()
    await gie._expire_elevator_prompt(bot, CHAT_ID, PROMPT_ID, "ru")
    env.pop_candidate.assert_not_awaited()
    bot.edit_message_text.assert_not_awaited()


async def test_schedule_creates_one_shot_task(monkeypatch, env, world):
    monkeypatch.undo()  # настоящий schedule_elevator_timeout
    monkeypatch.setattr(settings, "BOT_USERNAME", "test_bot")
    monkeypatch.setattr(gie, "ELEVATOR_ANSWER_TIMEOUT", 0)
    monkeypatch.setattr(gi.pending, "get_candidate", AsyncMock(return_value=None))
    bot = make_bot()
    task = gie.schedule_elevator_timeout(bot, CHAT_ID, PROMPT_ID, "ru")
    await task
    assert task.done() and task.exception() is None


def test_phase_candidate_ttl_outlives_timer():
    assert gie.ELEVATOR_PHASE_TTL > gie.ELEVATOR_ANSWER_TIMEOUT
