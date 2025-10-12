# Unit Tests for AI Integration Service
# UK Management Bot - Shift Service Tests

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from services.ai_integration import AIIntegrationService


@pytest.mark.asyncio
class TestAIIntegrationService:
    """Test AI Integration Service"""

    def test_service_initialization(self):
        """Test AI service initialization"""
        service = AIIntegrationService()

        assert service.ai_service_url is not None
        assert service.timeout > 0
        assert service.fallback_enabled is True

    @patch('middleware.auth_middleware.get_service_token', new_callable=AsyncMock)
    @patch('httpx.AsyncClient')
    async def test_optimize_shift_assignments_success(self, mock_client, mock_get_token):
        """Test successful shift optimization request"""
        # Mock get_service_token as async
        mock_get_token.return_value = "test-token-123"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={
            "confidence": 0.85,
            "impact_score": 0.6,
            "recommendations": []
        })

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        service = AIIntegrationService()
        result = await service.optimize_shift_assignments({"shifts": []})

        assert result is not None
        assert result["confidence"] == 0.85

    @patch('httpx.AsyncClient')
    async def test_optimize_shift_assignments_timeout(self, mock_client):
        """Test optimization with timeout fallback"""
        import httpx

        mock_client_instance = AsyncMock()
        mock_client_instance.post.side_effect = httpx.TimeoutException("Timeout")
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        service = AIIntegrationService()
        result = await service.optimize_shift_assignments({"shifts": []})

        # Should return fallback result
        assert result is not None
        assert result.get("fallback") is True

    @patch('httpx.AsyncClient')
    async def test_optimize_shift_assignments_error(self, mock_client):
        """Test optimization with error fallback"""
        mock_response = AsyncMock()
        mock_response.status_code = 500

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        service = AIIntegrationService()
        result = await service.optimize_shift_assignments({"shifts": []})

        # Should return fallback result
        assert result is not None
        assert result.get("fallback") is True

    async def test_fallback_optimization_enhanced_mode(self):
        """Test enhanced fallback optimization"""
        service = AIIntegrationService()

        request_data = {
            "shifts": [
                {
                    "id": "shift-1",
                    "specialization": "plumbing",
                    "location": "Building A"
                }
            ],
            "executors": [
                {
                    "id": "exec-1",
                    "specialization": "plumbing"
                }
            ]
        }

        result = await service._fallback_optimization(request_data)

        assert result["fallback"] is True
        assert result["fallback_mode"] == "enhanced"
        assert "confidence" in result
        assert "recommendations" in result

    async def test_enhanced_fallback_optimization_scoring(self):
        """Test enhanced fallback uses weighted scoring"""
        service = AIIntegrationService()

        request_data = {
            "shifts": [
                {"id": "1", "specialization": "plumbing"},
                {"id": "2", "specialization": "electrical"}
            ],
            "executors": []
        }

        result = await service._enhanced_fallback_optimization(request_data)

        assert "impact_score" in result
        assert "recommendations" in result
        assert len(result["recommendations"]) == 2

        # Check scoring factors
        for rec in result["recommendations"]:
            assert "optimization_score" in rec
            assert "factors" in rec
            assert "specialization" in rec["factors"]
            assert "geography" in rec["factors"]
            assert "workload" in rec["factors"]

    async def test_predict_workload_success(self):
        """Test workload prediction"""
        service = AIIntegrationService()

        prediction_data = {
            "target_date": datetime.utcnow().date().isoformat()
        }

        result = await service._fallback_workload_prediction(prediction_data)

        assert result is not None
        assert "predicted_workload" in result
        assert "confidence" in result

    async def test_enhanced_workload_prediction_temporal_analysis(self):
        """Test enhanced workload prediction uses temporal analysis"""
        service = AIIntegrationService()

        prediction_data = {
            "target_date": datetime.utcnow().date().isoformat()
        }

        result = await service._enhanced_workload_prediction(prediction_data)

        assert "predicted_workload" in result
        assert "confidence" in result
        assert "factors" in result
        assert "weekly_factor" in result["factors"]
        assert "seasonal_factor" in result["factors"]
        assert "prediction_range" in result

    async def test_get_assignment_recommendations_fallback(self):
        """Test assignment recommendations with fallback"""
        service = AIIntegrationService()

        shift_data = {
            "shift_id": "test-shift",
            "specialization": "plumbing",
            "urgency": "high"
        }

        result = await service._fallback_assignment_recommendations(shift_data)

        assert isinstance(result, list)
        if len(result) > 0:
            assert "executor_id" in result[0]
            assert "total_score" in result[0]
            assert "confidence" in result[0]

    async def test_enhanced_assignment_recommendations_scoring(self):
        """Test enhanced assignment recommendations use weighted scoring"""
        service = AIIntegrationService()

        shift_data = {
            "specialization": "plumbing",
            "location": {"lat": 55.75, "lon": 37.61},
            "urgency": "high"
        }

        result = await service._enhanced_assignment_recommendations(shift_data)

        assert len(result) >= 3  # Should generate 3-5 recommendations
        assert len(result) <= 5

        # Check scoring components
        for rec in result:
            assert "total_score" in rec
            assert "specialization_match" in rec
            assert "location_score" in rec
            assert "availability_score" in rec
            assert "rating_score" in rec

        # Check recommendations are sorted by score
        scores = [r["total_score"] for r in result]
        assert scores == sorted(scores, reverse=True)

    @patch('httpx.AsyncClient')
    async def test_check_ai_service_health_healthy(self, mock_client):
        """Test AI service health check when healthy"""
        mock_response = AsyncMock()
        mock_response.status_code = 200

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        service = AIIntegrationService()
        health = await service.check_ai_service_health()

        assert health["available"] is True
        assert health["status"] == "healthy"
        assert health["fallback_needed"] is False

    @patch('httpx.AsyncClient')
    async def test_check_ai_service_health_unhealthy(self, mock_client):
        """Test AI service health check when unhealthy"""
        mock_response = AsyncMock()
        mock_response.status_code = 503

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        service = AIIntegrationService()
        health = await service.check_ai_service_health()

        assert health["available"] is False
        assert health["fallback_needed"] is True

    async def test_get_fallback_status(self):
        """Test getting fallback configuration status"""
        service = AIIntegrationService()
        status = await service.get_fallback_status()

        assert "ai_service_health" in status
        assert "fallback_enabled" in status
        assert "fallback_mode" in status
        assert "fallback_confidence" in status
        assert "currently_using_fallback" in status

    async def test_fallback_mode_simple(self):
        """Test simple fallback mode"""
        service = AIIntegrationService()
        result = await service._simple_fallback_optimization({"shifts": []})

        assert result["fallback"] is True
        assert result["fallback_mode"] == "simple"
        assert result["confidence"] == 0.5

    async def test_fallback_mode_historical(self):
        """Test historical fallback mode"""
        service = AIIntegrationService()

        request_data = {
            "shifts": [
                {"id": "1", "specialization": "plumbing"}
            ]
        }

        result = await service._historical_fallback_optimization(request_data)

        assert result["fallback"] is True
        assert result["fallback_mode"] == "historical"
        assert "recommendations" in result

    def test_calculate_specialization_score(self):
        """Test specialization score calculation"""
        service = AIIntegrationService()

        shift = {"specialization": "plumbing"}
        executors = [
            {"specialization": "plumbing"},
            {"specialization": "electrical"}
        ]

        score = service._calculate_specialization_score(shift, executors)

        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_calculate_mock_specialization_score(self):
        """Test mock specialization score for different types"""
        service = AIIntegrationService()

        # High-skill specializations should have higher scores
        plumbing_score = service._calculate_mock_specialization_score("plumbing")
        general_score = service._calculate_mock_specialization_score("general")

        assert isinstance(plumbing_score, float)
        assert isinstance(general_score, float)
        assert 0.0 <= plumbing_score <= 1.0
        assert 0.0 <= general_score <= 1.0

    def test_generate_recommendation_reason(self):
        """Test recommendation reason generation"""
        service = AIIntegrationService()

        # High specialization and location scores
        reason = service._generate_recommendation_reason(0.9, 0.9)
        assert "specialization" in reason.lower() or "location" in reason.lower()

        # High specialization only
        reason = service._generate_recommendation_reason(0.9, 0.5)
        assert "specialization" in reason.lower()

        # High location only
        reason = service._generate_recommendation_reason(0.5, 0.9)
        assert "location" in reason.lower()
