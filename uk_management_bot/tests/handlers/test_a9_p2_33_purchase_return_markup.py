"""A9-P2-33: «Вернуть в работу» из закупа — edit_text без ReplyKeyboardMarkup.

`handle_return_to_work` после успешного MANAGER_PURCHASE_DONE редактировал
карточку заявки (inline-сообщение) с ReplyKeyboardMarkup главного меню.
editMessageText принимает только inline-клавиатуру → исключение → менеджер
видел «Произошла ошибка», хотя заявка уже вернулась в работу.

Хендлер настоящий, запись настоящая (run_command_sync на sqlite), Telegram
застаблен уровнем ниже — Bot-сессией, которая держит контракт Bot API:
EditMessageText с не-inline reply_markup → TelegramBadRequest.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery, EditMessageText
from aiogram.types import CallbackQuery, InlineKeyboardMarkup
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.database import session as session_mod
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_PURCHASE,
)

MANAGER_TG = 3
RETURNED = "260923-001"
OTHER = "260923-002"


class BotApiContractSession(BaseSession):
    """Bot-сессия без сети, но с контрактом Bot API для editMessageText."""

    def __init__(self):
        super().__init__()
        self.calls: list = []

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, EditMessageText):
            markup = method.reply_markup
            if markup is not None and not isinstance(markup, InlineKeyboardMarkup):
                raise TelegramBadRequest(method=method, message="Bad Request: inline keyboard expected")
        return True

    async def stream_content(self, url, headers=None, timeout=30,
                             chunk_size=65536, raise_for_status=True):
        raise NotImplementedError
        yield b""  # pragma: no cover

    async def close(self):
        pass


@pytest.fixture()
def factory(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    from uk_management_bot.database.models import (  # noqa: F401
        audit, rating, request, request_assignment, user, webhook_outbox,
    )
    from uk_management_bot.database.session import Base
    Base.metadata.create_all(bind=engine)
    SF = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    # run_command_sync берёт SessionLocal module-global lookup'ом.
    monkeypatch.setattr(session_mod, "SessionLocal", SF)
    yield SF
    engine.dispose()


def _seed(SF, numbers):
    from uk_management_bot.database.models.request import Request
    from uk_management_bot.database.models.user import User

    s = SF()
    s.add(User(id=2, telegram_id=2, first_name="Resident", roles='["applicant"]',
               active_role="applicant", status="approved", language="ru"))
    s.add(User(id=MANAGER_TG, telegram_id=MANAGER_TG, first_name="Mgr", roles='["manager"]',
               active_role="manager", status="approved", language="ru"))
    s.add(User(id=4, telegram_id=4, first_name="Exec", roles='["executor"]',
               active_role="executor", status="approved", language="ru"))
    for n in numbers:
        s.add(Request(request_number=n, user_id=2, category="electricity",
                      address="ул. <Тест>, 1", description="d", urgency="high",
                      status=REQUEST_STATUS_PURCHASE, executor_id=4,
                      requested_materials="кабель 10 м"))
    s.commit()
    s.close()


def _callback(bot):
    return CallbackQuery.model_validate({
        "id": "cbq-1",
        "from": {"id": MANAGER_TG, "is_bot": False, "first_name": "Mgr"},
        "chat_instance": "ci",
        "data": f"purchase_return_to_work_{RETURNED}",
        "message": {
            "message_id": 10,
            "date": int(datetime.now(timezone.utc).timestamp()),
            "chat": {"id": MANAGER_TG, "type": "private"},
            "text": f"#{RETURNED} карточка закупа",
        },
    }, context={"bot": bot})


@pytest.mark.asyncio
@pytest.mark.parametrize("numbers", [[RETURNED], [RETURNED, OTHER]],
                         ids=["list-becomes-empty", "list-remains"])
async def test_return_to_work_answers_without_error(factory, numbers):
    from uk_management_bot.database.models.request import Request
    from uk_management_bot.database.models.user import User
    from uk_management_bot.handlers.admin.materials import handle_return_to_work

    _seed(factory, numbers)
    tg_session = BotApiContractSession()
    bot = Bot(token="42:TEST", session=tg_session)
    db = factory()
    manager = db.get(User, MANAGER_TG)

    await handle_return_to_work(_callback(bot), db=db, roles=["manager"],
                                active_role="manager", user=manager, language="ru")

    edits = [m for m in tg_session.calls if isinstance(m, EditMessageText)]
    assert len(edits) == 1
    assert edits[0].reply_markup is None or isinstance(edits[0].reply_markup, InlineKeyboardMarkup)
    alerts = [m for m in tg_session.calls
              if isinstance(m, AnswerCallbackQuery) and m.show_alert]
    assert alerts == [], "менеджер не должен видеть «Произошла ошибка» после успешного возврата"

    check = factory()
    assert check.query(Request).filter_by(request_number=RETURNED).one().status == REQUEST_STATUS_IN_PROGRESS
    check.close()
    db.close()
