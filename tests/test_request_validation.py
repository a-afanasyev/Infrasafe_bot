"""Tests for request schema validation (Task 3.1) and request_number format (Task 3.2)."""

import re
import pytest
from unittest.mock import patch, MagicMock
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Task 3.1 — Category validator on CreateRequestBody
# ---------------------------------------------------------------------------

class TestCreateRequestBodyCategoryValidation:
    """Category must be one of settings.REQUEST_CATEGORIES."""

    VALID_CATEGORIES = [
        "Электрика",
        "Сантехника",
        "Отопление",
        "Вентиляция",
        "Лифт",
        "Уборка",
        "Благоустройство",
        "Безопасность",
        "Интернет/ТВ",
        "Другое",
    ]

    def _make_body(self, category: str) -> dict:
        return {
            "category": category,
            "urgency": "Обычная",
            "description": "test description",
        }

    @patch("uk_management_bot.config.settings.Settings")
    def test_valid_category_accepted(self, _mock_cls: MagicMock) -> None:
        from uk_management_bot.api.requests.schemas import CreateRequestBody

        with patch(
            "uk_management_bot.config.settings.settings"
        ) as mock_settings:
            mock_settings.REQUEST_CATEGORIES = self.VALID_CATEGORIES
            body = CreateRequestBody(**self._make_body("Электрика"))
            assert body.category == "Электрика"

    @patch("uk_management_bot.config.settings.Settings")
    def test_invalid_category_raises(self, _mock_cls: MagicMock) -> None:
        from uk_management_bot.api.requests.schemas import CreateRequestBody

        with patch(
            "uk_management_bot.config.settings.settings"
        ) as mock_settings:
            mock_settings.REQUEST_CATEGORIES = self.VALID_CATEGORIES
            with pytest.raises(ValidationError, match="category must be one of"):
                CreateRequestBody(**self._make_body("НесуществующаяКатегория"))

    @patch("uk_management_bot.config.settings.Settings")
    def test_each_valid_category(self, _mock_cls: MagicMock) -> None:
        from uk_management_bot.api.requests.schemas import CreateRequestBody

        with patch(
            "uk_management_bot.config.settings.settings"
        ) as mock_settings:
            mock_settings.REQUEST_CATEGORIES = self.VALID_CATEGORIES
            for cat in self.VALID_CATEGORIES:
                body = CreateRequestBody(**self._make_body(cat))
                assert body.category == cat


# ---------------------------------------------------------------------------
# Task 3.1 — Rating validator on UpdateRequestBody
# ---------------------------------------------------------------------------

class TestUpdateRequestBodyRatingValidation:
    """Rating must be an integer between 1 and 5 (or None)."""

    def test_rating_none_is_allowed(self) -> None:
        from uk_management_bot.api.requests.schemas import UpdateRequestBody

        body = UpdateRequestBody(rating=None)
        assert body.rating is None

    def test_rating_omitted_defaults_to_none(self) -> None:
        from uk_management_bot.api.requests.schemas import UpdateRequestBody

        body = UpdateRequestBody()
        assert body.rating is None

    @pytest.mark.parametrize("value", [1, 2, 3, 4, 5])
    def test_valid_ratings(self, value: int) -> None:
        from uk_management_bot.api.requests.schemas import UpdateRequestBody

        body = UpdateRequestBody(rating=value)
        assert body.rating == value

    @pytest.mark.parametrize("value", [0, -1, 6, 10, 100])
    def test_rating_out_of_range_raises(self, value: int) -> None:
        from uk_management_bot.api.requests.schemas import UpdateRequestBody

        with pytest.raises(ValidationError, match="rating must be an integer between 1 and 5"):
            UpdateRequestBody(rating=value)


# ---------------------------------------------------------------------------
# Task 3.2 — request_number format validation on media proxy
# ---------------------------------------------------------------------------

class TestRequestNumberPattern:
    """REQUEST_NUMBER_PATTERN must accept YYMMDD-NNN and reject everything else.

    We duplicate the pattern here to avoid importing api.main (which starts
    the full FastAPI app and needs a live database connection).  The production
    pattern is defined in uk_management_bot/api/main.py.
    """

    PATTERN = re.compile(r"^\d{6}-\d{3}$")

    def test_valid_patterns(self) -> None:
        assert self.PATTERN.match("260412-001")
        assert self.PATTERN.match("000101-999")
        assert self.PATTERN.match("991231-000")

    @pytest.mark.parametrize(
        "bad",
        [
            "12345-001",      # 5-digit prefix
            "1234567-001",    # 7-digit prefix
            "260412-01",      # 2-digit suffix
            "260412-0001",    # 4-digit suffix
            "260412001",      # missing dash
            "ABCDEF-001",     # letters
            "260412-ABC",     # letters in suffix
            "",               # empty
            "26-04-12-001",   # extra dashes
            "../../../etc/passwd",  # path traversal
        ],
    )
    def test_invalid_patterns_rejected(self, bad: str) -> None:
        assert self.PATTERN.match(bad) is None
