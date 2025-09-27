"""
Smoke tests for Request Service
UK Management Bot - Request Management System

Smoke tests for basic Request Service functionality as required by SPRINT_8_9_PLAN.md.
These tests verify core functionality works without detailed testing of edge cases.
"""

import pytest
import asyncio
from httpx import AsyncClient
from unittest.mock import patch

from tests.conftest import RequestFactory


@pytest.mark.smoke
class TestRequestServiceSmokeTests:
    """Smoke tests for Request Service basic functionality"""

    @pytest.mark.asyncio
    async def test_service_health_check(self, test_client: AsyncClient):
        """Test basic service health and connectivity"""
        # Test internal health endpoint
        response = await test_client.get("/api/v1/internal/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "unhealthy"]
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_create_request_smoke(self, test_client: AsyncClient):
        """Smoke test for request creation"""
        with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                   return_value="250927-SMOKE"):

            request_data = RequestFactory.create_request_data(
                title="Smoke Test Request",
                description="Basic smoke test for request creation",
                address="ул. Тестовая, д. 1, кв. 100",
                category="сантехника",
                priority="обычный"
            )

            response = await test_client.post("/api/v1/requests/", json=request_data)

            assert response.status_code == 201
            data = response.json()

            assert data["request_number"] == "250927-SMOKE"
            assert data["title"] == "Smoke Test Request"
            assert data["status"] == "новая"
            assert data["category"] == "сантехника"

    @pytest.mark.asyncio
    async def test_get_request_smoke(self, test_client: AsyncClient):
        """Smoke test for request retrieval"""
        # First create a request
        with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                   return_value="250927-GET"):

            request_data = RequestFactory.create_request_data()
            create_response = await test_client.post("/api/v1/requests/", json=request_data)
            assert create_response.status_code == 201

            request_number = create_response.json()["request_number"]

        # Then retrieve it
        response = await test_client.get(f"/api/v1/requests/{request_number}")

        assert response.status_code == 200
        data = response.json()
        assert data["request_number"] == request_number

    @pytest.mark.asyncio
    async def test_list_requests_smoke(self, test_client: AsyncClient):
        """Smoke test for request listing"""
        response = await test_client.get("/api/v1/requests/")

        assert response.status_code == 200
        data = response.json()

        assert "requests" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert isinstance(data["requests"], list)

    @pytest.mark.asyncio
    async def test_add_comment_smoke(self, test_client: AsyncClient):
        """Smoke test for adding comments"""
        # Create request first
        with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                   return_value="250927-COM"):

            request_data = RequestFactory.create_request_data()
            create_response = await test_client.post("/api/v1/requests/", json=request_data)
            request_number = create_response.json()["request_number"]

        # Add comment
        comment_data = RequestFactory.create_comment_data(
            comment_text="Smoke test comment",
            author_user_id="smoke_user_123"
        )

        response = await test_client.post(
            f"/api/v1/requests/{request_number}/comments/",
            json=comment_data
        )

        assert response.status_code == 201
        data = response.json()
        assert data["comment_text"] == "Smoke test comment"

    @pytest.mark.asyncio
    async def test_update_status_smoke(self, test_client: AsyncClient):
        """Smoke test for status updates"""
        # Create request first
        with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                   return_value="250927-STAT"):

            request_data = RequestFactory.create_request_data()
            create_response = await test_client.post("/api/v1/requests/", json=request_data)
            request_number = create_response.json()["request_number"]

        # Update status
        status_data = {
            "status": "в работе",
            "comment": "Smoke test status change",
            "user_id": "smoke_user_123"
        }

        response = await test_client.put(
            f"/api/v1/requests/{request_number}/status",
            json=status_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "в работе"

    @pytest.mark.asyncio
    async def test_assign_executor_smoke(self, test_client: AsyncClient):
        """Smoke test for executor assignment"""
        # Create request first
        with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                   return_value="250927-ASSIGN"):

            request_data = RequestFactory.create_request_data()
            create_response = await test_client.post("/api/v1/requests/", json=request_data)
            request_number = create_response.json()["request_number"]

        # Assign executor
        assignment_data = RequestFactory.create_assignment_data(
            assigned_to="smoke_executor_123",
            assignment_reason="Smoke test assignment"
        )

        response = await test_client.post(
            f"/api/v1/requests/{request_number}/assign",
            json=assignment_data,
            params={"assigned_by": "smoke_manager_123"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["assigned"] == True

    @pytest.mark.asyncio
    async def test_add_rating_smoke(self, test_client: AsyncClient):
        """Smoke test for adding ratings"""
        # Create and complete request first
        with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                   return_value="250927-RATE"):

            request_data = RequestFactory.create_request_data()
            create_response = await test_client.post("/api/v1/requests/", json=request_data)
            request_number = create_response.json()["request_number"]

            # Complete the request
            status_data = {
                "status": "выполнена",
                "comment": "Work completed",
                "user_id": "executor_123"
            }
            await test_client.put(f"/api/v1/requests/{request_number}/status", json=status_data)

        # Add rating
        rating_data = RequestFactory.create_rating_data(
            rating=5,
            feedback="Smoke test rating - excellent work!",
            author_user_id="smoke_user_123"
        )

        response = await test_client.post(
            f"/api/v1/requests/{request_number}/ratings/",
            json=rating_data
        )

        assert response.status_code == 201
        data = response.json()
        assert data["rating"] == 5

    @pytest.mark.asyncio
    async def test_search_requests_smoke(self, test_client: AsyncClient):
        """Smoke test for request search"""
        response = await test_client.get(
            "/api/v1/requests/search",
            params={
                "text_query": "test",
                "limit": 10
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "requests" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_get_statistics_smoke(self, test_client: AsyncClient):
        """Smoke test for statistics"""
        response = await test_client.get("/api/v1/requests/stats/summary")

        assert response.status_code == 200
        data = response.json()

        assert "total_requests" in data
        assert "by_status" in data
        assert "by_category" in data
        assert isinstance(data["total_requests"], int)

    @pytest.mark.asyncio
    async def test_ai_optimization_smoke(self, test_client: AsyncClient):
        """Smoke test for AI optimization"""
        # Create request first
        with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                   return_value="250927-AI"):

            request_data = RequestFactory.create_request_data()
            create_response = await test_client.post("/api/v1/requests/", json=request_data)
            request_number = create_response.json()["request_number"]

        # Test AI optimization
        optimize_data = {
            "request_number": request_number,
            "max_suggestions": 3
        }

        response = await test_client.post("/api/v1/ai/optimize", json=optimize_data)

        assert response.status_code == 200
        data = response.json()
        assert data["request_number"] == request_number
        assert "suggestions" in data
        assert "algorithm_used" in data

    @pytest.mark.asyncio
    async def test_export_functionality_smoke(self, test_client: AsyncClient):
        """Smoke test for export functionality"""
        # Test JSON export
        response = await test_client.get("/api/v1/requests/export/json?limit=5")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

        # Test CSV export
        response = await test_client.get("/api/v1/requests/export/csv?limit=5")

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]


@pytest.mark.smoke
class TestRequestServiceSmokePerformance:
    """Smoke tests for basic performance requirements"""

    @pytest.mark.asyncio
    async def test_response_time_smoke(self, test_client: AsyncClient):
        """Smoke test for basic response times"""
        import time

        # Test request creation response time
        start_time = time.time()

        with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                   return_value="250927-PERF"):

            request_data = RequestFactory.create_request_data()
            response = await test_client.post("/api/v1/requests/", json=request_data)

        end_time = time.time()

        assert response.status_code == 201

        # Should complete within 2 seconds for smoke test
        execution_time = end_time - start_time
        assert execution_time < 2.0

    @pytest.mark.asyncio
    async def test_concurrent_requests_smoke(self, test_client: AsyncClient):
        """Smoke test for handling concurrent requests"""
        with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                   side_effect=[f"250927-C{i:02d}" for i in range(1, 6)]):

            # Create 5 concurrent requests
            async def create_request(index):
                request_data = RequestFactory.create_request_data(
                    title=f"Concurrent Smoke Test {index}"
                )
                return await test_client.post("/api/v1/requests/", json=request_data)

            tasks = [create_request(i) for i in range(1, 6)]
            responses = await asyncio.gather(*tasks)

            # All should succeed
            for response in responses:
                assert response.status_code == 201

            # All should have unique request numbers
            request_numbers = [r.json()["request_number"] for r in responses]
            assert len(set(request_numbers)) == len(request_numbers)


@pytest.mark.smoke
class TestRequestServiceSmokeReliability:
    """Smoke tests for basic reliability and error handling"""

    @pytest.mark.asyncio
    async def test_invalid_request_handling_smoke(self, test_client: AsyncClient):
        """Smoke test for invalid request handling"""
        # Test with missing required fields
        invalid_data = {
            "title": "",  # Empty title
            "description": "Test"
            # Missing other required fields
        }

        response = await test_client.post("/api/v1/requests/", json=invalid_data)

        assert response.status_code == 422  # Validation error
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_not_found_handling_smoke(self, test_client: AsyncClient):
        """Smoke test for not found error handling"""
        response = await test_client.get("/api/v1/requests/999999-999")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_service_fallback_smoke(self, test_client: AsyncClient):
        """Smoke test for service fallback mechanisms"""
        # Test AI service fallback when external service fails
        with patch('app.services.ai_service.AIService._get_ai_service_suggestions',
                   side_effect=Exception("External AI service unavailable")):

            # Create request first
            with patch('app.services.request_number_service.RequestNumberService.generate_request_number',
                       return_value="250927-FALL"):

                request_data = RequestFactory.create_request_data()
                create_response = await test_client.post("/api/v1/requests/", json=request_data)
                request_number = create_response.json()["request_number"]

            # AI optimization should still work with fallback
            optimize_data = {
                "request_number": request_number,
                "max_suggestions": 3
            }

            response = await test_client.post("/api/v1/ai/optimize", json=optimize_data)

            assert response.status_code == 200  # Should work with local fallback
            data = response.json()
            assert data["algorithm_used"] in ["greedy", "genetic", "simulated_annealing", "hybrid"]


def run_smoke_tests():
    """
    Run smoke tests independently

    This function can be called directly for quick smoke testing
    without running the full test suite.
    """
    import subprocess
    import sys

    try:
        # Run only smoke tests
        result = subprocess.run([
            sys.executable, "-m", "pytest",
            "tests/smoke_tests.py",
            "-m", "smoke",
            "-v",
            "--tb=short"
        ], capture_output=True, text=True)

        print("Smoke Test Results:")
        print("=" * 50)
        print(result.stdout)

        if result.stderr:
            print("Errors:")
            print(result.stderr)

        return result.returncode == 0

    except Exception as e:
        print(f"Failed to run smoke tests: {e}")
        return False


if __name__ == "__main__":
    # Allow running smoke tests directly
    success = run_smoke_tests()
    exit(0 if success else 1)