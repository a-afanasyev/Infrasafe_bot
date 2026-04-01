"""
Unit tests for keyboards/user_verification.py

Mocks get_text and DocumentType imports. Tests return types and
callback-data conventions for all keyboard builder functions.
"""
import pytest
from unittest.mock import patch, MagicMock

from aiogram.types import InlineKeyboardMarkup

GET_TEXT_PATH = "uk_management_bot.keyboards.user_verification.get_text"


def _echo(key: str, language: str = "ru", **kwargs) -> str:
    return key


def _flat_texts(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.text for row in markup.inline_keyboard for btn in row]


def _flat_cbs(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.callback_data for row in markup.inline_keyboard for btn in row]


def _make_user(uid: int = 1, first_name: str = "Test",
               last_name: str = "User", username: str = "tuser",
               verification_status: str = "pending") -> MagicMock:
    u = MagicMock()
    u.id = uid
    u.first_name = first_name
    u.last_name = last_name
    u.username = username
    u.verification_status = verification_status
    return u


# ---------------------------------------------------------------------------
# get_verification_main_keyboard
# ---------------------------------------------------------------------------

class TestGetVerificationMainKeyboard:
    def test_returns_inline_keyboard_markup(self):
        stats = {"pending": 2, "verified": 5, "rejected": 1, "pending_documents": 3}
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_verification_main_keyboard
            result = get_verification_main_keyboard(stats)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_six_buttons(self):
        stats = {"pending": 0, "verified": 0, "rejected": 0, "pending_documents": 0}
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_verification_main_keyboard
            result = get_verification_main_keyboard(stats)
        # stats + pending + verified + rejected + pending_docs + back = 6
        assert len(_flat_texts(result)) == 6

    def test_stat_counts_embedded(self):
        stats = {"pending": 7, "verified": 0, "rejected": 0, "pending_documents": 0}
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_verification_main_keyboard
            result = get_verification_main_keyboard(stats)
        texts = _flat_texts(result)
        assert any("7" in t for t in texts)

    def test_back_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_verification_main_keyboard
            result = get_verification_main_keyboard({})
        assert "user_management_panel" in _flat_cbs(result)


# ---------------------------------------------------------------------------
# get_user_verification_keyboard
# ---------------------------------------------------------------------------

class TestGetUserVerificationKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_user_verification_keyboard
            result = get_user_verification_keyboard(user_id=1)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_six_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_user_verification_keyboard
            result = get_user_verification_keyboard(user_id=1)
        assert len(_flat_texts(result)) == 6

    def test_approve_and_reject_callbacks(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_user_verification_keyboard
            result = get_user_verification_keyboard(user_id=5)
        cbs = _flat_cbs(result)
        assert "verify_approve_5" in cbs
        assert "verify_reject_5" in cbs

    def test_view_documents_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_user_verification_keyboard
            result = get_user_verification_keyboard(user_id=3)
        cbs = _flat_cbs(result)
        assert "view_user_documents_3" in cbs

    def test_back_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_user_verification_keyboard
            result = get_user_verification_keyboard(user_id=1)
        assert "user_verification_panel" in _flat_cbs(result)


# ---------------------------------------------------------------------------
# get_verification_request_keyboard
# ---------------------------------------------------------------------------

class TestGetVerificationRequestKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_verification_request_keyboard
            result = get_verification_request_keyboard(user_id=1)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_seven_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_verification_request_keyboard
            result = get_verification_request_keyboard(user_id=1)
        # 6 info types + back = 7
        assert len(_flat_texts(result)) == 7

    def test_callbacks_contain_user_id(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_verification_request_keyboard
            result = get_verification_request_keyboard(user_id=9)
        cbs = _flat_cbs(result)
        assert any("9" in cb for cb in cbs)

    def test_back_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_verification_request_keyboard
            result = get_verification_request_keyboard(user_id=1)
        cbs = _flat_cbs(result)
        assert any("verification_user_1" in cb for cb in cbs)


# ---------------------------------------------------------------------------
# get_document_verification_keyboard
# ---------------------------------------------------------------------------

class TestGetDocumentVerificationKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_document_verification_keyboard
            result = get_document_verification_keyboard(document_id=10)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_four_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_document_verification_keyboard
            result = get_document_verification_keyboard(document_id=10)
        assert len(_flat_texts(result)) == 4

    def test_approve_and_reject_callbacks(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_document_verification_keyboard
            result = get_document_verification_keyboard(document_id=10)
        cbs = _flat_cbs(result)
        assert "document_approve_10" in cbs
        assert "document_reject_10" in cbs

    def test_download_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_document_verification_keyboard
            result = get_document_verification_keyboard(document_id=10)
        cbs = _flat_cbs(result)
        assert "download_document_10" in cbs


# ---------------------------------------------------------------------------
# get_document_management_keyboard
# ---------------------------------------------------------------------------

class TestGetDocumentManagementKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_document_management_keyboard
            result = get_document_management_keyboard(user_id=1)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_two_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_document_management_keyboard
            result = get_document_management_keyboard(user_id=1)
        assert len(_flat_texts(result)) == 2

    def test_request_documents_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_document_management_keyboard
            result = get_document_management_keyboard(user_id=4)
        cbs = _flat_cbs(result)
        assert "request_documents_4" in cbs


# ---------------------------------------------------------------------------
# get_access_rights_keyboard
# ---------------------------------------------------------------------------

class TestGetAccessRightsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_access_rights_keyboard
            result = get_access_rights_keyboard(user_id=1)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_five_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_access_rights_keyboard
            result = get_access_rights_keyboard(user_id=1)
        # grant_apartment + grant_house + grant_yard + revoke + back = 5
        assert len(_flat_texts(result)) == 5

    def test_grant_and_revoke_callbacks(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_access_rights_keyboard
            result = get_access_rights_keyboard(user_id=6)
        cbs = _flat_cbs(result)
        assert any("grant_access_6" in cb for cb in cbs)
        assert "revoke_rights_6" in cbs


# ---------------------------------------------------------------------------
# get_verification_list_keyboard
# ---------------------------------------------------------------------------

class TestGetVerificationListKeyboard:
    def _data(self, users=None, current_page=1, total_pages=1):
        return {
            "users": users or [],
            "current_page": current_page,
            "total_pages": total_pages,
        }

    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_verification_list_keyboard
            result = get_verification_list_keyboard(self._data(), "pending")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_empty_list_has_no_users_button(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_verification_list_keyboard
            result = get_verification_list_keyboard(self._data(), "pending")
        cbs = _flat_cbs(result)
        assert "no_action" in cbs

    def test_user_button_callback(self):
        user = _make_user(uid=8)
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_verification_list_keyboard
            result = get_verification_list_keyboard(self._data(users=[user]), "verified")
        cbs = _flat_cbs(result)
        assert "verification_user_8" in cbs

    def test_next_page_button_when_more_pages(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_verification_list_keyboard
            result = get_verification_list_keyboard(
                self._data(current_page=1, total_pages=3), "pending"
            )
        cbs = _flat_cbs(result)
        assert any("pending_2" in cb for cb in cbs)

    def test_back_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_verification_list_keyboard
            result = get_verification_list_keyboard(self._data(), "pending")
        assert "user_verification_panel" in _flat_cbs(result)


# ---------------------------------------------------------------------------
# get_cancel_keyboard (user_verification module)
# ---------------------------------------------------------------------------

class TestGetCancelKeyboardVerification:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_cancel_keyboard
            result = get_cancel_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_one_button(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_cancel_keyboard
            result = get_cancel_keyboard()
        assert len(_flat_texts(result)) == 1

    def test_cancel_action_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_verification import get_cancel_keyboard
            result = get_cancel_keyboard()
        assert "cancel_action" in _flat_cbs(result)
