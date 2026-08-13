"""BUG-147 — autofill.parse_apartment_range: RU-хардкод текстов ошибок диапазона.

Тексты ValueError уходили пользователю через range_parse_error.format(error=e)
как есть — UZ-пользователь получал русскую вставку внутри узбекского текста.
Фикс: исключение несёт код ошибки + параметры, хендлер рендерит по ключу локали
(str(e) остаётся русским фолбэком для логов и plain-ValueError).
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from uk_management_bot.handlers.address_apartments import autofill
from uk_management_bot.handlers.address_apartments.autofill import (
    parse_apartment_range,
)
from uk_management_bot.utils.helpers import get_text


# ---------------------------------------------------------------------------
# Исключения несут локализуемый код + параметры
# ---------------------------------------------------------------------------

class TestRangeErrorsCarryLocaleCode:
    @pytest.mark.parametrize(
        "raw,code,params",
        [
            ("abc-def", "range_invalid_chunk", {"part": "abc-def"}),
            ("5-1", "range_reversed", {"start": 5, "end": 1}),
            ("xx", "range_invalid_number", {"part": "xx"}),
        ],
    )
    def test_error_has_code_and_params(self, raw, code, params):
        with pytest.raises(ValueError) as ei:
            parse_apartment_range(raw)
        assert getattr(ei.value, "code", None) == code, (
            f"исключение не несёт код ошибки: {ei.value!r}"
        )
        assert getattr(ei.value, "params", None) == params

    def test_locale_keys_exist_in_both_locales(self):
        """Каждый код рендерится ключом в ru И uz (не эхо самого ключа)."""
        for code in ("range_invalid_chunk", "range_reversed", "range_invalid_number"):
            key = f"address_apartments.handlers.{code}"
            for lang in ("ru", "uz"):
                text = get_text(key, language=lang)
                assert text != key, f"нет ключа {key} в локали {lang}"


# ---------------------------------------------------------------------------
# Хендлер рендерит ошибку на языке пользователя
# ---------------------------------------------------------------------------

def _make_message(text):
    message = MagicMock()
    message.text = text
    message.answer = AsyncMock()
    return message


class TestHandlerLocalizesRangeError:
    async def test_uz_user_gets_uz_error_text(self):
        message = _make_message("5-1")
        state = AsyncMock()

        await autofill.process_autofill_range(message, state, language="uz")

        message.answer.assert_awaited_once()
        sent = message.answer.await_args.args[0]
        assert "Некорректный" not in sent, (
            f"русская вставка ушла UZ-пользователю: {sent!r}"
        )
        expected_error = get_text(
            "address_apartments.handlers.range_reversed", language="uz"
        ).format(start=5, end=1)
        assert expected_error in sent

    async def test_ru_user_still_gets_ru_error_text(self):
        message = _make_message("abc-def")
        state = AsyncMock()

        await autofill.process_autofill_range(message, state, language="ru")

        sent = message.answer.await_args.args[0]
        expected_error = get_text(
            "address_apartments.handlers.range_invalid_chunk", language="ru"
        ).format(part="abc-def")
        assert expected_error in sent
