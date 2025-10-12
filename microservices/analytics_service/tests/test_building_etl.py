"""
Analytics Service - Building ETL Integration Tests
Task 11.1 - Integration Testing

Tests for BuildingETLService with SCD Type 2 logic
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.dim_building import DimBuilding
from services.building_etl_service import BuildingETLService


class TestBuildingETLService:
    """Integration tests for Building ETL Service"""

    @pytest.fixture
    async def etl_service(self, db_session: AsyncSession):
        """Create ETL service instance"""
        return BuildingETLService(
            session=db_session,
            directory_api_url="http://localhost:8001",
            management_company_id="00000000-0000-0000-0000-000000000001"
        )

    @pytest.fixture
    def sample_building_data(self):
        """Sample building data from Directory API"""
        return {
            'id': str(uuid4()),
            'management_company_id': '00000000-0000-0000-0000-000000000001',
            'city': 'Tashkent',
            'district': 'Mirzo-Ulugbek',
            'street': 'Amir Temur',
            'house_number': '42',
            'building_corpus': 'A',
            'full_address': 'Tashkent, Amir Temur, 42A',
            'latitude': '41.311158',
            'longitude': '69.279737',
            'coordinates_source': 'google_maps',
            'building_type': 'residential',
            'floors_count': 9,
            'apartments_count': 54,
            'is_active': True,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }

    # ========================================================================
    # Transform Tests
    # ========================================================================

    def test_transform_building(self, etl_service, sample_building_data):
        """Test building data transformation"""
        transformed = etl_service.transform_building(sample_building_data)

        assert 'building_id' in transformed
        assert transformed['city'] == 'Tashkent'
        assert transformed['street'] == 'Amir Temur'
        assert transformed['house_number'] == '42'
        assert transformed['full_address'] == 'Tashkent, Amir Temur, 42A'
        assert transformed['is_active'] is True

    # ========================================================================
    # SCD Type 2 - Load Tests
    # ========================================================================

    @pytest.mark.asyncio
    async def test_load_building_scd2_insert_new(
        self, etl_service, db_session, sample_building_data
    ):
        """Test SCD Type 2 - Insert new building (no current version exists)"""
        transformed = etl_service.transform_building(sample_building_data)

        # Load building
        building_key = await etl_service.load_building_scd2(transformed)

        assert building_key is not None

        # Verify inserted
        result = await db_session.execute(
            select(DimBuilding).where(DimBuilding.building_key == building_key)
        )
        building = result.scalar_one()

        assert building.building_id == transformed['building_id']
        assert building.is_current is True
        assert building.effective_to is None
        assert building.full_address == 'Tashkent, Amir Temur, 42A'

    @pytest.mark.asyncio
    async def test_load_building_scd2_no_changes(
        self, etl_service, db_session, sample_building_data
    ):
        """Test SCD Type 2 - No changes (update metadata only)"""
        transformed = etl_service.transform_building(sample_building_data)

        # First load
        building_key_1 = await etl_service.load_building_scd2(transformed)
        await db_session.commit()

        # Load same data again (no changes)
        building_key_2 = await etl_service.load_building_scd2(transformed)

        # Should return same key (no new version created)
        assert building_key_1 == building_key_2

        # Verify only one version exists
        result = await db_session.execute(
            select(DimBuilding).where(
                DimBuilding.building_id == transformed['building_id']
            )
        )
        versions = result.scalars().all()
        assert len(versions) == 1
        assert versions[0].is_current is True

    @pytest.mark.asyncio
    async def test_load_building_scd2_with_changes(
        self, etl_service, db_session, sample_building_data
    ):
        """Test SCD Type 2 - Changes detected (expire old, insert new)"""
        transformed = etl_service.transform_building(sample_building_data)

        # First load
        building_key_1 = await etl_service.load_building_scd2(transformed)
        await db_session.commit()

        # Change address
        sample_building_data['street'] = 'New Street'
        sample_building_data['full_address'] = 'Tashkent, New Street, 42A'
        transformed_new = etl_service.transform_building(sample_building_data)

        # Load with changes
        building_key_2 = await etl_service.load_building_scd2(transformed_new)
        await db_session.commit()

        # Should create new version
        assert building_key_1 != building_key_2

        # Verify two versions exist
        result = await db_session.execute(
            select(DimBuilding).where(
                DimBuilding.building_id == transformed['building_id']
            ).order_by(DimBuilding.effective_from)
        )
        versions = result.scalars().all()
        assert len(versions) == 2

        # Old version - expired
        old_version = versions[0]
        assert old_version.building_key == building_key_1
        assert old_version.is_current is False
        assert old_version.effective_to is not None
        assert old_version.street == 'Amir Temur'

        # New version - current
        new_version = versions[1]
        assert new_version.building_key == building_key_2
        assert new_version.is_current is True
        assert new_version.effective_to is None
        assert new_version.street == 'New Street'

    @pytest.mark.asyncio
    async def test_load_building_scd2_multiple_changes(
        self, etl_service, db_session, sample_building_data
    ):
        """Test SCD Type 2 - Multiple changes over time"""
        transformed = etl_service.transform_building(sample_building_data)

        # Version 1
        key_1 = await etl_service.load_building_scd2(transformed)
        await db_session.commit()

        # Version 2 - change address
        sample_building_data['house_number'] = '43'
        sample_building_data['full_address'] = 'Tashkent, Amir Temur, 43A'
        transformed_v2 = etl_service.transform_building(sample_building_data)
        key_2 = await etl_service.load_building_scd2(transformed_v2)
        await db_session.commit()

        # Version 3 - change status
        sample_building_data['is_active'] = False
        transformed_v3 = etl_service.transform_building(sample_building_data)
        key_3 = await etl_service.load_building_scd2(transformed_v3)
        await db_session.commit()

        # Verify 3 versions
        result = await db_session.execute(
            select(DimBuilding).where(
                DimBuilding.building_id == transformed['building_id']
            ).order_by(DimBuilding.effective_from)
        )
        versions = result.scalars().all()
        assert len(versions) == 3

        # Check version progression
        assert versions[0].building_key == key_1
        assert versions[0].is_current is False
        assert versions[0].house_number == '42'
        assert versions[0].is_active is True

        assert versions[1].building_key == key_2
        assert versions[1].is_current is False
        assert versions[1].house_number == '43'
        assert versions[1].is_active is True

        assert versions[2].building_key == key_3
        assert versions[2].is_current is True
        assert versions[2].house_number == '43'
        assert versions[2].is_active is False

    # ========================================================================
    # Statistics Tests
    # ========================================================================

    @pytest.mark.asyncio
    async def test_get_sync_statistics(
        self, etl_service, db_session, sample_building_data
    ):
        """Test getting warehouse statistics"""
        # Insert test data
        transformed = etl_service.transform_building(sample_building_data)
        await etl_service.load_building_scd2(transformed)

        # Change and load again (create historical version)
        sample_building_data['street'] = 'New Street'
        transformed_new = etl_service.transform_building(sample_building_data)
        await etl_service.load_building_scd2(transformed_new)

        await db_session.commit()

        # Get statistics
        stats = await etl_service.get_sync_statistics()

        assert stats['current_buildings'] >= 1
        assert stats['historical_versions'] >= 1
        assert stats['total_records'] >= 2
        assert 'cities' in stats
        assert 'Tashkent' in stats['cities']

    # ========================================================================
    # Cleanup Tests
    # ========================================================================

    @pytest.mark.asyncio
    async def test_cleanup_obsolete_records(
        self, etl_service, db_session, sample_building_data
    ):
        """Test cleanup of obsolete non-current records"""
        transformed = etl_service.transform_building(sample_building_data)

        # Create old version (expired 100 days ago)
        old_building = DimBuilding(
            **transformed,
            effective_from=datetime.utcnow() - timedelta(days=120),
            effective_to=datetime.utcnow() - timedelta(days=100),
            is_current=False
        )
        db_session.add(old_building)
        await db_session.commit()

        old_building_key = old_building.building_key

        # Run cleanup (keep records newer than 90 days)
        deleted_count = await etl_service.cleanup_obsolete_records(days=90)

        assert deleted_count >= 1

        # Verify old record deleted
        result = await db_session.execute(
            select(DimBuilding).where(DimBuilding.building_key == old_building_key)
        )
        assert result.scalar_one_or_none() is None


class TestSCDType2Queries:
    """Test SCD Type 2 query patterns"""

    @pytest.mark.asyncio
    async def test_get_current_version(self, db_session):
        """Test getting current version of building"""
        building_id = uuid4()

        # Create historical version
        old = DimBuilding(
            building_id=building_id,
            management_company_id=uuid4(),
            city='Tashkent',
            street='Old Street',
            house_number='1',
            full_address='Tashkent, Old Street, 1',
            effective_from=datetime.utcnow() - timedelta(days=30),
            effective_to=datetime.utcnow() - timedelta(days=10),
            is_current=False,
            is_active=True
        )
        db_session.add(old)

        # Create current version
        current = DimBuilding(
            building_id=building_id,
            management_company_id=old.management_company_id,
            city='Tashkent',
            street='New Street',
            house_number='1',
            full_address='Tashkent, New Street, 1',
            effective_from=datetime.utcnow() - timedelta(days=10),
            effective_to=None,
            is_current=True,
            is_active=True
        )
        db_session.add(current)
        await db_session.commit()

        # Query current version
        result = await db_session.execute(
            select(DimBuilding).where(
                DimBuilding.building_id == building_id,
                DimBuilding.is_current == True
            )
        )
        found = result.scalar_one()

        assert found.building_key == current.building_key
        assert found.street == 'New Street'

    @pytest.mark.asyncio
    async def test_get_version_at_time(self, db_session):
        """Test getting building version at specific point in time"""
        building_id = uuid4()

        # Version 1: 30 days ago to 10 days ago
        v1 = DimBuilding(
            building_id=building_id,
            management_company_id=uuid4(),
            city='Tashkent',
            street='Street V1',
            house_number='1',
            full_address='Tashkent, Street V1, 1',
            effective_from=datetime.utcnow() - timedelta(days=30),
            effective_to=datetime.utcnow() - timedelta(days=10),
            is_current=False,
            is_active=True
        )
        db_session.add(v1)

        # Version 2: 10 days ago to now (current)
        v2 = DimBuilding(
            building_id=building_id,
            management_company_id=v1.management_company_id,
            city='Tashkent',
            street='Street V2',
            house_number='1',
            full_address='Tashkent, Street V2, 1',
            effective_from=datetime.utcnow() - timedelta(days=10),
            effective_to=None,
            is_current=True,
            is_active=True
        )
        db_session.add(v2)
        await db_session.commit()

        # Query version at 20 days ago (should get v1)
        target_time = datetime.utcnow() - timedelta(days=20)
        result = await db_session.execute(
            select(DimBuilding).where(
                DimBuilding.building_id == building_id,
                DimBuilding.effective_from <= target_time,
                (DimBuilding.effective_to.is_(None)) | (DimBuilding.effective_to > target_time)
            )
        )
        found = result.scalar_one()

        assert found.building_key == v1.building_key
        assert found.street == 'Street V1'

        # Query version at 5 days ago (should get v2)
        target_time_2 = datetime.utcnow() - timedelta(days=5)
        result = await db_session.execute(
            select(DimBuilding).where(
                DimBuilding.building_id == building_id,
                DimBuilding.effective_from <= target_time_2,
                (DimBuilding.effective_to.is_(None)) | (DimBuilding.effective_to > target_time_2)
            )
        )
        found_2 = result.scalar_one()

        assert found_2.building_key == v2.building_key
        assert found_2.street == 'Street V2'


# ============================================================================
# Pytest Configuration
# ============================================================================

@pytest.fixture
async def db_session():
    """Create async database session for tests"""
    # TODO: Configure async test database
    # For now, placeholder that would be configured with test DB
    pass
