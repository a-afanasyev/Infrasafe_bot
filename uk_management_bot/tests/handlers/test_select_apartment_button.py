"""Кнопка «🏠 Выбрать квартиру» в онбординге жителя была мёртвой.

`handlers/base.py` рисует её текстом `base.handlers.btn_select_apartment`, но
фильтра на этот текст не было ни в одном хендлере, а `start_apartment_selection`
объявлена без декоратора и вызывалась только программно из onboarding после
ввода телефона. Нажатие первой кнопкой не давало ничего — молча.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message
from aiogram.types import User as TgUser


def _make_message(text=""):
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.from_user = MagicMock(spec=TgUser)
    msg.from_user.id = 123
    msg.answer = AsyncMock()
    return msg


def _make_state():
    st = AsyncMock()
    st.clear = AsyncMock()
    st.set_state = AsyncMock()
    st.update_data = AsyncMock()
    st.get_data = AsyncMock(return_value={})
    return st


class TestSelectApartmentButtonWired:
    def test_ssot_texts_match_what_the_keyboard_renders(self):
        """SSOT-паритет: ловим ровно те строки, что кладём на клавиатуру.
        Заведи фильтр на другой ключ локали — воспроизведёшь тот же дефект."""
        from uk_management_bot.utils.button_texts import get_select_apartment_texts
        from uk_management_bot.utils.helpers import get_text

        texts = get_select_apartment_texts()

        for lang in ("ru", "uz"):
            rendered = get_text("base.handlers.btn_select_apartment", language=lang)
            assert rendered in texts, f"{lang}: «{rendered}» не ловится фильтром"

    def test_handler_is_registered_in_router(self):
        from uk_management_bot.handlers import user_apartment_selection as mod

        names = [h.callback.__name__ for h in mod.router.message.handlers]
        assert "start_apartment_selection" in names

    @pytest.mark.asyncio
    async def test_button_is_not_mistaken_for_a_phone_number(self):
        """В состоянии ввода телефона оживлённая кнопка не должна разбираться
        как номер (`process_manual_phone` фильтрует системные тексты списком)."""
        from uk_management_bot.handlers.onboarding import process_manual_phone
        from uk_management_bot.utils.helpers import get_text

        msg = _make_message(text=get_text("base.handlers.btn_select_apartment", language="ru"))
        state = _make_state()

        with patch("uk_management_bot.handlers.onboarding.Validator") as MockValidator:
            await process_manual_phone(msg, state, _db=MagicMock())

        MockValidator.validate_phone.assert_not_called()
        state.clear.assert_awaited()
