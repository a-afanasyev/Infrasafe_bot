"""Кнопка «📷 Фото до работ» на живой карточке исполнителя (handle_view_request).

Решение владельца 2026-10-31: в любом незакрытом статусе своей заявки (В работе,
Закуп, Уточнение, Возвращена); у закрытой и у чужой — нет.
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
NUMBER = "260705-951"
BEFORE_CB = f"executor_before_{NUMBER}"


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


def _seed(db, *, status, executor_id=1, is_returned=False):
    db.add(User(id=1, telegram_id=EXECUTOR_TG, first_name="Exec",
                roles='["executor"]', active_role="executor", status="approved"))
    db.add(User(id=2, telegram_id=1, first_name="Other",
                roles='["executor"]', active_role="executor", status="approved"))
    db.flush()
    db.add(Request(request_number=NUMBER, user_id=2, executor_id=executor_id,
                   category="electrics", status=status, description="тест",
                   urgency="medium", address="x",
                   created_at=datetime.now(timezone.utc),
                   is_returned=is_returned, manager_confirmed=False))
    db.commit()


async def _callbacks(db) -> list[str]:
    cb = MagicMock()
    cb.data = f"view_request_{NUMBER}"
    cb.from_user.id = EXECUTOR_TG
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"my_requests_page": 1})
    await listing.handle_view_request(cb, state)
    markup = cb.message.edit_text.await_args.kwargs["reply_markup"]
    return [b.callback_data for row in markup.inline_keyboard for b in row]


@pytest.mark.asyncio
@pytest.mark.parametrize("status, returned", [
    ("В работе", False), ("Закуп", False), ("Уточнение", False), ("Исполнено", True),
])
async def test_open_own_request_has_before_button(db, status, returned):
    _seed(db, status=status, is_returned=returned)
    assert BEFORE_CB in await _callbacks(db)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["Выполнена", "Исполнено", "Принято", "Отменена"])
async def test_closed_request_has_no_before_button(db, status):
    _seed(db, status=status)
    assert BEFORE_CB not in await _callbacks(db)
