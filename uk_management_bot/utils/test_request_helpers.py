"""
Unit tests for utils/request_helpers.py

Tests RequestCallbackHelper class methods, standalone format/validation functions.
Uses MagicMock for ORM objects; no DB or network calls.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime


GET_TEXT_PATH = "uk_management_bot.utils.request_helpers.get_text"


def _mock_get_text(key: str, language: str = "ru", **kwargs) -> str:
    return key


def _make_request(request_number="250101-001", category="plumbing", status="Новая",
                  address="Дом: 5", description="Описание", urgency="low",
                  apartment=None, notes=None, executor_id=None, media_files=None):
    r = MagicMock()
    r.request_number = request_number
    r.category = category
    r.status = status
    r.address = address
    r.description = description
    r.urgency = urgency
    r.apartment = apartment
    r.notes = notes
    r.executor_id = executor_id
    r.media_files = media_files
    r.created_at = datetime(2025, 1, 1, 12, 0)
    r.updated_at = None
    r.format_number_for_display = MagicMock(return_value=f"#{request_number}")
    return r


# ---------------------------------------------------------------------------
# RequestCallbackHelper.extract_request_number_from_callback
# ---------------------------------------------------------------------------

class TestExtractRequestNumber:
    def test_valid_callback_returns_number(self):
        from uk_management_bot.utils.request_helpers import RequestCallbackHelper
        result = RequestCallbackHelper.extract_request_number_from_callback(
            "view_250101-001", "view_"
        )
        assert result == "250101-001"

    def test_wrong_prefix_returns_none(self):
        from uk_management_bot.utils.request_helpers import RequestCallbackHelper
        result = RequestCallbackHelper.extract_request_number_from_callback(
            "view_250101-001", "edit_"
        )
        assert result is None

    def test_invalid_number_format_returns_none(self):
        from uk_management_bot.utils.request_helpers import RequestCallbackHelper
        result = RequestCallbackHelper.extract_request_number_from_callback(
            "view_invalid-num", "view_"
        )
        assert result is None

    def test_various_valid_prefixes(self):
        from uk_management_bot.utils.request_helpers import RequestCallbackHelper
        for prefix in ["view_", "edit_", "cancel_"]:
            result = RequestCallbackHelper.extract_request_number_from_callback(
                f"{prefix}250615-042", prefix
            )
            assert result == "250615-042", f"Failed for prefix: {prefix}"


# ---------------------------------------------------------------------------
# RequestCallbackHelper.create_callback_data_with_request_number
# ---------------------------------------------------------------------------

class TestCreateCallbackData:
    def test_creates_callback_with_prefix(self):
        from uk_management_bot.utils.request_helpers import RequestCallbackHelper
        result = RequestCallbackHelper.create_callback_data_with_request_number(
            "view_", "250101-001"
        )
        assert result == "view_250101-001"

    def test_invalid_number_still_creates_callback(self):
        from uk_management_bot.utils.request_helpers import RequestCallbackHelper
        # Invalid format logs a warning but still creates the string
        result = RequestCallbackHelper.create_callback_data_with_request_number(
            "view_", "invalid-num"
        )
        assert result == "view_invalid-num"

    def test_different_prefixes(self):
        from uk_management_bot.utils.request_helpers import RequestCallbackHelper
        for prefix in ["a_", "edit_", "cancel_"]:
            result = RequestCallbackHelper.create_callback_data_with_request_number(
                prefix, "250101-001"
            )
            assert result.startswith(prefix)


# ---------------------------------------------------------------------------
# RequestCallbackHelper.is_request_number_callback
# ---------------------------------------------------------------------------

class TestIsRequestNumberCallback:
    def test_valid_callback_returns_true(self):
        from uk_management_bot.utils.request_helpers import RequestCallbackHelper
        assert RequestCallbackHelper.is_request_number_callback("view_250101-001", "view_") is True

    def test_invalid_callback_returns_false(self):
        from uk_management_bot.utils.request_helpers import RequestCallbackHelper
        assert RequestCallbackHelper.is_request_number_callback("view_not_a_number", "view_") is False

    def test_wrong_prefix_returns_false(self):
        from uk_management_bot.utils.request_helpers import RequestCallbackHelper
        assert RequestCallbackHelper.is_request_number_callback("view_250101-001", "edit_") is False


# ---------------------------------------------------------------------------
# format_request_for_list
# ---------------------------------------------------------------------------

class TestFormatRequestForList:
    def test_with_number_includes_display_number(self):
        from uk_management_bot.utils.request_helpers import format_request_for_list
        req = _make_request()
        result = format_request_for_list(req, include_number=True)
        assert "#250101-001" in result
        assert "Дом: 5" in result

    def test_without_number_excludes_display_number(self):
        from uk_management_bot.utils.request_helpers import format_request_for_list
        req = _make_request()
        result = format_request_for_list(req, include_number=False)
        assert "Дом: 5" in result
        # format_number_for_display was not called
        req.format_number_for_display.assert_not_called()


# ---------------------------------------------------------------------------
# get_status_icon
# ---------------------------------------------------------------------------

class TestGetStatusIcon:
    @pytest.mark.parametrize("status, expected_emoji", [
        ("Новая", "🆕"),
        ("В работе", "🔧"),
        ("Выполнена", "✅"),
        ("Отменена", "❌"),
        ("Уточнение", "💬"),
    ])
    def test_known_statuses(self, status, expected_emoji):
        from uk_management_bot.utils.request_helpers import get_status_icon
        assert get_status_icon(status) == expected_emoji

    def test_unknown_status_returns_default(self):
        from uk_management_bot.utils.request_helpers import get_status_icon
        result = get_status_icon("UnknownStatus")
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# validate_callback_request_number
# ---------------------------------------------------------------------------

class TestValidateCallbackRequestNumber:
    def test_valid_callback_returns_number(self):
        from uk_management_bot.utils.request_helpers import validate_callback_request_number
        result = validate_callback_request_number("view_250101-001", "view_")
        assert result == "250101-001"

    def test_invalid_callback_returns_none(self):
        from uk_management_bot.utils.request_helpers import validate_callback_request_number
        result = validate_callback_request_number("view_bad-format", "view_")
        assert result is None


# ---------------------------------------------------------------------------
# format_request_details
# ---------------------------------------------------------------------------

class TestFormatRequestDetails:
    def test_returns_string(self):
        from uk_management_bot.utils.request_helpers import format_request_details
        req = _make_request()
        result = format_request_details(req, language="ru")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_includes_request_number(self):
        from uk_management_bot.utils.request_helpers import format_request_details
        req = _make_request(request_number="250101-999")
        result = format_request_details(req, language="ru")
        assert "250101-999" in result

    def test_includes_description(self):
        from uk_management_bot.utils.request_helpers import format_request_details
        req = _make_request(description="Важная проблема")
        result = format_request_details(req, language="ru")
        assert "Важная проблема" in result

    def test_urgency_localized_not_raw_key(self):
        # TASK 17: urgency хранится ключом, но в сообщении показывается локализованно.
        from uk_management_bot.utils.request_helpers import format_request_details
        req = _make_request(urgency="high", description="нет утечки ключа")
        result = format_request_details(req, language="ru")
        assert "Срочная" in result
        assert "high" not in result  # сырой ключ не должен утечь

    def test_with_apartment(self):
        from uk_management_bot.utils.request_helpers import format_request_details
        req = _make_request(apartment="42")
        result = format_request_details(req, language="ru")
        assert "42" in result

    def test_with_updated_at(self):
        from uk_management_bot.utils.request_helpers import format_request_details
        req = _make_request()
        req.updated_at = datetime(2025, 6, 15, 10, 0)
        result = format_request_details(req, language="ru")
        assert "15.06.2025" in result

    def test_with_media_files_json(self):
        from uk_management_bot.utils.request_helpers import format_request_details
        req = _make_request(media_files='["file1.jpg", "file2.jpg"]')
        result = format_request_details(req, language="ru")
        # Should include media count
        assert isinstance(result, str)

    def test_uz_language(self):
        from uk_management_bot.utils.request_helpers import format_request_details
        req = _make_request()
        result = format_request_details(req, language="uz")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# format_requests_list_header
# ---------------------------------------------------------------------------

class TestFormatRequestsListHeader:
    def test_executor_role_returns_string(self):
        from uk_management_bot.utils.request_helpers import format_requests_list_header
        result = format_requests_list_header(
            total_requests=10, current_page=1, total_pages=2,
            status_filter="all", role="executor", language="ru"
        )
        assert isinstance(result, str)
        assert "1/2" in result

    def test_applicant_active_filter(self):
        from uk_management_bot.utils.request_helpers import format_requests_list_header
        result = format_requests_list_header(
            total_requests=5, current_page=1, total_pages=1,
            status_filter="active", role="applicant", language="ru"
        )
        assert isinstance(result, str)

    def test_applicant_archive_filter(self):
        from uk_management_bot.utils.request_helpers import format_requests_list_header
        result = format_requests_list_header(
            total_requests=3, current_page=2, total_pages=3,
            status_filter="archive", role="applicant", language="ru"
        )
        assert isinstance(result, str)

    def test_applicant_all_filter(self):
        from uk_management_bot.utils.request_helpers import format_requests_list_header
        result = format_requests_list_header(
            total_requests=8, current_page=1, total_pages=1,
            status_filter="all", role="applicant", language="ru"
        )
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# format_request_list_item
# ---------------------------------------------------------------------------

class TestFormatRequestListItem:
    def test_returns_string(self):
        from uk_management_bot.utils.request_helpers import format_request_list_item
        req = _make_request()
        result = format_request_list_item(req, index=1, language="ru")
        assert isinstance(result, str)
        assert "1." in result

    def test_includes_request_number(self):
        from uk_management_bot.utils.request_helpers import format_request_list_item
        req = _make_request(request_number="250115-005")
        result = format_request_list_item(req, index=3, language="ru")
        assert "250115-005" in result

    def test_without_details(self):
        from uk_management_bot.utils.request_helpers import format_request_list_item
        req = _make_request()
        result = format_request_list_item(req, index=1, language="ru", show_details=False)
        assert isinstance(result, str)

    def test_cancelled_status_with_notes(self):
        from uk_management_bot.utils.request_helpers import format_request_list_item
        req = _make_request(status="Отменена", notes="Причина отмены")
        result = format_request_list_item(req, index=1, language="ru")
        assert isinstance(result, str)

    def test_clarification_status_with_notes(self):
        from uk_management_bot.utils.request_helpers import format_request_list_item
        req = _make_request(status="Уточнение", notes="Вопрос 1\nВопрос 2\nВопрос 3")
        result = format_request_list_item(req, index=1, language="ru")
        assert isinstance(result, str)
