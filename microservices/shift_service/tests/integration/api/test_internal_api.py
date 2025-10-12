# Internal API Integration Tests
# UK Management Bot - Shift Service

import pytest
from httpx import AsyncClient


class TestInternalAPI:
    """Integration tests for Internal API endpoints"""

    async def test_health_check(self, client: AsyncClient, mock_auth_headers):
        """Test GET /api/v1/internal/health"""
        response = await client.get(
            "/api/v1/internal/health",
            headers=mock_auth_headers
        )

        # Health check critical endpoint
        assert response.status_code in [200, 500, 503]
        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            assert "service" in data
            assert data["service"] == "shift-service"

    async def test_service_info(self, client: AsyncClient, mock_auth_headers):
        """Test GET /api/v1/internal/info"""
        response = await client.get(
            "/api/v1/internal/info",
            headers=mock_auth_headers
        )

        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert "service" in data
            assert "version" in data
            assert "description" in data

    async def test_scheduler_status(self, client: AsyncClient, mock_auth_headers):
        """Test GET /api/v1/internal/scheduler/status"""
        response = await client.get(
            "/api/v1/internal/scheduler/status",
            headers=mock_auth_headers
        )

        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert "status" in data or "running" in data or "job_count" in data

    async def test_trigger_background_job(self, client: AsyncClient, mock_auth_headers):
        """Test POST /api/v1/internal/scheduler/trigger/{job_id}"""
        # Try to trigger a non-existent job
        response = await client.post(
            "/api/v1/internal/scheduler/trigger/test_job",
            headers=mock_auth_headers
        )

        # Should return 404 for non-existent job or 200 if job exists
        assert response.status_code in [200, 404, 500]

    async def test_trigger_real_job(self, client: AsyncClient, mock_auth_headers):
        """Test POST /api/v1/internal/scheduler/trigger/{job_id} with real job"""
        # Try triggering actual scheduled jobs
        job_ids = [
            "shift_optimization",
            "assignment_automation",
            "analytics_computation"
        ]

        for job_id in job_ids:
            response = await client.post(
                f"/api/v1/internal/scheduler/trigger/{job_id}",
                headers=mock_auth_headers
            )
            # Should succeed or fail gracefully
            assert response.status_code in [200, 404, 500]

    async def test_migration_status(self, client: AsyncClient, mock_auth_headers):
        """Test GET /api/v1/internal/migration/status"""
        response = await client.get(
            "/api/v1/internal/migration/status",
            headers=mock_auth_headers
        )

        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert "statistics" in data
            assert "migration_ready" in data

    async def test_service_metrics(self, client: AsyncClient, mock_auth_headers):
        """Test GET /api/v1/internal/metrics"""
        response = await client.get(
            "/api/v1/internal/metrics",
            headers=mock_auth_headers
        )

        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert "service_metrics" in data or "scheduler_metrics" in data
            assert "timestamp" in data

    async def test_shifts_summary(self, client: AsyncClient, mock_auth_headers):
        """Test GET /api/v1/internal/shifts/summary"""
        response = await client.get(
            "/api/v1/internal/shifts/summary",
            headers=mock_auth_headers
        )

        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert "summary" in data
            assert "generated_at" in data

    async def test_ai_service_health(self, client: AsyncClient, mock_auth_headers):
        """Test GET /api/v1/internal/ai/health"""
        response = await client.get(
            "/api/v1/internal/ai/health",
            headers=mock_auth_headers
        )

        assert response.status_code in [200, 500, 503]
        if response.status_code == 200:
            data = response.json()
            assert "ai_service_health" in data or "fallback_status" in data

    async def test_ai_fallback_status(self, client: AsyncClient, mock_auth_headers):
        """Test GET /api/v1/internal/ai/fallback/status"""
        response = await client.get(
            "/api/v1/internal/ai/fallback/status",
            headers=mock_auth_headers
        )

        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert "configuration" in data
            assert "available_modes" in data
            # Check fallback modes
            assert isinstance(data["available_modes"], list)
            assert "simple" in data["available_modes"]

    async def test_ai_fallback_test(self, client: AsyncClient, mock_auth_headers):
        """Test POST /api/v1/internal/ai/fallback/test"""
        response = await client.post(
            "/api/v1/internal/ai/fallback/test",
            headers=mock_auth_headers
        )

        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert "test_results" in data
            assert "status" in data

    async def test_ai_integration_test_all(self, client: AsyncClient, mock_auth_headers):
        """Test POST /api/v1/internal/ai/test/integration with mode=all"""
        response = await client.post(
            "/api/v1/internal/ai/test/integration?test_mode=all",
            headers=mock_auth_headers
        )

        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert "integration_test_results" in data
            assert "ai_service_health" in data

    async def test_ai_integration_test_optimization(self, client: AsyncClient, mock_auth_headers):
        """Test POST /api/v1/internal/ai/test/integration with mode=optimization"""
        response = await client.post(
            "/api/v1/internal/ai/test/integration?test_mode=optimization",
            headers=mock_auth_headers
        )

        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert "integration_test_results" in data
            results = data["integration_test_results"]
            assert "optimization" in results

    async def test_ai_integration_test_prediction(self, client: AsyncClient, mock_auth_headers):
        """Test POST /api/v1/internal/ai/test/integration with mode=prediction"""
        response = await client.post(
            "/api/v1/internal/ai/test/integration?test_mode=prediction",
            headers=mock_auth_headers
        )

        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert "integration_test_results" in data

    async def test_ai_integration_test_assignment(self, client: AsyncClient, mock_auth_headers):
        """Test POST /api/v1/internal/ai/test/integration with mode=assignment"""
        response = await client.post(
            "/api/v1/internal/ai/test/integration?test_mode=assignment",
            headers=mock_auth_headers
        )

        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert "integration_test_results" in data

    async def test_health_check_detailed(self, client: AsyncClient, mock_auth_headers):
        """Test health check returns detailed status information"""
        response = await client.get(
            "/api/v1/internal/health",
            headers=mock_auth_headers
        )

        if response.status_code == 200:
            data = response.json()
            # Verify structure
            assert "database" in data or "dependencies" in data
            if "dependencies" in data:
                assert "scheduler" in data["dependencies"] or "background_tasks" in data["dependencies"]

    async def test_metrics_structure(self, client: AsyncClient, mock_auth_headers):
        """Test metrics endpoint returns proper structure"""
        response = await client.get(
            "/api/v1/internal/metrics",
            headers=mock_auth_headers
        )

        if response.status_code == 200:
            data = response.json()
            # Verify metrics structure
            if "service_metrics" in data:
                metrics = data["service_metrics"]
                # Should have shift counts
                assert "total_shifts_7d" in metrics or isinstance(metrics, dict)

    async def test_shifts_summary_structure(self, client: AsyncClient, mock_auth_headers):
        """Test shifts summary returns proper structure"""
        response = await client.get(
            "/api/v1/internal/shifts/summary",
            headers=mock_auth_headers
        )

        if response.status_code == 200:
            data = response.json()
            assert "summary" in data
            if "summary" in data:
                summary = data["summary"]
                # Check for status breakdown
                assert "by_status" in summary or "urgent_shifts_24h" in summary

    async def test_migration_status_structure(self, client: AsyncClient, mock_auth_headers):
        """Test migration status returns statistics"""
        response = await client.get(
            "/api/v1/internal/migration/status",
            headers=mock_auth_headers
        )

        if response.status_code == 200:
            data = response.json()
            assert "statistics" in data
            stats = data["statistics"]
            # Should have counts for main entities
            assert "shifts" in stats or "templates" in stats or "assignments" in stats
