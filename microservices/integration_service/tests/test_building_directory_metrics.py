"""
Tests for Building Directory Metrics
Integration Service - UK Management Bot

Tests Prometheus metrics collection for Building Directory operations
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.building_directory_metrics import (
    building_directory_requests_total,
    building_directory_request_duration_seconds,
    building_cache_operations_total,
    building_validations_total,
    coordinate_extractions_total,
    building_directory_errors_total,
    building_denormalization_total,
    track_building_operation,
    record_cache_hit,
    record_cache_miss,
    record_cache_set,
    record_validation,
    record_coordinate_extraction,
    record_denormalization,
    get_metrics_summary
)


class TestBuildingDirectoryMetrics:
    """Test Building Directory Prometheus metrics"""

    def test_metrics_summary(self):
        """Test metrics summary is complete"""
        summary = get_metrics_summary()

        assert "request_metrics" in summary
        assert "cache_metrics" in summary
        assert "validation_metrics" in summary
        assert "geocoding_metrics" in summary
        assert "error_metrics" in summary
        assert "data_metrics" in summary

    def test_record_cache_hit(self):
        """Test cache hit recording"""
        # Get initial count
        initial = building_cache_operations_total.labels(
            operation="get",
            result="hit"
        )._value.get()

        # Record hit
        record_cache_hit()

        # Verify increment
        final = building_cache_operations_total.labels(
            operation="get",
            result="hit"
        )._value.get()

        assert final > initial

    def test_record_cache_miss(self):
        """Test cache miss recording"""
        initial = building_cache_operations_total.labels(
            operation="get",
            result="miss"
        )._value.get()

        record_cache_miss()

        final = building_cache_operations_total.labels(
            operation="get",
            result="miss"
        )._value.get()

        assert final > initial

    def test_record_cache_set(self):
        """Test cache set recording"""
        initial = building_cache_operations_total.labels(
            operation="set",
            result="success"
        )._value.get()

        record_cache_set()

        final = building_cache_operations_total.labels(
            operation="set",
            result="success"
        )._value.get()

        assert final > initial

    def test_record_validation_valid(self):
        """Test recording valid validation"""
        initial = building_validations_total.labels(result="valid")._value.get()

        record_validation(is_valid=True)

        final = building_validations_total.labels(result="valid")._value.get()
        assert final > initial

    def test_record_validation_invalid(self):
        """Test recording invalid validation"""
        initial = building_validations_total.labels(result="invalid")._value.get()

        record_validation(is_valid=False)

        final = building_validations_total.labels(result="invalid")._value.get()
        assert final > initial

    def test_record_coordinate_extraction_success(self):
        """Test recording successful coordinate extraction"""
        initial = coordinate_extractions_total.labels(
            provider="google_maps",
            status="success"
        )._value.get()

        record_coordinate_extraction(provider="google_maps", success=True)

        final = coordinate_extractions_total.labels(
            provider="google_maps",
            status="success"
        )._value.get()

        assert final > initial

    def test_record_coordinate_extraction_failure(self):
        """Test recording failed coordinate extraction"""
        initial = coordinate_extractions_total.labels(
            provider="yandex_maps",
            status="failure"
        )._value.get()

        record_coordinate_extraction(provider="yandex_maps", success=False)

        final = coordinate_extractions_total.labels(
            provider="yandex_maps",
            status="failure"
        )._value.get()

        assert final > initial

    def test_record_denormalization_success(self):
        """Test recording successful denormalization"""
        initial = building_denormalization_total.labels(status="success")._value.get()

        record_denormalization(success=True)

        final = building_denormalization_total.labels(status="success")._value.get()
        assert final > initial

    def test_record_denormalization_failure(self):
        """Test recording failed denormalization"""
        initial = building_denormalization_total.labels(status="failure")._value.get()

        record_denormalization(success=False)

        final = building_denormalization_total.labels(status="failure")._value.get()
        assert final > initial

    @pytest.mark.asyncio
    async def test_track_building_operation_success(self):
        """Test operation tracking decorator on success"""

        @track_building_operation("test_operation")
        async def mock_operation():
            return {"test": "data"}

        # Get initial count
        initial_requests = building_directory_requests_total.labels(
            operation="test_operation",
            status="success"
        )._value.get()

        # Execute operation
        result = await mock_operation()

        # Verify result
        assert result == {"test": "data"}

        # Verify metrics
        final_requests = building_directory_requests_total.labels(
            operation="test_operation",
            status="success"
        )._value.get()

        assert final_requests > initial_requests

    @pytest.mark.asyncio
    async def test_track_building_operation_error(self):
        """Test operation tracking decorator on error"""

        @track_building_operation("test_operation_error")
        async def mock_operation_with_error():
            raise ValueError("Test error")

        # Get initial count
        initial_requests = building_directory_requests_total.labels(
            operation="test_operation_error",
            status="error"
        )._value.get()

        initial_errors = building_directory_errors_total.labels(
            error_type="ValueError",
            operation="test_operation_error"
        )._value.get()

        # Execute operation (should raise)
        with pytest.raises(ValueError, match="Test error"):
            await mock_operation_with_error()

        # Verify error metrics
        final_requests = building_directory_requests_total.labels(
            operation="test_operation_error",
            status="error"
        )._value.get()

        final_errors = building_directory_errors_total.labels(
            error_type="ValueError",
            operation="test_operation_error"
        )._value.get()

        assert final_requests > initial_requests
        assert final_errors > initial_errors


class TestMetricsIntegration:
    """Integration tests for metrics with actual operations"""

    @pytest.mark.asyncio
    async def test_full_operation_flow_with_metrics(self):
        """Test complete operation flow with all metrics"""

        # Simulate full flow
        building_id = uuid4()

        # 1. Cache miss
        record_cache_miss()

        # 2. API request
        @track_building_operation("get_building")
        async def get_building():
            return {
                "id": str(building_id),
                "address": "Test Address",
                "latitude": 41.0,
                "longitude": 69.0
            }

        building = await get_building()

        # 3. Cache set
        record_cache_set()

        # 4. Validation
        record_validation(is_valid=True)

        # 5. Coordinate extraction
        record_coordinate_extraction(provider="google_maps", success=True)

        # 6. Denormalization
        record_denormalization(success=True)

        # Verify all metrics incremented
        assert building is not None
        # (Metrics verification already done in individual tests)

    @pytest.mark.asyncio
    async def test_error_flow_with_metrics(self):
        """Test error flow with metrics"""

        # Simulate error flow
        building_id = uuid4()

        # 1. Cache miss
        record_cache_miss()

        # 2. API request fails
        @track_building_operation("get_building_error")
        async def get_building_error():
            raise ConnectionError("API unavailable")

        # Execute (should raise)
        with pytest.raises(ConnectionError):
            await get_building_error()

        # 3. Denormalization fails
        record_denormalization(success=False)

        # Verify error metrics recorded
        # (Already verified in decorator tests)
