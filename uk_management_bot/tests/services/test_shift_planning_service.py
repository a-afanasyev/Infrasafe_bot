"""Unit tests for ShiftPlanningService."""
from datetime import date
from unittest.mock import MagicMock, patch

from uk_management_bot.services.shift_planning_service import ShiftPlanningService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_template(
    template_id=1,
    name="Test Template",
    is_active=True,
    auto_create=True,
    min_executors=2,
    start_hour=9,
    start_minute=0,
    duration_hours=8,
    required_specializations=None,
    coverage_areas=None,
    geographic_zone=None,
    default_max_requests=10,
    priority_level=3,
    default_shift_type="regular",
    advance_days=7,
    included_days=None,
):
    t = MagicMock()
    t.id = template_id
    t.name = name
    t.is_active = is_active
    t.auto_create = auto_create
    t.min_executors = min_executors
    t.start_hour = start_hour
    t.start_minute = start_minute
    t.duration_hours = duration_hours
    t.required_specializations = required_specializations or []
    t.coverage_areas = coverage_areas or ["all"]
    t.geographic_zone = geographic_zone
    t.default_max_requests = default_max_requests
    t.priority_level = priority_level
    t.default_shift_type = default_shift_type
    t.advance_days = advance_days
    # Production code now drives generation via is_date_included(date).
    # included_days (if given) lists weekday numbers (1=Mon..7=Sun) for parity
    # with the previous is_day_included semantics.
    if included_days is None:
        t.is_date_included = MagicMock(return_value=True)
    else:
        t.is_date_included = MagicMock(side_effect=lambda d: (d.weekday() + 1) in included_days)
    return t


def _make_executor(user_id=10, status="approved", roles=None, specialization=None, telegram_id=1010):
    u = MagicMock()
    u.id = user_id
    u.telegram_id = telegram_id
    u.status = status
    u.roles = roles or ["executor"]
    u.specialization = specialization
    return u


def _make_service():
    db = MagicMock()
    with (
        patch("uk_management_bot.services.shift_planning_service.ShiftAnalytics"),
        patch("uk_management_bot.services.shift_planning_service.MetricsManager"),
        patch("uk_management_bot.services.shift_planning_service.RecommendationEngine"),
        patch("uk_management_bot.services.shift_planning_service.ShiftAssignmentService"),
    ):
        service = ShiftPlanningService(db)
    service.db = db
    return service, db


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------

class TestConstructor:
    def test_service_has_db(self):
        service, db = _make_service()
        assert service.db is db

    def test_analytics_initialized(self):
        service, _ = _make_service()
        assert service.analytics is not None


# ---------------------------------------------------------------------------
# _can_executor_work_template
# ---------------------------------------------------------------------------

class TestCanExecutorWorkTemplate:
    def test_approved_executor_with_matching_spec(self):
        service, _ = _make_service()
        template = _make_template(required_specializations=["plumbing"])
        executor = _make_executor(status="approved", specialization=["plumbing"])
        assert service._can_executor_work_template(executor, template) is True

    def test_pending_executor_rejected(self):
        service, _ = _make_service()
        template = _make_template(required_specializations=[])
        executor = _make_executor(status="pending", roles=["executor"])
        assert service._can_executor_work_template(executor, template) is False

    def test_no_executor_role_rejected(self):
        service, _ = _make_service()
        template = _make_template(required_specializations=[])
        executor = _make_executor(status="approved", roles=["applicant"])
        assert service._can_executor_work_template(executor, template) is False

    def test_wrong_specialization_rejected(self):
        service, _ = _make_service()
        template = _make_template(required_specializations=["electric"])
        executor = _make_executor(status="approved", roles=["executor"], specialization=["plumbing"])
        assert service._can_executor_work_template(executor, template) is False

    def test_universal_executor_accepted(self):
        service, _ = _make_service()
        template = _make_template(required_specializations=["electric"])
        executor = _make_executor(status="approved", roles=["executor"], specialization=["universal"])
        assert service._can_executor_work_template(executor, template) is True

    def test_no_required_specs_any_executor_accepted(self):
        service, _ = _make_service()
        template = _make_template(required_specializations=[])
        executor = _make_executor(status="approved", roles=["executor"], specialization=[])
        assert service._can_executor_work_template(executor, template) is True


# ---------------------------------------------------------------------------
# _calculate_gap_severity
# ---------------------------------------------------------------------------

class TestCalculateGapSeverity:
    def test_empty_hours_returns_none(self):
        service, _ = _make_service()
        assert service._calculate_gap_severity([]) == "none"

    def test_many_critical_hours_returns_critical(self):
        service, _ = _make_service()
        # More than 6 critical hours (8-17)
        assert service._calculate_gap_severity(list(range(8, 16))) == "critical"

    def test_moderate_critical_hours_returns_high(self):
        service, _ = _make_service()
        assert service._calculate_gap_severity([9, 10, 11, 14]) == "high"

    def test_few_critical_hours_returns_medium(self):
        service, _ = _make_service()
        assert service._calculate_gap_severity([9]) == "medium"

    def test_only_night_hours_returns_low(self):
        service, _ = _make_service()
        # Hours 0-7 and 18-23 are not critical
        assert service._calculate_gap_severity([0, 1, 2, 22, 23]) == "low"


# ---------------------------------------------------------------------------
# create_shift_from_template
# ---------------------------------------------------------------------------

class TestCreateShiftFromTemplate:
    def test_template_not_found_returns_empty(self):
        service, db = _make_service()
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        db.query.return_value = q
        result = service.create_shift_from_template(999, date(2026, 4, 7))
        assert result == []

    def test_day_not_included_returns_empty(self):
        service, db = _make_service()
        template = _make_template()
        template.is_date_included = MagicMock(return_value=False)
        q = MagicMock()
        q.filter.return_value.first.return_value = template
        db.query.return_value = q
        result = service.create_shift_from_template(1, date(2026, 4, 7))
        assert result == []

    def test_existing_shifts_returns_empty(self):
        service, db = _make_service()
        template = _make_template()

        def _side(model):
            q = MagicMock()
            if "ShiftTemplate" in str(model):
                q.filter.return_value.first.return_value = template
            else:
                # existing_shifts count > 0
                q.filter.return_value.count.return_value = 1
            return q

        db.query.side_effect = _side
        result = service.create_shift_from_template(1, date(2026, 4, 7))
        assert result == []

    def test_exception_returns_empty_and_rollback(self):
        service, db = _make_service()
        db.query.side_effect = Exception("db error")
        result = service.create_shift_from_template(1, date(2026, 4, 7))
        assert result == []
        db.rollback.assert_called()


# ---------------------------------------------------------------------------
# plan_weekly_schedule
# ---------------------------------------------------------------------------

class TestPlanWeeklySchedule:
    def test_returns_week_start(self):
        service, db = _make_service()
        # No active templates
        q = MagicMock()
        q.filter.return_value.filter.return_value.all.return_value = []
        db.query.return_value = q
        service._update_shift_schedule = MagicMock()
        result = service.plan_weekly_schedule(date(2026, 4, 5))
        assert "week_start" in result
        assert "statistics" in result

    def test_no_templates_creates_no_shifts(self):
        service, db = _make_service()
        q = MagicMock()
        q.filter.return_value.filter.return_value.all.return_value = []
        db.query.return_value = q
        service._update_shift_schedule = MagicMock()
        result = service.plan_weekly_schedule(date(2026, 4, 5))
        assert result["statistics"]["total_shifts"] == 0

    def test_week_start_adjusted_to_monday(self):
        service, db = _make_service()
        # April 5 2026 is Sunday
        q = MagicMock()
        q.filter.return_value.filter.return_value.all.return_value = []
        db.query.return_value = q
        service._update_shift_schedule = MagicMock()
        result = service.plan_weekly_schedule(date(2026, 4, 5))
        # week_start should be Monday March 30 or April 6 depending on weekday
        assert result["week_start"].weekday() == 0  # Monday

    def test_exception_returns_error_structure(self):
        service, db = _make_service()
        db.query.side_effect = Exception("fail")
        result = service.plan_weekly_schedule(date(2026, 4, 5))
        assert "errors" in result
        assert len(result["errors"]) > 0


# ---------------------------------------------------------------------------
# auto_create_shifts
# ---------------------------------------------------------------------------

class TestAutoCreateShifts:
    def test_no_auto_templates_returns_zero(self):
        service, db = _make_service()
        q = MagicMock()
        q.filter.return_value.filter.return_value.all.return_value = []
        db.query.return_value = q
        result = service.auto_create_shifts(days_ahead=3)
        assert result["total_created"] == 0

    def test_exception_returns_error_structure(self):
        service, db = _make_service()
        db.query.side_effect = Exception("fail")
        result = service.auto_create_shifts(days_ahead=3)
        assert "errors" in result

    def test_result_has_date_range(self):
        service, db = _make_service()
        q = MagicMock()
        q.filter.return_value.filter.return_value.all.return_value = []
        db.query.return_value = q
        result = service.auto_create_shifts(days_ahead=5)
        assert "start_date" in result
        assert "end_date" in result


# ---------------------------------------------------------------------------
# get_coverage_gaps
# ---------------------------------------------------------------------------

class TestGetCoverageGaps:
    def test_no_shifts_all_hours_uncovered(self):
        service, db = _make_service()
        q = MagicMock()
        q.filter.return_value.filter.return_value.all.return_value = []
        db.query.return_value = q
        start = date(2026, 4, 5)
        end = date(2026, 4, 5)
        gaps = service.get_coverage_gaps(start, end)
        assert len(gaps) == 1
        assert gaps[0]["total_shifts"] == 0

    def test_exception_returns_empty(self):
        service, db = _make_service()
        db.query.side_effect = Exception("fail")
        gaps = service.get_coverage_gaps(date(2026, 4, 5), date(2026, 4, 5))
        assert gaps == []

    def test_single_day_gap_has_required_keys(self):
        service, db = _make_service()
        q = MagicMock()
        q.filter.return_value.filter.return_value.all.return_value = []
        db.query.return_value = q
        gaps = service.get_coverage_gaps(date(2026, 4, 5), date(2026, 4, 5))
        if gaps:
            assert "date" in gaps[0]
            assert "uncovered_hours" in gaps[0]
            assert "gap_severity" in gaps[0]


# ---------------------------------------------------------------------------
# _get_available_executors_for_template
# ---------------------------------------------------------------------------

class TestGetAvailableExecutorsForTemplate:
    def test_returns_executors_that_can_work_template(self):
        service, db = _make_service()
        template = _make_template(required_specializations=[])
        executor = _make_executor(status="approved", roles=["executor"])

        q = MagicMock()
        q.filter.return_value.all.return_value = [executor]
        db.query.return_value = q

        service._can_executor_work_template = MagicMock(return_value=True)
        service._is_executor_busy = MagicMock(return_value=False)

        result = service._get_available_executors_for_template(template, date(2026, 4, 5))
        assert executor in result

    def test_excludes_busy_executors(self):
        service, db = _make_service()
        template = _make_template(required_specializations=[])
        executor = _make_executor(status="approved", roles=["executor"])

        q = MagicMock()
        q.filter.return_value.all.return_value = [executor]
        db.query.return_value = q

        service._can_executor_work_template = MagicMock(return_value=True)
        service._is_executor_busy = MagicMock(return_value=True)

        result = service._get_available_executors_for_template(template, date(2026, 4, 5))
        assert result == []

    def test_excludes_executors_not_matching_template(self):
        service, db = _make_service()
        template = _make_template(required_specializations=["electric"])
        executor = _make_executor(status="approved", roles=["executor"], specialization=["plumbing"])

        q = MagicMock()
        q.filter.return_value.all.return_value = [executor]
        db.query.return_value = q

        service._can_executor_work_template = MagicMock(return_value=False)
        service._is_executor_busy = MagicMock(return_value=False)

        result = service._get_available_executors_for_template(template, date(2026, 4, 5))
        assert result == []

    def test_returns_empty_on_db_error(self):
        service, db = _make_service()
        template = _make_template()
        db.query.side_effect = Exception("db fail")

        result = service._get_available_executors_for_template(template, date(2026, 4, 5))
        assert result == []


# ---------------------------------------------------------------------------
# _is_executor_busy
# ---------------------------------------------------------------------------

class TestIsExecutorBusy:
    def test_no_overlapping_shifts_returns_false(self):
        service, db = _make_service()
        template = _make_template(start_hour=9, start_minute=0, duration_hours=8)

        q = MagicMock()
        q.filter.return_value.count.return_value = 0
        db.query.return_value = q

        result = service._is_executor_busy(10, date(2026, 4, 5), template)
        assert result is False

    def test_overlapping_shifts_returns_true(self):
        service, db = _make_service()
        template = _make_template(start_hour=9, start_minute=0, duration_hours=8)

        q = MagicMock()
        q.filter.return_value.count.return_value = 2
        db.query.return_value = q

        result = service._is_executor_busy(10, date(2026, 4, 5), template)
        assert result is True

    def test_returns_true_on_db_error(self):
        service, db = _make_service()
        template = _make_template(start_hour=9, start_minute=0, duration_hours=8)
        db.query.side_effect = Exception("fail")

        result = service._is_executor_busy(10, date(2026, 4, 5), template)
        assert result is True  # safe default


# ---------------------------------------------------------------------------
# create_shift_from_template — executor_ids path
# ---------------------------------------------------------------------------

class TestCreateShiftFromTemplateWithExecutors:
    def test_creates_shifts_for_specific_executors(self):
        service, db = _make_service()
        template = _make_template(min_executors=1)
        executor = _make_executor()

        call_count = [0]

        def _side(model):
            q = MagicMock()
            call_count[0] += 1
            if "ShiftTemplate" in str(model):
                q.filter.return_value.first.return_value = template
            elif "User" in str(model):
                q.filter.return_value.first.return_value = executor
            else:
                q.filter.return_value.count.return_value = 0
            return q

        db.query.side_effect = _side
        service._can_executor_work_template = MagicMock(return_value=True)
        service._create_single_shift_from_template = MagicMock(return_value=MagicMock())

        service.create_shift_from_template(1, date(2026, 4, 5), executor_ids=[1010])

        # Single executor → single shift attempted
        service._create_single_shift_from_template.assert_called_once()


# ---------------------------------------------------------------------------
# QA-02 regression: get_optimization_recommendations must call the engine's
# real method generate_comprehensive_recommendations, NOT the non-existent
# get_shift_optimization_recommendations (которая роняла весь отчёт в {'error'}).
# ---------------------------------------------------------------------------

class TestGetOptimizationRecommendations:
    def test_calls_generate_comprehensive_and_no_error(self):
        import asyncio
        from unittest.mock import AsyncMock

        service, db = _make_service()
        # current_shifts query → пустой список (нам важен только блок 4)
        db.query.return_value.filter.return_value.all.return_value = []
        # изолируем приватные аналитические helper'ы
        service._calculate_hour_coverage = MagicMock(return_value=list(range(24)))
        service._calculate_load_balance_score = MagicMock(return_value=100)
        service._calculate_specialization_coverage_score = MagicMock(return_value=100)
        # движок: реальный метод существует, старый — нет
        service.recommendation_engine.generate_comprehensive_recommendations = AsyncMock(
            return_value={"recommendations": [{"description": "x"}]}
        )

        result = asyncio.get_event_loop().run_until_complete(
            service.get_optimization_recommendations(date(2026, 6, 20))
        )

        assert "error" not in result
        assert result["ai_recommendations"] == {"recommendations": [{"description": "x"}]}
        service.recommendation_engine.generate_comprehensive_recommendations.assert_awaited_once()
        # старый несуществующий метод НЕ вызывается
        assert not service.recommendation_engine.get_shift_optimization_recommendations.called


# ---------------------------------------------------------------------------
# QA-NEW-01 regression: _get_specialization_priority must read request.category,
# NOT request.specialization (которого у модели Request нет → AttributeError →
# функция всегда возвращала []). SimpleNamespace без .specialization падал бы.
# ---------------------------------------------------------------------------

class TestGetSpecializationPriority:
    def test_counts_by_category(self):
        import asyncio
        from types import SimpleNamespace

        service, _ = _make_service()
        reqs = [
            SimpleNamespace(category="Сантехника"),
            SimpleNamespace(category="Сантехника"),
            SimpleNamespace(category="Электрика"),
        ]
        result = asyncio.get_event_loop().run_until_complete(
            service._get_specialization_priority(reqs)
        )
        assert result, "priority list must be non-empty for non-empty history"
        assert result[0]["specialization"] == "Сантехника"
        assert result[0]["request_count"] == 2
