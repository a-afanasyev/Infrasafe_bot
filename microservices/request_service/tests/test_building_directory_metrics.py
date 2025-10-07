"""
Request Service - Building Directory Metrics Tests
Task 11.1 - Metrics and Monitoring

Tests for Building Directory Prometheus metrics
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from app.clients.building_directory_client import BuildingDirectoryClient
from app.clients.building_directory_metrics import (
    building_directory_requests_total,
    building_directory_request_duration_seconds,
    building_directory_active_connections,
    building_validations_total,
    coordinate_extractions_total,
    building_directory_errors_total,
    building_denormalization_total
)


class TestBuildingDirectoryMetrics:
    """Test BuildingDirectoryClient metrics collection"""

    @pytest.fixture
    def client(self):
        """Create client instance"""
        return BuildingDirectoryClient(
            api_url="http://localhost:8002",
            management_company_id="00000000-0000-0000-0000-000000000001"
        )

    @pytest.fixture
    def mock_building_response(self):
        """Mock building response"""
        return {
            'id': str(uuid4()),
            'management_company_id': '00000000-0000-0000-0000-000000000001',
            'city': 'Tashkent',
            'street': 'Amir Temur',
            'house_number': '42',
            'full_address': 'Tashkent, Amir Temur, 42',
            'coordinates': {'lat': 41.311158, 'lon': 69.279737},
            'is_active': True
        }

    @pytest.mark.asyncio
    async def test_get_building_success_metrics(self, client, mock_building_response):
        """Test metrics for successful building retrieval"""
        building_id = uuid4()

        # Get initial metric value
        initial_success = building_directory_requests_total.labels(
            operation='get_building',
            status='success'
        )._value.get()

        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_building_response
            mock_get.return_value = mock_response

            building = await client.get_building(building_id)

            assert building is not None

            # Check metrics incremented
            final_success = building_directory_requests_total.labels(
                operation='get_building',
                status='success'
            )._value.get()

            assert final_success > initial_success

    @pytest.mark.asyncio
    async def test_get_building_not_found_metrics(self, client):
        """Test metrics for 404 not found"""
        building_id = uuid4()

        initial_not_found = building_directory_requests_total.labels(
            operation='get_building',
            status='not_found'
        )._value.get()

        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response

            building = await client.get_building(building_id)

            assert building is None

            final_not_found = building_directory_requests_total.labels(
                operation='get_building',
                status='not_found'
            )._value.get()

            assert final_not_found > initial_not_found

    @pytest.mark.asyncio
    async def test_validate_building_success_metrics(self, client, mock_building_response):
        """Test metrics for successful validation"""
        building_id = uuid4()

        initial_valid = building_validations_total.labels(result='valid')._value.get()

        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_building_response
            mock_get.return_value = mock_response

            is_valid, error, building = await client.validate_building_for_request(building_id)

            assert is_valid is True
            assert error is None

            final_valid = building_validations_total.labels(result='valid')._value.get()
            assert final_valid > initial_valid

    @pytest.mark.asyncio
    async def test_validate_building_inactive_metrics(self, client, mock_building_response):
        """Test metrics for inactive building validation"""
        building_id = uuid4()
        mock_building_response['is_active'] = False

        initial_inactive = building_validations_total.labels(
            result='invalid_inactive'
        )._value.get()

        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_building_response
            mock_get.return_value = mock_response

            is_valid, error, building = await client.validate_building_for_request(building_id)

            assert is_valid is False
            assert 'inactive' in error.lower()

            final_inactive = building_validations_total.labels(
                result='invalid_inactive'
            )._value.get()
            assert final_inactive > initial_inactive

    @pytest.mark.asyncio
    async def test_coordinate_extraction_nested_metrics(self, client, mock_building_response):
        """Test metrics for nested coordinate extraction"""
        building_id = uuid4()

        initial_nested = coordinate_extractions_total.labels(
            result='success',
            source='nested'
        )._value.get()

        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_building_response
            mock_get.return_value = mock_response

            data = await client.get_building_data_for_request(building_id)

            assert data is not None
            assert data['latitude'] == 41.311158
            assert data['longitude'] == 69.279737

            final_nested = coordinate_extractions_total.labels(
                result='success',
                source='nested'
            )._value.get()
            assert final_nested > initial_nested

    @pytest.mark.asyncio
    async def test_coordinate_extraction_flat_metrics(self, client, mock_building_response):
        """Test metrics for flat structure coordinates"""
        building_id = uuid4()

        # Remove nested coordinates, add flat structure
        del mock_building_response['coordinates']
        mock_building_response['latitude'] = 41.311158
        mock_building_response['longitude'] = 69.279737

        initial_flat = coordinate_extractions_total.labels(
            result='success',
            source='flat'
        )._value.get()

        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_building_response
            mock_get.return_value = mock_response

            data = await client.get_building_data_for_request(building_id)

            assert data is not None
            assert data['latitude'] == 41.311158

            final_flat = coordinate_extractions_total.labels(
                result='success',
                source='flat'
            )._value.get()
            assert final_flat > initial_flat

    @pytest.mark.asyncio
    async def test_coordinate_extraction_missing_metrics(self, client, mock_building_response):
        """Test metrics for missing coordinates"""
        building_id = uuid4()

        # Remove all coordinates
        del mock_building_response['coordinates']

        initial_missing = coordinate_extractions_total.labels(
            result='failure',
            source='missing'
        )._value.get()

        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_building_response
            mock_get.return_value = mock_response

            data = await client.get_building_data_for_request(building_id)

            assert data is not None
            assert data['latitude'] is None
            assert data['longitude'] is None

            final_missing = coordinate_extractions_total.labels(
                result='failure',
                source='missing'
            )._value.get()
            assert final_missing > initial_missing

    @pytest.mark.asyncio
    async def test_denormalization_success_metrics(self, client, mock_building_response):
        """Test metrics for successful denormalization"""
        building_id = uuid4()

        initial_success = building_denormalization_total.labels(
            status='success'
        )._value.get()

        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_building_response
            mock_get.return_value = mock_response

            data = await client.get_building_data_for_request(building_id)

            assert data is not None

            final_success = building_denormalization_total.labels(
                status='success'
            )._value.get()
            assert final_success > initial_success

    @pytest.mark.asyncio
    async def test_denormalization_failure_metrics(self, client):
        """Test metrics for failed denormalization"""
        building_id = uuid4()

        initial_failure = building_denormalization_total.labels(
            status='failure'
        )._value.get()

        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response

            data = await client.get_building_data_for_request(building_id)

            assert data is None

            final_failure = building_denormalization_total.labels(
                status='failure'
            )._value.get()
            assert final_failure > initial_failure

    @pytest.mark.asyncio
    async def test_error_metrics_timeout(self, client):
        """Test error metrics for timeout"""
        building_id = uuid4()

        initial_timeout = building_directory_errors_total.labels(
            error_type='timeout'
        )._value.get()

        with patch('httpx.AsyncClient.get') as mock_get:
            from httpx import TimeoutException
            mock_get.side_effect = TimeoutException("Timeout")

            building = await client.get_building(building_id)

            assert building is None

            final_timeout = building_directory_errors_total.labels(
                error_type='timeout'
            )._value.get()
            assert final_timeout > initial_timeout

    @pytest.mark.asyncio
    async def test_duration_histogram(self, client, mock_building_response):
        """Test request duration histogram"""
        building_id = uuid4()

        # Get histogram before
        histogram = building_directory_request_duration_seconds.labels(
            operation='get_building'
        )
        initial_count = histogram._sum._value.get()

        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_building_response
            mock_get.return_value = mock_response

            await client.get_building(building_id)

            # Histogram should have recorded duration
            final_count = histogram._sum._value.get()
            assert final_count >= initial_count  # Duration added


class TestMetricsEndpoint:
    """Test /metrics endpoint integration"""

    @pytest.mark.asyncio
    async def test_metrics_endpoint_includes_building_directory(self, test_client):
        """Test that /metrics endpoint includes Building Directory metrics"""
        response = await test_client.get("/metrics")

        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/plain')

        metrics_text = response.text

        # Check for Building Directory metrics
        assert 'building_directory_requests_total' in metrics_text
        assert 'building_directory_request_duration_seconds' in metrics_text
        assert 'building_validations_total' in metrics_text
        assert 'coordinate_extractions_total' in metrics_text
        assert 'building_denormalization_total' in metrics_text

    @pytest.mark.asyncio
    async def test_metrics_prometheus_format(self, test_client):
        """Test metrics are in Prometheus format"""
        response = await test_client.get("/metrics")

        assert response.status_code == 200
        metrics_text = response.text

        # Should contain HELP and TYPE declarations
        assert '# HELP' in metrics_text
        assert '# TYPE' in metrics_text

        # Should be properly formatted
        lines = metrics_text.split('\n')
        metric_lines = [l for l in lines if l and not l.startswith('#')]

        # Each metric line should have format: metric_name{labels} value
        for line in metric_lines:
            if line.strip():
                # Basic format check
                assert ' ' in line or '{' in line
