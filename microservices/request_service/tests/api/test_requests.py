"""
API tests for Request endpoints
"""

import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock

from app.models import Request, RequestStatus, RequestPriority, RequestCategory
from tests.conftest import RequestFactory


@pytest.mark.api
class TestRequestsAPI:
    """Test Request API endpoints"""

    @pytest.mark.asyncio
    async def test_create_request_success(self, test_client: AsyncClient, mock_request_number_service):
        """Test successful request creation"""
        with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                   return_value="250927-001"):

            request_data = RequestFactory.create_request_data()

            response = await test_client.post("/api/v1/requests/", json=request_data)

            assert response.status_code == 201
            data = response.json()

            assert data["request_number"] == "250927-001"
            assert data["title"] == request_data["title"]
            assert data["status"] == "новая"
            assert data["applicant_user_id"] == request_data["applicant_user_id"]

    @pytest.mark.asyncio
    async def test_create_request_validation_error(self, test_client: AsyncClient):
        """Test request creation with validation errors"""
        # Missing required fields
        invalid_data = {
            "title": "",  # Empty title
            "description": "Test",
            "category": "invalid_category",  # Invalid category
            "address": "Test Address"
            # Missing applicant_user_id
        }

        response = await test_client.post("/api/v1/requests/", json=invalid_data)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_create_request_with_media(self, test_client: AsyncClient):
        """Test request creation with media files"""
        with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                   return_value="250927-002"):

            request_data = RequestFactory.create_request_data(
                media_file_ids=["file_1", "file_2"]
            )

            response = await test_client.post("/api/v1/requests/", json=request_data)

            assert response.status_code == 201
            data = response.json()

            assert data["media_file_ids"] == ["file_1", "file_2"]

    @pytest.mark.asyncio
    async def test_get_request_success(self, test_client: AsyncClient, sample_request: Request):
        """Test successful request retrieval"""
        response = await test_client.get(f"/api/v1/requests/{sample_request.request_number}")

        assert response.status_code == 200
        data = response.json()

        assert data["request_number"] == sample_request.request_number
        assert data["title"] == sample_request.title
        assert data["status"] == sample_request.status

    @pytest.mark.asyncio
    async def test_get_request_not_found(self, test_client: AsyncClient):
        """Test request retrieval for non-existent request"""
        response = await test_client.get("/api/v1/requests/999999-999")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_list_requests_default(self, test_client: AsyncClient, sample_request: Request):
        """Test listing requests with default parameters"""
        response = await test_client.get("/api/v1/requests/")

        assert response.status_code == 200
        data = response.json()

        assert "requests" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert len(data["requests"]) >= 1

    @pytest.mark.asyncio
    async def test_list_requests_with_filters(self, test_client: AsyncClient, sample_request: Request):
        """Test listing requests with filters"""
        response = await test_client.get(
            "/api/v1/requests/",
            params={
                "status": "новая",
                "category": "сантехника",
                "limit": 10
            }
        )

        assert response.status_code == 200
        data = response.json()

        # All returned requests should match filters
        for request in data["requests"]:
            assert request["status"] == "новая"
            assert request["category"] == "сантехника"

    @pytest.mark.asyncio
    async def test_update_request_success(self, test_client: AsyncClient, sample_request: Request):
        """Test successful request update"""
        update_data = {
            "title": "Updated Title",
            "description": "Updated Description",
            "priority": "высокий"
        }

        response = await test_client.put(
            f"/api/v1/requests/{sample_request.request_number}",
            json=update_data
        )

        assert response.status_code == 200
        data = response.json()

        assert data["title"] == "Updated Title"
        assert data["description"] == "Updated Description"
        assert data["priority"] == "высокий"

    @pytest.mark.asyncio
    async def test_update_request_not_found(self, test_client: AsyncClient):
        """Test update for non-existent request"""
        update_data = {"title": "Updated Title"}

        response = await test_client.put("/api/v1/requests/999999-999", json=update_data)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_request_status(self, test_client: AsyncClient, sample_request: Request):
        """Test request status update"""
        status_data = {
            "status": "в работе",
            "comment": "Начинаем работу",
            "user_id": "executor_123"
        }

        response = await test_client.put(
            f"/api/v1/requests/{sample_request.request_number}/status",
            json=status_data
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "в работе"

    @pytest.mark.asyncio
    async def test_delete_request_success(self, test_client: AsyncClient, sample_request: Request):
        """Test successful request deletion (soft delete)"""
        response = await test_client.delete(
            f"/api/v1/requests/{sample_request.request_number}",
            params={"user_id": "admin_123"}
        )

        assert response.status_code == 204

        # Verify it's soft deleted (not found in normal queries)
        get_response = await test_client.get(f"/api/v1/requests/{sample_request.request_number}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_request_not_found(self, test_client: AsyncClient):
        """Test deletion of non-existent request"""
        response = await test_client.delete(
            "/api/v1/requests/999999-999",
            params={"user_id": "admin_123"}
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_request_statistics(self, test_client: AsyncClient, sample_request: Request):
        """Test request statistics endpoint"""
        response = await test_client.get("/api/v1/requests/stats/summary")

        assert response.status_code == 200
        data = response.json()

        assert "total_requests" in data
        assert "by_status" in data
        assert "by_category" in data
        assert "by_priority" in data
        assert data["total_requests"] >= 1

    @pytest.mark.asyncio
    async def test_get_request_statistics_with_date_filter(self, test_client: AsyncClient):
        """Test request statistics with date filtering"""
        response = await test_client.get(
            "/api/v1/requests/stats/summary",
            params={"days": 7}
        )

        assert response.status_code == 200
        data = response.json()

        assert "period_start" in data
        assert "period_end" in data


@pytest.mark.api
class TestRequestsAPIErrorHandling:
    """Test Request API error handling"""

    @pytest.mark.asyncio
    async def test_create_request_database_error(self, test_client: AsyncClient):
        """Test request creation with database error"""
        with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                   side_effect=Exception("Database connection failed")):

            request_data = RequestFactory.create_request_data()

            response = await test_client.post("/api/v1/requests/", json=request_data)

            assert response.status_code == 500
            data = response.json()
            assert "error" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_invalid_request_number_format(self, test_client: AsyncClient):
        """Test API with invalid request number format"""
        invalid_numbers = [
            "invalid-format",
            "123",
            "abc-def",
            "250927-0000"
        ]

        for invalid_number in invalid_numbers:
            response = await test_client.get(f"/api/v1/requests/{invalid_number}")
            assert response.status_code in [400, 404]

    @pytest.mark.asyncio
    async def test_request_with_too_large_payload(self, test_client: AsyncClient):
        """Test request creation with payload that's too large"""
        # Create request with very long description
        request_data = RequestFactory.create_request_data(
            description="x" * 10000  # Exceeds max length
        )

        response = await test_client.post("/api/v1/requests/", json=request_data)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_concurrent_request_creation(self, test_client: AsyncClient):
        """Test concurrent request creation"""
        import asyncio

        with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                   side_effect=["250927-001", "250927-002", "250927-003"]):

            # Create multiple requests concurrently
            tasks = []
            for i in range(3):
                request_data = RequestFactory.create_request_data(
                    title=f"Concurrent Request {i+1}",
                    applicant_user_id=f"user_{i+1}"
                )
                task = test_client.post("/api/v1/requests/", json=request_data)
                tasks.append(task)

            responses = await asyncio.gather(*tasks)

            # All should succeed
            for response in responses:
                assert response.status_code == 201

            # All should have unique request numbers
            request_numbers = [r.json()["request_number"] for r in responses]
            assert len(set(request_numbers)) == len(request_numbers)


@pytest.mark.api
class TestRequestsAPIPerformance:
    """Test Request API performance"""

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_list_requests_performance(self, test_client: AsyncClient):
        """Test performance of request listing with large dataset"""
        # This would be expanded in a real performance test
        import time

        start_time = time.time()
        response = await test_client.get("/api/v1/requests/", params={"limit": 100})
        end_time = time.time()

        assert response.status_code == 200

        # Should complete within reasonable time (adjust threshold as needed)
        execution_time = end_time - start_time
        assert execution_time < 5.0  # 5 seconds threshold

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_request_search_performance(self, test_client: AsyncClient):
        """Test performance of request search"""
        import time

        start_time = time.time()
        response = await test_client.get(
            "/api/v1/requests/search",
            params={
                "text_query": "тест",
                "category": "сантехника",
                "limit": 50
            }
        )
        end_time = time.time()

        assert response.status_code == 200

        execution_time = end_time - start_time
        assert execution_time < 3.0  # 3 seconds threshold


@pytest.mark.api
class TestRequestsAPIIntegration:
    """Test Request API integration scenarios"""

    @pytest.mark.asyncio
    async def test_request_lifecycle_complete(self, test_client: AsyncClient):
        """Test complete request lifecycle through API"""
        # 1. Create request
        with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                   return_value="250927-100"):

            request_data = RequestFactory.create_request_data()
            create_response = await test_client.post("/api/v1/requests/", json=request_data)

            assert create_response.status_code == 201
            request_number = create_response.json()["request_number"]

        # 2. Update request
        update_data = {"priority": "высокий"}
        update_response = await test_client.put(
            f"/api/v1/requests/{request_number}",
            json=update_data
        )
        assert update_response.status_code == 200

        # 3. Add comment
        comment_data = RequestFactory.create_comment_data()
        comment_response = await test_client.post(
            f"/api/v1/requests/{request_number}/comments/",
            json=comment_data
        )
        assert comment_response.status_code == 201

        # 4. Assign executor
        assignment_data = RequestFactory.create_assignment_data()
        assign_response = await test_client.post(
            f"/api/v1/requests/{request_number}/assign",
            json=assignment_data,
            params={"assigned_by": "manager_123"}
        )
        assert assign_response.status_code == 200

        # 5. Update status to completed
        status_data = {
            "status": "выполнена",
            "comment": "Работа завершена",
            "user_id": "executor_123"
        }
        status_response = await test_client.put(
            f"/api/v1/requests/{request_number}/status",
            json=status_data
        )
        assert status_response.status_code == 200

        # 6. Add rating
        rating_data = RequestFactory.create_rating_data()
        rating_response = await test_client.post(
            f"/api/v1/requests/{request_number}/ratings/",
            json=rating_data
        )
        assert rating_response.status_code == 201

        # 7. Verify final state
        final_response = await test_client.get(f"/api/v1/requests/{request_number}")
        assert final_response.status_code == 200

        final_data = final_response.json()
        assert final_data["status"] == "выполнена"
        assert final_data["priority"] == "высокий"

    @pytest.mark.asyncio
    async def test_bulk_operations(self, test_client: AsyncClient):
        """Test bulk operations on requests"""
        # Create multiple requests first
        request_numbers = []

        with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                   side_effect=["250927-101", "250927-102", "250927-103"]):

            for i in range(3):
                request_data = RequestFactory.create_request_data(
                    title=f"Bulk Request {i+1}"
                )
                response = await test_client.post("/api/v1/requests/", json=request_data)
                assert response.status_code == 201
                request_numbers.append(response.json()["request_number"])

        # Test bulk assignment (would need to implement this endpoint)
        # This is a placeholder for future bulk operations
        assert len(request_numbers) == 3