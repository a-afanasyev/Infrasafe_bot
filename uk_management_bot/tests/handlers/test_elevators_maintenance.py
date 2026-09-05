"""T10 (Ф5): бот лифтёра — отметка ТО / освидетельствования выполненным.

Свойства (RED-первыми):
1. ``elvm:occs:{id}`` → planned-пункты обоих видов, просроченные помечены.
2. ``elvm:occ:{oid}:done`` → FSM ``occ_comment`` с «Пропустить»/«Отмена».
3. ТО: комментарий (или пропуск) → ``complete_occurrence_sync`` → done, actor, комментарий;
   ответ «Выполнено, следующее ТО: {дата следующего planned}».
4. Освидетельствование: после комментария — номер акта, срок (ДД.ММ.ГГГГ, переспрос при
   мусоре), ссылка (опц., переспрос при не-http); паспорт лифта обновлён.
5. Уже закрытый пункт → локализованная ошибка состояния; без специализации — отказ.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.elevator import Elevator, ElevatorMaintenanceOccurrence
from uk_management_bot.handlers.elevators import card, maintenance
from uk_management_bot.states.elevators import ElevatorStates
from uk_management_bot.tests.handlers import elevators_harness as h
from uk_management_bot.utils.business_time import business_today, fmt_date
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
    with patch.object(maintenance, "run_db", run), patch.object(card, "run_db", run):
        yield


@pytest.fixture()
def today() -> date:
    return business_today()


@pytest.fixture()
def world(db, today):
    return h.build_world(db, today=today)


async def _state_for(occurrence, kind: str, **extra) -> h.FakeState:
    state = h.FakeState()
    await state.update_data(
        elvm_occurrence_id=occurrence.id, elvm_elevator_id=occurrence.elevator_id,
        elvm_kind=kind, **extra,
    )
    return state


@pytest.mark.asyncio
async def test_occurrences_list_shows_planned_of_both_kinds(world, db, today):
    overdue = ElevatorMaintenanceOccurrence(
        elevator_id=world["working"].id, kind="maintenance",
        due_on=today - timedelta(days=10), state="planned",
    )
    db.add(overdue)
    db.commit()
    cb = h.make_callback(f"elvm:occs:{world['working'].id}")
    await maintenance.handle_occurrences(cb, language="ru")
    kwargs = cb.message.edit_text.await_args.kwargs
    markup = kwargs["reply_markup"]
    callbacks = h.callbacks_of(markup)
    for occ in (world["soon"], world["later"], world["cert"], overdue):
        assert f"elvm:occ:{occ.id}:done" in callbacks
    texts = h.texts_of(markup)
    mark = get_text("elevators.bot.occ_overdue_mark", language="ru")
    assert sum(1 for t in texts if t.startswith(mark)) == 1
    assert any(get_text("elevators.bot.kind.certification", language="ru") in t for t in texts)
    assert f"elvm:card:{world['working'].id}" in callbacks


@pytest.mark.asyncio
async def test_occurrences_empty(world, db):
    for occ in (world["soon"], world["later"], world["cert"]):
        occ.state = "cancelled"
    db.commit()
    cb = h.make_callback(f"elvm:occs:{world['working'].id}")
    await maintenance.handle_occurrences(cb, language="ru")
    assert get_text("elevators.bot.occ_none", language="ru") in cb.message.edit_text.await_args.args[0]


@pytest.mark.asyncio
async def test_pick_enters_comment_state(world):
    state = h.FakeState()
    cb = h.make_callback(f"elvm:occ:{world['soon'].id}:done")
    await maintenance.handle_occurrence_pick(cb, state, language="ru")
    assert state.state == ElevatorStates.occ_comment
    assert state.data["elvm_occurrence_id"] == world["soon"].id
    assert state.data["elvm_kind"] == "maintenance"
    assert state.data["elvm_elevator_id"] == world["working"].id
    callbacks = h.callbacks_of(cb.message.edit_text.await_args.kwargs["reply_markup"])
    assert "elvm:skip" in callbacks and "elvm:cancel" in callbacks


@pytest.mark.asyncio
async def test_pick_denied_without_specialization(world):
    state = h.FakeState()
    cb = h.make_callback(f"elvm:occ:{world['soon'].id}:done", from_id=h.PLAIN_TG)
    await maintenance.handle_occurrence_pick(cb, state, language="ru")
    assert state.state is None
    assert cb.answer.await_args.args[0] == get_text("elevators.bot.no_spec", language="ru")


@pytest.mark.asyncio
async def test_pick_of_closed_occurrence_is_rejected(world, db):
    world["soon"].state = "done"
    db.commit()
    cb = h.make_callback(f"elvm:occ:{world['soon'].id}:done")
    await maintenance.handle_occurrence_pick(cb, h.FakeState(), language="ru")
    assert cb.answer.await_args.args[0] == get_text("elevators.bot.occ_state_error", language="ru")


@pytest.mark.asyncio
async def test_maintenance_comment_completes_and_names_next(world, db):
    state = await _state_for(world["soon"], "maintenance")
    await state.set_state(ElevatorStates.occ_comment)
    msg = h.make_message("смазал направляющие")
    await maintenance.handle_comment_text(msg, state, language="ru")
    db.expire_all()
    occ = db.get(ElevatorMaintenanceOccurrence, world["soon"].id)
    assert occ.state == "done"
    assert occ.comment == "смазал направляющие"
    assert occ.done_by_user_id == world["tech"].id
    assert state.state is None
    shown = msg.answer.await_args_list[0].args[0]
    assert shown == get_text("elevators.bot.occ_done", language="ru",
                             next=fmt_date(world["later"].due_on))


@pytest.mark.asyncio
async def test_maintenance_skip_comment_completes_without_next(world, db):
    world["later"].state = "cancelled"
    db.commit()
    state = await _state_for(world["soon"], "maintenance")
    await state.set_state(ElevatorStates.occ_comment)
    cb = h.make_callback("elvm:skip")
    await maintenance.handle_skip(cb, state, language="ru")
    db.expire_all()
    assert db.get(ElevatorMaintenanceOccurrence, world["soon"].id).comment is None
    assert db.get(ElevatorMaintenanceOccurrence, world["soon"].id).state == "done"
    shown = cb.message.edit_text.await_args.args[0]
    assert shown == get_text("elevators.bot.occ_done", language="ru",
                             next=get_text("elevators.bot.next_none", language="ru"))


@pytest.mark.asyncio
async def test_certification_asks_number_after_comment(world):
    state = await _state_for(world["cert"], "certification")
    await state.set_state(ElevatorStates.occ_comment)
    cb = h.make_callback("elvm:skip")
    await maintenance.handle_skip(cb, state, language="ru")
    assert state.state == ElevatorStates.cert_number
    assert cb.message.edit_text.await_args.args[0] == get_text("elevators.bot.cert_number_prompt", language="ru")


@pytest.mark.asyncio
async def test_certification_number_then_date_validation(world):
    state = await _state_for(world["cert"], "certification")
    await state.set_state(ElevatorStates.cert_number)
    await maintenance.handle_cert_number(h.make_message("АКТ-77"), state, language="ru")
    assert state.state == ElevatorStates.cert_valid_until
    assert state.data["elvm_cert_number"] == "АКТ-77"

    bad = h.make_message("завтра")
    await maintenance.handle_cert_date(bad, state, language="ru")
    assert state.state == ElevatorStates.cert_valid_until
    assert bad.answer.await_args.args[0] == get_text("elevators.bot.cert_date_invalid", language="ru")

    await maintenance.handle_cert_date(h.make_message("31.12.2027"), state, language="ru")
    assert state.state == ElevatorStates.cert_url
    assert state.data["elvm_cert_valid_until"] == "2027-12-31"


@pytest.mark.asyncio
async def test_certification_url_validation_and_completion(world, db):
    state = await _state_for(
        world["cert"], "certification", elvm_cert_number="АКТ-77", elvm_cert_valid_until="2027-12-31",
    )
    await state.set_state(ElevatorStates.cert_url)
    bad = h.make_message("ftp://acts/77")
    await maintenance.handle_cert_url(bad, state, language="ru")
    assert state.state == ElevatorStates.cert_url
    assert bad.answer.await_args.args[0] == get_text("elevators.bot.cert_url_invalid", language="ru")

    good = h.make_message("https://acts.example/77")
    await maintenance.handle_cert_url(good, state, language="ru")
    db.expire_all()
    occ = db.get(ElevatorMaintenanceOccurrence, world["cert"].id)
    assert occ.state == "done"
    elevator = db.get(Elevator, world["working"].id)
    assert elevator.cert_number == "АКТ-77"
    assert elevator.cert_valid_until == date(2027, 12, 31)
    assert elevator.cert_act_url == "https://acts.example/77"
    assert state.state is None
    shown = good.answer.await_args_list[0].args[0]
    assert shown == get_text("elevators.bot.occ_done", language="ru",
                             next=get_text("elevators.bot.next_none", language="ru"))


@pytest.mark.asyncio
async def test_certification_url_skip_completes(world, db):
    state = await _state_for(
        world["cert"], "certification", elvm_cert_number="АКТ-78", elvm_cert_valid_until="2027-01-15",
    )
    await state.set_state(ElevatorStates.cert_url)
    cb = h.make_callback("elvm:skip")
    await maintenance.handle_skip(cb, state, language="ru")
    db.expire_all()
    assert db.get(ElevatorMaintenanceOccurrence, world["cert"].id).state == "done"
    assert db.get(Elevator, world["working"].id).cert_act_url is None


@pytest.mark.asyncio
async def test_complete_denied_without_specialization(world, db):
    state = await _state_for(world["soon"], "maintenance")
    await state.set_state(ElevatorStates.occ_comment)
    cb = h.make_callback("elvm:skip", from_id=h.PLAIN_TG)
    await maintenance.handle_skip(cb, state, language="ru")
    db.expire_all()
    assert db.get(ElevatorMaintenanceOccurrence, world["soon"].id).state == "planned"
    assert cb.answer.await_args.args[0] == get_text("elevators.bot.no_spec", language="ru")


@pytest.mark.asyncio
async def test_non_text_in_fsm_state_gets_hint(world):
    state = h.FakeState()
    await state.set_state(ElevatorStates.occ_comment)
    msg = h.make_message(None)
    await maintenance.handle_non_text(msg, language="ru")
    assert msg.answer.await_args.args[0] == get_text("elevators.bot.text_only", language="ru")
