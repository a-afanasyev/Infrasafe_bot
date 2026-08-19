"""BUG-157 (механика): сохранение заявки не открывает сессию на event loop.

Два последних места, где создание заявки шло мимо канона run_db:

  * `inspector_requests.inspector_confirm` открывал `session_scope` прямо в
    async и передавал живую сессию третьим позиционным в `save_request` —
    ядро исполнялось синхронно на loop'е;
  * `requests/create_callbacks.handle_confirmation` делал то же через
    `_db_scope(None)` — тестовый seam работал как прод-механизм.

Пин: третьим позиционным в `save_request` уходит РОВНО значение seam'а
хендлера (`_db`; в проде None → run_db уводит ядро в поток). До правки тесты
красные: старый код передаёт свежую сессию контекст-менеджера, а у
`handle_confirmation` seam'а нет вовсе (TypeError).

Первые тесты этих хендлеров вообще (раньше — только гейты/инвентари).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.user import User


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _state(data):
    store = dict(data)

    async def _get_data():
        return dict(store)

    st = AsyncMock()
    st.get_data = AsyncMock(side_effect=_get_data)
    return st


def _callback(tg_id):
    cb = MagicMock()
    cb.from_user.id = tg_id
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    cb.bot = MagicMock()
    return cb


class TestInspectorConfirmSeam:
    # Гейт `_approved_inspector` патчится: он импортирует
    # `api.dependencies._parse_user_roles` (fastapi), которого нет в лёгком
    # локальном venv; сама роль-проверка запинена authz-BASELINE'ом отдельно.
    # Здесь свойство — куда уходит сессия сохранения.
    @pytest.mark.asyncio
    async def test_save_request_receives_handler_seam(self, db):
        from uk_management_bot.handlers import inspector_requests

        db.add(User(id=1, telegram_id=555, username="insp", first_name="I",
                    roles='["inspector"]', status="approved", language="ru"))
        db.commit()

        cb = _callback(555)
        saved = AsyncMock(return_value="260819-001")
        state = _state({"category": "Электрика"})

        with patch("uk_management_bot.handlers.requests.save_request", saved), \
             patch.object(inspector_requests, "_approved_inspector", lambda s, tg: True):
            await inspector_requests.inspector_confirm(cb, state, _db=db)

        assert saved.await_count == 1
        args = saved.await_args.args
        assert args[2] is db, (
            "третьим позиционным обязан идти seam хендлера (_db), а не сессия "
            "локального session_scope — иначе ядро исполняется на event loop"
        )
        assert saved.await_args.kwargs.get("source") == "inspector"
        state.clear.assert_awaited()
        cb.message.edit_text.assert_awaited()

    @pytest.mark.asyncio
    async def test_non_inspector_is_rejected_before_save(self, db):
        from uk_management_bot.handlers import inspector_requests

        db.add(User(id=1, telegram_id=666, username="app", first_name="A",
                    roles='["applicant"]', status="approved", language="ru"))
        db.commit()

        cb = _callback(666)
        saved = AsyncMock(return_value="260819-002")

        with patch("uk_management_bot.handlers.requests.save_request", saved), \
             patch.object(inspector_requests, "_approved_inspector", lambda s, tg: False):
            await inspector_requests.inspector_confirm(cb, _state({}), _db=db)

        saved.assert_not_awaited()


class TestHandleConfirmationSeam:
    @pytest.mark.asyncio
    async def test_save_request_receives_handler_seam(self, db):
        from uk_management_bot.handlers.requests import create_callbacks

        db.add(User(id=1, telegram_id=777, username="app", first_name="A",
                    roles='["applicant"]', status="approved", language="ru"))
        db.commit()

        cb = _callback(777)
        cb.data = "confirm_yes"
        saved = AsyncMock(return_value="260819-003")

        with patch.object(create_callbacks, "save_request", saved):
            await create_callbacks.handle_confirmation(
                cb, _state({"category": "electrician", "urgency": "low"}), _db=db,
            )

        assert saved.await_count == 1
        args = saved.await_args.args
        assert args[2] is db, (
            "seam хендлера обязан уходить сквозным третьим позиционным в "
            "save_request; в проде это None — сессию открывает run_db в потоке"
        )
