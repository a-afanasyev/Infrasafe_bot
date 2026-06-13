"""PR-19 — FE-094: локализация bot-side ошибок address_service (гибрид).

Частые без-интерполяции ошибки несут стабильный `code` → handler локализует
через `localize_address_error` (ru/uz); интерполированные сообщения
(`AddressConflict` без кода) фоллбэчат на русский текст как есть.
"""
import inspect

import pytest

from uk_management_bot.services.addresses.exceptions import (
    AddressError, AddressNotFound, AddressConflict, AddressValidationError,
)
from uk_management_bot.services.addresses import core as addr_core
from uk_management_bot.utils.address_helpers import localize_address_error
from uk_management_bot.utils.helpers import get_text


CODES = [
    "yard_not_found", "building_not_found", "apartment_not_found", "request_not_found",
    "yard_inactive", "building_inactive", "apartment_inactive",
    "request_already_pending", "already_resident",
    "save_failed", "delete_failed", "request_create_failed", "request_process_failed",
]


class TestAddressErrorCode:
    def test_code_defaults_none(self):
        assert AddressError("msg").code is None
        assert AddressNotFound("msg").code is None

    def test_code_carried(self):
        e = AddressNotFound("Двор не найден", code="yard_not_found")
        assert e.code == "yard_not_found"
        assert str(e) == "Двор не найден"  # сообщение сохранено (для API/логов)

    def test_subclasses_accept_code(self):
        for cls in (AddressConflict, AddressValidationError):
            assert cls("x", code="c").code == "c"


class TestLocalizeHelper:
    @pytest.mark.parametrize("code", CODES)
    def test_known_code_localized_ru_and_uz(self, code):
        ru = localize_address_error(code, "ru")
        uz = localize_address_error(code, "uz")
        # резолвится (не равно сырому коду) на обоих языках
        assert ru != code and uz != code
        # ru и uz различаются (реально переведено), кроме идентичных по природе
        assert ru and uz

    def test_interpolated_message_falls_back_as_is(self):
        msg = "Двор с названием 'X' уже существует"
        assert localize_address_error(msg, "uz") == msg
        assert localize_address_error(msg, "ru") == msg

    def test_unknown_code_returns_as_is(self):
        assert localize_address_error("totally_unknown_code", "uz") == "totally_unknown_code"

    def test_empty_returns_empty(self):
        assert localize_address_error(None, "uz") == ""
        assert localize_address_error("", "ru") == ""


class TestLocaleCompleteness:
    @pytest.mark.parametrize("code", CODES)
    @pytest.mark.parametrize("lang", ["ru", "uz"])
    def test_code_present_in_locale(self, code, lang):
        key = f"address_errors.{code}"
        val = get_text(key, language=lang)
        assert val != key, f"{lang}: отсутствует локаль для {key}"


class TestCoreRaisesCoded:
    def test_not_found_and_inactive_raises_have_codes(self):
        src = inspect.getsource(addr_core)
        # ключевые без-интерполяции raise'ы несут code=
        for needle in (
            'code="yard_not_found"', 'code="building_not_found"',
            'code="apartment_not_found"', 'code="request_not_found"',
            'code="yard_inactive"', 'code="building_inactive"',
            'code="apartment_inactive"',
        ):
            assert needle in src, f"core не содержит {needle}"
