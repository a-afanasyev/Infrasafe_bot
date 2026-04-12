"""
Extra mock-based unit tests for RequestNumberService.

Complements the existing tests in tests/test_request_number_service.py
with additional edge-case coverage.
"""
import pytest
from datetime import date, datetime
from unittest.mock import MagicMock

from uk_management_bot.services.request_number_service import RequestNumberService


class TestGenerateNextNumberEdgeCases:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = RequestNumberService(self.db)

    def test_handles_db_exception_with_fallback(self):
        """When DB query fails, should return fallback number."""
        self.db.execute.side_effect = Exception("DB connection lost")
        test_date = date(2026, 4, 12)
        number = RequestNumberService.generate_next_number(test_date, self.db)
        assert number.startswith("260412-")
        # Fallback uses timestamp, just check the format
        assert len(number.split("-")[1]) == 3

    def test_uses_today_when_no_date(self):
        """When creation_date is None, uses today's date."""
        self.db.execute.return_value.fetchone.return_value = None
        number = RequestNumberService.generate_next_number(db=self.db)
        today_prefix = date.today().strftime("%y%m%d")
        assert number.startswith(today_prefix)

    def test_sequence_over_999(self):
        """Supports >999 requests per day."""
        mock_result = MagicMock()
        mock_result.__getitem__ = MagicMock(return_value="260412-1500")
        self.db.execute.return_value.fetchone.return_value = mock_result
        test_date = date(2026, 4, 12)
        number = RequestNumberService.generate_next_number(test_date, self.db)
        assert number == "260412-1501"


class TestValidateRequestNumberFormatEdgeCases:
    def test_valid_4_digit_sequence(self):
        """Numbers with 4+ digits in sequence should be valid."""
        assert RequestNumberService.validate_request_number_format("260412-1000") is True

    def test_february_29_leap_year(self):
        assert RequestNumberService.validate_request_number_format("240229-001") is True

    def test_february_29_non_leap_year(self):
        assert RequestNumberService.validate_request_number_format("250229-001") is False

    def test_month_13_invalid(self):
        assert RequestNumberService.validate_request_number_format("251301-001") is False

    def test_day_31_in_30_day_month(self):
        assert RequestNumberService.validate_request_number_format("250631-001") is False

    def test_with_whitespace_is_invalid(self):
        assert RequestNumberService.validate_request_number_format(" 260412-001") is False
        assert RequestNumberService.validate_request_number_format("260412-001 ") is False


class TestParseRequestNumberEdgeCases:
    def test_large_sequence(self):
        result = RequestNumberService.parse_request_number("260412-1234")
        assert result["valid"] is True
        assert result["sequence"] == 1234

    def test_date_components(self):
        result = RequestNumberService.parse_request_number("251231-042")
        assert result["year"] == 2025
        assert result["month"] == 12
        assert result["day"] == 31


class TestGetRequestsByDate:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = RequestNumberService(self.db)

    def test_db_exception_returns_empty(self):
        self.db.execute.side_effect = Exception("fail")
        result = self.svc.get_requests_by_date(date(2026, 4, 12))
        assert result == []


class TestCheckNumberAvailability:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = RequestNumberService(self.db)

    def test_db_exception_returns_false(self):
        self.db.execute.side_effect = Exception("fail")
        assert self.svc.check_number_availability("260412-001") is False


class TestFormatForDisplay:
    def test_invalid_date_in_format(self):
        """Format returns as-is for invalid format."""
        assert RequestNumberService.format_for_display("bad") == "bad"

    def test_valid_format(self):
        result = RequestNumberService.format_for_display("260101-001")
        assert "01.01.2026" in result
        assert "260101-001" in result
