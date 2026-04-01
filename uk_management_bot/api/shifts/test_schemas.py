"""
Unit tests for api/shifts/schemas.py

Tests Pydantic validation for CreateShiftBody, UpdateShiftBody,
CreateFromTemplateBody, HandleTransferBody, CreateTemplateBody,
UpdateTemplateBody, CreateInviteRequest, CreateEmployeeRequest,
DeleteEmployeeRequest, EmployeeBrief.
"""
import pytest
from datetime import datetime, date

from uk_management_bot.api.shifts.schemas import (
    CreateShiftBody,
    UpdateShiftBody,
    CreateFromTemplateBody,
    HandleTransferBody,
    CreateTemplateBody,
    UpdateTemplateBody,
    CreateInviteRequest,
    CreateInviteResponse,
    CreateEmployeeRequest,
    DeleteEmployeeRequest,
    ActiveRequestsCount,
    EmployeeBrief,
    ShiftBrief,
)


# ---------------------------------------------------------------------------
# EmployeeBrief
# ---------------------------------------------------------------------------

class TestEmployeeBrief:
    def test_dict_with_list_specialization(self):
        data = {
            "id": 1,
            "first_name": "Ivan",
            "last_name": "Petrov",
            "phone": "+998901234567",
            "specialization": ["plumber", "electrician"],
            "active_shift_id": None,
            "verification_status": "verified",
        }
        brief = EmployeeBrief(**data)
        assert brief.specialization == ["plumber", "electrician"]

    def test_dict_with_json_string_specialization(self):
        data = {
            "id": 2,
            "first_name": "Anna",
            "last_name": None,
            "phone": None,
            "specialization": '["electrician"]',
            "active_shift_id": None,
            "verification_status": "pending",
        }
        brief = EmployeeBrief(**data)
        assert brief.specialization == ["electrician"]

    def test_none_specialization_defaults_to_empty_list(self):
        data = {
            "id": 3,
            "first_name": "Igor",
            "last_name": "Sidorov",
            "phone": None,
            "specialization": None,
            "active_shift_id": None,
            "verification_status": "verified",
        }
        brief = EmployeeBrief(**data)
        assert brief.specialization == []

    def test_status_defaults_to_approved(self):
        data = {
            "id": 4,
            "first_name": "Test",
            "last_name": None,
            "phone": None,
            "specialization": [],
            "active_shift_id": None,
            "verification_status": "verified",
        }
        brief = EmployeeBrief(**data)
        assert brief.status == "approved"

    def test_invalid_json_specialization_defaults_to_empty(self):
        data = {
            "id": 5,
            "first_name": "Test",
            "last_name": None,
            "phone": None,
            "specialization": "not-valid-json[[[",
            "active_shift_id": None,
            "verification_status": "verified",
        }
        brief = EmployeeBrief(**data)
        assert brief.specialization == []


# ---------------------------------------------------------------------------
# CreateShiftBody
# ---------------------------------------------------------------------------

class TestCreateShiftBody:
    def _base(self, **overrides) -> dict:
        base = {
            "user_id": 1,
            "start_time": datetime(2026, 1, 1, 8, 0),
            "end_time": datetime(2026, 1, 1, 16, 0),
        }
        base.update(overrides)
        return base

    def test_valid_minimal(self):
        body = CreateShiftBody(**self._base())
        assert body.shift_type == "regular"
        assert body.max_requests == 10
        assert body.priority_level == 1
        assert body.specialization_focus == []

    def test_end_before_start_raises(self):
        with pytest.raises(Exception):
            CreateShiftBody(**self._base(
                start_time=datetime(2026, 1, 1, 16, 0),
                end_time=datetime(2026, 1, 1, 8, 0),
            ))

    def test_end_equal_start_raises(self):
        t = datetime(2026, 1, 1, 8, 0)
        with pytest.raises(Exception):
            CreateShiftBody(**self._base(start_time=t, end_time=t))

    def test_max_requests_must_be_at_least_1(self):
        with pytest.raises(Exception):
            CreateShiftBody(**self._base(max_requests=0))

    def test_priority_level_bounds(self):
        # Valid edge cases
        body_low = CreateShiftBody(**self._base(priority_level=1))
        body_high = CreateShiftBody(**self._base(priority_level=5))
        assert body_low.priority_level == 1
        assert body_high.priority_level == 5

    def test_priority_level_out_of_range_raises(self):
        with pytest.raises(Exception):
            CreateShiftBody(**self._base(priority_level=6))

    def test_shift_types_accepted(self):
        for st in ("regular", "emergency", "overtime", "maintenance"):
            body = CreateShiftBody(**self._base(shift_type=st))
            assert body.shift_type == st

    def test_invalid_shift_type_raises(self):
        with pytest.raises(Exception):
            CreateShiftBody(**self._base(shift_type="unknown"))

    def test_notes_optional(self):
        body = CreateShiftBody(**self._base(notes="Замечание"))
        assert body.notes == "Замечание"


# ---------------------------------------------------------------------------
# UpdateShiftBody
# ---------------------------------------------------------------------------

class TestUpdateShiftBody:
    def test_all_optional_defaults_none(self):
        body = UpdateShiftBody()
        assert body.status is None
        assert body.user_id is None
        assert body.shift_type is None
        assert body.end_time is None
        assert body.notes is None
        assert body.max_requests is None

    def test_valid_status(self):
        body = UpdateShiftBody(status="completed")
        assert body.status == "completed"

    def test_invalid_status_raises(self):
        with pytest.raises(Exception):
            UpdateShiftBody(status="BOGUS")

    def test_max_requests_ge_1(self):
        with pytest.raises(Exception):
            UpdateShiftBody(max_requests=0)

    def test_valid_max_requests(self):
        body = UpdateShiftBody(max_requests=5)
        assert body.max_requests == 5


# ---------------------------------------------------------------------------
# CreateFromTemplateBody
# ---------------------------------------------------------------------------

class TestCreateFromTemplateBody:
    def test_valid(self):
        body = CreateFromTemplateBody(
            template_id=1,
            date=date(2026, 1, 15),
            user_ids=[1, 2, 3],
        )
        assert body.template_id == 1
        assert len(body.user_ids) == 3

    def test_user_ids_must_not_be_empty(self):
        with pytest.raises(Exception):
            CreateFromTemplateBody(
                template_id=1,
                date=date(2026, 1, 15),
                user_ids=[],
            )


# ---------------------------------------------------------------------------
# HandleTransferBody
# ---------------------------------------------------------------------------

class TestHandleTransferBody:
    def test_approve_without_executor_valid(self):
        body = HandleTransferBody(action="approve")
        assert body.action == "approve"
        assert body.to_executor_id is None

    def test_reject_action(self):
        body = HandleTransferBody(action="reject")
        assert body.action == "reject"

    def test_cancel_action(self):
        body = HandleTransferBody(action="cancel")
        assert body.action == "cancel"

    def test_invalid_action_raises(self):
        with pytest.raises(Exception):
            HandleTransferBody(action="INVALID")

    def test_approve_with_executor_id(self):
        body = HandleTransferBody(action="approve", to_executor_id=5)
        assert body.to_executor_id == 5


# ---------------------------------------------------------------------------
# CreateTemplateBody
# ---------------------------------------------------------------------------

class TestCreateTemplateBody:
    def _base(self, **overrides) -> dict:
        base = {
            "name": "Дневная смена",
            "start_hour": 8,
            "duration_hours": 8,
        }
        base.update(overrides)
        return base

    def test_valid_minimal(self):
        body = CreateTemplateBody(**self._base())
        assert body.start_minute == 0
        assert body.min_executors == 1
        assert body.max_executors == 3
        assert body.default_max_requests == 10
        assert body.auto_create is False
        assert body.default_shift_type == "regular"
        assert body.priority_level == 1

    def test_name_empty_raises(self):
        with pytest.raises(Exception):
            CreateTemplateBody(**self._base(name=""))

    def test_name_too_long_raises(self):
        with pytest.raises(Exception):
            CreateTemplateBody(**self._base(name="x" * 201))

    def test_start_hour_bounds(self):
        CreateTemplateBody(**self._base(start_hour=0))
        CreateTemplateBody(**self._base(start_hour=23))

    def test_start_hour_out_of_bounds_raises(self):
        with pytest.raises(Exception):
            CreateTemplateBody(**self._base(start_hour=24))

    def test_duration_hours_bounds(self):
        CreateTemplateBody(**self._base(duration_hours=1))
        CreateTemplateBody(**self._base(duration_hours=24))

    def test_duration_hours_zero_raises(self):
        with pytest.raises(Exception):
            CreateTemplateBody(**self._base(duration_hours=0))

    def test_min_executors_greater_than_max_raises(self):
        with pytest.raises(Exception):
            CreateTemplateBody(**self._base(min_executors=5, max_executors=3))

    def test_invalid_days_of_week_raises(self):
        with pytest.raises(Exception):
            CreateTemplateBody(**self._base(days_of_week=[0, 7]))  # 7 is out of range

    def test_valid_days_of_week(self):
        body = CreateTemplateBody(**self._base(days_of_week=[0, 1, 2, 3, 4, 5, 6]))
        assert len(body.days_of_week) == 7


# ---------------------------------------------------------------------------
# UpdateTemplateBody
# ---------------------------------------------------------------------------

class TestUpdateTemplateBody:
    def test_all_optional_defaults_none(self):
        body = UpdateTemplateBody()
        assert body.name is None
        assert body.start_hour is None
        assert body.duration_hours is None

    def test_partial_update(self):
        body = UpdateTemplateBody(name="Ночная смена", start_hour=22)
        assert body.name == "Ночная смена"
        assert body.start_hour == 22

    def test_min_greater_than_max_raises(self):
        with pytest.raises(Exception):
            UpdateTemplateBody(min_executors=5, max_executors=3)

    def test_invalid_days_of_week_raises(self):
        with pytest.raises(Exception):
            UpdateTemplateBody(days_of_week=[-1, 3])

    def test_valid_partial_executor_range(self):
        """Only setting min_executors with no max should not raise."""
        body = UpdateTemplateBody(min_executors=2)
        assert body.min_executors == 2


# ---------------------------------------------------------------------------
# DeleteEmployeeRequest
# ---------------------------------------------------------------------------

class TestDeleteEmployeeRequest:
    def test_valid(self):
        req = DeleteEmployeeRequest(reason="Уволен")
        assert req.reason == "Уволен"
        assert req.reassign_to is None

    def test_with_reassign(self):
        req = DeleteEmployeeRequest(reason="Уволен", reassign_to=5)
        assert req.reassign_to == 5

    def test_empty_reason_raises(self):
        with pytest.raises(Exception):
            DeleteEmployeeRequest(reason="")


# ---------------------------------------------------------------------------
# ActiveRequestsCount
# ---------------------------------------------------------------------------

class TestActiveRequestsCount:
    def test_valid(self):
        obj = ActiveRequestsCount(count=3)
        assert obj.count == 3


# ---------------------------------------------------------------------------
# CreateInviteRequest
# ---------------------------------------------------------------------------

class TestCreateInviteRequest:
    def test_valid_executor(self):
        req = CreateInviteRequest(role="executor")
        assert req.role == "executor"
        assert req.hours == 24
        assert req.specializations == []

    def test_valid_manager(self):
        req = CreateInviteRequest(role="manager")
        assert req.role == "manager"

    def test_invalid_role_raises(self):
        with pytest.raises(Exception):
            CreateInviteRequest(role="applicant")

    def test_hours_range(self):
        CreateInviteRequest(role="executor", hours=1)
        CreateInviteRequest(role="executor", hours=168)

    def test_hours_zero_raises(self):
        with pytest.raises(Exception):
            CreateInviteRequest(role="executor", hours=0)

    def test_hours_too_large_raises(self):
        with pytest.raises(Exception):
            CreateInviteRequest(role="executor", hours=169)


# ---------------------------------------------------------------------------
# CreateEmployeeRequest
# ---------------------------------------------------------------------------

class TestCreateEmployeeRequest:
    def test_valid(self):
        req = CreateEmployeeRequest(
            first_name="Ivan",
            last_name="Petrov",
            phone="+998901234567",
            role="executor",
        )
        assert req.status == "approved"
        assert req.specializations == []

    def test_manager_role(self):
        req = CreateEmployeeRequest(
            first_name="Anna",
            last_name="Ivanova",
            phone="+998901234567",
            role="manager",
        )
        assert req.role == "manager"

    def test_invalid_role_raises(self):
        with pytest.raises(Exception):
            CreateEmployeeRequest(
                first_name="Ivan",
                last_name="Petrov",
                phone="+998901234567",
                role="applicant",
            )

    def test_empty_first_name_raises(self):
        with pytest.raises(Exception):
            CreateEmployeeRequest(
                first_name="",
                last_name="Petrov",
                phone="+998901234567",
                role="executor",
            )

    def test_phone_too_short_raises(self):
        with pytest.raises(Exception):
            CreateEmployeeRequest(
                first_name="Ivan",
                last_name="Petrov",
                phone="123",
                role="executor",
            )

    def test_pending_status_accepted(self):
        req = CreateEmployeeRequest(
            first_name="Ivan",
            last_name="Petrov",
            phone="+998901234567",
            role="executor",
            status="pending",
        )
        assert req.status == "pending"
