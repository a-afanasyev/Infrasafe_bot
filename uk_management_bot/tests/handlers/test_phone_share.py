"""Приём контакта вне онбординга (кнопка «Запросить номер телефона» с дашборда).

Менеджер жмёт кнопку на дашборде → API шлёт пользователю сообщение с
request_contact-клавиатурой → пользователь делится контактом БЕЗ активного
FSM-состояния. До этой фичи такой contact-месседж молча проваливался мимо
всех хендлеров (onboarding ловит contact только в waiting_for_phone).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message
from aiogram.types import User as TgUser


def _make_contact_message(*, own: bool = True, phone: str = "+998901234567"):
    msg = MagicMock(spec=Message)
    msg.text = None
    msg.from_user = MagicMock(spec=TgUser)
    msg.from_user.id = 123
    msg.contact = MagicMock()
    msg.contact.phone_number = phone
    msg.contact.user_id = 123 if own else 999
    msg.answer = AsyncMock()
    return msg


class TestPhoneShareHandler:
    @pytest.mark.asyncio
    async def test_own_contact_saved(self):
        from uk_management_bot.handlers.phone_share import receive_shared_contact

        msg = _make_contact_message()
        with patch("uk_management_bot.handlers.phone_share.run_db",
                   new=AsyncMock(return_value=True)) as run_db:
            await receive_shared_contact(msg, language="ru", _db=MagicMock())

        run_db.assert_awaited_once()
        msg.answer.assert_awaited_once()
        # Подтверждение с номером и снятие reply-клавиатуры.
        text = msg.answer.await_args.args[0]
        assert "+998901234567" in text
        assert msg.answer.await_args.kwargs["reply_markup"] is not None

    @pytest.mark.asyncio
    async def test_phone_without_plus_normalized(self):
        from uk_management_bot.handlers.phone_share import receive_shared_contact

        msg = _make_contact_message(phone="998901234567")
        captured: list = []

        async def fake_run_db(unit, db=None):
            fake_session = MagicMock()
            captured.append(unit(fake_session))
            return True

        with patch("uk_management_bot.handlers.phone_share.run_db", new=fake_run_db), \
             patch("uk_management_bot.handlers.phone_share._apply_phone",
                   side_effect=lambda s, tg_id, phone: phone) :
            await receive_shared_contact(msg, language="ru", _db=MagicMock())

        assert captured == ["+998901234567"]

    @pytest.mark.asyncio
    async def test_foreign_contact_rejected(self):
        from uk_management_bot.handlers.phone_share import receive_shared_contact

        msg = _make_contact_message(own=False)
        with patch("uk_management_bot.handlers.phone_share.run_db",
                   new=AsyncMock(return_value=True)) as run_db:
            await receive_shared_contact(msg, language="ru", _db=MagicMock())

        run_db.assert_not_awaited()
        msg.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_user_gets_error(self):
        from uk_management_bot.handlers.phone_share import receive_shared_contact

        msg = _make_contact_message()
        with patch("uk_management_bot.handlers.phone_share.run_db",
                   new=AsyncMock(return_value=False)):
            await receive_shared_contact(msg, language="ru", _db=MagicMock())

        msg.answer.assert_awaited_once()
        assert "+998901234567" not in msg.answer.await_args.args[0]
