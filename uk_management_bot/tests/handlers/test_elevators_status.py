"""T10 (Ф5): бот лифтёра — смена статуса лифта с опциональной причиной.

Свойства (RED-первыми):
1. ``elvm:st:{id}`` → клавиатура четырёх статусов, текущий помечен; невведённый → отказ.
2. ``elvm:st:{id}:{status}`` → FSM ``status_reason`` с кнопкой «Без причины».
3. Причина текстом → настоящий ``set_status_sync`` (``source="manual"``, actor, reason),
   commit, ``send_notify_messages`` ПОСЛЕ, ответ «X → Y (уведомлено: N)» и карточка.
4. Тот же статус → «Без изменений», журнал пуст. Слишком длинная причина — переспрос.
5. Мусорный статус из callback отклоняется без БД; без специализации — отказ.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.elevator import Elevator, ElevatorStatusEvent
from uk_management_bot.handlers.elevators import card, status
from uk_management_bot.services.elevator_service import MAX_REASON_LEN
from uk_management_bot.states.elevators import ElevatorStates
from uk_management_bot.tests.handlers import elevators_harness as h
from uk_management_bot.utils.business_time import business_today
from uk_management_bot.utils.helpers import get_text


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
def _run_db_on_sqlite(db):
    run = h.run_db_on(db)
    with patch.object(status, "run_db", run), patch.object(card, "run_db", run):
        yield


@pytest.fixture()
def world(db):
    return h.build_world(db, today=business_today())


@pytest.mark.asyncio
async def test_status_menu_marks_current(world):
    elevator_id = world["working"].id
    cb = h.make_callback(f"elvm:st:{elevator_id}")
    await status.handle_status_menu(cb, language="ru")
    kwargs = cb.message.edit_text.await_args.kwargs
    markup = kwargs["reply_markup"]
    callbacks = h.callbacks_of(markup)
    for st in ("working", "not_working", "under_repair", "maintenance"):
        assert f"elvm:st:{elevator_id}:{st}" in callbacks
    marked = [t for t in h.texts_of(markup) if t.startswith("• ")]
    assert marked == ["• " + get_text("elevators.status.working", language="ru")]
    assert f"elvm:card:{elevator_id}" in callbacks


@pytest.mark.asyncio
async def test_status_menu_rejects_uncommissioned(world):
    cb = h.make_callback(f"elvm:st:{world['raw'].id}")
    await status.handle_status_menu(cb, language="ru")
    assert cb.answer.await_args.args[0] == get_text("elevators.bot.status_not_commissioned", language="ru")
    cb.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_status_pick_enters_reason_state(world):
    elevator_id = world["working"].id
    state = h.FakeState()
    cb = h.make_callback(f"elvm:st:{elevator_id}:under_repair")
    await status.handle_status_pick(cb, state, language="ru")
    assert state.state == ElevatorStates.status_reason
    assert state.data["elvm_elevator_id"] == elevator_id
    assert state.data["elvm_status"] == "under_repair"
    kwargs = cb.message.edit_text.await_args.kwargs
    callbacks = h.callbacks_of(kwargs["reply_markup"])
    assert "elvm:noreason" in callbacks and "elvm:cancel" in callbacks


@pytest.mark.asyncio
async def test_status_pick_garbage_rejected_without_db(world):
    cb = h.make_callback(f"elvm:st:{world['working'].id}:exploded")
    with patch.object(status, "run_db", AsyncMock()) as run_db:
        await status.handle_status_pick(cb, h.FakeState(), language="ru")
    run_db.assert_not_awaited()
    cb.answer.assert_awaited()


@pytest.mark.asyncio
async def test_reason_text_applies_manual_status_and_notifies(world, db):
    elevator_id = world["working"].id
    state = h.FakeState()
    await state.update_data(elvm_elevator_id=elevator_id, elvm_status="under_repair")
    await state.set_state(ElevatorStates.status_reason)
    msg = h.make_message("сгорел двигатель")
    with patch.object(status, "send_notify_messages", AsyncMock(return_value=1)) as notify:
        await status.handle_reason_text(msg, state, language="ru")

    db.expire_all()
    assert db.get(Elevator, elevator_id).current_status == "under_repair"
    event = db.query(ElevatorStatusEvent).filter_by(elevator_id=elevator_id).one()
    assert event.source == "manual"
    assert event.actor_user_id == world["tech"].id
    assert event.reason == "сгорел двигатель"
    assert event.old_status == "working" and event.new_status == "under_repair"

    notify.assert_awaited_once()
    messages = notify.await_args.args[1]
    assert [m[0] for m in messages] == [h.RESIDENT_TG]

    assert state.state is None
    shown = msg.answer.await_args_list[0].args[0]
    assert shown == get_text(
        "elevators.bot.status_changed", language="ru",
        old=get_text("elevators.status.working", language="ru"),
        new=get_text("elevators.status.under_repair", language="ru"), count=1,
    )
    # затем карточка с актуальным статусом
    card_text = msg.answer.await_args_list[1].args[0]
    assert get_text("elevators.status.under_repair", language="ru") in card_text


@pytest.mark.asyncio
async def test_no_reason_button_applies_status(world, db):
    elevator_id = world["working"].id
    state = h.FakeState()
    await state.update_data(elvm_elevator_id=elevator_id, elvm_status="not_working")
    await state.set_state(ElevatorStates.status_reason)
    cb = h.make_callback("elvm:noreason")
    with patch.object(status, "send_notify_messages", AsyncMock(return_value=0)) as notify:
        await status.handle_no_reason(cb, state, language="ru")
    db.expire_all()
    event = db.query(ElevatorStatusEvent).filter_by(elevator_id=elevator_id).one()
    assert event.reason is None and event.new_status == "not_working"
    notify.assert_not_awaited()  # для not_working уведомления жителям нет
    assert state.state is None


@pytest.mark.asyncio
async def test_same_status_is_noop(world, db):
    state = h.FakeState()
    await state.update_data(elvm_elevator_id=world["working"].id, elvm_status="working")
    await state.set_state(ElevatorStates.status_reason)
    cb = h.make_callback("elvm:noreason")
    with patch.object(status, "send_notify_messages", AsyncMock()) as notify:
        await status.handle_no_reason(cb, state, language="ru")
    assert db.query(ElevatorStatusEvent).count() == 0
    notify.assert_not_awaited()
    shown = cb.message.edit_text.await_args.args[0]
    assert shown == get_text("elevators.bot.status_unchanged", language="ru",
                             status=get_text("elevators.status.working", language="ru"))


@pytest.mark.asyncio
async def test_too_long_reason_is_reasked(world, db):
    state = h.FakeState()
    await state.update_data(elvm_elevator_id=world["working"].id, elvm_status="not_working")
    await state.set_state(ElevatorStates.status_reason)
    msg = h.make_message("x" * (MAX_REASON_LEN + 1))
    await status.handle_reason_text(msg, state, language="ru")
    assert state.state == ElevatorStates.status_reason
    assert db.query(ElevatorStatusEvent).count() == 0
    assert msg.answer.await_args.args[0] == get_text(
        "elevators.bot.reason_too_long", language="ru", max=MAX_REASON_LEN)


@pytest.mark.asyncio
async def test_apply_denied_without_specialization(world, db):
    state = h.FakeState()
    await state.update_data(elvm_elevator_id=world["working"].id, elvm_status="not_working")
    await state.set_state(ElevatorStates.status_reason)
    cb = h.make_callback("elvm:noreason", from_id=h.PLAIN_TG)
    await status.handle_no_reason(cb, state, language="ru")
    assert db.query(ElevatorStatusEvent).count() == 0
    assert cb.answer.await_args.args[0] == get_text("elevators.bot.no_spec", language="ru")


@pytest.mark.asyncio
async def test_reason_state_without_fsm_data_is_cancelled(world):
    """Осиротевшее состояние (данные потеряны) — не падение, а сброс."""
    state = h.FakeState()
    await state.set_state(ElevatorStates.status_reason)
    msg = h.make_message("причина")
    await status.handle_reason_text(msg, state, language="ru")
    assert state.state is None
    assert msg.answer.await_args.args[0] == get_text("elevators.bot.cancelled", language="ru")
