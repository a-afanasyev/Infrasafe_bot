"""
Unit tests for keyboards/admin.py

Tests that each keyboard builder function:
- Returns the correct markup type (ReplyKeyboardMarkup or InlineKeyboardMarkup)
- Has the expected number of buttons
- Contains buttons with non-empty text and callback_data (where applicable)
- Conditional logic (has_media, is_returned, page navigation) works correctly

No DB, no network. get_text and RequestCallbackHelper are mocked.
"""
import pytest
from unittest.mock import MagicMock, patch
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup


# ---------------------------------------------------------------------------
# Patch targets
# ---------------------------------------------------------------------------

GET_TEXT_PATH = "uk_management_bot.keyboards.admin.get_text"
CALLBACK_HELPER_PATH = "uk_management_bot.keyboards.admin.RequestCallbackHelper"


def _mock_get_text(key: str, language: str = "ru", **kwargs) -> str:
    return key  # echo key


def _mock_create_callback(prefix: str, request_number: str) -> str:
    return f"{prefix}{request_number}"


def _all_reply_texts(markup: ReplyKeyboardMarkup) -> list[str]:
    return [btn.text for row in markup.keyboard for btn in row]


def _all_inline_buttons(markup: InlineKeyboardMarkup) -> list:
    return [btn for row in markup.inline_keyboard for btn in row]


def _all_inline_texts(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.text for btn in _all_inline_buttons(markup)]


def _all_inline_callbacks(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.callback_data for btn in _all_inline_buttons(markup) if btn.callback_data]


# ---------------------------------------------------------------------------
# get_manager_main_keyboard
# ---------------------------------------------------------------------------

class TestGetManagerMainKeyboard:
    def test_returns_reply_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_manager_main_keyboard
            result = get_manager_main_keyboard()
        assert isinstance(result, ReplyKeyboardMarkup)

    def test_resize_keyboard_true(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_manager_main_keyboard
            result = get_manager_main_keyboard()
        assert result.resize_keyboard is True

    def test_has_eleven_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_manager_main_keyboard
            result = get_manager_main_keyboard()
        assert len(_all_reply_texts(result)) == 11

    def test_all_buttons_have_non_empty_text(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_manager_main_keyboard
            result = get_manager_main_keyboard()
        for text in _all_reply_texts(result):
            assert len(text) > 0

    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_language_parameter_accepted(self, language):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_manager_main_keyboard
            result = get_manager_main_keyboard(language=language)
        assert isinstance(result, ReplyKeyboardMarkup)


# ---------------------------------------------------------------------------
# get_completed_requests_submenu
# ---------------------------------------------------------------------------

class TestGetCompletedRequestsSubmenu:
    def test_returns_reply_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_completed_requests_submenu
            result = get_completed_requests_submenu()
        assert isinstance(result, ReplyKeyboardMarkup)

    def test_has_four_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_completed_requests_submenu
            result = get_completed_requests_submenu()
        assert len(_all_reply_texts(result)) == 4


# ---------------------------------------------------------------------------
# get_manager_requests_inline
# ---------------------------------------------------------------------------

class TestGetManagerRequestsInline:
    def test_returns_inline_keyboard_markup(self):
        from uk_management_bot.keyboards.admin import get_manager_requests_inline
        result = get_manager_requests_inline(page=1, total_pages=3)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_first_page_has_no_prev_button(self):
        from uk_management_bot.keyboards.admin import get_manager_requests_inline
        result = get_manager_requests_inline(page=1, total_pages=3)
        callbacks = _all_inline_callbacks(result)
        assert not any(c.startswith("mreq_page_0") for c in callbacks)

    def test_last_page_has_no_next_button(self):
        from uk_management_bot.keyboards.admin import get_manager_requests_inline
        result = get_manager_requests_inline(page=3, total_pages=3)
        callbacks = _all_inline_callbacks(result)
        assert not any(c == "mreq_page_4" for c in callbacks)

    def test_middle_page_has_both_nav_buttons(self):
        from uk_management_bot.keyboards.admin import get_manager_requests_inline
        result = get_manager_requests_inline(page=2, total_pages=5)
        callbacks = _all_inline_callbacks(result)
        assert "mreq_page_1" in callbacks
        assert "mreq_page_3" in callbacks

    def test_shows_page_indicator(self):
        from uk_management_bot.keyboards.admin import get_manager_requests_inline
        result = get_manager_requests_inline(page=2, total_pages=5)
        texts = _all_inline_texts(result)
        assert any("2/5" in t for t in texts)


# ---------------------------------------------------------------------------
# get_invite_role_keyboard
# ---------------------------------------------------------------------------

class TestGetInviteRoleKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_invite_role_keyboard
            result = get_invite_role_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_five_buttons(self):
        # applicant/executor/manager/inspector + cancel (inspector добавлен —
        # план «Обходчик»).
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_invite_role_keyboard
            result = get_invite_role_keyboard()
        assert len(_all_inline_buttons(result)) == 5

    def test_role_callbacks(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_invite_role_keyboard
            result = get_invite_role_keyboard()
        callbacks = set(_all_inline_callbacks(result))
        assert "invite_role_applicant" in callbacks
        assert "invite_role_executor" in callbacks
        assert "invite_role_manager" in callbacks
        assert "invite_role_inspector" in callbacks
        assert "invite_cancel" in callbacks


# ---------------------------------------------------------------------------
# get_invite_specialization_keyboard
# ---------------------------------------------------------------------------

class TestGetInviteSpecializationKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_invite_specialization_keyboard
            result = get_invite_specialization_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_ten_buttons(self):
        """9 specializations + cancel = 10"""
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_invite_specialization_keyboard
            result = get_invite_specialization_keyboard()
        assert len(_all_inline_buttons(result)) == 10


# ---------------------------------------------------------------------------
# get_invite_expiry_keyboard
# ---------------------------------------------------------------------------

class TestGetInviteExpiryKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_invite_expiry_keyboard
            result = get_invite_expiry_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_four_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_invite_expiry_keyboard
            result = get_invite_expiry_keyboard()
        assert len(_all_inline_buttons(result)) == 4

    def test_expiry_callbacks(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_invite_expiry_keyboard
            result = get_invite_expiry_keyboard()
        callbacks = set(_all_inline_callbacks(result))
        assert "invite_expiry_1h" in callbacks
        assert "invite_expiry_24h" in callbacks
        assert "invite_expiry_7d" in callbacks


# ---------------------------------------------------------------------------
# get_invite_confirmation_keyboard
# ---------------------------------------------------------------------------

class TestGetInviteConfirmationKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_invite_confirmation_keyboard
            result = get_invite_confirmation_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_two_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_invite_confirmation_keyboard
            result = get_invite_confirmation_keyboard()
        assert len(_all_inline_buttons(result)) == 2

    def test_confirm_and_cancel_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_invite_confirmation_keyboard
            result = get_invite_confirmation_keyboard()
        callbacks = set(_all_inline_callbacks(result))
        assert "invite_confirm" in callbacks
        assert "invite_cancel" in callbacks


# ---------------------------------------------------------------------------
# get_user_approval_keyboard
# ---------------------------------------------------------------------------

class TestGetUserApprovalKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_user_approval_keyboard
            result = get_user_approval_keyboard(user_id=42)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_three_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_user_approval_keyboard
            result = get_user_approval_keyboard(user_id=42)
        assert len(_all_inline_buttons(result)) == 3

    def test_callbacks_contain_user_id(self):
        user_id = 777
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_user_approval_keyboard
            result = get_user_approval_keyboard(user_id=user_id)
        callbacks = set(_all_inline_callbacks(result))
        assert f"approve_user_{user_id}" in callbacks
        assert f"reject_user_{user_id}" in callbacks
        assert f"view_user_{user_id}" in callbacks


# ---------------------------------------------------------------------------
# get_manager_request_actions_keyboard
# ---------------------------------------------------------------------------

class TestGetManagerRequestActionsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text), \
             patch(CALLBACK_HELPER_PATH + ".create_callback_data_with_request_number",
                   side_effect=_mock_create_callback):
            from uk_management_bot.keyboards.admin import get_manager_request_actions_keyboard
            result = get_manager_request_actions_keyboard("250101-020")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_without_media_has_six_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text), \
             patch(CALLBACK_HELPER_PATH + ".create_callback_data_with_request_number",
                   side_effect=_mock_create_callback):
            from uk_management_bot.keyboards.admin import get_manager_request_actions_keyboard
            result = get_manager_request_actions_keyboard("250101-020", has_media=False)
        assert len(_all_inline_buttons(result)) == 6

    def test_with_media_has_seven_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text), \
             patch(CALLBACK_HELPER_PATH + ".create_callback_data_with_request_number",
                   side_effect=_mock_create_callback):
            from uk_management_bot.keyboards.admin import get_manager_request_actions_keyboard
            result = get_manager_request_actions_keyboard("250101-021", has_media=True)
        assert len(_all_inline_buttons(result)) == 7


# ---------------------------------------------------------------------------
# get_manager_completed_request_actions_keyboard
# ---------------------------------------------------------------------------

class TestGetManagerCompletedRequestActionsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text), \
             patch(CALLBACK_HELPER_PATH + ".create_callback_data_with_request_number",
                   side_effect=_mock_create_callback):
            from uk_management_bot.keyboards.admin import get_manager_completed_request_actions_keyboard
            result = get_manager_completed_request_actions_keyboard("250101-030")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_not_returned_has_confirm_completion_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text), \
             patch(CALLBACK_HELPER_PATH + ".create_callback_data_with_request_number",
                   side_effect=_mock_create_callback):
            from uk_management_bot.keyboards.admin import get_manager_completed_request_actions_keyboard
            result = get_manager_completed_request_actions_keyboard("250101-030", is_returned=False)
        callbacks = _all_inline_callbacks(result)
        assert any("confirm_completed_" in c for c in callbacks)

    def test_returned_has_reconfirm_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text), \
             patch(CALLBACK_HELPER_PATH + ".create_callback_data_with_request_number",
                   side_effect=_mock_create_callback):
            from uk_management_bot.keyboards.admin import get_manager_completed_request_actions_keyboard
            result = get_manager_completed_request_actions_keyboard("250101-031", is_returned=True)
        callbacks = _all_inline_callbacks(result)
        assert any("reconfirm_completed_" in c for c in callbacks)

    def test_both_variants_have_return_to_work_button(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text), \
             patch(CALLBACK_HELPER_PATH + ".create_callback_data_with_request_number",
                   side_effect=_mock_create_callback):
            from uk_management_bot.keyboards.admin import get_manager_completed_request_actions_keyboard
            for is_returned in (True, False):
                result = get_manager_completed_request_actions_keyboard("250101-032", is_returned=is_returned)
                callbacks = _all_inline_callbacks(result)
                assert any("return_to_work_" in c for c in callbacks)


# ---------------------------------------------------------------------------
# get_rating_keyboard
# ---------------------------------------------------------------------------

class TestGetRatingKeyboard:
    def test_returns_inline_keyboard_markup(self):
        from uk_management_bot.keyboards.admin import get_rating_keyboard
        result = get_rating_keyboard("250101-040")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_five_buttons(self):
        from uk_management_bot.keyboards.admin import get_rating_keyboard
        result = get_rating_keyboard("250101-040")
        assert len(_all_inline_buttons(result)) == 5

    def test_callback_data_contains_request_number_and_rating(self):
        rn = "250101-041"
        from uk_management_bot.keyboards.admin import get_rating_keyboard
        result = get_rating_keyboard(rn)
        for i, btn in enumerate(_all_inline_buttons(result), start=1):
            assert rn in btn.callback_data
            assert str(i) in btn.callback_data


# ---------------------------------------------------------------------------
# get_applicant_completed_request_actions_keyboard
# ---------------------------------------------------------------------------

class TestGetApplicantCompletedRequestActionsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_applicant_completed_request_actions_keyboard
            result = get_applicant_completed_request_actions_keyboard("250101-050")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_three_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_applicant_completed_request_actions_keyboard
            result = get_applicant_completed_request_actions_keyboard("250101-050")
        assert len(_all_inline_buttons(result)) == 3

    def test_accept_and_return_callbacks(self):
        rn = "250101-051"
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_applicant_completed_request_actions_keyboard
            result = get_applicant_completed_request_actions_keyboard(rn)
        callbacks = set(_all_inline_callbacks(result))
        assert f"accept_request_{rn}" in callbacks
        assert f"return_request_{rn}" in callbacks
        assert "back_to_pending_acceptance" in callbacks


# ---------------------------------------------------------------------------
# get_skip_media_keyboard
# ---------------------------------------------------------------------------

class TestGetSkipMediaKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_skip_media_keyboard
            result = get_skip_media_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_one_button(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_skip_media_keyboard
            result = get_skip_media_keyboard()
        assert len(_all_inline_buttons(result)) == 1

    def test_skip_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_skip_media_keyboard
            result = get_skip_media_keyboard()
        assert _all_inline_callbacks(result)[0] == "skip_return_media"


# ---------------------------------------------------------------------------
# get_assignment_type_keyboard
# ---------------------------------------------------------------------------

class TestGetAssignmentTypeKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_assignment_type_keyboard
            result = get_assignment_type_keyboard("250101-060")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_two_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_assignment_type_keyboard
            result = get_assignment_type_keyboard("250101-060")
        assert len(_all_inline_buttons(result)) == 2

    def test_callbacks_contain_request_number(self):
        rn = "250101-061"
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_assignment_type_keyboard
            result = get_assignment_type_keyboard(rn)
        callbacks = _all_inline_callbacks(result)
        assert any(rn in c for c in callbacks)


# ---------------------------------------------------------------------------
# get_executors_by_category_keyboard
# ---------------------------------------------------------------------------

class TestGetExecutorsByCategoryKeyboard:
    def _make_executors(self, count: int) -> list:
        executors = []
        for i in range(count):
            e = MagicMock()
            e.first_name = f"Name{i}"
            e.last_name = f"Last{i}"
            e.username = None
            e.id = i + 1
            e.on_shift = True
            executors.append(e)
        return executors

    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_executors_by_category_keyboard
            result = get_executors_by_category_keyboard("250101-070", "plumber", [])
        assert isinstance(result, InlineKeyboardMarkup)

    def test_empty_executors_shows_no_available_button(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_executors_by_category_keyboard
            result = get_executors_by_category_keyboard("250101-070", "plumber", [])
        callbacks = _all_inline_callbacks(result)
        assert "no_executors" in callbacks

    def test_with_executors_shows_each_as_button(self):
        executors = self._make_executors(3)
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_executors_by_category_keyboard
            result = get_executors_by_category_keyboard("250101-071", "electrician", executors)
        # 3 executor buttons + 1 back button
        assert len(_all_inline_buttons(result)) == 4

    def test_executor_callbacks_contain_request_number_and_executor_id(self):
        executors = self._make_executors(2)
        rn = "250101-072"
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_executors_by_category_keyboard
            result = get_executors_by_category_keyboard(rn, "plumber", executors)
        exec_callbacks = [
            c for c in _all_inline_callbacks(result)
            if c.startswith("assign_executor_")
        ]
        assert len(exec_callbacks) == 2
        for c in exec_callbacks:
            assert rn in c


# ---------------------------------------------------------------------------
# get_unaccepted_request_actions_keyboard
# ---------------------------------------------------------------------------

class TestGetUnacceptedRequestActionsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_unaccepted_request_actions_keyboard
            result = get_unaccepted_request_actions_keyboard("250101-080")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_three_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_unaccepted_request_actions_keyboard
            result = get_unaccepted_request_actions_keyboard("250101-080")
        assert len(_all_inline_buttons(result)) == 3

    def test_remind_and_accept_callbacks(self):
        rn = "250101-081"
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.admin import get_unaccepted_request_actions_keyboard
            result = get_unaccepted_request_actions_keyboard(rn)
        callbacks = set(_all_inline_callbacks(result))
        assert f"unaccepted_remind_{rn}" in callbacks
        assert f"unaccepted_accept_{rn}" in callbacks
        assert "unaccepted_back_to_list" in callbacks


# ---------------------------------------------------------------------------
# get_manager_request_list_kb  (list + pagination)
# ---------------------------------------------------------------------------

class TestGetManagerRequestListKb:
    def _make_request(self, n: int) -> dict:
        return {
            "request_number": f"250101-{n:03d}",
            "category": "Сантехника",
            "address": "ул. Пушкина, д. 1",
            "status": "Новая",
        }

    def test_returns_inline_keyboard_markup(self):
        with patch(CALLBACK_HELPER_PATH + ".create_callback_data_with_request_number",
                   side_effect=_mock_create_callback):
            from uk_management_bot.keyboards.admin import get_manager_request_list_kb
            result = get_manager_request_list_kb(
                requests=[self._make_request(1)],
                page=1,
                total_pages=1,
            )
        assert isinstance(result, InlineKeyboardMarkup)

    def test_each_request_is_a_button(self):
        reqs = [self._make_request(i) for i in range(5)]
        with patch(CALLBACK_HELPER_PATH + ".create_callback_data_with_request_number",
                   side_effect=_mock_create_callback):
            from uk_management_bot.keyboards.admin import get_manager_request_list_kb
            result = get_manager_request_list_kb(requests=reqs, page=1, total_pages=1)
        # 5 request buttons + 1 page indicator (single page = no nav)
        btns = _all_inline_buttons(result)
        assert len(btns) >= 5

    def test_pagination_prev_not_shown_on_first_page(self):
        with patch(CALLBACK_HELPER_PATH + ".create_callback_data_with_request_number",
                   side_effect=_mock_create_callback):
            from uk_management_bot.keyboards.admin import get_manager_request_list_kb
            result = get_manager_request_list_kb(requests=[], page=1, total_pages=3)
        callbacks = _all_inline_callbacks(result)
        assert "mreq_page_0" not in callbacks

    def test_pagination_next_shown_when_not_last_page(self):
        with patch(CALLBACK_HELPER_PATH + ".create_callback_data_with_request_number",
                   side_effect=_mock_create_callback):
            from uk_management_bot.keyboards.admin import get_manager_request_list_kb
            result = get_manager_request_list_kb(requests=[], page=1, total_pages=3)
        callbacks = _all_inline_callbacks(result)
        assert "mreq_page_2" in callbacks
