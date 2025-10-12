"""
Request Service - Building Directory Integration Tests
Task 11.1 - Integration Testing

Tests for Building Directory integration in Request Service
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from app.clients.building_directory_client import BuildingDirectoryClient
from app.schemas.request import RequestCreate
from app.models.request import Request, RequestStatus, RequestCategory


class TestBuildingDirectoryClient:
    """Test BuildingDirectoryClient"""

    @pytest.fixture
    def client(self):
        """Create client instance"""
        return BuildingDirectoryClient(
            api_url="http://localhost:8001",
            management_company_id="00000000-0000-0000-0000-000000000001"
        )

    @pytest.fixture
    def mock_building_response(self):
        """Mock building response from Directory API"""
        return {
            'id': str(uuid4()),
            'management_company_id': '00000000-0000-0000-0000-000000000001',
            'city': 'Tashkent',
            'street': 'Amir Temur',
            'house_number': '42',
            'building_corpus': 'A',
            'full_address': 'Tashkent, Amir Temur, 42A',
            'latitude': 41.311158,
            'longitude': 69.279737,
            'building_type': 'residential',
            'is_active': True
        }

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient.get')
    async def test_get_building_success(
        self, mock_get, client, mock_building_response
    ):
        """Test getting building by ID"""
        building_id = uuid4()
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_building_response

        building = await client.get_building(building_id)

        assert building is not None
        assert building['city'] == 'Tashkent'
        assert building['full_address'] == 'Tashkent, Amir Temur, 42A'
        assert building['is_active'] is True

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient.get')
    async def test_get_building_not_found(self, mock_get, client):
        """Test 404 for non-existent building"""
        building_id = uuid4()
        mock_get.return_value.status_code = 404

        building = await client.get_building(building_id)

        assert building is None

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient.get')
    async def test_validate_building_for_request_success(
        self, mock_get, client, mock_building_response
    ):
        """Test successful building validation"""
        building_id = uuid4()
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_building_response

        is_valid, error, building = await client.validate_building_for_request(building_id)

        assert is_valid is True
        assert error is None
        assert building is not None
        assert building['is_active'] is True

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient.get')
    async def test_validate_building_not_found(self, mock_get, client):
        """Test validation failure - building not found"""
        building_id = uuid4()
        mock_get.return_value.status_code = 404

        is_valid, error, building = await client.validate_building_for_request(building_id)

        assert is_valid is False
        assert 'not found' in error.lower()
        assert building is None

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient.get')
    async def test_validate_building_inactive(
        self, mock_get, client, mock_building_response
    ):
        """Test validation failure - building inactive"""
        building_id = uuid4()
        mock_building_response['is_active'] = False
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_building_response

        is_valid, error, building = await client.validate_building_for_request(building_id)

        assert is_valid is False
        assert 'inactive' in error.lower()
        assert building is not None

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient.get')
    async def test_get_building_data_for_request(
        self, mock_get, client, mock_building_response
    ):
        """Test getting building data for request denormalization"""
        building_id = uuid4()
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_building_response

        data = await client.get_building_data_for_request(building_id)

        assert data is not None
        assert data['building_address'] == 'Tashkent, Amir Temur, 42A'
        assert data['latitude'] == 41.311158
        assert data['longitude'] == 69.279737
        assert data['city'] == 'Tashkent'
        assert data['street'] == 'Amir Temur'


class TestRequestCreationWithBuilding:
    """Test request creation with Building Directory integration"""

    @pytest.fixture
    def valid_request_data(self):
        """Valid request creation data"""
        return {
            'title': 'Test Request',
            'description': 'Test Description',
            'category': 'plumbing',
            'priority': 'medium',
            'building_id': str(uuid4()),
            'address': 'кв. 5, 3 подъезд',  # User details only
            'apartment_number': '5',
            'applicant_user_id': str(uuid4()),
            'media_file_ids': []
        }

    @pytest.fixture
    def mock_building(self):
        """Mock building from Directory"""
        return {
            'id': str(uuid4()),
            'management_company_id': '00000000-0000-0000-0000-000000000001',
            'city': 'Tashkent',
            'street': 'Amir Temur',
            'house_number': '42',
            'full_address': 'г. Ташкент, ул. Амир Темур, 42',
            'latitude': 41.311158,
            'longitude': 69.279737,
            'is_active': True
        }

    @pytest.mark.asyncio
    @patch('app.clients.building_directory_client.BuildingDirectoryClient.validate_building_for_request')
    @patch('app.clients.building_directory_client.BuildingDirectoryClient.get_building_data_for_request')
    async def test_create_request_with_valid_building(
        self, mock_get_data, mock_validate, valid_request_data, mock_building, db_session
    ):
        """Test creating request with valid building"""
        # Mock validation success
        mock_validate.return_value = (True, None, mock_building)

        # Mock building data
        mock_get_data.return_value = {
            'building_address': mock_building['full_address'],
            'latitude': mock_building['latitude'],
            'longitude': mock_building['longitude'],
            'city': mock_building['city'],
            'street': mock_building['street'],
            'house_number': mock_building['house_number'],
            'building_corpus': None,
            'building_type': 'residential'
        }

        # Create request via API
        from main import app as fastapi_app
        async with AsyncClient(app=fastapi_app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/requests/",
                json=valid_request_data,
                headers={'Authorization': 'Bearer test-token'}
            )

        assert response.status_code == 201
        data = response.json()

        # Verify request created with denormalized building data
        assert data['building_id'] == valid_request_data['building_id']
        assert data['building_address'] == 'г. Ташкент, ул. Амир Темур, 42'
        assert data['address'] == 'кв. 5, 3 подъезд'
        assert data['latitude'] == 41.311158
        assert data['longitude'] == 69.279737

    @pytest.mark.asyncio
    @patch('app.clients.building_directory_client.BuildingDirectoryClient.validate_building_for_request')
    async def test_create_request_with_invalid_building(
        self, mock_validate, valid_request_data, db_session
    ):
        """Test creating request with invalid building ID"""
        # Mock validation failure
        mock_validate.return_value = (
            False,
            f"Building {valid_request_data['building_id']} not found in Directory",
            None
        )

        from main import app as fastapi_app
        async with AsyncClient(app=fastapi_app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/requests/",
                json=valid_request_data,
                headers={'Authorization': 'Bearer test-token'}
            )

        # Should return 400 Bad Request
        assert response.status_code == 400
        assert 'not found' in response.json()['detail'].lower()

    @pytest.mark.asyncio
    @patch('app.clients.building_directory_client.BuildingDirectoryClient.validate_building_for_request')
    async def test_create_request_with_inactive_building(
        self, mock_validate, valid_request_data, db_session, mock_building
    ):
        """Test creating request with inactive building"""
        # Mock validation failure - inactive
        mock_building['is_active'] = False
        mock_validate.return_value = (
            False,
            f"Building {mock_building['full_address']} is inactive",
            mock_building
        )

        from main import app as fastapi_app
        async with AsyncClient(app=fastapi_app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/requests/",
                json=valid_request_data,
                headers={'Authorization': 'Bearer test-token'}
            )

        assert response.status_code == 400
        assert 'inactive' in response.json()['detail'].lower()

    @pytest.mark.asyncio
    async def test_create_request_without_building_id(
        self, valid_request_data, db_session
    ):
        """Test creating request without building_id (should fail validation)"""
        # Remove building_id (now required)
        del valid_request_data['building_id']

        from main import app as fastapi_app
        async with AsyncClient(app=fastapi_app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/requests/",
                json=valid_request_data,
                headers={'Authorization': 'Bearer test-token'}
            )

        # Should return 422 Validation Error
        assert response.status_code == 422


class TestRequestModel:
    """Test Request model with Building Directory fields"""

    @pytest.mark.asyncio
    async def test_request_model_with_building_fields(self, db_session):
        """Test Request model with new building fields"""
        building_id = uuid4()

        request = Request(
            request_number='251007-001',
            title='Test Request',
            description='Test Description',
            category=RequestCategory.PLUMBING,
            # Building Directory fields
            building_id=building_id,
            building_address='г. Ташкент, ул. Амир Темур, 42',
            address='кв. 5, 3 подъезд',
            # Standard fields
            applicant_user_id=str(uuid4()),
            status=RequestStatus.NEW
        )

        db_session.add(request)
        await db_session.commit()
        await db_session.refresh(request)

        # Verify fields
        assert request.building_id == building_id
        assert request.building_address == 'г. Ташкент, ул. Амир Темур, 42'
        assert request.address == 'кв. 5, 3 подъезд'

    @pytest.mark.asyncio
    async def test_request_query_by_building(self, db_session):
        """Test querying requests by building_id"""
        building_id = uuid4()

        # Create multiple requests for same building
        for i in range(3):
            request = Request(
                request_number=f'251007-{i:03d}',
                title=f'Request {i}',
                description='Test',
                category=RequestCategory.PLUMBING,
                building_id=building_id,
                building_address='Test Address',
                address=f'кв. {i+1}',
                applicant_user_id=str(uuid4()),
                status=RequestStatus.NEW
            )
            db_session.add(request)

        await db_session.commit()

        # Query by building_id
        from sqlalchemy import select
        result = await db_session.execute(
            select(Request).where(Request.building_id == building_id)
        )
        requests = result.scalars().all()

        assert len(requests) == 3
        assert all(r.building_id == building_id for r in requests)


# ============================================================================
# Test Configuration
# ============================================================================

@pytest.fixture
async def db_session():
    """Database session fixture"""
    # TODO: Configure test database
    pass
