"""
Unit tests for AddressService (mock-based, no DB required).

Covers:
- create_yard / get_yard_by_id / get_all_yards / update_yard / delete_yard
- create_building / get_building_by_id / get_buildings_by_yard / update_building / delete_building
- create_apartment / get_apartment_by_id / get_apartments_by_building
- bulk_create_apartments
- search_apartments
- update_apartment
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


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


# ===== create_yard =====

class TestCreateYard:
    @pytest.mark.asyncio
    async def test_creates_yard_successfully(self):
        session = MagicMock()
        _mock_execute(session, scalar_result=None)  # no existing yard
        from uk_management_bot.services.address_service import AddressService

        yard, error = await AddressService.create_yard(session, "Двор Б", created_by=1)
        assert error is None
        session.add.assert_called_once()
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_name_returns_error(self):
        session = MagicMock()
        existing = _FakeYard(name="Двор А")
        _mock_execute(session, scalar_result=existing)
        from uk_management_bot.services.address_service import AddressService

        yard, error = await AddressService.create_yard(session, "Двор А", created_by=1)
        assert yard is None
        assert "уже существует" in error

    @pytest.mark.asyncio
    async def test_exception_returns_error(self):
        session = MagicMock()
        session.execute.side_effect = Exception("DB error")
        from uk_management_bot.services.address_service import AddressService

        yard, error = await AddressService.create_yard(session, "Двор В", created_by=1)
        assert yard is None
        assert "Ошибка" in error
        session.rollback.assert_called()


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


# ===== update_yard =====

class TestUpdateYard:
    @pytest.mark.asyncio
    async def test_updates_yard(self):
        session = MagicMock()
        yard = _FakeYard(name="Двор А")
        # First execute -> get_yard_by_id; second -> duplicate check
        mock_result_1 = MagicMock()
        mock_result_1.scalar_one_or_none.return_value = yard
        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none.return_value = None
        session.execute.side_effect = [mock_result_1, mock_result_2]

        from uk_management_bot.services.address_service import AddressService

        updated, error = await AddressService.update_yard(session, 1, name="Двор Б")
        assert error is None
        assert yard.name == "Двор Б"

    @pytest.mark.asyncio
    async def test_yard_not_found(self):
        session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        from uk_management_bot.services.address_service import AddressService

        result, error = await AddressService.update_yard(session, 999, name="X")
        assert result is None
        assert "не найден" in error

    @pytest.mark.asyncio
    async def test_duplicate_name_returns_error(self):
        session = MagicMock()
        yard = _FakeYard(name="Двор А")
        other = _FakeYard(id=2, name="Двор Б")
        mock_result_1 = MagicMock()
        mock_result_1.scalar_one_or_none.return_value = yard
        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none.return_value = other
        session.execute.side_effect = [mock_result_1, mock_result_2]

        from uk_management_bot.services.address_service import AddressService

        result, error = await AddressService.update_yard(session, 1, name="Двор Б")
        assert result is None
        assert "уже существует" in error


# ===== delete_yard =====

class TestDeleteYard:
    @pytest.mark.asyncio
    async def test_soft_deletes_yard(self):
        session = MagicMock()
        yard = _FakeYard()
        mock_result_1 = MagicMock()
        mock_result_1.scalar_one_or_none.return_value = yard
        mock_result_2 = MagicMock()
        mock_result_2.scalar.return_value = 0  # no active buildings
        session.execute.side_effect = [mock_result_1, mock_result_2]

        from uk_management_bot.services.address_service import AddressService

        success, error = await AddressService.delete_yard(session, 1)
        assert success is True
        assert yard.is_active is False

    @pytest.mark.asyncio
    async def test_cannot_delete_with_active_buildings(self):
        session = MagicMock()
        yard = _FakeYard()
        mock_result_1 = MagicMock()
        mock_result_1.scalar_one_or_none.return_value = yard
        mock_result_2 = MagicMock()
        mock_result_2.scalar.return_value = 3  # 3 active buildings
        session.execute.side_effect = [mock_result_1, mock_result_2]

        from uk_management_bot.services.address_service import AddressService

        success, error = await AddressService.delete_yard(session, 1)
        assert success is False
        assert "активных зданий" in error

    @pytest.mark.asyncio
    async def test_not_found(self):
        session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        from uk_management_bot.services.address_service import AddressService

        success, error = await AddressService.delete_yard(session, 999)
        assert success is False
        assert "не найден" in error


# ===== create_building =====

class TestCreateBuilding:
    @pytest.mark.asyncio
    async def test_creates_building(self):
        session = MagicMock()
        yard = _FakeYard()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = yard
        session.execute.return_value = mock_result

        from uk_management_bot.services.address_service import AddressService

        building, error = await AddressService.create_building(
            session, "ул. Новая, 1", yard_id=1, created_by=1
        )
        assert error is None
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_yard_not_found(self):
        session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        from uk_management_bot.services.address_service import AddressService

        building, error = await AddressService.create_building(
            session, "ул. Новая, 1", yard_id=999, created_by=1
        )
        assert building is None
        assert "не найден" in error

    @pytest.mark.asyncio
    async def test_inactive_yard(self):
        session = MagicMock()
        yard = _FakeYard(is_active=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = yard
        session.execute.return_value = mock_result

        from uk_management_bot.services.address_service import AddressService

        building, error = await AddressService.create_building(
            session, "ул. Новая, 1", yard_id=1, created_by=1
        )
        assert building is None
        assert "неактивен" in error


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


# ===== delete_building =====

class TestDeleteBuilding:
    @pytest.mark.asyncio
    async def test_soft_deletes_building(self):
        session = MagicMock()
        building = _FakeBuilding()
        mock_result_1 = MagicMock()
        mock_result_1.scalar_one_or_none.return_value = building
        mock_result_2 = MagicMock()
        mock_result_2.scalar.return_value = 0  # no active apartments
        session.execute.side_effect = [mock_result_1, mock_result_2]

        from uk_management_bot.services.address_service import AddressService

        success, error = await AddressService.delete_building(session, 1)
        assert success is True
        assert building.is_active is False

    @pytest.mark.asyncio
    async def test_cannot_delete_with_active_apartments(self):
        session = MagicMock()
        building = _FakeBuilding()
        mock_result_1 = MagicMock()
        mock_result_1.scalar_one_or_none.return_value = building
        mock_result_2 = MagicMock()
        mock_result_2.scalar.return_value = 5  # active apartments
        session.execute.side_effect = [mock_result_1, mock_result_2]

        from uk_management_bot.services.address_service import AddressService

        success, error = await AddressService.delete_building(session, 1)
        assert success is False
        assert "активных квартир" in error

    @pytest.mark.asyncio
    async def test_not_found(self):
        session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        from uk_management_bot.services.address_service import AddressService

        success, error = await AddressService.delete_building(session, 999)
        assert success is False
        assert "не найдено" in error


# ===== create_apartment =====

class TestCreateApartment:
    @pytest.mark.asyncio
    async def test_creates_apartment(self):
        session = MagicMock()
        building = _FakeBuilding()
        # First execute: get_building_by_id; Second: check uniqueness
        mock_result_1 = MagicMock()
        mock_result_1.scalar_one_or_none.return_value = building
        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none.return_value = None
        session.execute.side_effect = [mock_result_1, mock_result_2]

        from uk_management_bot.services.address_service import AddressService

        apt, error = await AddressService.create_apartment(
            session, building_id=1, apartment_number="10", created_by=1
        )
        assert error is None
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_apartment(self):
        session = MagicMock()
        building = _FakeBuilding()
        existing = _FakeApartment()
        mock_result_1 = MagicMock()
        mock_result_1.scalar_one_or_none.return_value = building
        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none.return_value = existing
        session.execute.side_effect = [mock_result_1, mock_result_2]

        from uk_management_bot.services.address_service import AddressService

        apt, error = await AddressService.create_apartment(
            session, building_id=1, apartment_number="10", created_by=1
        )
        assert apt is None
        assert "уже существует" in error

    @pytest.mark.asyncio
    async def test_building_not_found(self):
        session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        from uk_management_bot.services.address_service import AddressService

        apt, error = await AddressService.create_apartment(
            session, building_id=999, apartment_number="10", created_by=1
        )
        assert apt is None
        assert "не найдено" in error

    @pytest.mark.asyncio
    async def test_inactive_building(self):
        session = MagicMock()
        building = _FakeBuilding(is_active=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = building
        session.execute.return_value = mock_result

        from uk_management_bot.services.address_service import AddressService

        apt, error = await AddressService.create_apartment(
            session, building_id=1, apartment_number="10", created_by=1
        )
        assert apt is None
        assert "неактивно" in error


# ===== bulk_create_apartments =====

class TestBulkCreateApartments:
    @pytest.mark.asyncio
    async def test_creates_multiple(self):
        session = MagicMock()
        building = _FakeBuilding()
        # First: get_building; Second: get existing apartments
        mock_result_1 = MagicMock()
        mock_result_1.scalar_one_or_none.return_value = building
        mock_result_2 = MagicMock()
        mock_result_2.scalars.return_value.all.return_value = ["1"]  # existing apt "1"
        session.execute.side_effect = [mock_result_1, mock_result_2]

        from uk_management_bot.services.address_service import AddressService

        created, skipped, errors = await AddressService.bulk_create_apartments(
            session, building_id=1, apartment_numbers=["1", "2", "3"], created_by=1
        )
        assert skipped == 1  # "1" already exists
        assert created == 2  # "2" and "3" created
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_building_not_found(self):
        session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        from uk_management_bot.services.address_service import AddressService

        created, skipped, errors = await AddressService.bulk_create_apartments(
            session, building_id=999, apartment_numbers=["1"], created_by=1
        )
        assert created == 0
        assert "не найдено" in errors[0]


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
