"""Тесты `work_report_service.derive_public_address` (T5).

Чистая функция без I/O — все Request/Apartment/Building/Yard здесь
транзиентные (не сохраняются в БД), связи проставлены напрямую в Python, что
не триггерит lazy-load. Основной инвариант всей фичи «до/после»: публичный
адрес квартирной заявки НИКОГДА не содержит "кв." — иначе анонимизация всей
витрины ломается.
"""
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services.work_report_service import derive_public_address


def _base_request(**overrides) -> Request:
    defaults = dict(
        request_number="260725-001",
        user_id=1,
        category="plumbing",
        description="test",
        urgency="low",
    )
    defaults.update(overrides)
    return Request(**defaults)


def test_apartment_address_never_contains_apartment_number():
    """Core privacy invariant: "кв." must never leak into the public address."""
    yard = Yard(id=1, name="Двор")
    building = Building(id=1, address="ул. X, д. 5", yard=yard)
    apartment = Apartment(id=1, apartment_number="42", building=building)
    request = _base_request(
        address_type="apartment",
        apartment_obj=apartment,
        address="ул. X, д. 5, кв. 42 (Двор)",  # legacy field — irrelevant here
    )

    result = derive_public_address(request)

    assert result == "ул. X, д. 5 (Двор)"
    assert "кв." not in result


def test_yard_address_uses_yard_name():
    yard = Yard(id=2, name="Двор Солнечный")
    request = _base_request(address_type="yard", yard_obj=yard)

    assert derive_public_address(request) == "Двор Солнечный"


def test_building_address_with_yard_suffix():
    yard = Yard(id=3, name="Двор Северный")
    building = Building(id=2, address="ул. Ленина, д. 10", yard=yard)
    request = _base_request(address_type="building", building_obj=building)

    assert derive_public_address(request) == "ул. Ленина, д. 10 (Двор Северный)"


def test_building_address_without_yard_has_no_suffix():
    building = Building(id=3, address="ул. Ленина, д. 11", yard=None)
    request = _base_request(address_type="building", building_obj=building)

    assert derive_public_address(request) == "ул. Ленина, д. 11"


def test_legacy_address_type_returns_none():
    request = _base_request(address_type="legacy")

    assert derive_public_address(request) is None


def test_null_address_type_returns_none():
    request = _base_request(address_type=None)

    assert derive_public_address(request) is None


def test_apartment_type_with_none_apartment_obj_does_not_crash():
    """Defensive: real data always has apartment_obj set for address_type
    'apartment', but the function must not crash on the edge case."""
    request = _base_request(address_type="apartment", apartment_obj=None)

    assert derive_public_address(request) is None
