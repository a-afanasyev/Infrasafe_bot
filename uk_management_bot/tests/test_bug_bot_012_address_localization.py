"""
BUG-BOT-012: UZ-профиль показывает `кв.` (RU shorthand).

После фикса `localize_address(addr, language="uz")` не содержит "кв." и "д."
(используются i18n-строки address.apartment_short / building_short).
"""
import pytest

from uk_management_bot.utils.address_helpers import localize_address


class TestBugBot012AddressLocalization:
    @pytest.mark.parametrize("address", [
        "Yangi Olmazor, 14V, кв. 54",
        "Дом: 14, кв. 54",
        "д. 14, кв. 54",
    ])
    def test_uz_address_does_not_contain_ru_shorthand(self, address):
        result = localize_address(address, language="uz")
        assert "кв." not in result, f"UZ-адрес содержит 'кв.': '{result}'"

    def test_uz_apartment_replaced_with_uz_suffix(self):
        result = localize_address("Yangi Olmazor, 14V, кв. 54", language="uz")
        assert "xon." in result, f"Ожидался 'xon.' в '{result}'"
        assert "54" in result

    @pytest.mark.parametrize("number", ["12А", "3/1", "5Б"])
    def test_uz_freeform_apartment_number_localized(self, number):
        """COD-09: freeform-номера квартир ('12А', '3/1') тоже локализуются."""
        result = localize_address(f"ул. Ленина 10, кв. {number}", language="uz")
        assert "кв." not in result, f"UZ-адрес содержит 'кв.': '{result}'"
        assert number in result, f"Номер '{number}' потерялся: '{result}'"

    def test_uz_building_short_replaced(self):
        result = localize_address("д. 14, кв. 54", language="uz")
        assert "д. " not in result, f"UZ-адрес содержит 'д.': '{result}'"
        assert "uy" in result

    def test_ru_address_kept_unchanged(self):
        original = "Дом: 14, кв. 54"
        result = localize_address(original, language="ru")
        assert result == original

    def test_empty_address_returns_empty(self):
        assert localize_address("", language="uz") == ""
        assert localize_address(None, language="uz") is None

    def test_locale_keys_exist(self):
        from uk_management_bot.utils.helpers import get_text
        for lang in ("ru", "uz"):
            apt = get_text("address.apartment_short", language=lang)
            bld = get_text("address.building_short", language=lang)
            assert apt and apt != "address.apartment_short", lang
            assert bld and bld != "address.building_short", lang
