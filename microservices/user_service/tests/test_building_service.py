"""Unit Tests for BuildingService.

Task 3.1: Create Unit Tests for Building Models and Service (P0)
Week 1, Day 3 - Building Directory Implementation
"""

import pytest
from uuid import uuid4
from decimal import Decimal

from models.building import Building
from services.building_service import BuildingService
from schemas.building import BuildingCreate, BuildingUpdate, BuildingFilter


@pytest.fixture
async def building_service(async_db):
    """BuildingService instance with test database."""
    return BuildingService(async_db)


class TestBuildingServiceCreate:
    """Tests for BuildingService.create_building()."""

    @pytest.mark.asyncio
    async def test_create_building_minimal(self, building_service, mc_id, async_db):
        """Test creating building with minimal data."""
        building_data = BuildingCreate(
            city="Tashkent",
            street="Amir Temur",
            house_number="42"
        )

        result = await building_service.create_building(
            building_data=building_data,
            management_company_id=mc_id
        )

        assert result.city == "Tashkent"
        assert result.street == "Amir Temur"
        assert result.house_number == "42"
        assert result.management_company_id == mc_id
        assert result.is_active is True
        assert result.full_address == "Tashkent, Amir Temur, 42"

    @pytest.mark.asyncio
    async def test_create_building_with_coordinates(self, building_service, mc_id):
        """Test creating building with manual coordinates."""
        building_data = BuildingCreate(
            city="Tashkent",
            street="Amir Temur",
            house_number="42",
            latitude=Decimal("41.311158"),
            longitude=Decimal("69.279737"),
            coordinates_source="manual"
        )

        result = await building_service.create_building(
            building_data=building_data,
            management_company_id=mc_id
        )

        assert result.coordinates is not None
        assert result.coordinates.lat == pytest.approx(41.311158, rel=1e-6)
        assert result.coordinates.lon == pytest.approx(69.279737, rel=1e-6)
        assert result.coordinates_source == "manual"
        assert result.geocoded_at is not None

    @pytest.mark.asyncio
    async def test_create_building_duplicate_address(self, building_service, mc_id):
        """Test that duplicate address raises IntegrityError (database constraint)."""
        from sqlalchemy.exc import IntegrityError

        building_data = BuildingCreate(
            city="Tashkent",
            street="Amir Temur",
            house_number="42"
        )

        # Create first building
        await building_service.create_building(
            building_data=building_data,
            management_company_id=mc_id
        )

        # Attempt to create duplicate - should raise IntegrityError from DB
        with pytest.raises(IntegrityError, match="ix_buildings_unique_address"):
            await building_service.create_building(
                building_data=building_data,
                management_company_id=mc_id
            )

    @pytest.mark.asyncio
    async def test_create_building_different_mc_allowed(self, building_service):
        """Test that same address for different MC is allowed."""
        mc_id_1 = uuid4()
        mc_id_2 = uuid4()

        building_data = BuildingCreate(
            city="Tashkent",
            street="Amir Temur",
            house_number="42"
        )

        # Create for MC 1
        result1 = await building_service.create_building(
            building_data=building_data,
            management_company_id=mc_id_1
        )

        # Create same address for MC 2 - should succeed
        result2 = await building_service.create_building(
            building_data=building_data,
            management_company_id=mc_id_2
        )

        assert result1.id != result2.id
        assert result1.management_company_id != result2.management_company_id

    @pytest.mark.asyncio
    async def test_create_building_full_data(self, building_service, mc_id, user_id):
        """Test creating building with all fields."""
        building_data = BuildingCreate(
            city="Tashkent",
            street="Amir Temur",
            house_number="42",
            district="Yunusabad",
            building_corpus="A",
            postal_code="100000",
            building_type="residential",
            floors_count=9,
            entrance_count=3,
            apartments_count=72,
            year_built=2015,
            notes="Test building",
            extra_data={"color": "red"}
        )

        result = await building_service.create_building(
            building_data=building_data,
            management_company_id=mc_id,
            created_by=user_id
        )

        assert result.district == "Yunusabad"
        assert result.building_corpus == "A"
        assert result.building_type == "residential"
        assert result.floors_count == 9
        assert result.extra_data == {"color": "red"}


class TestBuildingServiceRead:
    """Tests for BuildingService read operations."""

    @pytest.mark.asyncio
    async def test_get_building_by_id(self, building_service, mc_id):
        """Test getting building by ID."""
        building_data = BuildingCreate(
            city="Tashkent",
            street="Amir Temur",
            house_number="42"
        )

        created = await building_service.create_building(
            building_data=building_data,
            management_company_id=mc_id
        )

        result = await building_service.get_building_by_id(
            building_id=created.id,
            management_company_id=mc_id
        )

        assert result is not None
        assert result.id == created.id
        assert result.city == "Tashkent"

    @pytest.mark.asyncio
    async def test_get_building_wrong_mc(self, building_service, mc_id):
        """Test getting building with wrong MC returns None."""
        building_data = BuildingCreate(
            city="Tashkent",
            street="Amir Temur",
            house_number="42"
        )

        created = await building_service.create_building(
            building_data=building_data,
            management_company_id=mc_id
        )

        # Try to get with different MC ID
        wrong_mc_id = uuid4()
        result = await building_service.get_building_by_id(
            building_id=created.id,
            management_company_id=wrong_mc_id
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_list_buildings_empty(self, building_service, mc_id):
        """Test listing buildings when none exist."""
        filters = BuildingFilter()

        result = await building_service.list_buildings(
            management_company_id=mc_id,
            filters=filters
        )

        assert result.total == 0
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_list_buildings(self, building_service, mc_id):
        """Test listing buildings."""
        # Create 3 buildings
        for i in range(3):
            building_data = BuildingCreate(
                city="Tashkent",
                street="Amir Temur",
                house_number=str(40 + i)
            )
            await building_service.create_building(
                building_data=building_data,
                management_company_id=mc_id
            )

        filters = BuildingFilter()
        result = await building_service.list_buildings(
            management_company_id=mc_id,
            filters=filters
        )

        assert result.total == 3
        assert len(result.items) == 3

    @pytest.mark.asyncio
    async def test_list_buildings_filter_city(self, building_service, mc_id):
        """Test filtering buildings by city."""
        # Create buildings in different cities
        await building_service.create_building(
            BuildingCreate(city="Tashkent", street="Amir Temur", house_number="1"),
            mc_id
        )
        await building_service.create_building(
            BuildingCreate(city="Samarkand", street="Registan", house_number="2"),
            mc_id
        )

        filters = BuildingFilter(city="Tashkent")
        result = await building_service.list_buildings(mc_id, filters)

        assert result.total == 1
        assert result.items[0].city == "Tashkent"

    @pytest.mark.asyncio
    async def test_list_buildings_pagination(self, building_service, mc_id):
        """Test building list pagination."""
        # Create 5 buildings
        for i in range(5):
            await building_service.create_building(
                BuildingCreate(city="Tashkent", street="Street", house_number=str(i)),
                mc_id
            )

        # Get page 1 (2 items per page)
        filters = BuildingFilter(page=1, page_size=2)
        result = await building_service.list_buildings(mc_id, filters)

        assert result.total == 5
        assert len(result.items) == 2
        assert result.page == 1
        assert result.total_pages == 3

    @pytest.mark.asyncio
    async def test_search_buildings(self, building_service, mc_id):
        """Test searching buildings."""
        await building_service.create_building(
            BuildingCreate(city="Tashkent", street="Amir Temur", house_number="42"),
            mc_id
        )
        await building_service.create_building(
            BuildingCreate(city="Tashkent", street="Mustaqillik", house_number="10"),
            mc_id
        )

        results = await building_service.search_buildings(
            management_company_id=mc_id,
            query_text="Amir",
            limit=10
        )

        assert len(results) == 1
        assert results[0].street == "Amir Temur"


class TestBuildingServiceUpdate:
    """Tests for BuildingService update operations."""

    @pytest.mark.asyncio
    async def test_update_building(self, building_service, mc_id):
        """Test updating building."""
        created = await building_service.create_building(
            BuildingCreate(city="Tashkent", street="Amir Temur", house_number="42"),
            mc_id
        )

        update_data = BuildingUpdate(floors_count=10, notes="Updated")

        result = await building_service.update_building(
            building_id=created.id,
            management_company_id=mc_id,
            building_data=update_data
        )

        assert result is not None
        assert result.floors_count == 10
        assert result.notes == "Updated"
        assert result.city == "Tashkent"  # Unchanged

    @pytest.mark.asyncio
    async def test_update_building_coordinates(self, building_service, mc_id):
        """Test updating building coordinates."""
        created = await building_service.create_building(
            BuildingCreate(city="Tashkent", street="Amir Temur", house_number="42"),
            mc_id
        )

        result = await building_service.update_building_coordinates(
            building_id=created.id,
            management_company_id=mc_id,
            latitude=41.311158,
            longitude=69.279737,
            source='google_maps'
        )

        assert result is not None
        assert result.coordinates is not None
        assert result.coordinates_source == 'google_maps'


class TestBuildingServiceDelete:
    """Tests for BuildingService delete operations."""

    @pytest.mark.asyncio
    async def test_soft_delete(self, building_service, mc_id):
        """Test soft deleting building."""
        created = await building_service.create_building(
            BuildingCreate(city="Tashkent", street="Amir Temur", house_number="42"),
            mc_id
        )

        deleted = await building_service.delete_building(
            building_id=created.id,
            management_company_id=mc_id,
            soft=True
        )

        assert deleted is True

        # Should not be found in normal queries
        result = await building_service.get_building_by_id(created.id, mc_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_restore_building(self, building_service, mc_id):
        """Test restoring soft-deleted building."""
        created = await building_service.create_building(
            BuildingCreate(city="Tashkent", street="Amir Temur", house_number="42"),
            mc_id
        )

        # Soft delete
        await building_service.delete_building(created.id, mc_id, soft=True)

        # Restore
        restored = await building_service.restore_building(created.id, mc_id)

        assert restored is not None
        assert restored.is_active is True


class TestBuildingServiceStatistics:
    """Tests for BuildingService statistics operations."""

    @pytest.mark.asyncio
    async def test_get_statistics(self, building_service, mc_id):
        """Test getting building statistics."""
        # Create buildings with and without coordinates
        await building_service.create_building(
            BuildingCreate(
                city="Tashkent",
                street="Amir Temur",
                house_number="42",
                latitude=Decimal("41.311158"),
                longitude=Decimal("69.279737")
            ),
            mc_id
        )
        await building_service.create_building(
            BuildingCreate(city="Tashkent", street="Mustaqillik", house_number="10"),
            mc_id
        )

        stats = await building_service.get_statistics(mc_id)

        assert stats.total_buildings == 2
        assert stats.buildings_with_coordinates == 1
        assert stats.buildings_without_coordinates == 1
        assert stats.geocoding_coverage_percent == 50.0

    @pytest.mark.asyncio
    async def test_get_buildings_needing_geocoding(self, building_service, mc_id):
        """Test getting buildings without coordinates."""
        # With coordinates
        await building_service.create_building(
            BuildingCreate(
                city="Tashkent",
                street="Amir Temur",
                house_number="42",
                latitude=Decimal("41.311158"),
                longitude=Decimal("69.279737")
            ),
            mc_id
        )
        # Without coordinates
        await building_service.create_building(
            BuildingCreate(city="Tashkent", street="Mustaqillik", house_number="10"),
            mc_id
        )

        results = await building_service.get_buildings_needing_geocoding(mc_id, limit=100)

        assert len(results) == 1
        assert results[0].street == "Mustaqillik"


class TestBuildingServiceFuzzyMatching:
    """Tests for BuildingService fuzzy matching."""

    @pytest.mark.asyncio
    async def test_find_similar_addresses(self, building_service, mc_id):
        """Test finding similar addresses."""
        await building_service.create_building(
            BuildingCreate(city="Tashkent", street="Amir Temur", house_number="42"),
            mc_id
        )
        await building_service.create_building(
            BuildingCreate(city="Tashkent", street="Amir Timur", house_number="42"),
            mc_id
        )

        results = await building_service.find_similar_addresses(
            management_company_id=mc_id,
            address_text="Tashkent, Amir Temur, 42",
            threshold=0.7,
            limit=10
        )

        assert len(results) >= 1
        # First result should be exact match
        assert results[0][1] >= 0.9  # High similarity score
