"""
Unit tests for Request Service business logic services
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal
from datetime import datetime

from app.services.request_number_service import RequestNumberService
from app.services.ai_service import AIService, AssignmentAlgorithm, ExecutorProfile, AssignmentSuggestion
from app.services.smart_dispatcher import SmartDispatcher, DispatchMode
from app.services.geo_optimizer import GeoOptimizer, GeoPoint, DistanceUnit
from app.models import Request, RequestStatus, RequestPriority, RequestCategory


@pytest.mark.unit
class TestRequestNumberService:
    """Test RequestNumberService functionality"""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client"""
        redis_mock = MagicMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.incr = AsyncMock(return_value=1)
        redis_mock.expire = AsyncMock(return_value=True)
        return redis_mock

    @pytest.fixture
    def service(self, mock_redis):
        """Create RequestNumberService with mocked Redis"""
        return RequestNumberService(redis_client=mock_redis)

    @pytest.mark.asyncio
    async def test_generate_request_number_new_day(self, service, mock_redis):
        """Test generating request number for new day"""
        # Mock Redis to return None (new day)
        mock_redis.get.return_value = None
        mock_redis.incr.return_value = 1

        request_number = await service.generate_request_number()

        # Should generate format YYMMDD-001
        assert len(request_number) == 10
        assert request_number.endswith("-001")
        assert "-" in request_number

        # Check Redis calls
        mock_redis.get.assert_called_once()
        mock_redis.incr.assert_called_once()
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_request_number_existing_day(self, service, mock_redis):
        """Test generating request number for existing day"""
        # Mock Redis to return existing counter
        mock_redis.incr.return_value = 5

        request_number = await service.generate_request_number()

        # Should generate format YYMMDD-005
        assert request_number.endswith("-005")

        # Should call incr but not expire (key already exists)
        mock_redis.incr.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_request_number_database_fallback(self, service, mock_redis):
        """Test database fallback when Redis fails"""
        # Mock Redis to raise exception
        mock_redis.incr.side_effect = Exception("Redis connection failed")

        with patch.object(service, '_generate_from_database', return_value="250927-001") as mock_db:
            request_number = await service.generate_request_number()

            assert request_number == "250927-001"
            mock_db.assert_called_once()

    def test_validate_request_number_valid(self, service):
        """Test validation of valid request numbers"""
        valid_numbers = [
            "250927-001",
            "991231-999",
            "000101-123"
        ]

        for number in valid_numbers:
            assert service.validate_request_number(number) == True

    def test_validate_request_number_invalid(self, service):
        """Test validation of invalid request numbers"""
        invalid_numbers = [
            "25092-001",      # Wrong date format
            "250927-0001",    # Too many digits in sequence
            "250927001",      # Missing dash
            "250927-",        # Missing sequence
            "abc927-001",     # Non-numeric date
            "250927-abc",     # Non-numeric sequence
            "",               # Empty string
            "250927-000",     # Zero sequence
            "250927-1000"     # Sequence too high
        ]

        for number in invalid_numbers:
            assert service.validate_request_number(number) == False

    def test_parse_request_number(self, service):
        """Test parsing request number components"""
        date_part, sequence = service._parse_request_number("250927-123")

        assert date_part == "250927"
        assert sequence == 123

    def test_format_request_number(self, service):
        """Test formatting request number"""
        formatted = service._format_request_number("250927", 42)

        assert formatted == "250927-042"

    def test_get_date_key(self, service):
        """Test getting date key for current date"""
        date_key = service._get_date_key()

        # Should be YYMMDD format
        assert len(date_key) == 6
        assert date_key.isdigit()


@pytest.mark.unit
class TestAIService:
    """Test AIService functionality"""

    @pytest.fixture
    def ai_service(self):
        """Create AIService instance"""
        return AIService()

    @pytest.fixture
    def sample_request(self):
        """Create sample request for testing"""
        return Request(
            request_number="250927-001",
            title="Test Request",
            description="Test Description",
            category=RequestCategory.PLUMBING,
            priority=RequestPriority.NORMAL,
            status=RequestStatus.NEW,
            address="Test Address",
            applicant_user_id="user_123",
            latitude=55.7558,
            longitude=37.6176
        )

    @pytest.fixture
    def sample_executors(self):
        """Create sample executor profiles"""
        return [
            ExecutorProfile(
                user_id="executor_001",
                specializations=["сантехника", "водопровод"],
                current_workload=2,
                avg_completion_time=4.5,
                rating=4.8,
                location=(55.7558, 37.6176),
                availability_score=0.9,
                skills_match_score=0.8
            ),
            ExecutorProfile(
                user_id="executor_002",
                specializations=["электрика", "освещение"],
                current_workload=1,
                avg_completion_time=3.2,
                rating=4.6,
                location=(55.7575, 37.6200),
                availability_score=0.95,
                skills_match_score=0.7
            )
        ]

    def test_calculate_specialization_score(self, ai_service, sample_request):
        """Test specialization score calculation"""
        # Perfect match
        executor = ExecutorProfile(
            user_id="test",
            specializations=["сантехника", "водопровод"],
            current_workload=0,
            avg_completion_time=0,
            rating=0,
            location=None,
            availability_score=0,
            skills_match_score=0
        )

        score = ai_service._calculate_specialization_score(sample_request, executor)
        assert score > 0.5  # Should have high score for plumbing specialization

        # No match
        executor.specializations = ["уборка", "клининг"]
        score = ai_service._calculate_specialization_score(sample_request, executor)
        assert score <= 0.5  # Should have low score for non-matching specialization

    def test_calculate_geographic_score(self, ai_service, sample_request):
        """Test geographic score calculation"""
        # Same location
        executor = ExecutorProfile(
            user_id="test",
            specializations=[],
            current_workload=0,
            avg_completion_time=0,
            rating=0,
            location=(55.7558, 37.6176),  # Same as request
            availability_score=0,
            skills_match_score=0
        )

        score = ai_service._calculate_geographic_score(sample_request, executor)
        assert score == 1.0  # Perfect score for same location

        # No location data
        executor.location = None
        score = ai_service._calculate_geographic_score(sample_request, executor)
        assert score == 0.5  # Neutral score when no location data

    def test_calculate_workload_score(self, ai_service):
        """Test workload score calculation"""
        # No workload
        executor = ExecutorProfile(
            user_id="test",
            specializations=[],
            current_workload=0,
            avg_completion_time=0,
            rating=0,
            location=None,
            availability_score=0,
            skills_match_score=0
        )

        score = ai_service._calculate_workload_score(executor)
        assert score == 1.0  # Perfect score for no workload

        # High workload
        executor.current_workload = 10
        score = ai_service._calculate_workload_score(executor)
        assert score < 0.5  # Low score for high workload

    def test_generate_reasoning(self, ai_service):
        """Test reasoning generation"""
        reasoning = ai_service._generate_reasoning(0.9, 0.8, 0.7, 0.9)

        assert "отличное соответствие специализации" in reasoning
        assert "близкое расположение" in reasoning
        assert "умеренная загрузка" in reasoning
        assert "высокий рейтинг" in reasoning

        # Test with low scores
        reasoning = ai_service._generate_reasoning(0.2, 0.3, 0.4, 0.2)
        assert "базовое соответствие критериям" in reasoning

    def test_select_best_algorithm(self, ai_service, sample_request):
        """Test algorithm selection logic"""
        # Emergency request
        sample_request.priority = RequestPriority.EMERGENCY
        algorithm = ai_service._select_best_algorithm(sample_request, 5)
        assert algorithm == AssignmentAlgorithm.GREEDY

        # Large executor pool
        sample_request.priority = RequestPriority.NORMAL
        algorithm = ai_service._select_best_algorithm(sample_request, 15)
        assert algorithm == AssignmentAlgorithm.HYBRID

        # Medium pool
        algorithm = ai_service._select_best_algorithm(sample_request, 7)
        assert algorithm == AssignmentAlgorithm.GENETIC

        # Small pool
        algorithm = ai_service._select_best_algorithm(sample_request, 3)
        assert algorithm == AssignmentAlgorithm.GREEDY

    @pytest.mark.asyncio
    async def test_greedy_assignment(self, ai_service, sample_request, sample_executors):
        """Test greedy assignment algorithm"""
        suggestions = await ai_service._greedy_assignment(sample_request, sample_executors, 2)

        assert len(suggestions) <= 2
        assert all(isinstance(s, AssignmentSuggestion) for s in suggestions)

        # Should be sorted by confidence score
        if len(suggestions) > 1:
            assert suggestions[0].confidence_score >= suggestions[1].confidence_score

        # Check suggestion properties
        for suggestion in suggestions:
            assert suggestion.executor_user_id in ["executor_001", "executor_002"]
            assert 0 <= suggestion.confidence_score <= 1
            assert suggestion.reasoning
            assert suggestion.estimated_completion_time > 0

    @pytest.mark.asyncio
    async def test_hybrid_optimization(self, ai_service, sample_request, sample_executors):
        """Test hybrid optimization algorithm"""
        suggestions = await ai_service._hybrid_optimization(sample_request, sample_executors, 2)

        assert len(suggestions) <= 2
        assert all("Hybrid optimization" in s.reasoning for s in suggestions)


@pytest.mark.unit
class TestSmartDispatcher:
    """Test SmartDispatcher functionality"""

    @pytest.fixture
    def smart_dispatcher(self):
        """Create SmartDispatcher instance"""
        return SmartDispatcher()

    @pytest.fixture
    def sample_request(self):
        """Create sample request for testing"""
        return Request(
            request_number="250927-001",
            title="Test Request",
            description="Test Description",
            category=RequestCategory.PLUMBING,
            priority=RequestPriority.NORMAL,
            status=RequestStatus.NEW,
            address="Test Address",
            applicant_user_id="user_123"
        )

    def test_get_dispatch_rule_priority(self, smart_dispatcher, sample_request):
        """Test getting dispatch rule by priority"""
        # Emergency priority
        sample_request.priority = RequestPriority.EMERGENCY
        rule = smart_dispatcher._get_dispatch_rule(sample_request)

        assert rule.dispatch_mode == DispatchMode.AUTO_ASSIGN
        assert rule.auto_assign_threshold == 0.6
        assert rule.max_wait_time_minutes == 5

        # Normal priority
        sample_request.priority = RequestPriority.NORMAL
        rule = smart_dispatcher._get_dispatch_rule(sample_request)

        assert rule.dispatch_mode == DispatchMode.BATCH_OPTIMIZE
        assert rule.max_wait_time_minutes == 480

    def test_get_dispatch_rule_category(self, smart_dispatcher, sample_request):
        """Test getting dispatch rule by category"""
        # Plumbing category
        sample_request.category = RequestCategory.PLUMBING
        rule = smart_dispatcher._get_dispatch_rule(sample_request)

        assert rule.require_specialization == True
        assert rule.enable_geo_optimization == True

    def test_select_algorithm(self, smart_dispatcher, sample_request):
        """Test algorithm selection for dispatch modes"""
        # Auto-assign mode
        algorithm = smart_dispatcher._select_algorithm(sample_request, DispatchMode.AUTO_ASSIGN)
        assert algorithm == AssignmentAlgorithm.GREEDY

        # Emergency priority
        sample_request.priority = RequestPriority.EMERGENCY
        algorithm = smart_dispatcher._select_algorithm(sample_request, DispatchMode.AI_ASSISTED)
        assert algorithm == AssignmentAlgorithm.GREEDY

        # Batch optimize mode
        algorithm = smart_dispatcher._select_algorithm(sample_request, DispatchMode.BATCH_OPTIMIZE)
        assert algorithm == AssignmentAlgorithm.HYBRID

        # AI assisted mode
        sample_request.priority = RequestPriority.NORMAL
        algorithm = smart_dispatcher._select_algorithm(sample_request, DispatchMode.AI_ASSISTED)
        assert algorithm == AssignmentAlgorithm.GENETIC

    def test_update_metrics(self, smart_dispatcher):
        """Test metrics update functionality"""
        initial_total = smart_dispatcher.metrics["total_dispatches"]

        # Mock dispatch result
        result = MagicMock()
        result.assigned = True
        result.assignment_method = "auto_assign_success"
        result.suggestions_count = 3

        smart_dispatcher._update_metrics(result, 150.5)

        assert smart_dispatcher.metrics["total_dispatches"] == initial_total + 1
        assert smart_dispatcher.metrics["auto_assignments"] == 1
        assert smart_dispatcher.metrics["ai_suggestions"] == 1
        assert smart_dispatcher.metrics["avg_dispatch_time_ms"] > 0

    def test_metrics_calculation(self, smart_dispatcher):
        """Test metrics calculation accuracy"""
        # Simulate multiple dispatches
        for i in range(5):
            result = MagicMock()
            result.assigned = True
            result.assignment_method = "auto_assign_success" if i < 3 else "manual_assign"
            result.suggestions_count = 2

            smart_dispatcher._update_metrics(result, 100.0 + i * 10)

        metrics = smart_dispatcher.metrics
        assert metrics["total_dispatches"] == 5
        assert metrics["auto_assignments"] == 3
        assert metrics["manual_assignments"] == 2
        assert metrics["success_rate"] == 1.0  # All assigned


@pytest.mark.unit
class TestGeoOptimizer:
    """Test GeoOptimizer functionality"""

    @pytest.fixture
    def geo_optimizer(self):
        """Create GeoOptimizer instance"""
        return GeoOptimizer()

    def test_geo_point_creation(self):
        """Test GeoPoint creation and validation"""
        # Valid coordinates
        point = GeoPoint(55.7558, 37.6176, "Moscow")
        assert point.latitude == 55.7558
        assert point.longitude == 37.6176
        assert point.label == "Moscow"

        # Invalid latitude
        with pytest.raises(ValueError, match="Invalid latitude"):
            GeoPoint(91.0, 37.6176)

        # Invalid longitude
        with pytest.raises(ValueError, match="Invalid longitude"):
            GeoPoint(55.7558, 181.0)

    def test_calculate_distance(self, geo_optimizer):
        """Test distance calculation between points"""
        point1 = GeoPoint(55.7558, 37.6176)  # Moscow
        point2 = GeoPoint(55.7558, 37.6176)  # Same location

        # Same location should be 0 distance
        distance = geo_optimizer.calculate_distance(point1, point2)
        assert distance == 0.0

        # Different locations
        point3 = GeoPoint(55.7600, 37.6250)  # Slightly different
        distance = geo_optimizer.calculate_distance(point1, point3)
        assert distance > 0

        # Test different units
        distance_km = geo_optimizer.calculate_distance(point1, point3, DistanceUnit.KILOMETERS)
        distance_m = geo_optimizer.calculate_distance(point1, point3, DistanceUnit.METERS)
        distance_miles = geo_optimizer.calculate_distance(point1, point3, DistanceUnit.MILES)

        assert distance_m == distance_km * 1000
        assert abs(distance_miles - distance_km * 0.621371) < 0.001

    def test_calculate_travel_time(self, geo_optimizer):
        """Test travel time calculation"""
        # Walking 5km
        time_walking = geo_optimizer.calculate_travel_time(5.0, "walking")
        assert time_walking == 60.0  # 1 hour at 5 km/h

        # Car 30km
        time_car = geo_optimizer.calculate_travel_time(30.0, "car")
        assert time_car == 60.0  # 1 hour at 30 km/h

        # Bicycle 15km
        time_bicycle = geo_optimizer.calculate_travel_time(15.0, "bicycle")
        assert time_bicycle == 60.0  # 1 hour at 15 km/h

        # Unknown method defaults to walking
        time_unknown = geo_optimizer.calculate_travel_time(5.0, "unknown_method")
        assert time_unknown == 60.0  # Same as walking

    def test_calculate_distance_matrix(self, geo_optimizer):
        """Test distance matrix calculation"""
        request_locations = [
            GeoPoint(55.7558, 37.6176),
            GeoPoint(55.7600, 37.6250)
        ]

        executor_locations = [
            GeoPoint(55.7575, 37.6200),
            GeoPoint(55.7550, 37.6150)
        ]

        matrix = geo_optimizer._calculate_distance_matrix(request_locations, executor_locations)

        # Should be 2x2 matrix (2 executors, 2 requests)
        assert len(matrix) == 2  # 2 executors
        assert len(matrix[0]) == 2  # 2 requests for first executor
        assert len(matrix[1]) == 2  # 2 requests for second executor

        # All distances should be positive
        for row in matrix:
            for distance in row:
                assert distance >= 0

    def test_calculate_efficiency_score(self, geo_optimizer):
        """Test efficiency score calculation"""
        # Perfect efficiency (0 distance, 0 time)
        score = geo_optimizer._calculate_efficiency_score(0.0, 0.0, 1)
        assert score == 1.0

        # Poor efficiency (high distance and time)
        score = geo_optimizer._calculate_efficiency_score(50.0, 300.0, 1)
        assert score < 0.5

        # No requests
        score = geo_optimizer._calculate_efficiency_score(10.0, 60.0, 0)
        assert score == 0.0

    def test_calculate_naive_assignment_distance(self, geo_optimizer):
        """Test naive assignment distance calculation"""
        from app.services.geo_optimizer import RequestLocation, ExecutorLocation

        request_locations = [
            RequestLocation("req_001", GeoPoint(55.7558, 37.6176)),
            RequestLocation("req_002", GeoPoint(55.7600, 37.6250))
        ]

        executor_locations = [
            ExecutorLocation("exec_001", GeoPoint(55.7575, 37.6200)),
            ExecutorLocation("exec_002", GeoPoint(55.7550, 37.6150))
        ]

        distance = geo_optimizer._calculate_naive_assignment_distance(
            request_locations, executor_locations
        )

        assert distance >= 0

        # Empty inputs
        assert geo_optimizer._calculate_naive_assignment_distance([], []) == 0.0
        assert geo_optimizer._calculate_naive_assignment_distance(request_locations, []) == 0.0

    @pytest.mark.asyncio
    async def test_optimize_route_sequence_empty(self, geo_optimizer):
        """Test route optimization with empty input"""
        start_point = GeoPoint(55.7558, 37.6176)

        # Empty list
        result = await geo_optimizer.optimize_route_sequence(start_point, [])
        assert result == []

        # Single request
        from app.services.geo_optimizer import RequestLocation
        single_request = [RequestLocation("req_001", GeoPoint(55.7600, 37.6250))]
        result = await geo_optimizer.optimize_route_sequence(start_point, single_request)
        assert len(result) == 1
        assert result[0].request_number == "req_001"

    def test_calculate_sequence_distance(self, geo_optimizer):
        """Test sequence distance calculation"""
        from app.services.geo_optimizer import RequestLocation

        start_point = GeoPoint(55.7558, 37.6176)
        sequence = [
            RequestLocation("req_001", GeoPoint(55.7600, 37.6250)),
            RequestLocation("req_002", GeoPoint(55.7650, 37.6300))
        ]

        distance = geo_optimizer._calculate_sequence_distance(start_point, sequence)
        assert distance > 0

        # With end location
        end_point = GeoPoint(55.7558, 37.6176)  # Return to start
        distance_with_return = geo_optimizer._calculate_sequence_distance(
            start_point, sequence, end_point
        )
        assert distance_with_return > distance  # Should be longer with return

        # Empty sequence
        distance_empty = geo_optimizer._calculate_sequence_distance(start_point, [])
        assert distance_empty == 0.0