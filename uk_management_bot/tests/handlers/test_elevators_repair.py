"""T10 (Ф5): бот лифтёра — создание заявки на ремонт из карточки лифта.

Свойства (RED-первыми):
1. ``elvm:rep:{id}`` → FSM ``repair_description`` (дом лифта в данных).
2. Описание короче 10 символов — переспрос; годное → ``repair_urgency`` с ``elvm:urg:*``.
3. Срочность → ``save_request`` получает category/elevator_id/operational=False/
   acceptance_mode=manager/адрес дома/роль staff_group; затем предложение «В ремонте?».
4. Интеграция: настоящий ``save_request_sync`` на sqlite создаёт заявку с этими полями.
5. «Да» на предложении → статус under_repair с reason «ремонт {номер}» и номером в журнале.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.elevator import Elevator, ElevatorStatusEvent
from uk_management_bot.database.models.request import Request
from uk_management_bot.handlers.elevators import _common, card, repair, status
from uk_management_bot.handlers.requests import create as create_mod
from uk_management_bot.states.elevators import ElevatorStates
from uk_management_bot.tests.handlers import elevators_harness as h
from uk_management_bot.utils.business_time import business_today
from uk_management_bot.utils.constants import ACCEPTANCE_MODE_MANAGER
from uk_management_bot.utils.helpers import get_text

NUMBER = "260906-001"


@pytest.fixture()
def db():
    session = h.make_db()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", True)


@pytest.fixture(autouse=True)
def _no_dispatch(monkeypatch):
    import uk_management_bot.services.dispatch as dispatch_mod

    monkeypatch.setattr(dispatch_mod, "auto_dispatch_new_request_sync", MagicMock())


@pytest.fixture(autouse=True)
def _run_db_on_sqlite(db):
    run = h.run_db_on(db)
    with patch.object(repair, "run_db", run), patch.object(card, "run_db", run), \
         patch.object(create_mod, "run_db", run), patch.object(_common, "run_db", run):
        yield


@pytest.fixture()
def world(db):
    return h.build_world(db, today=business_today())


async def _state_at_urgency(world) -> h.FakeState:
    state = h.FakeState()
    await state.update_data(
        elvm_elevator_id=world["working"].id, elvm_building_id=world["building"].id,
        elvm_description="Лифт застревает между этажами",
    )
    await state.set_state(ElevatorStates.repair_urgency)
    return state


@pytest.mark.asyncio
async def test_repair_start_enters_description_state(world):
    state = h.FakeState()
    cb = h.make_callback(f"elvm:rep:{world['working'].id}")
    await repair.handle_repair_start(cb, state, language="ru")
    assert state.state == ElevatorStates.repair_description
    assert state.data["elvm_elevator_id"] == world["working"].id
    assert state.data["elvm_building_id"] == world["building"].id
    assert "elvm:cancel" in h.callbacks_of(cb.message.edit_text.await_args.kwargs["reply_markup"])


@pytest.mark.asyncio
async def test_repair_start_denied_without_specialization(world):
    cb = h.make_callback(f"elvm:rep:{world['working'].id}", from_id=h.PLAIN_TG)
    state = h.FakeState()
    await repair.handle_repair_start(cb, state, language="ru")
    assert state.state is None
    assert cb.answer.await_args.args[0] == get_text("elevators.bot.no_spec", language="ru")


@pytest.mark.asyncio
async def test_short_description_is_reasked(world):
    state = h.FakeState()
    await state.update_data(elvm_elevator_id=world["working"].id, elvm_building_id=world["building"].id)
    await state.set_state(ElevatorStates.repair_description)
    msg = h.make_message("шумит")
    await repair.handle_description(msg, state, language="ru")
    assert state.state == ElevatorStates.repair_description
    assert msg.answer.await_args.args[0] == get_text(
        "elevators.bot.repair_description_short", language="ru", min=repair.MIN_DESCRIPTION_LEN)


@pytest.mark.asyncio
async def test_description_moves_to_urgency(world):
    state = h.FakeState()
    await state.update_data(elvm_elevator_id=world["working"].id, elvm_building_id=world["building"].id)
    await state.set_state(ElevatorStates.repair_description)
    msg = h.make_message("Лифт застревает между этажами")
    await repair.handle_description(msg, state, language="ru")
    assert state.state == ElevatorStates.repair_urgency
    assert state.data["elvm_description"] == "Лифт застревает между этажами"
    callbacks = h.callbacks_of(msg.answer.await_args.kwargs["reply_markup"])
    for key in ("low", "medium", "high", "critical"):
        assert f"elvm:urg:{key}" in callbacks
    assert "elvm:cancel" in callbacks


@pytest.mark.asyncio
async def test_urgency_calls_save_request_with_elevator_contract(world):
    state = await _state_at_urgency(world)
    cb = h.make_callback("elvm:urg:high")
    with patch.object(repair, "save_request", AsyncMock(return_value=NUMBER)) as save:
        await repair.handle_urgency(cb, state, language="ru")
    save.assert_awaited_once()
    data = save.await_args.args[0]
    assert save.await_args.args[1] == h.TECH_TG
    assert save.await_args.kwargs["role"] == "staff_group"
    assert data["category"] == "elevator"
    assert data["address_type"] == "building"
    assert data["address_id"] == world["building"].id
    assert data["elevator_id"] == world["working"].id
    assert data["elevator_operational"] is False
    assert data["acceptance_mode"] == ACCEPTANCE_MODE_MANAGER
    assert data["urgency"] == "high"
    assert data["description"] == "Лифт застревает между этажами"
    assert data["reported_by_user_id"] == world["tech"].id
    # Р18: лифтёр — персонал, лифт «В ремонте»/«На ТО» ему не запрещён.
    assert save.await_args.kwargs["allow_under_works"] is True
    # состояние снято, предложение статуса
    assert state.state is None
    shown = cb.message.edit_text.await_args.args[0]
    assert NUMBER in shown
    callbacks = h.callbacks_of(cb.message.edit_text.await_args.kwargs["reply_markup"])
    assert f"elvm:repst:{world['working'].id}:{NUMBER}:1" in callbacks
    assert f"elvm:repst:{world['working'].id}:{NUMBER}:0" in callbacks


@pytest.mark.asyncio
async def test_urgency_garbage_rejected_without_save(world):
    state = await _state_at_urgency(world)
    cb = h.make_callback("elvm:urg:asap")
    with patch.object(repair, "save_request", AsyncMock()) as save:
        await repair.handle_urgency(cb, state, language="ru")
    save.assert_not_awaited()
    assert state.state == ElevatorStates.repair_urgency


@pytest.mark.asyncio
async def test_save_failure_shows_localized_error(world):
    state = await _state_at_urgency(world)
    cb = h.make_callback("elvm:urg:low")
    with patch.object(repair, "save_request", AsyncMock(return_value=None)):
        await repair.handle_urgency(cb, state, language="ru")
    assert cb.message.edit_text.await_args.args[0] == get_text("elevators.bot.repair_failed", language="ru")
    assert state.state is None


@pytest.mark.asyncio
async def test_real_save_request_creates_elevator_repair(world, db):
    state = await _state_at_urgency(world)
    cb = h.make_callback("elvm:urg:critical")
    await repair.handle_urgency(cb, state, language="ru")
    db.expire_all()
    created = [r for r in db.query(Request).all() if r.request_number != h.OPEN_REQUEST_NUMBER]
    assert len(created) == 1
    request = created[0]
    assert request.category == "elevator"
    assert request.elevator_id == world["working"].id
    assert request.elevator_operational is False
    assert request.acceptance_mode == ACCEPTANCE_MODE_MANAGER
    assert request.building_id == world["building"].id
    assert request.address_type == "building"
    assert request.user_id == world["tech"].id
    assert request.urgency == "critical"
    assert request.request_number in cb.message.edit_text.await_args.args[0]


@pytest.mark.asyncio
async def test_repair_status_offer_yes_sets_under_repair(world, db):
    elevator_id = world["working"].id
    h.add_request(db, NUMBER, elevator_id=elevator_id, user_id=world["tech"].id)
    cb = h.make_callback(f"elvm:repst:{elevator_id}:{NUMBER}:1")
    with patch.object(status, "send_notify_messages", AsyncMock(return_value=1)) as notify:
        await repair.handle_repair_status_offer(cb, language="ru")
    db.expire_all()
    assert db.get(Elevator, elevator_id).current_status == "under_repair"
    event = db.query(ElevatorStatusEvent).filter_by(elevator_id=elevator_id).one()
    assert event.source == "manual"
    assert event.request_number == NUMBER
    assert event.reason == get_text("elevators.bot.repair_reason", language="ru", number=NUMBER)
    assert event.actor_user_id == world["tech"].id
    notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_repair_status_offer_foreign_number_rejected(world, db):
    """Номер заявки из callback_data не привязан к этому лифту — отказ, журнал пуст."""
    elevator_id = world["working"].id
    h.add_request(db, NUMBER, elevator_id=world["raw"].id, user_id=world["tech"].id)
    for number in (NUMBER, "260906-777"):  # чужой лифт / несуществующая
        cb = h.make_callback(f"elvm:repst:{elevator_id}:{number}:1")
        with patch.object(status, "send_notify_messages", AsyncMock()) as notify:
            await repair.handle_repair_status_offer(cb, language="ru")
        notify.assert_not_awaited()
        assert cb.answer.await_args.args[0] == get_text("elevators.bot.request_mismatch", language="ru")
        assert cb.answer.await_args.kwargs.get("show_alert") is True
    db.expire_all()
    assert db.query(ElevatorStatusEvent).count() == 0
    assert db.get(Elevator, elevator_id).current_status == "working"


@pytest.mark.asyncio
async def test_repair_start_refused_for_uncommissioned(world):
    """Кнопки в карточке нет, но устаревшая карточка/crafted callback — явный отказ."""
    state = h.FakeState()
    cb = h.make_callback(f"elvm:rep:{world['raw'].id}")
    await repair.handle_repair_start(cb, state, language="ru")
    assert state.state is None
    assert cb.answer.await_args.args[0] == get_text("elevators.bot.repair_not_commissioned", language="ru")
    cb.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_repair_status_offer_no_keeps_status(world, db):
    elevator_id = world["working"].id
    cb = h.make_callback(f"elvm:repst:{elevator_id}:{NUMBER}:0")
    await repair.handle_repair_status_offer(cb, language="ru")
    assert db.query(ElevatorStatusEvent).count() == 0
    assert cb.message.edit_text.await_args.args[0] == get_text("elevators.bot.repair_status_kept", language="ru")


@pytest.mark.asyncio
async def test_repair_status_offer_garbage_rejected(world):
    cb = h.make_callback("elvm:repst:abc:zzz:1")
    with patch.object(repair, "run_db", AsyncMock()) as run_db:
        await repair.handle_repair_status_offer(cb, language="ru")
    run_db.assert_not_awaited()
    cb.answer.assert_awaited()
