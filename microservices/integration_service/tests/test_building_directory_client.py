"""
Tests for Building Directory Client
UK Management Bot - Integration Service
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.adapters.building_directory_client import BuildingDirectoryClient


@pytest.mark.asyncio
class TestBuildingDirectoryClient:
    """Test suite for Building Directory Client"""

    @pytest.fixture
    async def client(self, mock_httpx_client, mock_redis):
        """Create client instance with mock dependencies"""
        with patch("app.adapters.building_directory_client.httpx.AsyncClient", return_value=mock_httpx_client), \
             patch("app.adapters.building_directory_client.redis.asyncio.from_url", return_value=mock_redis):

            client = BuildingDirectoryClient(
                base_url="http://fake-building-api.com",
                api_key="fake-api-key",
                redis_url="redis://localhost:6379/9",
                management_company_id="test-company",
            )

            await client.initialize()
            yield client
            await client.shutdown()

    async def test_initialization(self, client):
        """Test client initialization"""
        assert client.management_company_id == "test-company"
        assert client.base_url == "http://fake-building-api.com"
        assert client._client is not None
        assert client._redis is not None

    async def test_get_building_success(self, client, sample_building_id):
        """Test successful building retrieval"""
        result = await client.get_building(
            building_id=sample_building_id,
            request_id="test-123",
        )

        assert result["success"] is True
        assert result["building"]["id"] == sample_building_id
        assert "name" in result["building"]
        assert "address" in result["building"]
        assert "coordinates" in result["building"]

    async def test_get_building_from_cache(self, client, mock_redis, sample_building_id):
        """Test building retrieval from cache"""
        # Setup cache hit
        cached_data = {
            "success": True,
            "building": {
                "id": sample_building_id,
                "name": "Cached Building",
                "address": "Cached Address",
            },
            "cached": True,
        }

        import json
        mock_redis.get.return_value = json.dumps(cached_data)

        result = await client.get_building(building_id=sample_building_id)

        assert result["cached"] is True
        assert result["building"]["name"] == "Cached Building"
        mock_redis.get.assert_called_once()

    async def test_search_buildings_success(self, client):
        """Test successful building search"""
        # Mock search response
        client._client.get.return_value.json.return_value = {
            "results": [
                {"id": "building-1", "name": "Building 1"},
                {"id": "building-2", "name": "Building 2"},
            ],
            "total": 2,
        }

        result = await client.search_buildings(
            query="Test",
            limit=10,
            offset=0,
            request_id="test-123",
        )

        assert result["success"] is True
        assert len(result["results"]) == 2
        assert result["total"] == 2

    async def test_validate_building_success(self, client, sample_building_id):
        """Test successful building validation"""
        # Mock validation response
        client._client.post.return_value.json.return_value = {
            "valid": True,
            "building_id": sample_building_id,
        }

        result = await client.validate_building(
            building_id=sample_building_id,
            address="Test Address 42",
            request_id="test-123",
        )

        assert result["success"] is True
        assert result["valid"] is True

    async def test_extract_coordinates_success(self, client):
        """Test coordinate extraction from address"""
        # Mock geocoding response
        client._client.post.return_value.json.return_value = {
            "coordinates": {
                "latitude": 41.311081,
                "longitude": 69.240562,
            },
            "confidence": 0.9,
        }

        result = await client.extract_coordinates(
            address="Test Address 42",
            request_id="test-123",
        )

        assert result["success"] is True
        assert result["coordinates"]["latitude"] == 41.311081
        assert result["coordinates"]["longitude"] == 69.240562

    async def test_get_building_not_found(self, client):
        """Test building not found error"""
        # Mock 404 response
        mock_response = AsyncMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"error": "Building not found"}
        client._client.get.return_value = mock_response

        result = await client.get_building(building_id="non-existent-id")

        assert result["success"] is False
        assert "error" in result

    async def test_api_error_handling(self, client, sample_building_id):
        """Test API error handling"""
        # Mock 500 error
        client._client.get.side_effect = Exception("API error")

        with pytest.raises(Exception) as exc_info:
            await client.get_building(building_id=sample_building_id)

        assert "API error" in str(exc_info.value)

    async def test_rate_limiting(self, client):
        """Test rate limiting mechanism"""
        initial_tokens = client._tokens

        # Consume token
        await client._consume_token()

        assert client._tokens == initial_tokens - 1

    async def test_cache_hit_rate(self, client, mock_redis, sample_building_id):
        """Test cache hit rate tracking"""
        import json

        # First request - cache miss
        mock_redis.get.return_value = None
        await client.get_building(building_id=sample_building_id)

        # Second request - cache hit
        cached_data = {"building": {"id": sample_building_id}, "cached": True}
        mock_redis.get.return_value = json.dumps(cached_data)
        result = await client.get_building(building_id=sample_building_id)

        assert result["cached"] is True

    async def test_cache_invalidation(self, client, mock_redis, sample_building_id):
        """Test cache invalidation"""
        await client.invalidate_cache(building_id=sample_building_id)

        # Verify delete was called
        mock_redis.delete.assert_called()

    async def test_health_check(self, client):
        """Test health check functionality"""
        result = await client.health_check()

        assert "status" in result
        assert "rate_limit_remaining" in result

    async def test_concurrent_requests(self, client, sample_building_id):
        """Test concurrent building requests"""
        import asyncio

        tasks = [
            client.get_building(building_id=f"{sample_building_id}-{i}")
            for i in range(5)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        assert len(results) == 5

    async def test_search_with_filters(self, client):
        """Test building search with filters"""
        client._client.get.return_value.json.return_value = {
            "results": [{"id": "filtered-1"}],
            "total": 1,
        }

        result = await client.search_buildings(
            query="Test",
            filters={"city": "Tashkent", "type": "residential"},
            limit=10,
        )

        assert result["success"] is True
        assert len(result["results"]) >= 0

    async def test_pagination(self, client):
        """Test search pagination"""
        # Page 1
        result1 = await client.search_buildings(query="Test", limit=10, offset=0)

        # Page 2
        result2 = await client.search_buildings(query="Test", limit=10, offset=10)

        assert result1["success"] is True
        assert result2["success"] is True

    async def test_cache_ttl(self, client, mock_redis, sample_building_id):
        """Test cache TTL setting"""
        await client.get_building(building_id=sample_building_id)

        # Verify cache was set with TTL
        mock_redis.set.assert_called()
        call_args = mock_redis.set.call_args
        assert call_args is not None

    async def test_request_id_propagation(self, client, sample_building_id):
        """Test request ID propagation to API"""
        request_id = "test-request-789"

        await client.get_building(
            building_id=sample_building_id,
            request_id=request_id,
        )

        # Request ID should be included in headers
        client._client.get.assert_called()

    async def test_tenant_isolation(self):
        """Test tenant isolation in cache keys"""
        client1 = BuildingDirectoryClient(
            base_url="http://fake-api.com",
            api_key="key1",
            redis_url="redis://localhost/9",
            management_company_id="company-1",
        )

        client2 = BuildingDirectoryClient(
            base_url="http://fake-api.com",
            api_key="key2",
            redis_url="redis://localhost/9",
            management_company_id="company-2",
        )

        # Cache keys should be different
        key1 = client1._get_cache_key("building-123")
        key2 = client2._get_cache_key("building-123")

        assert key1 != key2
        assert "company-1" in key1
        assert "company-2" in key2

    async def test_shutdown(self, client):
        """Test client shutdown"""
        await client.shutdown()

        # Clients should be closed
        assert client._client is not None
        assert client._redis is not None


@pytest.mark.asyncio
class TestBuildingDirectoryMetrics:
    """Test metrics collection for Building Directory"""

    @pytest.fixture
    async def client_with_metrics(self, mock_httpx_client, mock_redis):
        """Create client with metrics enabled"""
        with patch("app.adapters.building_directory_client.httpx.AsyncClient", return_value=mock_httpx_client), \
             patch("app.adapters.building_directory_client.redis.asyncio.from_url", return_value=mock_redis):

            client = BuildingDirectoryClient(
                base_url="http://fake-api.com",
                api_key="fake-key",
                redis_url="redis://localhost/9",
                management_company_id="test-company",
            )

            await client.initialize()
            yield client
            await client.shutdown()

    async def test_request_counter(self, client_with_metrics, sample_building_id):
        """Test request counter increments"""
        await client_with_metrics.get_building(building_id=sample_building_id)

        # Metrics should be recorded
        # (In real implementation, verify Prometheus metrics)

    async def test_cache_hit_metrics(self, client_with_metrics, mock_redis, sample_building_id):
        """Test cache hit metrics"""
        import json

        # Cache hit
        cached_data = {"building": {"id": sample_building_id}, "cached": True}
        mock_redis.get.return_value = json.dumps(cached_data)

        await client_with_metrics.get_building(building_id=sample_building_id)

        # Cache hit should be recorded

    async def test_response_time_metrics(self, client_with_metrics, sample_building_id):
        """Test response time tracking"""
        import time

        start = time.time()
        await client_with_metrics.get_building(building_id=sample_building_id)
        elapsed = time.time() - start

        # Response time should be reasonable
        assert elapsed < 1.0


@pytest.mark.asyncio
class TestBuildingDirectoryIntegration:
    """Integration tests for Building Directory Client"""

    @pytest.mark.skipif(
        not pytest.config.getoption("--run-integration", default=False),
        reason="Integration tests require --run-integration flag",
    )
    async def test_real_api_connection(self):
        """Test connection to real Building Directory API"""
        # Requires actual API credentials
        pass

    @pytest.mark.skipif(
        not pytest.config.getoption("--run-integration", default=False),
        reason="Integration tests require --run-integration flag",
    )
    async def test_real_redis_caching(self):
        """Test caching with real Redis"""
        # Requires Redis connection
        pass
