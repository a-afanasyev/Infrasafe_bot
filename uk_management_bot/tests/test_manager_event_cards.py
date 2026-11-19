"""Карточки-решения менеджеру: событие по заявке приходит с кнопками.

Раньше адресные уведомления шли только жителю и исполнителю; менеджер узнавал
о работе, ждущей проверки, и о возврате жителем, открывая списки. Кнопки
карточки — существующие callback'и (подтверждение, возврат, назначение), новых
обработчиков нет. SQL и выборка получателей — на настоящей sqlite-сессии.
"""
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services import dispatch
from uk_management_bot.services.workflow_notifications import (
    collect_notify_messages_sync,
    collect_unassigned_messages_sync,
)
from uk_management_bot.utils.manager_cards import manager_card_markup

NUM = "261101-001"
MANAGER_TG, MANAGER_UZ_TG, APPLICANT_TG, EXECUTOR_TG = 100, 101, 200, 300


def _user(uid: int, tg: int, roles: str, lang: str = "ru") -> User:
    return User(id=uid, telegram_id=tg, first_name=f"U{uid}", roles=roles,
                active_role=roles.strip('[]"').split('"')[0], status="approved", language=lang)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine)()
    s.add_all([
        _user(1, MANAGER_TG, '["manager"]'),
        _user(2, MANAGER_UZ_TG, '["manager"]', "uz"),
        _user(3, APPLICANT_TG, '["applicant"]'),
        _user(4, EXECUTOR_TG, '["executor"]'),
    ])
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _request(db, status: str, **extra) -> None:
    db.add(Request(request_number=NUM, user_id=3, executor_id=4, category="plumbing",
                   description="Течёт труба", urgency="Обычная", status=status,
                   address="Дом 12 <A&B>", **extra))
    db.commit()


def _intent(action: str):
    return SimpleNamespace(kind="notify", data={"action": action})


def _callbacks(markup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]


def _by_chat(messages) -> dict:
    out: dict = {}
    for m in messages:
        out.setdefault(m[0], []).append(m)
    return out


def test_executor_complete_sends_managers_a_review_card(db):
    _request(db, "Выполнена")
    got = _by_chat(collect_notify_messages_sync(db, NUM, [_intent("executor_complete")]))

    card = got[MANAGER_TG][0]
    assert f"#{NUM}" in card[1] and "&lt;A&amp;B&gt;" in card[1]
    assert {f"confirm_completed_{NUM}", f"return_to_work_{NUM}", f"mview_{NUM}"} <= set(
        _callbacks(card.reply_markup))
    # житель получает прежний текст без менеджерских кнопок
    assert len(got[APPLICANT_TG]) == 1 and got[APPLICANT_TG][0].reply_markup is None
    assert got[APPLICANT_TG][0][1] != card[1]


def test_card_is_rendered_in_the_managers_language(db):
    _request(db, "Выполнена")
    got = _by_chat(collect_notify_messages_sync(db, NUM, [_intent("executor_complete")]))
    assert got[MANAGER_UZ_TG][0][1] != got[MANAGER_TG][0][1]
    assert f"#{NUM}" in got[MANAGER_UZ_TG][0][1]


def test_manager_who_is_the_applicant_gets_only_the_card(db):
    """Совмещение ролей: одно сообщение, менеджерское — оно несёт кнопки решения."""
    _request(db, "Выполнена")
    db.query(Request).update({"user_id": 1})
    db.commit()
    got = _by_chat(collect_notify_messages_sync(db, NUM, [_intent("executor_complete")]))
    assert len(got[MANAGER_TG]) == 1 and got[MANAGER_TG][0].reply_markup is not None


def test_applicant_return_sends_managers_a_decision_card(db):
    _request(db, "Возвращена", return_reason="Течь осталась")
    got = _by_chat(collect_notify_messages_sync(db, NUM, [_intent("applicant_return")]))

    card = got[MANAGER_TG][0]
    assert "Течь осталась" in card[1]
    assert {f"reconfirm_completed_{NUM}", f"return_to_work_{NUM}"} <= set(_callbacks(card.reply_markup))
    # исполнитель по-прежнему узнаёт о возврате
    assert EXECUTOR_TG in got


@pytest.mark.parametrize("request_kwargs,expected,forbidden", [
    # состояние важнее события: что бы ни вызвало карточку, кнопки — по заявке
    (dict(status="Выполнена"), "confirm_completed_", "req_reassign_duty_"),
    (dict(status="Возвращена"), "reconfirm_completed_", "confirm_completed_"),
    (dict(status="Новая", executor_id=None), "req_reassign_duty_", "confirm_completed_"),
    (dict(status="В работе", executor_id=4), "req_reassign_menu_", "req_reassign_duty_"),
])
def test_card_buttons_follow_request_state(request_kwargs, expected, forbidden):
    base = dict(request_number=NUM, is_returned=False, manager_confirmed=False, executor_id=None)
    base.update(request_kwargs)
    callbacks = _callbacks(manager_card_markup(SimpleNamespace(**base), "ru"))
    assert any(c.startswith(expected) for c in callbacks)
    assert not any(c.startswith(forbidden) for c in callbacks)
    assert f"mview_{NUM}" in callbacks


def test_unassigned_card_offers_assign_clarify_and_decline():
    request = SimpleNamespace(request_number=NUM, status="Новая", is_returned=False,
                              manager_confirmed=False, executor_id=None)
    callbacks = set(_callbacks(manager_card_markup(request, "ru")))
    assert {f"req_reassign_duty_{NUM}", f"req_reassign_pick_{NUM}",
            f"clarify_{NUM}", f"mgr_deny_{NUM}"} <= callbacks


# --- новая заявка без исполнителя ---------------------------------------------

def test_unassigned_request_card_goes_to_every_manager(db):
    _request(db, "Новая")
    db.query(Request).update({"executor_id": None})
    db.commit()
    got = _by_chat(collect_unassigned_messages_sync(db, NUM))

    assert set(got) == {MANAGER_TG, MANAGER_UZ_TG}
    card = got[MANAGER_TG][0]
    assert f"#{NUM}" in card[1] and "Течёт труба" in card[1]
    assert f"req_reassign_duty_{NUM}" in _callbacks(card.reply_markup)


def test_no_unassigned_card_once_somebody_took_the_request(db):
    """Между созданием и рассылкой заявку мог взять дежурный из пула."""
    _request(db, "В работе")
    assert collect_unassigned_messages_sync(db, NUM) == []
    assert collect_unassigned_messages_sync(db, "000000-000") == []


@pytest.mark.parametrize("kind,expected", [
    ("no_spec", True), ("disabled", True), ("failed", True), ("grouped", True),
    # назначена, ушла в уточнение ИИ, либо ждёт инженера (о нём пишет сверка)
    ("assigned", False), ("clarified", False), ("no_engineer", False),
])
def test_creation_dispatch_notifies_managers_only_when_nobody_is_assigned(monkeypatch, kind, expected):
    notified = []
    monkeypatch.setattr(dispatch, "auto_dispatch_new_request_sync",
                        lambda number, category, **kw: dispatch.DispatchResult(kind))
    monkeypatch.setattr(dispatch, "_notify_unassigned_sync", notified.append)

    result = dispatch.auto_dispatch_created_request_sync(NUM, "plumbing")

    assert result.kind == kind
    assert notified == ([NUM] if expected else [])


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,expected", [("grouped", True), ("assigned", False)])
async def test_api_creation_dispatch_defers_the_card_to_background(monkeypatch, kind, expected):
    async def fake_dispatch(number, category, **kw):
        return dispatch.DispatchResult(kind)

    scheduled = []
    monkeypatch.setattr(dispatch, "auto_dispatch_new_request_async", fake_dispatch)

    await dispatch.auto_dispatch_created_request_async(
        NUM, "plumbing", schedule_notify=lambda fn, *args: scheduled.append((fn.__name__, args)))

    assert scheduled == ([("notify_managers_unassigned_detached", (NUM,))] if expected else [])


# --- просрочки: дайджест с кнопкой на каждую заявку ------------------------------

def test_overdue_digest_gets_an_open_button_per_request():
    from uk_management_bot.services.ai_manager import sla

    plan = sla._Plan(
        manager_lines=["Просроченные заявки (2)",
                       "⏰ #261101-001 — Сантехника, просрочка 5 ч",
                       "⏰ #261101-002 — Лифт, просрочка 2 ч; повтор #261101-001"],
        manager_ids=[MANAGER_TG],
    )
    sla._flush_manager_digest(plan)

    (message,) = plan.messages
    assert message.chat_id == MANAGER_TG
    # по кнопке на заявку, без дублей, в порядке упоминания
    assert _callbacks(message.reply_markup) == ["mview_261101-001", "mview_261101-002"]


def test_digest_without_request_numbers_has_no_buttons():
    from uk_management_bot.utils.manager_cards import open_requests_markup

    assert open_requests_markup("Сводка: всё в порядке, 12 заявок закрыто") is None


def test_markup_survives_serialisation_for_the_api_sender():
    """API-путь шлёт разметку словарём (`telegram_send.send_message`): цвет и
    callback должны пережить `model_dump`."""
    request = SimpleNamespace(request_number=NUM, status="Выполнена", is_returned=False,
                              manager_confirmed=False, executor_id=4)
    dumped = manager_card_markup(request, "ru").model_dump(exclude_none=True)
    first = dumped["inline_keyboard"][0][0]
    assert first["callback_data"] == f"confirm_completed_{NUM}" and first["style"] == "success"


# --- устаревшая карточка: заявку уже обработал другой менеджер -------------------

@pytest.mark.asyncio
async def test_stale_card_answers_already_handled_and_drops_old_buttons(db):
    from unittest.mock import AsyncMock, MagicMock

    from uk_management_bot.handlers.admin import views

    _request(db, "Исполнено", manager_confirmed=True)  # первый менеджер уже подтвердил
    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.message.edit_reply_markup = AsyncMock()

    await views._answer_already_handled(callback, NUM, "ru", _db=db)

    text = callback.answer.await_args.args[0]
    assert text.startswith("Уже обработано") and "Исполнено" in text
    kept = _callbacks(callback.message.edit_reply_markup.await_args.kwargs["reply_markup"])
    assert kept == [f"mview_{NUM}"]


@pytest.mark.asyncio
@pytest.mark.parametrize("handler,data", [
    ("handle_manager_confirm_completed", f"confirm_completed_{NUM}"),
    ("handle_manager_reconfirm_completed", f"reconfirm_completed_{NUM}"),
])
async def test_rejected_decision_is_reported_as_already_handled(monkeypatch, handler, data):
    """Второй менеджер жмёт кнопку на своей копии карточки: канон отказывает,
    бот отвечает «Уже обработано», а не общим «ошибка подтверждения»."""
    from unittest.mock import AsyncMock, MagicMock

    from uk_management_bot.handlers.admin import views
    from uk_management_bot.services import workflow_runner
    from uk_management_bot.utils.request_workflow import InvalidTransition

    def rejected(*args, **kwargs):
        raise InvalidTransition("уже Исполнено")

    stale = AsyncMock()
    monkeypatch.setattr(workflow_runner, "run_command_sync", rejected)
    monkeypatch.setattr(views, "_answer_already_handled", stale)
    callback = MagicMock()
    callback.data = data
    callback.from_user.id = MANAGER_TG
    callback.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()

    await getattr(views, handler)(callback, MagicMock(), roles=["manager"],
                                  user=SimpleNamespace(id=1), language="ru")

    stale.assert_awaited_once()
    assert stale.await_args.args[1] == NUM
    callback.message.edit_text.assert_not_awaited()
