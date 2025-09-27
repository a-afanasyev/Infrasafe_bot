"""
API tests for AI endpoints
"""

import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock

from app.models import Request


@pytest.mark.api
class TestAIEndpoints:
    """Test AI API endpoints"""

    @pytest.mark.asyncio
    async def test_optimize_assignment_success(self, test_client: AsyncClient, sample_request: Request):
        """Test successful assignment optimization"""
        request_data = {
            "request_number": sample_request.request_number,
            "max_suggestions": 3,
            "algorithm": "greedy"
        }

        # Mock AI service response
        with patch('app.services.ai_service.AIService.get_smart_assignment_suggestions') as mock_ai:
            mock_optimization_result = type('OptimizationResult', (), {
                'suggestions': [
                    type('Suggestion', (), {
                        'executor_user_id': 'executor_001',
                        'confidence_score': 0.95,
                        'reasoning': 'Perfect match',
                        'estimated_completion_time': 4.5,
                        'cost_efficiency_score': 0.8,
                        'geographic_score': 0.9,
                        'workload_score': 0.85,
                        'specialization_score': 0.95
                    })()
                ],
                'algorithm_used': 'greedy',
                'execution_time_ms': 150.5,
                'optimization_score': 0.95,
                'metadata': {'source': 'local_optimization'}
            })()

            mock_ai.return_value = mock_optimization_result

            response = await test_client.post("/api/v1/ai/optimize", json=request_data)

            assert response.status_code == 200
            data = response.json()

            assert data["request_number"] == sample_request.request_number
            assert len(data["suggestions"]) == 1
            assert data["algorithm_used"] == "greedy"
            assert data["execution_time_ms"] == 150.5

            suggestion = data["suggestions"][0]
            assert suggestion["executor_user_id"] == "executor_001"
            assert suggestion["confidence_score"] == 0.95
            assert suggestion["reasoning"] == "Perfect match"

    @pytest.mark.asyncio
    async def test_optimize_assignment_not_found(self, test_client: AsyncClient):
        """Test optimization for non-existent request"""
        request_data = {
            "request_number": "999999-999",
            "max_suggestions": 3
        }

        response = await test_client.post("/api/v1/ai/optimize", json=request_data)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_optimize_batch_assignments(self, test_client: AsyncClient, sample_request: Request):
        """Test batch assignment optimization"""
        request_data = {
            "request_numbers": [sample_request.request_number],
            "algorithm": "hybrid",
            "optimization_mode": True
        }

        with patch('app.services.ai_service.AIService.optimize_batch_assignments') as mock_batch:
            mock_batch.return_value = {
                sample_request.request_number: type('OptimizationResult', (), {
                    'suggestions': [],
                    'algorithm_used': 'hybrid',
                    'execution_time_ms': 250.0,
                    'optimization_score': 0.88,
                    'metadata': {'source': 'batch_optimization'}
                })()
            }

            response = await test_client.post("/api/v1/ai/optimize/batch", json=request_data)

            assert response.status_code == 200
            data = response.json()

            assert len(data) == 1
            assert data[0]["request_number"] == sample_request.request_number
            assert data[0]["algorithm_used"] == "hybrid"

    @pytest.mark.asyncio
    async def test_smart_dispatch_success(self, test_client: AsyncClient, sample_request: Request):
        """Test successful smart dispatch"""
        request_data = {
            "request_number": sample_request.request_number,
            "dispatch_mode": "ai_assisted",
            "assigned_by_user_id": "manager_123"
        }

        with patch('app.services.smart_dispatcher.SmartDispatcher.dispatch_request') as mock_dispatch:
            mock_result = type('DispatchResult', (), {
                'request_number': sample_request.request_number,
                'assigned': True,
                'executor_user_id': 'executor_001',
                'assignment_method': 'ai_assisted_auto',
                'confidence_score': 0.92,
                'execution_time_ms': 180.0,
                'error_message': None,
                'suggestions_count': 3
            })()

            mock_dispatch.return_value = mock_result

            response = await test_client.post("/api/v1/ai/dispatch", json=request_data)

            assert response.status_code == 200
            data = response.json()

            assert data["request_number"] == sample_request.request_number
            assert data["assigned"] == True
            assert data["executor_user_id"] == "executor_001"
            assert data["assignment_method"] == "ai_assisted_auto"
            assert data["confidence_score"] == 0.92

    @pytest.mark.asyncio
    async def test_smart_dispatch_batch(self, test_client: AsyncClient, sample_request: Request):
        """Test batch smart dispatch"""
        request_data = {
            "request_numbers": [sample_request.request_number],
            "optimization_mode": True
        }

        with patch('app.services.smart_dispatcher.SmartDispatcher.dispatch_batch') as mock_batch_dispatch:
            mock_results = [
                type('DispatchResult', (), {
                    'request_number': sample_request.request_number,
                    'assigned': True,
                    'executor_user_id': 'executor_001',
                    'assignment_method': 'batch_auto_assign',
                    'confidence_score': 0.89,
                    'execution_time_ms': 300.0,
                    'error_message': None,
                    'suggestions_count': 2
                })()
            ]

            mock_batch_dispatch.return_value = mock_results

            response = await test_client.post("/api/v1/ai/dispatch/batch", json=request_data)

            assert response.status_code == 200
            data = response.json()

            assert len(data) == 1
            assert data[0]["request_number"] == sample_request.request_number
            assert data[0]["assigned"] == True
            assert data[0]["assignment_method"] == "batch_auto_assign"

    @pytest.mark.asyncio
    async def test_get_pending_assignments(self, test_client: AsyncClient, sample_request: Request):
        """Test getting pending assignments"""
        with patch('app.services.smart_dispatcher.SmartDispatcher.get_pending_assignments') as mock_pending:
            mock_pending.return_value = [
                {
                    "request_number": sample_request.request_number,
                    "title": sample_request.title,
                    "category": sample_request.category,
                    "priority": sample_request.priority,
                    "wait_time_minutes": 45.0,
                    "max_wait_time_minutes": 120,
                    "dispatch_mode": "ai_assisted",
                    "is_overdue": False,
                    "auto_assign_eligible": True,
                    "created_at": sample_request.created_at.isoformat(),
                    "address": sample_request.address
                }
            ]

            response = await test_client.get("/api/v1/ai/pending")

            assert response.status_code == 200
            data = response.json()

            assert "pending_assignments" in data
            assert "summary" in data
            assert len(data["pending_assignments"]) == 1

            assignment = data["pending_assignments"][0]
            assert assignment["request_number"] == sample_request.request_number
            assert assignment["is_overdue"] == False
            assert assignment["auto_assign_eligible"] == True

    @pytest.mark.asyncio
    async def test_get_pending_assignments_with_filter(self, test_client: AsyncClient):
        """Test getting pending assignments with time filter"""
        with patch('app.services.smart_dispatcher.SmartDispatcher.get_pending_assignments') as mock_pending:
            mock_pending.return_value = []

            response = await test_client.get(
                "/api/v1/ai/pending",
                params={"max_wait_minutes": 60}
            )

            assert response.status_code == 200
            data = response.json()

            assert data["pending_assignments"] == []
            assert data["summary"]["total_pending"] == 0

    @pytest.mark.asyncio
    async def test_get_available_algorithms(self, test_client: AsyncClient):
        """Test getting available AI algorithms"""
        response = await test_client.get("/api/v1/ai/algorithms")

        assert response.status_code == 200
        data = response.json()

        assert "algorithms" in data
        assert "recommendation" in data

        # Check that all expected algorithms are present
        algorithm_names = [alg["name"] for alg in data["algorithms"]]
        expected_algorithms = ["greedy", "genetic", "simulated_annealing", "hybrid", "ai_recommended"]

        for expected in expected_algorithms:
            assert expected in algorithm_names

        # Check algorithm details
        for algorithm in data["algorithms"]:
            assert "name" in algorithm
            assert "description" in algorithm
            assert "use_cases" in algorithm
            assert "performance" in algorithm
            assert "complexity" in algorithm

    @pytest.mark.asyncio
    async def test_get_dispatch_modes(self, test_client: AsyncClient):
        """Test getting available dispatch modes"""
        response = await test_client.get("/api/v1/ai/dispatch-modes")

        assert response.status_code == 200
        data = response.json()

        assert "dispatch_modes" in data
        assert "business_rules" in data

        # Check that all expected modes are present
        mode_names = [mode["name"] for mode in data["dispatch_modes"]]
        expected_modes = ["manual", "ai_assisted", "auto_assign", "batch_optimize"]

        for expected in expected_modes:
            assert expected in mode_names

        # Check mode details
        for mode in data["dispatch_modes"]:
            assert "name" in mode
            assert "description" in mode
            assert "automation_level" in mode
            assert "use_cases" in mode
            assert "requires_human_approval" in mode

    @pytest.mark.asyncio
    async def test_get_ai_metrics(self, test_client: AsyncClient):
        """Test getting AI service metrics"""
        with patch('app.services.ai_service.AIService.get_optimization_analytics') as mock_analytics, \
             patch('app.services.smart_dispatcher.SmartDispatcher.get_dispatcher_metrics') as mock_dispatcher:

            mock_analytics.return_value = {
                "period": {"days": 30},
                "optimization_metrics": {
                    "total_optimizations": 150,
                    "avg_optimization_time_ms": 200.5,
                    "success_rate": 0.96
                }
            }

            mock_dispatcher.return_value = {
                "performance_metrics": {
                    "total_dispatches": 75,
                    "auto_assignments": 45,
                    "success_rate": 0.94
                }
            }

            response = await test_client.get("/api/v1/ai/metrics")

            assert response.status_code == 200
            data = response.json()

            assert "ai_service_metrics" in data
            assert "smart_dispatcher_metrics" in data
            assert "service_health" in data

            # Check service health indicators
            health = data["service_health"]
            assert "ai_service_available" in health
            assert "fallback_enabled" in health
            assert "optimization_weights" in health


@pytest.mark.api
class TestAIEndpointsValidation:
    """Test AI API endpoints validation"""

    @pytest.mark.asyncio
    async def test_optimize_assignment_validation_errors(self, test_client: AsyncClient):
        """Test optimization request validation"""
        # Missing required fields
        invalid_data = {
            "max_suggestions": 10  # Missing request_number
        }

        response = await test_client.post("/api/v1/ai/optimize", json=invalid_data)
        assert response.status_code == 422

        # Invalid max_suggestions
        invalid_data = {
            "request_number": "250927-001",
            "max_suggestions": 0  # Below minimum
        }

        response = await test_client.post("/api/v1/ai/optimize", json=invalid_data)
        assert response.status_code == 422

        # Invalid algorithm
        invalid_data = {
            "request_number": "250927-001",
            "algorithm": "invalid_algorithm"
        }

        response = await test_client.post("/api/v1/ai/optimize", json=invalid_data)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_batch_optimization_validation(self, test_client: AsyncClient):
        """Test batch optimization validation"""
        # Empty request list
        invalid_data = {
            "request_numbers": []
        }

        response = await test_client.post("/api/v1/ai/optimize/batch", json=invalid_data)
        assert response.status_code == 422

        # Too many requests
        invalid_data = {
            "request_numbers": [f"250927-{i:03d}" for i in range(1, 52)]  # 51 requests (max 50)
        }

        response = await test_client.post("/api/v1/ai/optimize/batch", json=invalid_data)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_dispatch_validation_errors(self, test_client: AsyncClient):
        """Test dispatch request validation"""
        # Invalid dispatch mode
        invalid_data = {
            "request_number": "250927-001",
            "dispatch_mode": "invalid_mode"
        }

        response = await test_client.post("/api/v1/ai/dispatch", json=invalid_data)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_pending_assignments_validation(self, test_client: AsyncClient):
        """Test pending assignments parameter validation"""
        # Invalid max_wait_minutes
        response = await test_client.get(
            "/api/v1/ai/pending",
            params={"max_wait_minutes": 0}  # Below minimum
        )
        assert response.status_code == 422

        response = await test_client.get(
            "/api/v1/ai/pending",
            params={"max_wait_minutes": 1500}  # Above maximum
        )
        assert response.status_code == 422


@pytest.mark.api
class TestAIEndpointsErrorHandling:
    """Test AI API endpoints error handling"""

    @pytest.mark.asyncio
    async def test_optimization_service_error(self, test_client: AsyncClient, sample_request: Request):
        """Test handling of AI service errors"""
        request_data = {
            "request_number": sample_request.request_number,
            "max_suggestions": 3
        }

        with patch('app.services.ai_service.AIService.get_smart_assignment_suggestions',
                   side_effect=Exception("AI service temporarily unavailable")):

            response = await test_client.post("/api/v1/ai/optimize", json=request_data)

            assert response.status_code == 500
            data = response.json()
            assert "error" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_dispatch_service_error(self, test_client: AsyncClient, sample_request: Request):
        """Test handling of dispatch service errors"""
        request_data = {
            "request_number": sample_request.request_number
        }

        with patch('app.services.smart_dispatcher.SmartDispatcher.dispatch_request',
                   side_effect=Exception("Dispatch service error")):

            response = await test_client.post("/api/v1/ai/dispatch", json=request_data)

            assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_metrics_service_error(self, test_client: AsyncClient):
        """Test handling of metrics service errors"""
        with patch('app.services.ai_service.AIService.get_optimization_analytics',
                   side_effect=Exception("Analytics service error")):

            response = await test_client.get("/api/v1/ai/metrics")

            assert response.status_code == 500