"""
Unit tests for utils/status_display.py

Tests get_status_display() and get_status_with_emoji().
get_text is mocked to return locale keys for deterministic assertions.
"""
import pytest
from unittest.mock import patch


GET_TEXT_PATH = "uk_management_bot.utils.status_display.get_text"


def _mock_get_text(key: str, language: str = "ru", **kwargs) -> str:
    return key


# ---------------------------------------------------------------------------
# get_status_display
# ---------------------------------------------------------------------------

class TestGetStatusDisplay:
    def test_known_status_returns_display_key(self):
        from uk_management_bot.utils.constants import REQUEST_STATUS_NEW
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.utils.status_display import get_status_display
            result = get_status_display(REQUEST_STATUS_NEW)
        assert result == "statuses.new"

    def test_in_progress_status(self):
        from uk_management_bot.utils.constants import REQUEST_STATUS_IN_PROGRESS
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.utils.status_display import get_status_display
            result = get_status_display(REQUEST_STATUS_IN_PROGRESS)
        assert result == "statuses.in_progress"

    def test_completed_status(self):
        from uk_management_bot.utils.constants import REQUEST_STATUS_COMPLETED
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.utils.status_display import get_status_display
            result = get_status_display(REQUEST_STATUS_COMPLETED)
        assert result == "statuses.completed"

    def test_unknown_status_returned_as_is(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.utils.status_display import get_status_display
            result = get_status_display("nonexistent_status")
        assert result == "nonexistent_status"

    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_language_passed_to_get_text(self, language):
        from uk_management_bot.utils.constants import REQUEST_STATUS_NEW
        calls = []

        def mock_gt(key, language="ru", **kwargs):
            calls.append(language)
            return key

        with patch(GET_TEXT_PATH, side_effect=mock_gt):
            from uk_management_bot.utils.status_display import get_status_display
            get_status_display(REQUEST_STATUS_NEW, language=language)
        assert language in calls

    def test_all_known_statuses_resolve(self):
        from uk_management_bot.utils.status_display import STATUS_DISPLAY_KEYS
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.utils.status_display import get_status_display
            for status in STATUS_DISPLAY_KEYS:
                result = get_status_display(status)
                assert result == STATUS_DISPLAY_KEYS[status]


# ---------------------------------------------------------------------------
# get_status_with_emoji
# ---------------------------------------------------------------------------

class TestGetStatusWithEmoji:
    def test_known_status_has_emoji(self):
        from uk_management_bot.utils.constants import REQUEST_STATUS_NEW
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.utils.status_display import get_status_with_emoji
            result = get_status_with_emoji(REQUEST_STATUS_NEW)
        # Should contain the emoji from STATUS_EMOJI dict
        assert "🆕" in result

    def test_in_progress_has_emoji(self):
        from uk_management_bot.utils.constants import REQUEST_STATUS_IN_PROGRESS
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.utils.status_display import get_status_with_emoji
            result = get_status_with_emoji(REQUEST_STATUS_IN_PROGRESS)
        assert "🛠️" in result

    def test_unknown_status_uses_default_emoji(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.utils.status_display import get_status_with_emoji
            result = get_status_with_emoji("totally_unknown")
        # Default emoji is "📋"
        assert "📋" in result

    def test_result_contains_display_text(self):
        from uk_management_bot.utils.constants import REQUEST_STATUS_NEW
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.utils.status_display import get_status_with_emoji
            result = get_status_with_emoji(REQUEST_STATUS_NEW)
        # The display key text should be present
        assert "statuses.new" in result

    def test_result_format_is_emoji_space_text(self):
        from uk_management_bot.utils.constants import REQUEST_STATUS_NEW
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.utils.status_display import get_status_with_emoji
            result = get_status_with_emoji(REQUEST_STATUS_NEW)
        parts = result.split(" ", 1)
        assert len(parts) == 2
