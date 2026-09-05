"""T7 (Ф4a-2), часть B: подсказка менеджеру о статусе лифта после MANAGER_CONFIRM.

Свойства (RED-первыми):
1. Подсказка уходит только у заявок с ``elevator_id`` (и при включённом флаге);
   клавиатура — четыре статуса ``elv:st:{id}:{status}:{номер}`` + «оставить».
2. Кнопка статуса: ``has_admin_access`` — отказ неавторизованному до БД;
   менеджер → настоящий ``set_status_sync`` на sqlite с ``source="request_hint"``
   и номером заявки в журнале; сообщения жителям уходят через
   ``send_notify_messages`` ПОСЛЕ commit; повтор того же статуса — «без изменений».
3. ``handle_manager_confirm_completed`` (admin/views.py) зовёт подсказку с
   ``elevator_id`` подтверждённой заявки.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models import Apartment, Building, UserApartment, Yard
from uk_management_bot.database.models.elevator import Elevator, ElevatorStatusEvent
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.handlers.admin import elevator_hint as mod
from uk_management_bot.handlers.admin import views
from uk_management_bot.services.elevator_service import generate_public_code
from uk_management_bot.utils.helpers import get_text, load_locale

NUMBER = "260905-001"
MANAGER_ID, RESIDENT_ID = 5, 6


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
def _run_db_on_sqlite(db):
    session = db

    async def _run(unit, *, db=None):
        return unit(db if db is not None else session)

    with patch.object(mod, "run_db", _run):
        yield


@pytest.fixture()
def world(db):
    yard = Yard(name="Двор", is_active=True)
    building = Building(address="ул. Лифтовая, 1", yard=yard, is_active=True)
    apt = Apartment(apartment_number="7", building=building, entrance=1, is_active=True)
    manager = User(id=MANAGER_ID, telegram_id=500, roles='["manager"]', active_role="manager",
                   status="approved", language="ru")
    resident = User(id=RESIDENT_ID, telegram_id=600, roles='["applicant"]',
                    active_role="applicant", status="approved", language="ru")
    db.add_all([yard, building, apt, manager, resident])
    db.commit()
    db.add(UserApartment(user_id=resident.id, apartment_id=apt.id, status="approved"))
    elevator = Elevator(
        building_id=building.id, entrance_number=1, elevator_number=1,
        passport_number="P-1", manufacturer="OTIS", serial_number="S-1",
        public_code=generate_public_code(), is_commissioned=True,
        commissioned_at=date(2020, 1, 1), current_status="working",
    )
    db.add(elevator)
    db.commit()
    return {"elevator": elevator, "manager": manager, "resident": resident}


def _callback(data: str) -> MagicMock:
    cb = MagicMock()
    cb.data = data
    cb.id = "cb1"
    cb.from_user.id = 500
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    cb.bot = MagicMock()
    cb.bot.send_message = AsyncMock()
    return cb


def _callbacks(markup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row]


# ── 1. отправка подсказки ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_hint_without_elevator(world):
    bot = MagicMock()
    bot.send_message = AsyncMock()
    sent = await mod.send_elevator_hint(bot, 500, elevator_id=None, request_number=NUMBER, lang="ru")
    assert sent is False
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_hint_when_flag_off(world, monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", False)
    bot = MagicMock()
    bot.send_message = AsyncMock()
    sent = await mod.send_elevator_hint(
        bot, 500, elevator_id=world["elevator"].id, request_number=NUMBER, lang="ru")
    assert sent is False
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_hint_sent_with_status_keyboard(world):
    bot = MagicMock()
    bot.send_message = AsyncMock()
    elevator_id = world["elevator"].id
    sent = await mod.send_elevator_hint(
        bot, 500, elevator_id=elevator_id, request_number=NUMBER, lang="ru")
    assert sent is True
    args, kwargs = bot.send_message.await_args.args, bot.send_message.await_args.kwargs
    assert args[0] == 500
    text = args[1]
    assert "ул. Лифтовая, 1" in text
    assert get_text("elevators.status.working", language="ru") in text
    callbacks = _callbacks(kwargs["reply_markup"])
    for status in ("working", "not_working", "under_repair", "maintenance"):
        assert f"elv:st:{elevator_id}:{status}:{NUMBER}" in callbacks
    assert "elv:keep" in callbacks
    assert kwargs.get("parse_mode") == "HTML"


@pytest.mark.asyncio
async def test_hint_unknown_elevator_is_silent(world):
    bot = MagicMock()
    bot.send_message = AsyncMock()
    sent = await mod.send_elevator_hint(bot, 500, elevator_id=99999, request_number=NUMBER, lang="ru")
    assert sent is False
    bot.send_message.assert_not_awaited()


# ── 2. кнопка статуса ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_button_denied_for_non_admin(world):
    cb = _callback(f"elv:st:{world['elevator'].id}:not_working:{NUMBER}")
    with patch.object(mod, "run_db", AsyncMock()) as run_db:
        await mod.handle_elevator_status_hint(
            cb, roles=["executor"], user=None, language="ru")
    run_db.assert_not_awaited()
    cb.answer.assert_awaited()
    assert cb.answer.await_args.args[0] == get_text("admin.handlers.no_access_actions", language="ru")


@pytest.mark.asyncio
async def test_status_button_sets_status_from_request_hint(world, db):
    elevator_id = world["elevator"].id
    cb = _callback(f"elv:st:{elevator_id}:under_repair:{NUMBER}")
    with patch.object(mod, "send_notify_messages", AsyncMock(return_value=1)) as notify:
        await mod.handle_elevator_status_hint(
            cb, roles=["manager"], user=world["manager"], language="ru")

    db.expire_all()
    elevator = db.get(Elevator, elevator_id)
    assert elevator.current_status == "under_repair"
    event = db.query(ElevatorStatusEvent).filter_by(elevator_id=elevator_id).one()
    assert event.source == "request_hint"
    assert event.request_number == NUMBER
    assert event.actor_user_id == MANAGER_ID
    assert event.old_status == "working" and event.new_status == "under_repair"

    # жителям подъезда — после commit, через общий хелпер
    notify.assert_awaited_once()
    messages = notify.await_args.args[1]
    assert len(messages) == 1 and messages[0][0] == 600
    assert "ремонт" in messages[0][1]

    shown = cb.message.edit_text.await_args.args[0]
    assert get_text("elevators.status.working", language="ru") in shown
    assert get_text("elevators.status.under_repair", language="ru") in shown


@pytest.mark.asyncio
async def test_status_button_same_status_is_noop(world, db):
    elevator_id = world["elevator"].id
    cb = _callback(f"elv:st:{elevator_id}:working:{NUMBER}")
    with patch.object(mod, "send_notify_messages", AsyncMock(return_value=0)) as notify:
        await mod.handle_elevator_status_hint(
            cb, roles=["manager"], user=world["manager"], language="ru")
    assert db.query(ElevatorStatusEvent).count() == 0
    notify.assert_not_awaited()
    shown = cb.message.edit_text.await_args.args[0]
    assert shown == get_text("elevators.hint.unchanged", language="ru",
                             status=get_text("elevators.status.working", language="ru"))


@pytest.mark.asyncio
async def test_status_button_unknown_elevator(world):
    cb = _callback(f"elv:st:99999:working:{NUMBER}")
    await mod.handle_elevator_status_hint(
        cb, roles=["manager"], user=world["manager"], language="ru")
    assert cb.answer.await_args.args[0] == get_text("elevators.hint.not_found", language="ru")


@pytest.mark.asyncio
async def test_status_button_garbage_rejected_without_db(world):
    cb = _callback("elv:st:abc:working:zzz")
    with patch.object(mod, "run_db", AsyncMock()) as run_db:
        await mod.handle_elevator_status_hint(
            cb, roles=["manager"], user=world["manager"], language="ru")
    run_db.assert_not_awaited()
    cb.answer.assert_awaited()


@pytest.mark.asyncio
async def test_keep_button_just_acknowledges(world):
    cb = _callback("elv:keep")
    await mod.handle_elevator_keep(cb, language="ru")
    assert cb.message.edit_text.await_args.args[0] == get_text("elevators.hint.kept", language="ru")


# ── 3. стыковка с MANAGER_CONFIRM в admin/views.py ───────────────────────


def _confirm_env(elevator_id):
    request = SimpleNamespace(request_number=NUMBER, elevator_id=elevator_id, user=None,
                              format_number_for_display=lambda: NUMBER)
    svc = MagicMock()
    svc.get_request_by_number.return_value = request
    outcome = SimpleNamespace(post_commit_intents=[], old_status="Выполнена",
                              public_status="Принято")
    return svc, outcome


@pytest.mark.asyncio
@pytest.mark.parametrize("elevator_id", [42, None])
async def test_manager_confirm_calls_hint_with_request_elevator(elevator_id):
    svc, outcome = _confirm_env(elevator_id)
    cb = _callback(f"confirm_completed_{NUMBER}")
    user = SimpleNamespace(id=MANAGER_ID)
    with patch("uk_management_bot.services.workflow_runner.run_command_sync", return_value=outcome), \
         patch.object(views, "AdminHandlerService", return_value=svc), \
         patch.object(views, "dispatch_notify_intents_sync", AsyncMock()), \
         patch.object(views, "notify_channel_status_changed", AsyncMock()), \
         patch.object(views, "send_elevator_hint", AsyncMock(return_value=True)) as hint:
        await views.handle_manager_confirm_completed(
            cb, db=MagicMock(), roles=["manager"], user=user, language="ru")
    hint.assert_awaited_once()
    assert hint.await_args.args[:2] == (cb.bot, 500)
    assert hint.await_args.kwargs["elevator_id"] == elevator_id
    assert hint.await_args.kwargs["request_number"] == NUMBER
    cb.message.edit_text.assert_awaited()


def _lookup(locale: dict, dotted: str):
    """Ключ ровно в ЭТОЙ локали (get_text молча падает на ru — фолбэк спрятал бы дыру)."""
    node = locale
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


@pytest.mark.asyncio
async def test_hint_failure_does_not_break_confirmation():
    """Сбой подсказки (уже ПОСЛЕ commit MANAGER_CONFIRM) — не «ошибка подтверждения»:
    экран успеха показан, алерта об ошибке и rollback нет, исключение не утекает."""
    svc, outcome = _confirm_env(42)
    cb = _callback(f"confirm_completed_{NUMBER}")
    user = SimpleNamespace(id=MANAGER_ID)
    with patch("uk_management_bot.services.workflow_runner.run_command_sync", return_value=outcome), \
         patch.object(views, "AdminHandlerService", return_value=svc), \
         patch.object(views, "dispatch_notify_intents_sync", AsyncMock()), \
         patch.object(views, "notify_channel_status_changed", AsyncMock()), \
         patch.object(views, "send_elevator_hint", AsyncMock(side_effect=RuntimeError("boom"))):
        await views.handle_manager_confirm_completed(
            cb, db=MagicMock(), roles=["manager"], user=user, language="ru")
    shown = cb.message.edit_text.await_args.args[0]
    assert shown == get_text("admin.handlers.request_confirmed", language="ru").format(request_number=NUMBER)
    error_text = get_text("admin.handlers.error_confirming", language="ru")
    assert not [c for c in cb.answer.await_args_list if c.args and c.args[0] == error_text]
    svc.rollback.assert_not_called()


@pytest.mark.parametrize("lang", ["ru", "uz"])
def test_locale_keys_present(lang):
    for key in ("elevators.hint.prompt", "elevators.hint.keep_button", "elevators.hint.changed",
                "elevators.hint.unchanged", "elevators.hint.kept", "elevators.hint.rejected",
                "elevators.hint.not_found"):
        assert _lookup(load_locale(lang), key) is not None, (lang, key)
