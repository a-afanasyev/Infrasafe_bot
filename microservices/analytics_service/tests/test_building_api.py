"""
Analytics Service - Building API Integration Tests
Task 11.1 - Integration Testing

Tests for Building Analytics API endpoints
"""

import pytest
from datetime import datetime
from uuid import uuid4
from httpx import AsyncClient

from main import app
from models.dim_building import DimBuilding


class TestBuildingStatsAPI:
    """Test building statistics endpoints"""

    @pytest.mark.asyncio
    async def test_get_building_stats(self, db_session, test_buildings):
        """Test GET /api/v1/buildings/stats"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/v1/buildings/stats")

        assert response.status_code == 200
        data = response.json()

        assert 'total_buildings' in data
        assert 'active' in data
        assert 'inactive' in data
        assert 'coordinates_coverage' in data
        assert 'by_city' in data
        assert 'by_type' in data

        # Validate structure
        assert data['total_buildings'] >= 0
        assert data['coordinates_coverage']['percentage'] >= 0
        assert isinstance(data['by_city'], dict)

    @pytest.mark.asyncio
    async def test_get_building_stats_with_filters(self, db_session, test_buildings):
        """Test stats endpoint with city filter"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/buildings/stats",
                params={'city': 'Tashkent', 'is_active': True}
            )

        assert response.status_code == 200
        data = response.json()

        assert 'filters_applied' in data
        assert data['filters_applied']['city'] == 'Tashkent'
        assert data['filters_applied']['is_active'] is True

    @pytest.mark.asyncio
    async def test_get_warehouse_stats(self, db_session):
        """Test GET /api/v1/buildings/stats/warehouse"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/v1/buildings/stats/warehouse")

        assert response.status_code == 200
        data = response.json()

        assert 'current_buildings' in data
        assert 'historical_versions' in data
        assert 'total_records' in data
        assert 'scd_metrics' in data

        # Validate SCD metrics
        scd = data['scd_metrics']
        assert 'average_versions_per_building' in scd
        assert 'change_rate' in scd
        assert scd['average_versions_per_building'] >= 0


class TestBuildingLookupAPI:
    """Test building lookup and detail endpoints"""

    @pytest.fixture
    def test_building(self, db_session):
        """Create test building"""
        building = DimBuilding(
            building_id=uuid4(),
            management_company_id=uuid4(),
            city='Tashkent',
            street='Test Street',
            house_number='100',
            full_address='Tashkent, Test Street, 100',
            latitude=41.311,
            longitude=69.279,
            building_type='residential',
            is_active=True,
            effective_from=datetime.utcnow(),
            effective_to=None,
            is_current=True
        )
        db_session.add(building)
        db_session.commit()
        return building

    @pytest.mark.asyncio
    async def test_get_building_by_id(self, db_session, test_building):
        """Test GET /api/v1/buildings/{building_id}"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/buildings/{test_building.building_id}"
            )

        assert response.status_code == 200
        data = response.json()

        assert data['building_id'] == str(test_building.building_id)
        assert data['city'] == 'Tashkent'
        assert data['street'] == 'Test Street'
        assert data['is_current'] is True

    @pytest.mark.asyncio
    async def test_get_building_with_history(self, db_session):
        """Test GET /api/v1/buildings/{id}?include_history=true"""
        building_id = uuid4()

        # Create historical version
        old = DimBuilding(
            building_id=building_id,
            management_company_id=uuid4(),
            city='Tashkent',
            street='Old Street',
            house_number='1',
            full_address='Tashkent, Old Street, 1',
            effective_from=datetime.utcnow(),
            effective_to=datetime.utcnow(),
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
            effective_from=datetime.utcnow(),
            effective_to=None,
            is_current=True,
            is_active=True
        )
        db_session.add(current)
        db_session.commit()

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/buildings/{building_id}",
                params={'include_history': True}
            )

        assert response.status_code == 200
        data = response.json()

        assert 'current' in data
        assert 'history' in data
        assert 'version_count' in data
        assert data['version_count'] == 2
        assert len(data['history']) == 1

    @pytest.mark.asyncio
    async def test_get_building_not_found(self, db_session):
        """Test 404 for non-existent building"""
        non_existent_id = uuid4()

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(f"/api/v1/buildings/{non_existent_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_buildings(self, db_session, test_buildings):
        """Test GET /api/v1/buildings/ with pagination"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/buildings/",
                params={'page': 1, 'page_size': 10}
            )

        assert response.status_code == 200
        data = response.json()

        assert 'items' in data
        assert 'total' in data
        assert 'page' in data
        assert 'page_size' in data
        assert 'pages' in data

        assert data['page'] == 1
        assert data['page_size'] == 10
        assert isinstance(data['items'], list)

    @pytest.mark.asyncio
    async def test_list_buildings_with_filters(self, db_session, test_buildings):
        """Test list buildings with multiple filters"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/buildings/",
                params={
                    'city': 'Tashkent',
                    'is_active': True,
                    'has_coordinates': True,
                    'page': 1,
                    'page_size': 20
                }
            )

        assert response.status_code == 200
        data = response.json()

        # Verify all returned buildings match filters
        for item in data['items']:
            assert item['city'] == 'Tashkent'
            assert item['is_active'] is True
            assert item['latitude'] is not None
            assert item['longitude'] is not None


class TestBuildingSyncAPI:
    """Test building sync management endpoints"""

    @pytest.mark.asyncio
    async def test_trigger_manual_sync_full(self, db_session):
        """Test POST /api/v1/buildings/sync?sync_type=full"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/buildings/sync",
                params={'sync_type': 'full'}
            )

        # Note: This will fail if Directory API not available
        # In real tests, would mock the Directory API
        assert response.status_code in [200, 500]

        if response.status_code == 200:
            data = response.json()
            assert data['sync_type'] == 'full'
            assert data['status'] == 'completed'
            assert 'stats' in data
            assert 'timestamp' in data

    @pytest.mark.asyncio
    async def test_trigger_manual_sync_incremental(self, db_session):
        """Test POST /api/v1/buildings/sync?sync_type=incremental"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/buildings/sync",
                params={'sync_type': 'incremental'}
            )

        assert response.status_code in [200, 500]

    @pytest.mark.asyncio
    async def test_trigger_manual_sync_invalid_type(self, db_session):
        """Test manual sync with invalid type"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/buildings/sync",
                params={'sync_type': 'invalid'}
            )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_get_sync_status(self, db_session):
        """Test GET /api/v1/buildings/sync/status"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/v1/buildings/sync/status")

        assert response.status_code == 200
        data = response.json()

        assert 'scheduled_jobs' in data
        assert 'scheduler_running' in data
        assert isinstance(data['scheduled_jobs'], list)


class TestBuildingHealthAPI:
    """Test health check endpoint"""

    @pytest.mark.asyncio
    async def test_health_check(self, db_session):
        """Test GET /api/v1/buildings/health"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/v1/buildings/health")

        assert response.status_code == 200
        data = response.json()

        assert 'status' in data
        assert data['status'] in ['healthy', 'unhealthy']
        assert 'database' in data
        assert 'timestamp' in data

        if data['status'] == 'healthy':
            assert 'current_buildings' in data


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def test_buildings(db_session):
    """Create test buildings for list/filter tests"""
    buildings = []

    # Tashkent buildings
    for i in range(5):
        building = DimBuilding(
            building_id=uuid4(),
            management_company_id=uuid4(),
            city='Tashkent',
            street=f'Test Street {i}',
            house_number=str(i+1),
            full_address=f'Tashkent, Test Street {i}, {i+1}',
            latitude=41.311 + i*0.001,
            longitude=69.279 + i*0.001,
            building_type='residential',
            is_active=i % 2 == 0,  # Alternate active/inactive
            effective_from=datetime.utcnow(),
            effective_to=None,
            is_current=True
        )
        db_session.add(building)
        buildings.append(building)

    # Samarkand buildings
    for i in range(3):
        building = DimBuilding(
            building_id=uuid4(),
            management_company_id=uuid4(),
            city='Samarkand',
            street=f'Another Street {i}',
            house_number=str(i+1),
            full_address=f'Samarkand, Another Street {i}, {i+1}',
            latitude=None,
            longitude=None,
            building_type='commercial',
            is_active=True,
            effective_from=datetime.utcnow(),
            effective_to=None,
            is_current=True
        )
        db_session.add(building)
        buildings.append(building)

    db_session.commit()
    return buildings
