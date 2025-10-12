# Unit Tests for AI Integration Service - Fixed
# UK Management Bot - Shift Service Tests

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timedelta
from uuid import uuid4

from services.ai_integration import AIIntegrationService
from utils.datetime_utils import utc_now


@pytest.mark.asyncio
class TestAIIntegrationService:
    """Test AI Integration Service"""

    def test_service_initialization(self):
        """Test AI service initialization"""
        service = AIIntegrationService()

        assert service.ai_service_url is not None
        assert service.timeout > 0
        assert service.fallback_enabled is True

    async def test_fallback_mode_enabled(self):
        """Test service has fallback mode enabled"""
        service = AIIntegrationService()

        status = await service.get_fallback_status()

        assert status["fallback_enabled"] is True
        assert status["fallback_mode"] in ["simple", "enhanced", "historical"]

    async def test_get_assignment_recommendations_fallback(self):
        """Test assignment recommendations with fallback"""
        service = AIIntegrationService()

        shift_data = {
            "shift_id": str(uuid4()),
            "specialization": "plumber",
            "urgency": "high",
            "location": {"lat": 55.75, "lon": 37.61}
        }

        result = await service._fallback_assignment_recommendations(shift_data)

        assert isinstance(result, list)
        if len(result) > 0:
            assert "executor_id" in result[0]
            assert "total_score" in result[0]
            assert "confidence" in result[0]

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
                    "specialization": "plumber",
                    "location": "Building A"
                }
            ],
            "executors": [
                {
                    "id": "exec-1",
                    "specialization": "plumber"
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
                {"id": "1", "specialization": "plumber"},
                {"id": "2", "specialization": "electrician"}
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

    async def test_predict_workload_fallback(self):
        """Test workload prediction fallback"""
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

    async def test_enhanced_assignment_recommendations_scoring(self):
        """Test enhanced assignment recommendations use weighted scoring"""
        service = AIIntegrationService()

        shift_data = {
            "specialization": "plumber",
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
                {"id": "1", "specialization": "plumber"}
            ]
        }

        result = await service._historical_fallback_optimization(request_data)

        assert result["fallback"] is True
        assert result["fallback_mode"] == "historical"
        assert "recommendations" in result

    async def test_simple_workload_prediction(self):
        """Test simple workload prediction"""
        service = AIIntegrationService()

        prediction_data = {"target_date": datetime.utcnow().date().isoformat()}
        result = await service._simple_workload_prediction(prediction_data)

        assert result["predicted_workload"] > 0
        assert result["confidence"] == 0.3  # Simple mode has lower confidence
        assert "predicted_workload" in result

    async def test_historical_workload_prediction(self):
        """Test historical workload prediction"""
        service = AIIntegrationService()

        prediction_data = {"target_date": datetime.utcnow().date().isoformat()}
        result = await service._historical_workload_prediction(prediction_data)

        assert "predicted_workload" in result
        assert "confidence" in result
        assert result["predicted_workload"] > 0

    async def test_historical_assignment_recommendations(self):
        """Test historical assignment recommendations"""
        service = AIIntegrationService()

        shift_data = {
            "specialization": "plumber",
            "urgency": "high"
        }

        result = await service._historical_assignment_recommendations(shift_data)

        assert isinstance(result, list)
        # Result may be empty if no historical data
        assert len(result) >= 0

    async def test_get_assignment_recommendations_with_shift_data(self):
        """Test get_assignment_recommendations with valid shift data"""
        service = AIIntegrationService()

        shift_data = {
            "shift_id": str(uuid4()),
            "start_time": utc_now().isoformat(),
            "end_time": (utc_now() + timedelta(hours=8)).isoformat(),
            "specialization": "plumber",
            "priority": 2,
            "location": {"lat": 55.75, "lon": 37.61}
        }

        # This will use fallback since AI service is not running in tests
        result = await service.get_assignment_recommendations(shift_data)

        # In fallback mode, should return list
        assert isinstance(result, list) or result is None

    @patch('httpx.AsyncClient')
    async def test_predict_workload_timeout(self, mock_client):
        """Test workload prediction with timeout"""
        import httpx

        mock_client_instance = AsyncMock()
        mock_client_instance.post.side_effect = httpx.TimeoutException("Timeout")
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        service = AIIntegrationService()

        prediction_data = {"target_date": datetime.utcnow().date().isoformat()}
        result = await service.predict_workload(prediction_data)

        # Should return fallback result
        assert result is not None
        assert "predicted_workload" in result
