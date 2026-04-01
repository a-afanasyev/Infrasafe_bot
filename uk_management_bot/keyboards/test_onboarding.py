"""
Unit tests for keyboards/onboarding.py

Tests each keyboard builder and helper function.
get_text is mocked; uses real DocumentType enum.
"""
import pytest
from unittest.mock import patch, MagicMock
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup


GET_TEXT_PATH = "uk_management_bot.keyboards.onboarding.get_text"
LANG_HELPERS_PATH = "uk_management_bot.keyboards.onboarding.SUPPORTED_LANGUAGES"


def _mock_get_text(key: str, language: str = "ru", **kwargs) -> str:
    return key  # echo key


def _all_inline_buttons(markup: InlineKeyboardMarkup) -> list:
    return [btn for row in markup.inline_keyboard for btn in row]


def _all_reply_texts(markup: ReplyKeyboardMarkup) -> list[str]:
    return [btn.text for row in markup.keyboard for btn in row]


# ---------------------------------------------------------------------------
# get_document_type_keyboard
# ---------------------------------------------------------------------------

class TestGetDocumentTypeKeyboard:
    def test_returns_reply_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.onboarding import get_document_type_keyboard
            result = get_document_type_keyboard()
        assert isinstance(result, ReplyKeyboardMarkup)

    def test_has_six_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.onboarding import get_document_type_keyboard
            result = get_document_type_keyboard()
        assert len(_all_reply_texts(result)) == 6

    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_language_accepted(self, language):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.onboarding import get_document_type_keyboard
            result = get_document_type_keyboard(language=language)
        assert isinstance(result, ReplyKeyboardMarkup)


# ---------------------------------------------------------------------------
# get_document_confirmation_keyboard
# ---------------------------------------------------------------------------

class TestGetDocumentConfirmationKeyboard:
    def test_returns_reply_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.onboarding import get_document_confirmation_keyboard
            result = get_document_confirmation_keyboard()
        assert isinstance(result, ReplyKeyboardMarkup)

    def test_has_three_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.onboarding import get_document_confirmation_keyboard
            result = get_document_confirmation_keyboard()
        assert len(_all_reply_texts(result)) == 3


# ---------------------------------------------------------------------------
# get_onboarding_completion_keyboard
# ---------------------------------------------------------------------------

class TestGetOnboardingCompletionKeyboard:
    def test_returns_reply_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.onboarding import get_onboarding_completion_keyboard
            result = get_onboarding_completion_keyboard()
        assert isinstance(result, ReplyKeyboardMarkup)

    def test_has_two_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.onboarding import get_onboarding_completion_keyboard
            result = get_onboarding_completion_keyboard()
        assert len(_all_reply_texts(result)) == 2


# ---------------------------------------------------------------------------
# get_document_type_inline_keyboard
# ---------------------------------------------------------------------------

class TestGetDocumentTypeInlineKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.onboarding import get_document_type_inline_keyboard
            result = get_document_type_inline_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_five_buttons(self):
        """4 doc type buttons + 1 skip = 5"""
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.onboarding import get_document_type_inline_keyboard
            result = get_document_type_inline_keyboard()
        assert len(_all_inline_buttons(result)) == 5

    def test_doc_type_callbacks_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.onboarding import get_document_type_inline_keyboard
            result = get_document_type_inline_keyboard()
        callbacks = set(btn.callback_data for btn in _all_inline_buttons(result) if btn.callback_data)
        assert "doc_type_passport" in callbacks
        assert "doc_type_skip" in callbacks


# ---------------------------------------------------------------------------
# get_document_management_keyboard
# ---------------------------------------------------------------------------

class TestGetDocumentManagementKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.onboarding import get_document_management_keyboard
            result = get_document_management_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_three_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.onboarding import get_document_management_keyboard
            result = get_document_management_keyboard()
        assert len(_all_inline_buttons(result)) == 3

    def test_callbacks_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.onboarding import get_document_management_keyboard
            result = get_document_management_keyboard()
        callbacks = set(btn.callback_data for btn in _all_inline_buttons(result) if btn.callback_data)
        assert "add_document" in callbacks
        assert "complete_onboarding" in callbacks
        assert "skip_documents" in callbacks


# ---------------------------------------------------------------------------
# get_document_type_from_text
# ---------------------------------------------------------------------------

class TestGetDocumentTypeFromText:
    def test_recognizes_passport_text(self):
        from uk_management_bot.database.models.user_verification import DocumentType

        def mock_get_text(key, language="ru", **kwargs):
            if key == "onboarding.keyboards.passport" and language == "ru":
                return "Паспорт"
            return key

        with patch(GET_TEXT_PATH, side_effect=mock_get_text), \
             patch(LANG_HELPERS_PATH, ["ru"]):
            from uk_management_bot.keyboards.onboarding import get_document_type_from_text
            result = get_document_type_from_text("Паспорт", language="ru")
        assert result == DocumentType.PASSPORT

    def test_returns_none_for_unknown_text(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text), \
             patch(LANG_HELPERS_PATH, ["ru"]):
            from uk_management_bot.keyboards.onboarding import get_document_type_from_text
            result = get_document_type_from_text("unknown text", language="ru")
        assert result is None

    def test_fallback_checks_all_languages(self):
        """If not found in primary language, checks all supported languages."""
        from uk_management_bot.database.models.user_verification import DocumentType

        def mock_get_text(key, language="ru", **kwargs):
            if key == "onboarding.keyboards.passport" and language == "uz":
                return "Pasport"
            return "other"  # Returns something else for other keys/languages

        with patch(GET_TEXT_PATH, side_effect=mock_get_text), \
             patch(LANG_HELPERS_PATH, ["ru", "uz"]):
            from uk_management_bot.keyboards.onboarding import get_document_type_from_text
            result = get_document_type_from_text("Pasport", language="ru")
        assert result == DocumentType.PASSPORT


# ---------------------------------------------------------------------------
# get_document_type_name
# ---------------------------------------------------------------------------

class TestGetDocumentTypeName:
    def test_returns_string(self):
        from uk_management_bot.database.models.user_verification import DocumentType
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.onboarding import get_document_type_name
            result = get_document_type_name(DocumentType.PASSPORT)
        assert isinstance(result, str)

    def test_known_type_passport(self):
        from uk_management_bot.database.models.user_verification import DocumentType

        def mock_get_text(key, language="ru", **kwargs):
            if key == "onboarding.keyboards.doc_name_passport":
                return "Паспорт гражданина"
            return key

        with patch(GET_TEXT_PATH, side_effect=mock_get_text):
            from uk_management_bot.keyboards.onboarding import get_document_type_name
            result = get_document_type_name(DocumentType.PASSPORT)
        assert result == "Паспорт гражданина"

    def test_unknown_type_uses_other_key(self):
        """An unrecognized DocumentType falls back to 'doc_name_other' key."""
        from uk_management_bot.database.models.user_verification import DocumentType

        called_with = []

        def mock_get_text(key, language="ru", **kwargs):
            called_with.append(key)
            return key

        with patch(GET_TEXT_PATH, side_effect=mock_get_text):
            from uk_management_bot.keyboards.onboarding import get_document_type_name
            result = get_document_type_name(DocumentType.OTHER)
        assert "onboarding.keyboards.doc_name_other" in called_with
