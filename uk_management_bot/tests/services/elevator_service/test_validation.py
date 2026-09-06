"""Юнит-тесты чистых валидаторов модуля «Лифты» (Ф2a): Р11, статусы, паспорт."""
import pytest

from uk_management_bot.database.models.elevator import ELEVATOR_STATUSES
from uk_management_bot.keyboards.requests import CATEGORY_KEYS
from uk_management_bot.services.elevator_service import (
    ELEVATOR_CATEGORY,
    PASSPORT_REQUIRED_FIELDS,
    ElevatorConflictError,
    ElevatorServiceError,
    ElevatorStateError,
    ElevatorValidationError,
    can_set_status,
    require_elevator_for_category,
    validate_passport_required,
    validate_status,
)

pytestmark = pytest.mark.unit


def test_elevator_category_is_canonical_request_category():
    assert ELEVATOR_CATEGORY == "elevator"
    assert ELEVATOR_CATEGORY in CATEGORY_KEYS


def test_error_hierarchy():
    assert issubclass(ElevatorValidationError, ElevatorServiceError)
    assert issubclass(ElevatorStateError, ElevatorConflictError)
    assert issubclass(ElevatorConflictError, ElevatorServiceError)


# ---------------------------------------------------------------------------
# Р11: заявка категории «лифт» обязана нести elevator_id + elevator_operational
# ---------------------------------------------------------------------------

class TestRequireElevatorForCategory:
    def test_ok_when_both_fields_present(self):
        require_elevator_for_category("elevator", 5, True, enabled=True)
        require_elevator_for_category("elevator", 5, False, enabled=True)

    def test_missing_elevator_id(self):
        with pytest.raises(ElevatorValidationError) as exc:
            require_elevator_for_category("elevator", None, True, enabled=True)
        assert "elevator_id" in str(exc.value)

    def test_missing_operational_flag(self):
        with pytest.raises(ElevatorValidationError) as exc:
            require_elevator_for_category("elevator", 5, None, enabled=True)
        assert "elevator_operational" in str(exc.value)

    def test_both_missing_lists_both(self):
        with pytest.raises(ElevatorValidationError) as exc:
            require_elevator_for_category("elevator", None, None, enabled=True)
        assert "elevator_id" in str(exc.value)
        assert "elevator_operational" in str(exc.value)

    def test_disabled_flag_is_noop(self):
        require_elevator_for_category("elevator", None, None, enabled=False)

    def test_other_category_is_noop_without_fields(self):
        require_elevator_for_category("plumbing", None, None, enabled=True)

    def test_other_category_is_noop_with_fields(self):
        require_elevator_for_category("plumbing", 5, True, enabled=True)

    def test_none_category_is_noop(self):
        require_elevator_for_category(None, None, None, enabled=True)


# ---------------------------------------------------------------------------
# validate_status
# ---------------------------------------------------------------------------

class TestValidateStatus:
    @pytest.mark.parametrize("status", ELEVATOR_STATUSES)
    def test_accepts_canonical(self, status):
        assert validate_status(status) == status

    def test_normalizes_case_and_whitespace(self):
        assert validate_status("  Working ") == "working"

    @pytest.mark.parametrize("bad", ["", "broken", "WORKING_", None, 5])
    def test_rejects_unknown(self, bad):
        with pytest.raises(ElevatorValidationError):
            validate_status(bad)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# validate_passport_required
# ---------------------------------------------------------------------------

def _passport(**overrides):
    base = {
        "passport_number": "P-1",
        "manufacturer": "OTIS",
        "serial_number": "S-1",
        "building_id": 3,
        "entrance_number": 1,
        "elevator_number": 2,
    }
    return {**base, **overrides}


class TestValidatePassportRequired:
    def test_ok(self):
        validate_passport_required(_passport())

    def test_extra_keys_ignored(self):
        validate_passport_required(_passport(model="X", floors_served="1-9"))

    @pytest.mark.parametrize("field", PASSPORT_REQUIRED_FIELDS)
    def test_each_missing_field_named(self, field):
        data = _passport()
        del data[field]
        with pytest.raises(ElevatorValidationError) as exc:
            validate_passport_required(data)
        assert field in str(exc.value)

    @pytest.mark.parametrize("empty", [None, "", "   "])
    def test_blank_string_is_missing(self, empty):
        with pytest.raises(ElevatorValidationError) as exc:
            validate_passport_required(_passport(manufacturer=empty))
        assert "manufacturer" in str(exc.value)

    def test_lists_all_missing(self):
        with pytest.raises(ElevatorValidationError) as exc:
            validate_passport_required(_passport(passport_number="", serial_number=None))
        msg = str(exc.value)
        assert "passport_number" in msg and "serial_number" in msg

    @pytest.mark.parametrize("field", ["entrance_number", "elevator_number", "building_id"])
    @pytest.mark.parametrize("bad", [0, -1, "1", 1.5, True])
    def test_numbers_must_be_positive_int(self, field, bad):
        with pytest.raises(ElevatorValidationError) as exc:
            validate_passport_required(_passport(**{field: bad}))
        assert field in str(exc.value)


# ---------------------------------------------------------------------------
# can_set_status
# ---------------------------------------------------------------------------

class TestCanSetStatus:
    def test_ok_when_commissioned_and_active(self):
        can_set_status("working", is_commissioned=True, archived=False)

    def test_archived_forbidden(self):
        with pytest.raises(ElevatorStateError):
            can_set_status("working", is_commissioned=True, archived=True)

    def test_not_commissioned_forbidden_for_any_status(self):
        for status in ELEVATOR_STATUSES:
            with pytest.raises(ElevatorStateError):
                can_set_status(status, is_commissioned=False, archived=False)

    def test_unknown_status_is_validation_error(self):
        with pytest.raises(ElevatorValidationError):
            can_set_status("broken", is_commissioned=True, archived=False)
