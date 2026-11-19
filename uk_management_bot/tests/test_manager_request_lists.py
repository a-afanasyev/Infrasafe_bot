"""Списки заявок менеджера: реальная пагинация по виду списка.

Раньше каждый список брал `limit=10` и рисовал пейджер «1/1», а обработчик
`mreq_page_` листал только активные — 11-я новая заявка в боте была не видна.
SQL проверяется на настоящей sqlite-сессии, не на моках.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from types import SimpleNamespace

from aiogram.exceptions import TelegramBadRequest

from uk_management_bot.handlers import unaccepted_requests
from uk_management_bot.handlers.admin import lists, shared, views
from uk_management_bot.keyboards.admin import get_manager_request_list_kb
from uk_management_bot.services.admin_handler_service import AdminHandlerService

T0 = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine)()
    s.add(User(id=1, telegram_id=1, first_name="U", roles='["applicant"]',
               active_role="applicant", status="approved", language="ru"))
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _add(db, n: int, status: str, start: int = 1, **extra) -> None:
    for i in range(start, start + n):
        db.add(Request(
            request_number=f"261101-{i:03d}", user_id=1, category="plumbing",
            description="d", urgency="Обычная", status=status, address=f"Дом {i}",
            created_at=T0 + timedelta(minutes=i), **extra,
        ))
    db.commit()


def _texts(markup) -> list[str]:
    return [b.text for row in markup.inline_keyboard for b in row]


def _callbacks(markup) -> list[str]:
    # кнопки копирования и серые кнопки callback_data не несут
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]


def test_service_pages_cover_whole_list_without_overlap(db):
    _add(db, 23, "Новая")
    _add(db, 4, "В работе", start=100)
    svc = AdminHandlerService(db)

    assert svc.count_manager_list("new") == 23
    assert svc.count_manager_list("active") == 4
    pages = [svc.page_manager_list("new", offset, 10) for offset in (0, 10, 20)]
    assert [len(p) for p in pages] == [10, 10, 3]
    numbers = [r.request_number for p in pages for r in p]
    assert len(set(numbers)) == 23
    # новые — свежие сверху
    assert numbers[0] == "261101-023"


def test_service_rejects_unknown_kind(db):
    with pytest.raises(ValueError):
        AdminHandlerService(db).count_manager_list("nope")


def test_build_list_first_page_has_real_pager(db):
    _add(db, 23, "Новая")
    text, markup = lists.build_manager_list(AdminHandlerService(db), "new", 1, "ru")

    assert "Новые заявки" in text
    assert "1/3" in _texts(markup)
    assert "mreq_page_new_2" in _callbacks(markup)
    assert sum(c.startswith("ml:new:1:") for c in _callbacks(markup)) == 10


def test_build_list_clamps_page_and_handles_empty(db):
    text, markup = lists.build_manager_list(AdminHandlerService(db), "new", 1, "ru")
    assert markup is None and text == "Нет новых заявок"

    _add(db, 12, "Новая")
    _, markup = lists.build_manager_list(AdminHandlerService(db), "new", 99, "ru")
    assert "2/2" in _texts(markup)


def test_unaccepted_list_shows_waiting_time(db):
    _add(db, 1, "Выполнена", manager_confirmed=True,
         completed_at=datetime.now(timezone.utc) - timedelta(hours=5, minutes=10))
    _, markup = lists.build_manager_list(AdminHandlerService(db), "unaccepted", 1, "ru")
    assert any("⏳ 5ч" in t for t in _texts(markup))


def test_keyboard_keeps_legacy_signature_and_renders_suffix():
    items = [{"request_number": "261101-001", "category": "Сантехника",
              "address": "Дом 1", "status": "Новая", "suffix": "⏳ 2ч 5м"}]
    markup = get_manager_request_list_kb(items, 2, 3)
    assert any(t.endswith("⏳ 2ч 5м") for t in _texts(markup))
    # старые вызовы без kind листают активные, как и раньше
    assert {"mreq_page_active_1", "mreq_page_active_3"} <= set(_callbacks(markup))


@pytest.mark.asyncio
@pytest.mark.parametrize("data", ["mreq_page_new_2", "mreq_page_2"])
async def test_pagination_handler_pages_the_requested_list(db, data):
    """`mreq_page_new_2` листает новые; старый формат `mreq_page_2` — активные."""
    _add(db, 12, "Новая")
    _add(db, 12, "В работе", start=100)
    callback = MagicMock()
    callback.data = data
    callback.from_user.id = 1
    callback.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()

    await views.handle_manager_request_pagination(
        callback, db, roles=["manager"], active_role="manager", user=None, language="ru")

    callback.message.edit_text.assert_awaited_once()
    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    expected_first = "261101-002" if data == "mreq_page_new_2" else "261101-10"
    opened = [c for c in _callbacks(markup) if c.startswith("ml:")]
    assert len(opened) == 2 and expected_first in opened[0]
    callback.answer.assert_awaited_once_with()


# --- правки по ревью этапа 0 -------------------------------------------------

def _req(status: str, **extra):
    base = dict(request_number="261101-001", status=status, is_returned=False,
                manager_confirmed=False, executor_id=None, completion_report=None)
    base.update(extra)
    return SimpleNamespace(**base)


def _card_callbacks(request, **kwargs) -> list[str]:
    params = dict(active_assignment=None, has_media=False, roles=["manager"],
                  viewer_id=1, lang="ru", back=None)
    params.update(kwargs)
    return _callbacks(views.build_manager_card_keyboard(request, **params))


def test_list_buttons_carry_list_kind_and_page():
    items = [{"request_number": "261101-001", "category": "c", "address": "a", "status": "Новая"}]
    markup = get_manager_request_list_kb(items, 3, 3, kind="new")
    assert "ml:new:3:261101-001" in _callbacks(markup)


@pytest.mark.asyncio
async def test_card_opened_from_list_keeps_page_for_back(db, monkeypatch):
    """Сквозной путь: `ml:new:2:<номер>` → карточка с возвратом на страницу 2."""
    from uk_management_bot.keyboards.admin import ManagerListCb

    _add(db, 12, "Новая")
    monkeypatch.setattr(views, "get_completion_media_entries", AsyncMock(return_value=[]))
    callback = MagicMock()
    callback.data = "ml:new:2:261101-002"
    callback.from_user.id = 1
    callback.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()

    await views.handle_manager_view_request(
        callback, db, roles=["manager"], active_role="manager", user=None, language="ru",
        callback_data=ManagerListCb(kind="new", page=2, num="261101-002"))

    assert "261101-002" in callback.message.edit_text.await_args.args[0]
    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    assert "mreq_page_new_2" in _callbacks(markup)
    # один хендлер зарегистрирован на оба входа: mview_ и ml:
    registered = [h for h in views.router.callback_query.handlers
                  if h.callback is views.handle_manager_view_request]
    assert len(registered) == 2


def test_card_back_button_returns_to_the_same_page():
    assert "mreq_page_new_3" in _card_callbacks(_req("Новая"), back=("new", 3))
    assert "mreq_page_review_2" in _card_callbacks(_req("Выполнена"), back=("review", 2))
    unaccepted = _card_callbacks(_req("Исполнено"), back=("unaccepted", 2))
    assert "mreq_page_unaccepted_2" in unaccepted and "unaccepted_back_to_list" not in unaccepted
    # без контекста списка (старые сообщения, вход из других экранов) — прежний возврат
    assert "mreq_back_261101-001" in _card_callbacks(_req("Новая"))


def test_returned_request_card_offers_its_decisions():
    """Заявка, возвращённая жителем, раньше попадала в общую ветку без решений."""
    for request in (_req("Возвращена"), _req("Исполнено", is_returned=True)):
        callbacks = _card_callbacks(request)
        assert "reconfirm_completed_261101-001" in callbacks
        assert "return_to_work_261101-001" in callbacks


def test_awaiting_manager_card_confirms_not_force_accepts():
    """«Выполнена» подтверждается MANAGER_CONFIRM; MANAGER_FORCE_ACCEPT (кнопка
    reconfirm) из «Выполнена» канон не пускает — даже для легаси is_returned."""
    callbacks = _card_callbacks(_req("Выполнена", is_returned=True))
    assert "confirm_completed_261101-001" in callbacks
    assert "reconfirm_completed_261101-001" not in callbacks


@pytest.mark.asyncio
async def test_pagination_ignores_message_not_modified(db):
    _add(db, 3, "Новая")
    callback = MagicMock()
    callback.data = "mreq_page_new_1"
    callback.from_user.id = 1
    callback.answer = AsyncMock()
    callback.message.edit_text = AsyncMock(side_effect=TelegramBadRequest(
        method=MagicMock(), message="Bad Request: message is not modified"))

    await views.handle_manager_request_pagination(
        callback, db, roles=["manager"], active_role="manager", user=None, language="ru")

    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_back_from_unaccepted_card_uses_the_paginated_list(db):
    _add(db, 12, "Исполнено", completed_at=datetime.now(timezone.utc) - timedelta(hours=2))
    callback = MagicMock()
    callback.data = "unaccepted_back_to_list"
    callback.from_user.id = 1
    callback.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()

    await unaccepted_requests.handle_back_to_unaccepted_list(
        callback, roles=["manager"], active_role="manager", user=None, language="ru", _db=db)

    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    assert "1/2" in _texts(markup) and "mreq_page_unaccepted_2" in _callbacks(markup)
    assert any("⏳ 2" in t for t in _texts(markup))


def test_delete_admin_ids_tolerates_garbage(monkeypatch):
    monkeypatch.setenv("ADMIN_USER_IDS", "12, x, ,34")
    assert shared.delete_admin_ids() == frozenset({12, 34})


# --- этап 3: копирование номера и телефона --------------------------------------

def _copy_buttons(request, **kwargs) -> dict:
    params = dict(active_assignment=None, has_media=False, roles=["manager"],
                  viewer_id=1, lang="ru", back=None)
    params.update(kwargs)
    markup = views.build_manager_card_keyboard(request, **params)
    return {b.copy_text.text: b.text for row in markup.inline_keyboard for b in row
            if b.copy_text is not None}


def test_card_offers_copy_of_number_and_applicant_phone():
    copies = _copy_buttons(_req("Новая"), applicant_phone="+998901112233")
    assert set(copies) == {"261101-001", "+998901112233"}


def test_no_phone_copy_button_without_a_phone():
    assert set(_copy_buttons(_req("Новая"))) == {"261101-001"}
    # и в карточках других состояний номер копируется так же
    assert "261101-001" in _copy_buttons(_req("Выполнена"))
    assert "261101-001" in _copy_buttons(_req("Исполнено"))


# --- этап 3: архив листается, а не обрывается на десятой заявке -----------------

@pytest.mark.asyncio
async def test_archive_is_a_paginated_list_not_ten_separate_messages(db):
    _add(db, 14, "Принято")
    _add(db, 3, "Отменена", start=100)
    message = MagicMock()
    message.from_user.id = 1
    message.answer = AsyncMock()

    await lists.list_archive_requests(
        message, db, roles=["manager"], active_role="manager", user=None, language="ru")

    message.answer.assert_awaited_once()          # одно сообщение, не 10 + «конец архива»
    assert "17" in message.answer.await_args.args[0]
    markup = message.answer.await_args.kwargs["reply_markup"]
    assert "1/2" in _texts(markup) and "mreq_page_archive_2" in _callbacks(markup)


def test_archived_request_card_is_read_only():
    callbacks = _card_callbacks(_req("Принято"), back=("archive", 2))
    assert not any(c.startswith(("accept_", "mgr_deny_", "clarify_", "purchase_", "mgr_complete_"))
                   for c in callbacks)
    assert "mreq_page_archive_2" in callbacks
