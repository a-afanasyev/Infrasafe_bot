"""
Unit tests for utils/validators.py

Tests Validator class methods and standalone validation functions.
Pure logic tests with no DB or network dependencies.
"""
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Validator.validate_phone
# ---------------------------------------------------------------------------

class TestValidatorPhone:
    def test_empty_phone_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        valid, msg = Validator.validate_phone("")
        assert valid is False
        assert isinstance(msg, str)

    def test_none_phone_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        valid, msg = Validator.validate_phone(None)
        assert valid is False

    def test_valid_plus998(self):
        from uk_management_bot.utils.validators import Validator
        valid, msg = Validator.validate_phone("+998901234567")
        assert valid is True

    def test_valid_998_prefix(self):
        from uk_management_bot.utils.validators import Validator
        valid, msg = Validator.validate_phone("998901234567")
        assert valid is True

    def test_valid_nine_digits(self):
        from uk_management_bot.utils.validators import Validator
        valid, msg = Validator.validate_phone("901234567")
        assert valid is True

    def test_invalid_format_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        valid, msg = Validator.validate_phone("abc123")
        assert valid is False

    def test_spaces_stripped(self):
        from uk_management_bot.utils.validators import Validator
        valid, msg = Validator.validate_phone("+998 90 123 4567")
        assert valid is True


# ---------------------------------------------------------------------------
# Validator.validate_description
# ---------------------------------------------------------------------------

class TestValidatorDescription:
    def test_empty_description_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_description("")
        assert valid is False

    def test_none_description_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_description(None)
        assert valid is False

    def test_too_short_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_description("short")
        assert valid is False

    def test_valid_description(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_description("Описание проблемы очень подробное")
        assert valid is True

    def test_too_long_description_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        from uk_management_bot.utils.constants import MAX_DESCRIPTION_LENGTH
        valid, _ = Validator.validate_description("A" * (MAX_DESCRIPTION_LENGTH + 1))
        assert valid is False


# ---------------------------------------------------------------------------
# Validator.validate_apartment
# ---------------------------------------------------------------------------

class TestValidatorApartment:
    def test_empty_apartment_is_ok(self):
        """Empty apartment is optional."""
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_apartment("")
        assert valid is True

    def test_none_apartment_is_ok(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_apartment(None)
        assert valid is True

    def test_valid_apartment_number(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_apartment("42")
        assert valid is True

    def test_valid_alphanumeric_apartment(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_apartment("42A")
        assert valid is True

    def test_invalid_chars_in_apartment(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_apartment("кв. 42")  # contains spaces and dots
        assert valid is False

    def test_too_long_apartment_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        from uk_management_bot.utils.constants import MAX_APARTMENT_LENGTH
        valid, _ = Validator.validate_apartment("A" * (MAX_APARTMENT_LENGTH + 1))
        assert valid is False


# ---------------------------------------------------------------------------
# Validator.validate_status
# ---------------------------------------------------------------------------

class TestValidatorStatus:
    def test_empty_status_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_status("")
        assert valid is False

    def test_invalid_status_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_status("non_existent_status")
        assert valid is False

    def test_valid_status_from_constants(self):
        from uk_management_bot.utils.validators import Validator
        from uk_management_bot.utils.constants import REQUEST_STATUSES
        # Use first valid status
        status = REQUEST_STATUSES[0]
        valid, _ = Validator.validate_status(status)
        assert valid is True


# ---------------------------------------------------------------------------
# Validator.validate_role
# ---------------------------------------------------------------------------

class TestValidatorRole:
    def test_empty_role_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_role("")
        assert valid is False

    def test_invalid_role_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_role("superuser")
        assert valid is False

    def test_valid_applicant_role(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_role("applicant")
        assert valid is True

    def test_valid_executor_role(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_role("executor")
        assert valid is True


# ---------------------------------------------------------------------------
# Validator.validate_file_size
# ---------------------------------------------------------------------------

class TestValidatorFileSize:
    def test_small_file_valid(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_file_size(1024, file_type="document")
        assert valid is True

    def test_large_file_invalid(self):
        from uk_management_bot.utils.validators import Validator
        from uk_management_bot.utils.constants import MAX_DOCUMENT_SIZE
        valid, _ = Validator.validate_file_size(MAX_DOCUMENT_SIZE + 1, file_type="document")
        assert valid is False

    def test_photo_type_uses_photo_limit(self):
        from uk_management_bot.utils.validators import Validator
        from uk_management_bot.utils.constants import MAX_PHOTO_SIZE
        valid, _ = Validator.validate_file_size(MAX_PHOTO_SIZE - 1, file_type="photo")
        assert valid is True

    def test_unknown_file_type_uses_document_limit(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_file_size(1024, file_type="unknown_type")
        assert valid is True


# ---------------------------------------------------------------------------
# Validator.validate_rating
# ---------------------------------------------------------------------------

class TestValidatorRating:
    def test_rating_1_valid(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_rating(1)
        assert valid is True

    def test_rating_5_valid(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_rating(5)
        assert valid is True

    def test_rating_0_invalid(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_rating(0)
        assert valid is False

    def test_rating_6_invalid(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_rating(6)
        assert valid is False

    def test_rating_string_invalid(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_rating("5")
        assert valid is False


# ---------------------------------------------------------------------------
# Validator.validate_media_files_count
# ---------------------------------------------------------------------------

class TestValidatorMediaFilesCount:
    def test_zero_files_valid(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_media_files_count(0)
        assert valid is True

    def test_within_limit_valid(self):
        from uk_management_bot.utils.validators import Validator
        from uk_management_bot.utils.constants import MAX_MEDIA_FILES_PER_REQUEST
        valid, _ = Validator.validate_media_files_count(MAX_MEDIA_FILES_PER_REQUEST)
        assert valid is True

    def test_exceeds_limit_invalid(self):
        from uk_management_bot.utils.validators import Validator
        from uk_management_bot.utils.constants import MAX_MEDIA_FILES_PER_REQUEST
        valid, _ = Validator.validate_media_files_count(MAX_MEDIA_FILES_PER_REQUEST + 1)
        assert valid is False


# ---------------------------------------------------------------------------
# Validator.validate_media_file (method on class)
# ---------------------------------------------------------------------------

class TestValidatorMediaFile:
    def test_valid_photo(self):
        from uk_management_bot.utils.validators import Validator
        assert Validator.validate_media_file(1024, "photo") is True

    def test_valid_video(self):
        from uk_management_bot.utils.validators import Validator
        assert Validator.validate_media_file(1024, "video") is True

    def test_document_type_invalid(self):
        from uk_management_bot.utils.validators import Validator
        assert Validator.validate_media_file(1024, "document") is False

    def test_too_large_file_invalid(self):
        from uk_management_bot.utils.validators import Validator
        assert Validator.validate_media_file(21 * 1024 * 1024, "photo") is False


# ---------------------------------------------------------------------------
# Validator.sanitize_text
# ---------------------------------------------------------------------------

class TestValidatorSanitizeText:
    def test_removes_html_tags(self):
        from uk_management_bot.utils.validators import Validator
        result = Validator.sanitize_text("<b>bold text</b>")
        assert "<b>" not in result
        assert "bold text" in result

    def test_collapses_whitespace(self):
        from uk_management_bot.utils.validators import Validator
        result = Validator.sanitize_text("hello    world")
        assert result == "hello world"

    def test_strips_leading_trailing_spaces(self):
        from uk_management_bot.utils.validators import Validator
        result = Validator.sanitize_text("  hello  ")
        assert result == "hello"

    def test_empty_string(self):
        from uk_management_bot.utils.validators import Validator
        result = Validator.sanitize_text("")
        assert result == ""


# ---------------------------------------------------------------------------
# Standalone validate_description (FSM version)
# ---------------------------------------------------------------------------

class TestStandaloneValidateDescription:
    def test_short_fails(self):
        from uk_management_bot.utils.validators import validate_description
        assert validate_description("too short") is False

    def test_long_passes(self):
        from uk_management_bot.utils.validators import validate_description
        assert validate_description("This is a long enough description for FSM") is True


# ---------------------------------------------------------------------------
# Standalone validate_apartment (FSM version)
# ---------------------------------------------------------------------------

class TestStandaloneValidateApartment:
    def test_digit_passes(self):
        from uk_management_bot.utils.validators import validate_apartment
        assert validate_apartment("42") is True

    def test_letters_fail(self):
        from uk_management_bot.utils.validators import validate_apartment
        assert validate_apartment("abc") is False

    def test_empty_fails(self):
        from uk_management_bot.utils.validators import validate_apartment
        assert validate_apartment("") is False


# ---------------------------------------------------------------------------
# Standalone validate_media_file (FSM version)
# ---------------------------------------------------------------------------

class TestStandaloneValidateMediaFile:
    def test_valid_photo(self):
        from uk_management_bot.utils.validators import validate_media_file
        assert validate_media_file(1024, "photo") is True

    def test_too_large_fails(self):
        from uk_management_bot.utils.validators import validate_media_file
        assert validate_media_file(21 * 1024 * 1024, "photo") is False

    def test_invalid_type_fails(self):
        from uk_management_bot.utils.validators import validate_media_file
        assert validate_media_file(1024, "pdf") is False


# ---------------------------------------------------------------------------
# Validator.validate_category
# ---------------------------------------------------------------------------

class TestValidatorCategory:
    def test_empty_category_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_category("")
        assert valid is False

    def test_none_category_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_category(None)
        assert valid is False

    def test_invalid_category_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_category("totally_nonexistent_cat")
        assert valid is False

    def test_valid_internal_key(self):
        from uk_management_bot.utils.validators import Validator
        from uk_management_bot.keyboards.requests import CATEGORY_INTERNAL_KEYS
        valid, _ = Validator.validate_category(CATEGORY_INTERNAL_KEYS[0])
        assert valid is True


# ---------------------------------------------------------------------------
# Validator.validate_urgency
# ---------------------------------------------------------------------------

class TestValidatorUrgency:
    def test_empty_urgency_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_urgency("")
        assert valid is False

    def test_invalid_urgency_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_urgency("super_urgent")
        assert valid is False

    def test_valid_internal_key_low(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_urgency("low")
        assert valid is True

    def test_valid_internal_key_high(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_urgency("high")
        assert valid is True

    def test_legacy_russian_text_resolved(self):
        from uk_management_bot.utils.validators import Validator
        # "Срочная" should map to "high"
        valid, _ = Validator.validate_urgency("Срочная")
        assert valid is True


# ---------------------------------------------------------------------------
# Validator.validate_request_data
# ---------------------------------------------------------------------------

class TestValidatorRequestData:
    def _make_valid_data(self):
        from uk_management_bot.keyboards.requests import CATEGORY_INTERNAL_KEYS
        return {
            "category": CATEGORY_INTERNAL_KEYS[0],
            "address": "ул. Ленина 1, корпус 2",
            "description": "Описание проблемы очень подробное",
        }

    def test_valid_data_returns_true(self):
        from uk_management_bot.utils.validators import Validator
        valid, _ = Validator.validate_request_data(self._make_valid_data())
        assert valid is True

    def test_missing_required_field_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        data = self._make_valid_data()
        del data["description"]
        valid, _ = Validator.validate_request_data(data)
        assert valid is False

    def test_empty_required_field_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        data = self._make_valid_data()
        data["category"] = ""
        valid, _ = Validator.validate_request_data(data)
        assert valid is False

    def test_invalid_category_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        data = self._make_valid_data()
        data["category"] = "invalid_cat"
        valid, _ = Validator.validate_request_data(data)
        assert valid is False

    def test_short_address_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        data = self._make_valid_data()
        data["address"] = "ab"
        valid, _ = Validator.validate_request_data(data)
        assert valid is False

    def test_short_description_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        data = self._make_valid_data()
        data["description"] = "short"
        valid, _ = Validator.validate_request_data(data)
        assert valid is False

    def test_with_apartment_valid(self):
        from uk_management_bot.utils.validators import Validator
        data = self._make_valid_data()
        data["apartment"] = "42A"
        valid, _ = Validator.validate_request_data(data)
        assert valid is True

    def test_with_invalid_apartment_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        data = self._make_valid_data()
        data["apartment"] = "кв. 42"
        valid, _ = Validator.validate_request_data(data)
        assert valid is False

    def test_with_valid_urgency(self):
        from uk_management_bot.utils.validators import Validator
        data = self._make_valid_data()
        data["urgency"] = "high"
        valid, _ = Validator.validate_request_data(data)
        assert valid is True

    def test_with_invalid_urgency_returns_false(self):
        from uk_management_bot.utils.validators import Validator
        data = self._make_valid_data()
        data["urgency"] = "mega_urgent"
        valid, _ = Validator.validate_request_data(data)
        assert valid is False
