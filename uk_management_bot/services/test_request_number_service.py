"""Unit tests for RequestNumberService."""
import pytest
from datetime import date
from unittest.mock import MagicMock

from uk_management_bot.services.request_number_service import RequestNumberService


# ---------------------------------------------------------------------------
# validate_request_number_format
# ---------------------------------------------------------------------------

class TestValidateRequestNumberFormat:
    def test_valid_format(self):
        assert RequestNumberService.validate_request_number_format("260402-001") is True

    def test_valid_format_double_digit_sequence(self):
        assert RequestNumberService.validate_request_number_format("260402-010") is True

    def test_valid_format_triple_digit_sequence(self):
        assert RequestNumberService.validate_request_number_format("260402-100") is True

    def test_valid_format_large_sequence(self):
        # Supports >999 requests per day (3+ digits)
        assert RequestNumberService.validate_request_number_format("260402-1000") is True

    def test_invalid_format_missing_dash(self):
        assert RequestNumberService.validate_request_number_format("260402001") is False

    def test_invalid_format_too_short_sequence(self):
        # 2 digits — must be 3+
        assert RequestNumberService.validate_request_number_format("260402-01") is False

    def test_invalid_format_not_string(self):
        assert RequestNumberService.validate_request_number_format(260402001) is False

    def test_invalid_format_empty_string(self):
        assert RequestNumberService.validate_request_number_format("") is False

    def test_invalid_date_month_13(self):
        # Month 13 is invalid
        assert RequestNumberService.validate_request_number_format("261302-001") is False

    def test_invalid_date_day_00(self):
        assert RequestNumberService.validate_request_number_format("260400-001") is False

    def test_invalid_date_day_32(self):
        assert RequestNumberService.validate_request_number_format("260432-001") is False

    def test_invalid_format_with_letters(self):
        assert RequestNumberService.validate_request_number_format("26040A-001") is False


# ---------------------------------------------------------------------------
# generate_next_number
# ---------------------------------------------------------------------------

class TestGenerateNextNumber:
    def test_no_db_returns_001(self):
        target = date(2026, 4, 2)
        result = RequestNumberService.generate_next_number(creation_date=target, db=None)
        assert result == "260402-001"

    def test_format_yymmdd_nnn(self):
        """Result must match YYMMDD-NNN pattern."""
        target = date(2025, 9, 17)
        result = RequestNumberService.generate_next_number(creation_date=target, db=None)
        assert result == "250917-001"

    def test_with_db_no_existing_returns_001(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = None

        result = RequestNumberService.generate_next_number(
            creation_date=date(2026, 4, 2), db=db
        )
        assert result == "260402-001"

    def test_with_db_increments_from_last(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = ("260402-005",)

        result = RequestNumberService.generate_next_number(
            creation_date=date(2026, 4, 2), db=db
        )
        assert result == "260402-006"

    def test_padding_single_digit(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = None

        result = RequestNumberService.generate_next_number(
            creation_date=date(2026, 4, 2), db=db
        )
        # Sequence must be zero-padded to 3 digits
        seq_part = result.split("-")[1]
        assert len(seq_part) == 3
        assert seq_part == "001"

    def test_padding_two_digit_sequence(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = ("260402-009",)

        result = RequestNumberService.generate_next_number(
            creation_date=date(2026, 4, 2), db=db
        )
        assert result == "260402-010"

    def test_padding_three_digit_sequence(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = ("260402-099",)

        result = RequestNumberService.generate_next_number(
            creation_date=date(2026, 4, 2), db=db
        )
        assert result == "260402-100"

    def test_sequence_overflow_beyond_999(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = ("260402-999",)

        result = RequestNumberService.generate_next_number(
            creation_date=date(2026, 4, 2), db=db
        )
        assert result == "260402-1000"

    def test_db_exception_fallback(self):
        db = MagicMock()
        db.execute.side_effect = Exception("DB connection error")

        result = RequestNumberService.generate_next_number(
            creation_date=date(2026, 4, 2), db=db
        )
        # Fallback format: YYMMDD-<timestamp-based suffix>
        assert result.startswith("260402-")

    def test_default_date_is_today(self):
        """With no creation_date, uses today's date."""
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = None

        result = RequestNumberService.generate_next_number(db=db)
        today_prefix = date.today().strftime("%y%m%d")
        assert result.startswith(today_prefix)


# ---------------------------------------------------------------------------
# parse_request_number
# ---------------------------------------------------------------------------

class TestParseRequestNumber:
    def test_valid_number_returns_components(self):
        parsed = RequestNumberService.parse_request_number("260402-007")
        assert parsed["valid"] is True
        assert parsed["year"] == 2026
        assert parsed["month"] == 4
        assert parsed["day"] == 2
        assert parsed["sequence"] == 7
        assert parsed["date_prefix"] == "260402"
        assert parsed["sequence_str"] == "007"

    def test_valid_date_object(self):
        parsed = RequestNumberService.parse_request_number("260402-007")
        assert parsed["date"] == date(2026, 4, 2)

    def test_invalid_format_returns_invalid(self):
        parsed = RequestNumberService.parse_request_number("bad-format")
        assert parsed["valid"] is False
        assert "error" in parsed

    def test_empty_string_returns_invalid(self):
        parsed = RequestNumberService.parse_request_number("")
        assert parsed["valid"] is False

    def test_large_sequence(self):
        parsed = RequestNumberService.parse_request_number("260402-1234")
        assert parsed["valid"] is True
        assert parsed["sequence"] == 1234


# ---------------------------------------------------------------------------
# format_for_display
# ---------------------------------------------------------------------------

class TestFormatForDisplay:
    def test_valid_number_includes_date_in_parentheses(self):
        result = RequestNumberService.format_for_display("260402-001")
        assert "260402-001" in result
        assert "02.04.2026" in result
        assert result.startswith("№")

    def test_invalid_number_returned_as_is(self):
        invalid = "not-a-number"
        result = RequestNumberService.format_for_display(invalid)
        assert result == invalid


# ---------------------------------------------------------------------------
# check_number_availability
# ---------------------------------------------------------------------------

class TestCheckNumberAvailability:
    def test_available_when_not_in_db(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = None

        svc = RequestNumberService(db)
        assert svc.check_number_availability("260402-001") is True

    def test_not_available_when_in_db(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (1,)

        svc = RequestNumberService(db)
        assert svc.check_number_availability("260402-001") is False

    def test_invalid_format_returns_false(self):
        db = MagicMock()
        svc = RequestNumberService(db)
        assert svc.check_number_availability("bad") is False

    def test_db_exception_returns_false(self):
        db = MagicMock()
        db.execute.side_effect = Exception("DB error")

        svc = RequestNumberService(db)
        assert svc.check_number_availability("260402-001") is False
