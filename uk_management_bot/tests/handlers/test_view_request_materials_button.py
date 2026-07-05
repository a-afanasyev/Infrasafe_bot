"""Регресс: кнопка «📦 Материалы» на РЕАЛЬНОЙ карточке заявки исполнителя.

Первая реализация PR-4 добавила кнопку в get_executor_status_actions_keyboard
(keyboards/request_status.py) — а эта функция НИГДЕ не вызывается (мёртвая), и
живая карточка исполнителя строится инлайн в handlers/requests/listing.py::
handle_view_request. Баг найден MCP-тестом бота: кнопка не появлялась.

Этот тест бьёт по живому пути: реальная sqlite-сессия + вызов handle_view_request
для заявки «В работе» назначенного исполнителя → в клавиатуре обязан быть
callback matissue_start_<номер>.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.handlers.requests import listing

EXECUTOR_TG = 6055402868


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    @contextmanager
    def fake_scope(_):
        yield session

    monkeypatch.setattr(listing, "_db_scope", fake_scope)
    monkeypatch.setattr(listing, "get_user_language", lambda *a, **k: "ru")
    yield session
    session.close()


def _seed(db, status="В работе", executor_id=1):
    user = User(id=1, telegram_id=EXECUTOR_TG, first_name="Exec",
                roles='["executor"]', active_role="executor", status="approved")
    db.add(user)
    db.flush()
    req = Request(request_number="260705-950", user_id=1, executor_id=executor_id,
                  category="electrics", status=status, description="тест",
                  urgency="medium", address="x",
                  created_at=datetime.now(timezone.utc),
                  is_returned=False, manager_confirmed=False)
    db.add(req)
    db.commit()
    return user, req


def _callback(number="260705-950"):
    cb = MagicMock()
    cb.data = f"view_request_{number}"
    cb.from_user.id = EXECUTOR_TG
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    return cb


def _state():
    st = AsyncMock()
    st.get_data = AsyncMock(return_value={"my_requests_page": 1})
    return st


def _callbacks(markup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row]


@pytest.mark.asyncio
async def test_in_progress_card_has_materials_button(db):
    _seed(db, status="В работе", executor_id=1)
    cb = _callback()
    await listing.handle_view_request(cb, _state())

    cb.message.edit_text.assert_awaited_once()
    markup = cb.message.edit_text.await_args.kwargs["reply_markup"]
    cbs = _callbacks(markup)
    assert "matissue_start_260705-950" in cbs, (
        "кнопка «📦 Материалы» отсутствует на карточке «В работе» "
        f"(callbacks: {cbs})"
    )
    # соседние действия исполнителя тоже на месте
    assert "executor_complete_260705-950" in cbs
    assert "executor_purchase_260705-950" in cbs


@pytest.mark.asyncio
async def test_purchase_status_card_has_no_materials_button(db):
    """Кнопка только в статусе «В работе» — в «Закуп» её быть не должно."""
    _seed(db, status="Закуп", executor_id=1)
    cb = _callback()
    await listing.handle_view_request(cb, _state())

    markup = cb.message.edit_text.await_args.kwargs["reply_markup"]
    cbs = _callbacks(markup)
    assert not any(c.startswith("matissue_start_") for c in cbs), cbs
