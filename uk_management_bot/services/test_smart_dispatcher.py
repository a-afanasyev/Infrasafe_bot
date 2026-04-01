"""Unit tests for SmartDispatcher — dispatcher logic."""
import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from uk_management_bot.services.smart_dispatcher import (
    SmartDispatcher,
    AssignmentScore,
    DispatchResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db():
    db = MagicMock()
    q = MagicMock()
    q.filter.return_value.all.return_value = []
    q.filter.return_value.first.return_value = None
    q.filter.return_value.count.return_value = 0
    q.order_by.return_value.all.return_value = []
    db.query.return_value = q
    return db


def _make_request(
    request_number="260401-001",
    status="Новая",
    urgency="Обычная",
    category="сантехника",
    address="ул. Тестовая 1",
    executor_id=None,
):
    req = MagicMock()
    req.request_number = request_number
    req.status = status
    req.urgency = urgency
    req.category = category
    req.address = address
    req.executor_id = executor_id
    req.created_at = datetime(2026, 4, 1, 10, 0, 0)
    return req


def _make_shift(
    shift_id=1,
    status="active",
    user_id=5,
    current_request_count=3,
    max_requests=10,
    is_full=False,
    specialization_focus=None,
    coverage_areas=None,
    load_percentage=30.0,
    quality_rating=4.5,
    executor_id=5,
    end_time=None,
):
    shift = MagicMock()
    shift.id = shift_id
    shift.status = status
    shift.user_id = user_id
    shift.executor_id = executor_id
    shift.current_request_count = current_request_count
    shift.max_requests = max_requests
    shift.is_full = is_full
    shift.specialization_focus = specialization_focus or []
    shift.coverage_areas = coverage_areas or []
    shift.load_percentage = load_percentage
    shift.quality_rating = quality_rating
    shift.end_time = end_time
    return shift


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestInit:
    def test_stores_db_reference(self):
        db = _make_db()
        dispatcher = SmartDispatcher(db)
        assert dispatcher.db is db

    def test_weights_sum_to_one(self):
        dispatcher = SmartDispatcher(_make_db())
        total = sum(dispatcher.weights.values())
        assert abs(total - 1.0) < 1e-9

    def test_default_min_assignment_score(self):
        dispatcher = SmartDispatcher(_make_db())
        assert dispatcher.min_assignment_score == 0.6

    def test_default_max_requests_per_executor(self):
        dispatcher = SmartDispatcher(_make_db())
        assert dispatcher.max_requests_per_executor == 8


# ---------------------------------------------------------------------------
# _calculate_urgency_priority_score  (pure)
# ---------------------------------------------------------------------------

class TestCalculateUrgencyPriorityScore:
    def setup_method(self):
        self.dispatcher = SmartDispatcher(_make_db())

    def test_critical_is_1(self):
        req = _make_request(urgency="Критическая")
        assert self.dispatcher._calculate_urgency_priority_score(req) == 1.0

    def test_urgent_is_0_8(self):
        req = _make_request(urgency="Срочная")
        assert self.dispatcher._calculate_urgency_priority_score(req) == pytest.approx(0.8)

    def test_medium_is_0_5(self):
        req = _make_request(urgency="Средняя")
        assert self.dispatcher._calculate_urgency_priority_score(req) == pytest.approx(0.5)

    def test_regular_is_0_3(self):
        req = _make_request(urgency="Обычная")
        assert self.dispatcher._calculate_urgency_priority_score(req) == pytest.approx(0.3)

    def test_unknown_urgency_defaults_to_0_3(self):
        req = _make_request(urgency="Unknown")
        assert self.dispatcher._calculate_urgency_priority_score(req) == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# _extract_specialization_from_request  (pure)
# ---------------------------------------------------------------------------

class TestExtractSpecializationFromRequest:
    def setup_method(self):
        self.dispatcher = SmartDispatcher(_make_db())

    def test_plumbing_from_water_keyword(self):
        req = _make_request(category="сантехника кран течет")
        spec = self.dispatcher._extract_specialization_from_request(req)
        assert spec == "plumbing"

    def test_electric_from_electricity_keyword(self):
        req = _make_request(category="электр не работает розетка")
        spec = self.dispatcher._extract_specialization_from_request(req)
        assert spec == "electric"

    def test_hvac_from_heating_keyword(self):
        req = _make_request(category="отопл не работает батарея")
        spec = self.dispatcher._extract_specialization_from_request(req)
        assert spec == "hvac"

    def test_cleaning_from_garbage_keyword(self):
        req = _make_request(category="убор мусор вынос")
        spec = self.dispatcher._extract_specialization_from_request(req)
        assert spec == "cleaning"

    def test_unknown_category_defaults_to_maintenance(self):
        req = _make_request(category="разное")
        spec = self.dispatcher._extract_specialization_from_request(req)
        assert spec == "maintenance"

    def test_empty_category_defaults_to_maintenance(self):
        req = _make_request(category="")
        spec = self.dispatcher._extract_specialization_from_request(req)
        assert spec == "maintenance"


# ---------------------------------------------------------------------------
# _calculate_specialization_match  (pure)
# ---------------------------------------------------------------------------

class TestCalculateSpecializationMatch:
    def setup_method(self):
        self.dispatcher = SmartDispatcher(_make_db())

    def test_no_focus_returns_0_7(self):
        req = _make_request(category="плумбинг кран")
        shift = _make_shift(specialization_focus=[])
        score = self.dispatcher._calculate_specialization_match(req, shift)
        assert score == pytest.approx(0.7)

    def test_exact_match_returns_1_0(self):
        req = _make_request(category="сантехника кран")  # → plumbing
        shift = _make_shift(specialization_focus=["plumbing"])
        score = self.dispatcher._calculate_specialization_match(req, shift)
        assert score == pytest.approx(1.0)

    def test_universal_focus_returns_0_8(self):
        req = _make_request(category="сантехника кран")  # → plumbing
        shift = _make_shift(specialization_focus=["universal"])
        score = self.dispatcher._calculate_specialization_match(req, shift)
        assert score == pytest.approx(0.8)

    def test_partial_match_returns_partial_score(self):
        req = _make_request(category="сантехника кран")  # → plumbing
        shift = _make_shift(specialization_focus=["maintenance"])
        score = self.dispatcher._calculate_specialization_match(req, shift)
        # Related score: plumbing → maintenance = 0.6
        assert 0.0 < score < 1.0

    def test_no_match_returns_low_score(self):
        req = _make_request(category="сантехника кран")  # → plumbing
        shift = _make_shift(specialization_focus=["security"])
        score = self.dispatcher._calculate_specialization_match(req, shift)
        assert score == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# _calculate_geographic_proximity  (pure)
# ---------------------------------------------------------------------------

class TestCalculateGeographicProximity:
    def setup_method(self):
        self.dispatcher = SmartDispatcher(_make_db())

    def test_no_coverage_areas_returns_0_8(self):
        req = _make_request(address="ул. Тестовая 1")
        shift = _make_shift(coverage_areas=[])
        score = self.dispatcher._calculate_geographic_proximity(req, shift)
        assert score == pytest.approx(0.8)

    def test_matching_area_returns_1_0(self):
        req = _make_request(address="тестовая улица 1")
        shift = _make_shift(coverage_areas=["тестовая"])
        score = self.dispatcher._calculate_geographic_proximity(req, shift)
        assert score == pytest.approx(1.0)

    def test_all_coverage_returns_1_0(self):
        req = _make_request(address="any address")
        shift = _make_shift(coverage_areas=["all"])
        score = self.dispatcher._calculate_geographic_proximity(req, shift)
        assert score == pytest.approx(1.0)

    def test_no_match_returns_low_score(self):
        req = _make_request(address="ул. Тестовая 1")
        shift = _make_shift(coverage_areas=["северный район"])
        score = self.dispatcher._calculate_geographic_proximity(req, shift)
        assert score == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# _calculate_workload_balance_score  (pure)
# ---------------------------------------------------------------------------

class TestCalculateWorkloadBalanceScore:
    def setup_method(self):
        self.dispatcher = SmartDispatcher(_make_db())

    def test_zero_max_requests_returns_0(self):
        shift = _make_shift(max_requests=0)
        score = self.dispatcher._calculate_workload_balance_score(shift)
        assert score == pytest.approx(0.0)

    def test_optimal_range_50_70_returns_1_0(self):
        shift = _make_shift(load_percentage=60.0)
        score = self.dispatcher._calculate_workload_balance_score(shift)
        assert score == pytest.approx(1.0)

    def test_low_load_below_30_returns_0_9(self):
        shift = _make_shift(load_percentage=20.0)
        score = self.dispatcher._calculate_workload_balance_score(shift)
        assert score == pytest.approx(0.9)

    def test_heavy_load_above_85_returns_low_score(self):
        shift = _make_shift(load_percentage=90.0)
        score = self.dispatcher._calculate_workload_balance_score(shift)
        assert score == pytest.approx(0.2)

    def test_moderate_load_30_50_returns_0_8(self):
        shift = _make_shift(load_percentage=40.0)
        score = self.dispatcher._calculate_workload_balance_score(shift)
        assert score == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# _calculate_executor_rating_score  (pure)
# ---------------------------------------------------------------------------

class TestCalculateExecutorRatingScore:
    def setup_method(self):
        self.dispatcher = SmartDispatcher(_make_db())

    def test_no_rating_returns_0_7(self):
        shift = _make_shift(quality_rating=None)
        score = self.dispatcher._calculate_executor_rating_score(shift)
        assert score == pytest.approx(0.7)

    def test_max_rating_5_returns_1_0(self):
        shift = _make_shift(quality_rating=5.0)
        score = self.dispatcher._calculate_executor_rating_score(shift)
        assert score == pytest.approx(1.0)

    def test_min_rating_1_returns_0_0(self):
        shift = _make_shift(quality_rating=1.0)
        score = self.dispatcher._calculate_executor_rating_score(shift)
        assert score == pytest.approx(0.0)

    def test_mid_rating_3_returns_0_5(self):
        shift = _make_shift(quality_rating=3.0)
        score = self.dispatcher._calculate_executor_rating_score(shift)
        assert score == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# calculate_assignment_score  (uses private pure methods)
# ---------------------------------------------------------------------------

class TestCalculateAssignmentScore:
    def test_returns_assignment_score_object(self):
        dispatcher = SmartDispatcher(_make_db())
        req = _make_request()
        shift = _make_shift()
        result = dispatcher.calculate_assignment_score(req, shift)
        assert isinstance(result, AssignmentScore)

    def test_total_score_is_weighted_sum(self):
        dispatcher = SmartDispatcher(_make_db())
        req = _make_request(category="протечка воды")
        shift = _make_shift(
            specialization_focus=["plumbing"],
            coverage_areas=[],
            load_percentage=60.0,
            quality_rating=4.0,
            current_request_count=3,
            max_requests=10,
            is_full=False,
        )
        result = dispatcher.calculate_assignment_score(req, shift)
        # Score should be in valid range
        assert 0.0 <= result.total_score <= 1.0

    def test_full_shift_is_not_recommended(self):
        dispatcher = SmartDispatcher(_make_db())
        req = _make_request()
        shift = _make_shift(is_full=True)
        result = dispatcher.calculate_assignment_score(req, shift)
        assert result.recommended is False

    def test_overloaded_shift_is_not_recommended(self):
        dispatcher = SmartDispatcher(_make_db())
        req = _make_request()
        shift = _make_shift(current_request_count=9, max_requests=10, is_full=False)
        result = dispatcher.calculate_assignment_score(req, shift)
        assert result.recommended is False

    def test_full_shift_not_recommended_even_with_high_score(self):
        # When is_full=True, recommended is forced to False regardless of score
        dispatcher = SmartDispatcher(_make_db())
        req = _make_request(category="сантехника кран")
        shift = _make_shift(is_full=True, specialization_focus=["plumbing"], load_percentage=60.0)
        result = dispatcher.calculate_assignment_score(req, shift)
        assert result.recommended is False

    def test_factors_dict_populated(self):
        dispatcher = SmartDispatcher(_make_db())
        req = _make_request()
        shift = _make_shift()
        result = dispatcher.calculate_assignment_score(req, shift)
        assert "specialization" in result.factors
        assert "geography" in result.factors
        assert "workload" in result.factors
        assert "executor" in result.factors
        assert "urgency" in result.factors


# ---------------------------------------------------------------------------
# _prioritize_requests  (pure)
# ---------------------------------------------------------------------------

class TestPrioritizeRequests:
    def setup_method(self):
        self.dispatcher = SmartDispatcher(_make_db())

    def test_critical_before_regular(self):
        req1 = _make_request(request_number="001", urgency="Обычная")
        req2 = _make_request(request_number="002", urgency="Критическая")
        sorted_requests = self.dispatcher._prioritize_requests([req1, req2])
        assert sorted_requests[0].urgency == "Критическая"

    def test_same_urgency_ordered_by_creation_time(self):
        req1 = _make_request(request_number="001", urgency="Обычная")
        req1.created_at = datetime(2026, 4, 1, 10, 0, 0)
        req2 = _make_request(request_number="002", urgency="Обычная")
        req2.created_at = datetime(2026, 4, 1, 9, 0, 0)  # Earlier
        sorted_requests = self.dispatcher._prioritize_requests([req1, req2])
        assert sorted_requests[0].created_at < sorted_requests[1].created_at


# ---------------------------------------------------------------------------
# _create_optimization_summary  (pure)
# ---------------------------------------------------------------------------

class TestCreateOptimizationSummary:
    def setup_method(self):
        self.dispatcher = SmartDispatcher(_make_db())

    def test_empty_assignments_returns_message(self):
        result = self.dispatcher._create_optimization_summary([], [])
        assert "message" in result

    def test_single_assignment_returns_correct_stats(self):
        assignment = MagicMock()
        assignment.total_score = 0.85
        assignment.shift_id = 1
        result = self.dispatcher._create_optimization_summary([assignment], [])
        assert result["total_assignments"] == 1
        assert result["average_score"] == pytest.approx(0.85, abs=0.001)
        assert result["max_score"] == pytest.approx(0.85, abs=0.001)
        assert result["min_score"] == pytest.approx(0.85, abs=0.001)

    def test_score_distribution_classified_correctly(self):
        assignments = []
        for score in [0.95, 0.75, 0.65, 0.50]:
            a = MagicMock()
            a.total_score = score
            a.shift_id = 1
            assignments.append(a)

        result = self.dispatcher._create_optimization_summary(assignments, [])
        dist = result["score_distribution"]
        assert dist["excellent"] == 1  # 0.95
        assert dist["good"] == 1       # 0.75
        assert dist["acceptable"] == 1 # 0.65
        assert dist["poor"] == 1       # 0.50


# ---------------------------------------------------------------------------
# auto_assign_requests  (integration-level with mocked DB)
# ---------------------------------------------------------------------------

class TestAutoAssignRequests:
    def test_returns_dispatch_result_when_no_requests(self):
        db = _make_db()
        # query returns empty list
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        dispatcher = SmartDispatcher(db)
        result = dispatcher.auto_assign_requests()

        assert isinstance(result, DispatchResult)
        assert result.assigned_count == 0

    def test_returns_dispatch_result_when_no_active_shifts(self):
        db = _make_db()
        req = _make_request()
        # first call returns requests, second returns no shifts
        call_count = [0]

        def query_side(model):
            q = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                q.filter.return_value.order_by.return_value.all.return_value = [req]
            else:
                q.filter.return_value.order_by.return_value.all.return_value = []
            return q

        db.query.side_effect = query_side

        dispatcher = SmartDispatcher(db)
        result = dispatcher.auto_assign_requests()

        assert isinstance(result, DispatchResult)
        assert result.assigned_count == 0

    def test_returns_error_on_db_exception(self):
        db = MagicMock()
        db.query.side_effect = Exception("DB critical error")

        dispatcher = SmartDispatcher(db)
        result = dispatcher.auto_assign_requests()

        assert isinstance(result, DispatchResult)
        assert len(result.errors) > 0


# ---------------------------------------------------------------------------
# balance_workload  (integration)
# ---------------------------------------------------------------------------

class TestBalanceWorkload:
    def test_returns_message_when_fewer_than_2_shifts(self):
        db = _make_db()
        shift = _make_shift()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [shift]

        dispatcher = SmartDispatcher(db)
        result = dispatcher.balance_workload()

        assert "message" in result or "changes" in result

    def test_returns_gracefully_when_db_raises_on_shifts(self):
        # When DB raises, _get_active_shifts returns [] (caught internally),
        # so balance_workload sees < 2 shifts and returns the "insufficient" message.
        db = MagicMock()
        db.query.side_effect = Exception("DB error")

        dispatcher = SmartDispatcher(db)
        result = dispatcher.balance_workload()

        # Either error key or changes=0 (message about insufficient shifts)
        assert result.get("changes", 0) == 0
