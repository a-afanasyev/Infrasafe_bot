"""Tests for shift Pydantic schemas (uk_management_bot/api/shifts/schemas.py)."""
import pytest
from datetime import datetime, date, timedelta
from pydantic import ValidationError

from uk_management_bot.api.shifts.schemas import (
    EmployeeBrief,
    ShiftBrief,
    ShiftDetail,
    EmployeeDetail,
    TransferOut,
    ShiftStatsOut,
    CreateShiftBody,
    UpdateShiftBody,
    CreateFromTemplateBody,
    HandleTransferBody,
    TemplateBrief,
    CreateTemplateBody,
    UpdateTemplateBody,
    DeleteEmployeeRequest,
    ActiveRequestsCount,
    CreateInviteRequest,
    CreateInviteResponse,
    CreateEmployeeRequest,
)


# ═══════════════════════ EmployeeBrief ═══════════════════════


class TestEmployeeBrief:

    def test_from_dict(self):
        emp = EmployeeBrief(
            id=1, first_name="Ivan", last_name="Petrov",
            phone="+998901234567", specialization=["electrician"],
            active_shift_id=None, verification_status="approved",
        )
        assert emp.id == 1
        assert emp.specialization == ["electrician"]
        assert emp.status == "approved"

    def test_specialization_from_json_string(self):
        """JSON string in specialization is parsed to list."""
        emp = EmployeeBrief(
            id=1, first_name="A", last_name="B",
            phone=None, specialization='["plumber", "electrician"]',
            active_shift_id=None, verification_status="pending",
        )
        assert emp.specialization == ["plumber", "electrician"]

    def test_specialization_none_becomes_empty_list(self):
        emp = EmployeeBrief(
            id=1, first_name="A", last_name="B",
            phone=None, specialization=None,
            active_shift_id=None, verification_status="pending",
        )
        assert emp.specialization == []

    def test_specialization_invalid_json_becomes_empty_list(self):
        emp = EmployeeBrief(
            id=1, first_name="A", last_name="B",
            phone=None, specialization="{not-valid}",
            active_shift_id=None, verification_status="pending",
        )
        assert emp.specialization == []

    def test_specialization_json_non_list_becomes_empty(self):
        """JSON string that decodes to a non-list (e.g. dict) becomes empty."""
        emp = EmployeeBrief(
            id=1, first_name="A", last_name="B",
            phone=None, specialization='{"key":"val"}',
            active_shift_id=None, verification_status="pending",
        )
        assert emp.specialization == []

    def test_from_orm_like_object(self):
        """Model validator handles ORM-like objects with __dict__."""
        class FakeUser:
            id = 10
            first_name = "Test"
            last_name = "User"
            phone = "+123"
            specialization = '["plumber"]'
            active_shift_id = 5
            verification_status = "approved"
            status = "approved"

        emp = EmployeeBrief.model_validate(FakeUser())
        assert emp.id == 10
        assert emp.specialization == ["plumber"]

    def test_from_attributes_config(self):
        assert EmployeeBrief.model_config["from_attributes"] is True


# ═══════════════════════ ShiftBrief / ShiftDetail ═══════════════════════


class TestShiftBrief:

    def test_valid(self):
        now = datetime.now()
        shift = ShiftBrief(
            id=1, user_id=42, executor_name="Ivan",
            status="active", shift_type="regular",
            start_time=now, end_time=None,
            max_requests=10, current_request_count=3,
            load_percentage=30.0,
        )
        assert shift.id == 1
        assert shift.load_percentage == 30.0

    def test_from_attributes_config(self):
        assert ShiftBrief.model_config["from_attributes"] is True


class TestShiftDetail:

    def test_inherits_from_brief(self):
        now = datetime.now()
        detail = ShiftDetail(
            id=1, user_id=42, executor_name="Ivan",
            status="active", shift_type="regular",
            start_time=now, end_time=None,
            max_requests=10, current_request_count=3,
            load_percentage=30.0,
            notes="Test notes",
            specialization_focus=["plumber"],
            coverage_areas=[],
            priority_level=2,
            completed_requests=5,
            efficiency_score=0.85,
            quality_rating=4.5,
            template_id=None,
            created_at=now,
        )
        assert detail.notes == "Test notes"
        assert detail.priority_level == 2
        assert detail.completed_requests == 5


# ═══════════════════════ EmployeeDetail ═══════════════════════


class TestEmployeeDetail:

    def test_valid(self):
        emp = EmployeeDetail(
            id=1, first_name="A", last_name="B",
            phone=None, specialization=["electrician"],
            active_shift_id=None, verification_status="approved",
            active_shift=None, rating=4.5, total_shifts=10, total_completed=8,
        )
        assert emp.rating == 4.5
        assert emp.total_shifts == 10


# ═══════════════════════ TransferOut ═══════════════════════


class TestTransferOut:

    def test_valid(self):
        now = datetime.now()
        t = TransferOut(
            id=1, shift_id=5,
            from_executor_name="Ivan", to_executor_name="Petr",
            status="pending", reason="Заболел",
            urgency_level="high", comment=None,
            created_at=now,
        )
        assert t.status == "pending"
        assert t.reason == "Заболел"

    def test_from_attributes_config(self):
        assert TransferOut.model_config["from_attributes"] is True


# ═══════════════════════ ShiftStatsOut ═══════════════════════


class TestShiftStatsOut:

    def test_valid(self):
        stats = ShiftStatsOut(
            active_shifts=5, active_executors=3,
            coverage_pct=75.0, avg_efficiency=0.82,
            shifts_today=2, pending_transfers=1,
        )
        assert stats.coverage_pct == 75.0


# ═══════════════════════ CreateShiftBody ═══════════════════════


class TestCreateShiftBody:

    def test_valid_minimal(self):
        start = datetime.now()
        end = start + timedelta(hours=8)
        body = CreateShiftBody(user_id=1, start_time=start, end_time=end)
        assert body.shift_type == "regular"
        assert body.max_requests == 10
        assert body.priority_level == 1
        assert body.specialization_focus == []

    def test_end_before_start_raises(self):
        start = datetime.now()
        end = start - timedelta(hours=1)
        with pytest.raises(ValidationError) as exc_info:
            CreateShiftBody(user_id=1, start_time=start, end_time=end)
        assert "end_time must be after start_time" in str(exc_info.value)

    def test_end_equals_start_raises(self):
        now = datetime.now()
        with pytest.raises(ValidationError):
            CreateShiftBody(user_id=1, start_time=now, end_time=now)

    def test_max_requests_zero_raises(self):
        start = datetime.now()
        end = start + timedelta(hours=8)
        with pytest.raises(ValidationError):
            CreateShiftBody(user_id=1, start_time=start, end_time=end, max_requests=0)

    def test_priority_level_out_of_range_raises(self):
        start = datetime.now()
        end = start + timedelta(hours=8)
        with pytest.raises(ValidationError):
            CreateShiftBody(user_id=1, start_time=start, end_time=end, priority_level=6)

    @pytest.mark.parametrize("shift_type", ["regular", "emergency", "overtime", "maintenance"])
    def test_valid_shift_types(self, shift_type: str):
        start = datetime.now()
        end = start + timedelta(hours=8)
        body = CreateShiftBody(
            user_id=1, start_time=start, end_time=end, shift_type=shift_type
        )
        assert body.shift_type == shift_type

    def test_invalid_shift_type_raises(self):
        start = datetime.now()
        end = start + timedelta(hours=8)
        with pytest.raises(ValidationError):
            CreateShiftBody(
                user_id=1, start_time=start, end_time=end, shift_type="invalid"
            )


# ═══════════════════════ UpdateShiftBody ═══════════════════════


class TestUpdateShiftBody:

    def test_all_none(self):
        body = UpdateShiftBody()
        assert body.status is None
        assert body.user_id is None
        assert body.notes is None

    @pytest.mark.parametrize("status", ["active", "completed", "cancelled", "planned", "paused"])
    def test_valid_statuses(self, status: str):
        body = UpdateShiftBody(status=status)
        assert body.status == status

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationError):
            UpdateShiftBody(status="invalid_status")

    def test_max_requests_zero_raises(self):
        with pytest.raises(ValidationError):
            UpdateShiftBody(max_requests=0)


# ═══════════════════════ CreateFromTemplateBody ═══════════════════════


class TestCreateFromTemplateBody:

    def test_valid(self):
        body = CreateFromTemplateBody(
            template_id=1, date=date(2026, 4, 15), user_ids=[1, 2, 3]
        )
        assert body.template_id == 1
        assert body.date == date(2026, 4, 15)
        assert body.user_ids == [1, 2, 3]

    def test_empty_user_ids_raises(self):
        with pytest.raises(ValidationError):
            CreateFromTemplateBody(
                template_id=1, date=date(2026, 4, 15), user_ids=[]
            )


# ═══════════════════════ HandleTransferBody ═══════════════════════


class TestHandleTransferBody:

    @pytest.mark.parametrize("action", ["approve", "reject", "cancel"])
    def test_valid_actions(self, action: str):
        body = HandleTransferBody(action=action)
        assert body.action == action

    def test_invalid_action_raises(self):
        with pytest.raises(ValidationError):
            HandleTransferBody(action="invalid")

    def test_approve_with_executor(self):
        body = HandleTransferBody(action="approve", to_executor_id=42)
        assert body.to_executor_id == 42


# ═══════════════════════ CreateTemplateBody ═══════════════════════


class TestCreateTemplateBody:

    def test_valid_minimal(self):
        body = CreateTemplateBody(
            name="Morning shift", start_hour=8, duration_hours=8
        )
        assert body.name == "Morning shift"
        assert body.start_minute == 0
        assert body.min_executors == 1
        assert body.max_executors == 3
        assert body.auto_create is False
        assert body.default_shift_type == "regular"
        assert body.priority_level == 1

    def test_min_exceeds_max_executors_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            CreateTemplateBody(
                name="Bad", start_hour=8, duration_hours=8,
                min_executors=5, max_executors=2,
            )
        assert "min_executors" in str(exc_info.value)

    def test_invalid_day_of_week_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            CreateTemplateBody(
                name="Bad Days", start_hour=8, duration_hours=8,
                days_of_week=[0, 7],
            )
        assert "days_of_week" in str(exc_info.value)

    def test_name_too_long_raises(self):
        with pytest.raises(ValidationError):
            CreateTemplateBody(
                name="A" * 201, start_hour=8, duration_hours=8
            )

    def test_name_empty_raises(self):
        with pytest.raises(ValidationError):
            CreateTemplateBody(
                name="", start_hour=8, duration_hours=8
            )

    def test_start_hour_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            CreateTemplateBody(name="Bad", start_hour=24, duration_hours=8)

    def test_duration_hours_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            CreateTemplateBody(name="Bad", start_hour=8, duration_hours=25)

    def test_valid_days_of_week(self):
        body = CreateTemplateBody(
            name="Weekday", start_hour=9, duration_hours=8,
            days_of_week=[0, 1, 2, 3, 4],
        )
        assert body.days_of_week == [0, 1, 2, 3, 4]

    def test_default_recurrence_mode_is_weekday(self):
        body = CreateTemplateBody(name="Morning", start_hour=8, duration_hours=8)
        assert body.recurrence_mode == "weekday"
        assert body.cycle_days_on is None
        assert body.cycle_anchor_date is None

    def test_cycle_valid(self):
        body = CreateTemplateBody(
            name="Сутки через трое", start_hour=8, duration_hours=24,
            recurrence_mode="cycle", cycle_days_on=1, cycle_days_off=3,
            cycle_anchor_date=date(2026, 6, 5),
        )
        assert body.recurrence_mode == "cycle"
        assert body.cycle_days_on == 1
        assert body.cycle_days_off == 3
        assert body.cycle_anchor_date == date(2026, 6, 5)

    def test_cycle_missing_days_on_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            CreateTemplateBody(
                name="Bad cycle", start_hour=8, duration_hours=8,
                recurrence_mode="cycle", cycle_anchor_date=date(2026, 6, 5),
            )
        assert "cycle_days_on" in str(exc_info.value)

    def test_cycle_missing_anchor_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            CreateTemplateBody(
                name="Bad cycle", start_hour=8, duration_hours=8,
                recurrence_mode="cycle", cycle_days_on=1,
            )
        assert "cycle_anchor_date" in str(exc_info.value)

    def test_invalid_recurrence_mode_raises(self):
        with pytest.raises(ValidationError):
            CreateTemplateBody(
                name="Bad", start_hour=8, duration_hours=8,
                recurrence_mode="monthly",
            )

    def test_cycle_days_on_below_one_raises(self):
        with pytest.raises(ValidationError):
            CreateTemplateBody(
                name="Bad", start_hour=8, duration_hours=8,
                recurrence_mode="cycle", cycle_days_on=0,
                cycle_anchor_date=date(2026, 6, 5),
            )


# ═══════════════════════ UpdateTemplateBody ═══════════════════════


class TestUpdateTemplateBody:

    def test_all_none(self):
        body = UpdateTemplateBody()
        assert body.name is None
        assert body.start_hour is None

    def test_partial_update(self):
        body = UpdateTemplateBody(name="Updated", start_hour=10)
        assert body.name == "Updated"
        assert body.start_hour == 10

    def test_min_exceeds_max_executors_raises(self):
        with pytest.raises(ValidationError):
            UpdateTemplateBody(min_executors=5, max_executors=2)

    def test_only_min_set_no_validation_error(self):
        body = UpdateTemplateBody(min_executors=3)
        assert body.min_executors == 3

    def test_invalid_day_of_week_raises(self):
        with pytest.raises(ValidationError):
            UpdateTemplateBody(days_of_week=[0, 7])

    def test_none_days_of_week_no_validation(self):
        body = UpdateTemplateBody(days_of_week=None)
        assert body.days_of_week is None

    def test_default_recurrence_mode_none(self):
        body = UpdateTemplateBody()
        assert body.recurrence_mode is None
        assert body.cycle_days_on is None

    def test_cycle_update_valid(self):
        body = UpdateTemplateBody(
            recurrence_mode="cycle", cycle_days_on=2, cycle_days_off=2,
            cycle_anchor_date=date(2026, 6, 5),
        )
        assert body.recurrence_mode == "cycle"
        assert body.cycle_days_on == 2

    def test_cycle_update_missing_anchor_raises(self):
        with pytest.raises(ValidationError):
            UpdateTemplateBody(recurrence_mode="cycle", cycle_days_on=2)

    def test_cycle_update_mode_only_raises(self):
        """PATCH sending only recurrence_mode='cycle' (no cycle_days_on / anchor)
        must be rejected — otherwise model_dump(exclude_unset=True) would persist
        recurrence_mode='cycle' with NULL cycle fields and is_date_included would
        always return False."""
        with pytest.raises(ValidationError):
            UpdateTemplateBody(recurrence_mode="cycle")


# ═══════════════════════ DeleteEmployeeRequest ═══════════════════════


class TestDeleteEmployeeRequest:

    def test_valid(self):
        body = DeleteEmployeeRequest(reason="Уволен")
        assert body.reason == "Уволен"
        assert body.reassign_to is None

    def test_empty_reason_raises(self):
        with pytest.raises(ValidationError):
            DeleteEmployeeRequest(reason="")

    def test_with_reassign(self):
        body = DeleteEmployeeRequest(reason="Уволен", reassign_to=42)
        assert body.reassign_to == 42


# ═══════════════════════ CreateInviteRequest ═══════════════════════


class TestCreateInviteRequest:

    def test_valid_executor(self):
        body = CreateInviteRequest(role="executor")
        assert body.role == "executor"
        assert body.hours == 24
        assert body.specializations == []

    def test_valid_manager(self):
        body = CreateInviteRequest(role="manager", hours=48)
        assert body.hours == 48

    def test_invalid_role_raises(self):
        with pytest.raises(ValidationError):
            CreateInviteRequest(role="applicant")

    def test_hours_below_minimum_raises(self):
        with pytest.raises(ValidationError):
            CreateInviteRequest(role="executor", hours=0)

    def test_hours_above_maximum_raises(self):
        with pytest.raises(ValidationError):
            CreateInviteRequest(role="executor", hours=200)


# ═══════════════════════ CreateInviteResponse ═══════════════════════


class TestCreateInviteResponse:

    def test_valid(self):
        resp = CreateInviteResponse(
            token="abc123",
            bot_link="https://t.me/mybot?start=abc123",
            expires_at=datetime.now(),
        )
        assert resp.token == "abc123"


# ═══════════════════════ CreateEmployeeRequest ═══════════════════════


class TestCreateEmployeeRequest:

    def test_valid_minimal(self):
        body = CreateEmployeeRequest(
            first_name="Ivan", last_name="Petrov",
            phone="+998901234567", role="executor",
        )
        assert body.status == "approved"
        assert body.specializations == []

    def test_invalid_role_raises(self):
        with pytest.raises(ValidationError):
            CreateEmployeeRequest(
                first_name="Ivan", last_name="Petrov",
                phone="+998901234567", role="applicant",
            )

    def test_short_first_name_raises(self):
        with pytest.raises(ValidationError):
            CreateEmployeeRequest(
                first_name="", last_name="Petrov",
                phone="+998901234567", role="executor",
            )

    def test_short_phone_raises(self):
        with pytest.raises(ValidationError):
            CreateEmployeeRequest(
                first_name="Ivan", last_name="Petrov",
                phone="123", role="executor",
            )


# ═══════════════════════ ActiveRequestsCount ═══════════════════════


class TestActiveRequestsCount:

    def test_valid(self):
        c = ActiveRequestsCount(count=5)
        assert c.count == 5
