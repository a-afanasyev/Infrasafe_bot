"""Unit tests for AddressService read methods (mock-based, no DB required).

ARCH-014: the write methods (create/update/delete/bulk/moderation) are now thin
async adapters over services/addresses/core and open their own AsyncSession.
Their behaviour is covered by the Postgres suites
uk_management_bot/tests/test_address_core.py and test_address_e2e_parity.py.
The mock-based write-method tests that used to live here asserted sync-Session
side effects (session.commit/add/rollback, queue_webhook_sync) that no longer
apply, so they were retired. Only the read-method tests remain — read methods
still operate on the caller's sync Session and are unchanged.
"""
import pytest
from unittest.mock import MagicMock


class _FakeYard:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.name = kwargs.get("name", "Двор А")
        self.description = kwargs.get("description", "Тестовый")
        self.gps_latitude = kwargs.get("gps_latitude", None)
        self.gps_longitude = kwargs.get("gps_longitude", None)
        self.is_active = kwargs.get("is_active", True)
        self.created_by = kwargs.get("created_by", 1)
        self.buildings = kwargs.get("buildings", [])


class _FakeBuilding:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.address = kwargs.get("address", "ул. Тестовая, 1")
        self.yard_id = kwargs.get("yard_id", 1)
        self.is_active = kwargs.get("is_active", True)
        self.gps_latitude = kwargs.get("gps_latitude", None)
        self.gps_longitude = kwargs.get("gps_longitude", None)
        self.entrance_count = kwargs.get("entrance_count", 1)
        self.floor_count = kwargs.get("floor_count", 1)
        self.description = kwargs.get("description", None)
        self.created_by = kwargs.get("created_by", 1)


class _FakeApartment:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.building_id = kwargs.get("building_id", 1)
        self.apartment_number = kwargs.get("apartment_number", "10")
        self.is_active = kwargs.get("is_active", True)
        self.entrance = kwargs.get("entrance", None)
        self.floor = kwargs.get("floor", None)
        self.rooms_count = kwargs.get("rooms_count", None)
        self.area = kwargs.get("area", None)
        self.description = kwargs.get("description", None)
        self.created_by = kwargs.get("created_by", 1)


def _mock_execute(session, scalar_result=None, scalars_all=None):
    """Helper to mock session.execute().scalar_one_or_none() and .scalars().all()"""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scalar_result
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = scalars_all or []
    mock_result.scalars.return_value = mock_scalars
    mock_result.unique.return_value = mock_result
    mock_result.scalar.return_value = 0
    session.execute.return_value = mock_result
    return mock_result


# ===== get_yard_by_id =====

class TestGetYardById:
    @pytest.mark.asyncio
    async def test_returns_yard(self):
        session = MagicMock()
        yard = _FakeYard()
        _mock_execute(session, scalar_result=yard)
        from uk_management_bot.services.address_service import AddressService

        result = await AddressService.get_yard_by_id(session, 1)
        assert result == yard

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        session = MagicMock()
        _mock_execute(session, scalar_result=None)
        from uk_management_bot.services.address_service import AddressService

        result = await AddressService.get_yard_by_id(session, 999)
        assert result is None


# ===== get_all_yards =====

class TestGetAllYards:
    @pytest.mark.asyncio
    async def test_returns_active_yards(self):
        session = MagicMock()
        yards = [_FakeYard(id=1), _FakeYard(id=2)]
        _mock_execute(session, scalars_all=yards)
        from uk_management_bot.services.address_service import AddressService

        result = await AddressService.get_all_yards(session)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_all_yards_including_inactive(self):
        session = MagicMock()
        yards = [_FakeYard(is_active=False)]
        _mock_execute(session, scalars_all=yards)
        from uk_management_bot.services.address_service import AddressService

        result = await AddressService.get_all_yards(session, only_active=False)
        assert len(result) == 1


# ===== get_buildings_by_yard =====

class TestGetBuildingsByYard:
    @pytest.mark.asyncio
    async def test_returns_buildings(self):
        session = MagicMock()
        buildings = [_FakeBuilding(id=1), _FakeBuilding(id=2)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = buildings
        session.execute.return_value = mock_result

        from uk_management_bot.services.address_service import AddressService

        result = await AddressService.get_buildings_by_yard(session, 1)
        assert len(result) == 2


# ===== get_apartments_by_building =====

class TestGetApartmentsByBuilding:
    @pytest.mark.asyncio
    async def test_returns_sorted_apartments(self):
        session = MagicMock()
        apt1 = _FakeApartment(apartment_number="2")
        apt2 = _FakeApartment(apartment_number="1")
        apt3 = _FakeApartment(apartment_number="A")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [apt1, apt2, apt3]
        session.execute.return_value = mock_result

        from uk_management_bot.services.address_service import AddressService

        result = await AddressService.get_apartments_by_building(session, 1)
        # Numeric "1" before "2" before non-numeric "A"
        assert result[0].apartment_number == "1"
        assert result[1].apartment_number == "2"
        assert result[2].apartment_number == "A"


# ===== get_apartment_by_id =====

class TestGetApartmentById:
    @pytest.mark.asyncio
    async def test_returns_apartment(self):
        session = MagicMock()
        apt = _FakeApartment()
        _mock_execute(session, scalar_result=apt)
        from uk_management_bot.services.address_service import AddressService

        result = await AddressService.get_apartment_by_id(session, 1)
        assert result == apt

    @pytest.mark.asyncio
    async def test_returns_none(self):
        session = MagicMock()
        _mock_execute(session, scalar_result=None)
        from uk_management_bot.services.address_service import AddressService

        result = await AddressService.get_apartment_by_id(session, 999)
        assert result is None
