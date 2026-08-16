"""BUG-163: выбор квартиры терял язык пользователя.

`start_apartment_selection` объявляет `language: str = "ru"`, но три вызывающих
передавали только `(message, state)` позиционно — узбекоязычный житель получал
русские «Выберите двор / дом / квартиру». Дефект видно только по языку текста,
поэтому проверяем не рендер, а факт проброса.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TgUser


def _make_message(text="+998901234567"):
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.contact = None
    msg.from_user = MagicMock(spec=TgUser)
    msg.from_user.id = 123
    msg.answer = AsyncMock()
    return msg


def _make_callback():
    cb = MagicMock(spec=CallbackQuery)
    cb.data = "add_apartment"
    cb.from_user = MagicMock(spec=TgUser)
    cb.from_user.id = 123
    cb.answer = AsyncMock()
    cb.message = _make_message()
    return cb


def _make_state():
    st = AsyncMock()
    st.get_data = AsyncMock(return_value={})
    st.update_data = AsyncMock()
    st.set_state = AsyncMock()
    st.clear = AsyncMock()
    return st


def _passed_language(mock_call):
    """Язык, с которым реально позвали хендлер выбора квартиры."""
    if "language" in mock_call.kwargs:
        return mock_call.kwargs["language"]
    # позиционный третий аргумент (message, state, language)
    return mock_call.args[2] if len(mock_call.args) > 2 else None


class TestOnboardingKeepsLanguage:
    @pytest.mark.asyncio
    async def test_manual_phone_passes_language(self):
        from uk_management_bot.handlers.onboarding import process_manual_phone

        msg = _make_message()
        state = _make_state()

        with patch("uk_management_bot.handlers.user_apartment_selection.start_apartment_selection",
                   new=AsyncMock()) as target, \
             patch("uk_management_bot.handlers.onboarding.run_db",
                   new=AsyncMock(return_value=True)):
            await process_manual_phone(msg, state, language="uz", _db=MagicMock())

        target.assert_awaited_once()
        assert _passed_language(target.await_args) == "uz"

    @pytest.mark.asyncio
    async def test_contact_passes_language(self):
        from uk_management_bot.handlers.onboarding import process_contact

        msg = _make_message()
        msg.contact = MagicMock()
        msg.contact.phone_number = "+998901234567"
        state = _make_state()

        with patch("uk_management_bot.handlers.user_apartment_selection.start_apartment_selection",
                   new=AsyncMock()) as target, \
             patch("uk_management_bot.handlers.onboarding.run_db",
                   new=AsyncMock(return_value=True)):
            await process_contact(msg, state, language="uz", _db=MagicMock())

        target.assert_awaited_once()
        assert _passed_language(target.await_args) == "uz"


class TestProfileKeepsLanguage:
    @pytest.mark.asyncio
    async def test_add_apartment_from_profile_passes_language(self):
        """У хендлера не было `language` в сигнатуре вовсе — middleware его не
        прокидывал, и дефолт «ru» побеждал молча."""
        from uk_management_bot.handlers.user_apartments import start_add_apartment

        cb = _make_callback()
        state = _make_state()

        with patch("uk_management_bot.handlers.user_apartment_selection.start_apartment_selection_for_profile",
                   new=AsyncMock()) as target:
            await start_add_apartment(cb, state, language="uz")

        target.assert_awaited_once()
        assert _passed_language(target.await_args) == "uz"
