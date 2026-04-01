"""
Unit tests for keyboards/address_management.py

Tests each keyboard builder function:
- Returns correct markup type
- Has correct button count / structure
- Conditional logic (pagination, building_id) works correctly

No DB, no network — get_text is mocked, ORM objects replaced with MagicMock.
"""
import pytest
from unittest.mock import MagicMock, patch
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup


GET_TEXT_PATH = "uk_management_bot.keyboards.address_management.get_text"


def _mock_get_text(key: str, language: str = "ru", **kwargs) -> str:
    text = key
    for k, v in kwargs.items():
        text = text.replace(f"{{{k}}}", str(v))
    return text


def _all_inline_buttons(markup: InlineKeyboardMarkup) -> list:
    return [btn for row in markup.inline_keyboard for btn in row]


def _all_callbacks(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.callback_data for btn in _all_inline_buttons(markup) if btn.callback_data]


def _make_yard(yard_id: int, name: str = "Двор 1", is_active: bool = True) -> MagicMock:
    y = MagicMock()
    y.id = yard_id
    y.name = name
    y.is_active = is_active
    del y.buildings_count  # hasattr returns False unless set
    return y


def _make_building(bid: int, address: str = "ул. Пушкина, 1", is_active: bool = True) -> MagicMock:
    b = MagicMock()
    b.id = bid
    b.address = address
    b.is_active = is_active
    del b.apartments_count
    return b


def _make_apartment(aid: int, num: str = "42", is_active: bool = True) -> MagicMock:
    a = MagicMock()
    a.id = aid
    a.apartment_number = num
    a.is_active = is_active
    del a.residents_count
    del a.full_address
    return a


# ---------------------------------------------------------------------------
# get_address_management_menu
# ---------------------------------------------------------------------------

class TestGetAddressManagementMenu:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_address_management_menu
            result = get_address_management_menu()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_six_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_address_management_menu
            result = get_address_management_menu()
        assert len(_all_inline_buttons(result)) == 6

    def test_back_callback_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_address_management_menu
            result = get_address_management_menu()
        assert "admin_menu" in _all_callbacks(result)

    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_language_accepted(self, language):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_address_management_menu
            result = get_address_management_menu(language=language)
        assert isinstance(result, InlineKeyboardMarkup)


# ---------------------------------------------------------------------------
# get_yards_menu
# ---------------------------------------------------------------------------

class TestGetYardsMenu:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_yards_menu
            result = get_yards_menu()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_three_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_yards_menu
            result = get_yards_menu()
        assert len(_all_inline_buttons(result)) == 3


# ---------------------------------------------------------------------------
# get_yards_list_keyboard
# ---------------------------------------------------------------------------

class TestGetYardsListKeyboard:
    def test_empty_list_has_add_and_back(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_yards_list_keyboard
            result = get_yards_list_keyboard(yards=[])
        callbacks = _all_callbacks(result)
        assert "addr_yard_create" in callbacks
        assert "addr_menu" in callbacks

    def test_yards_appear_as_buttons(self):
        yards = [_make_yard(i) for i in range(3)]
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_yards_list_keyboard
            result = get_yards_list_keyboard(yards=yards)
        yard_callbacks = [c for c in _all_callbacks(result) if c.startswith("addr_yard_view:")]
        assert len(yard_callbacks) == 3

    def test_first_page_no_back_pagination(self):
        yards = [_make_yard(i) for i in range(3)]
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_yards_list_keyboard
            result = get_yards_list_keyboard(yards=yards, page=0, page_size=10)
        callbacks = _all_callbacks(result)
        assert not any("addr_yards_page:0" in c for c in callbacks)

    def test_pagination_forward_appears_when_more_pages(self):
        yards = [_make_yard(i) for i in range(15)]
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_yards_list_keyboard
            result = get_yards_list_keyboard(yards=yards, page=0, page_size=10)
        callbacks = _all_callbacks(result)
        assert any("addr_yards_page:1" in c for c in callbacks)


# ---------------------------------------------------------------------------
# get_yard_details_keyboard
# ---------------------------------------------------------------------------

class TestGetYardDetailsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_yard_details_keyboard
            result = get_yard_details_keyboard(yard_id=5)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_four_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_yard_details_keyboard
            result = get_yard_details_keyboard(yard_id=5)
        assert len(_all_inline_buttons(result)) == 4

    def test_callbacks_contain_yard_id(self):
        yard_id = 42
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_yard_details_keyboard
            result = get_yard_details_keyboard(yard_id=yard_id)
        id_cbs = [c for c in _all_callbacks(result) if str(yard_id) in c]
        assert len(id_cbs) > 0


# ---------------------------------------------------------------------------
# get_buildings_list_keyboard
# ---------------------------------------------------------------------------

class TestGetBuildingsListKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_buildings_list_keyboard
            result = get_buildings_list_keyboard(buildings=[])
        assert isinstance(result, InlineKeyboardMarkup)

    def test_buildings_appear_as_buttons(self):
        buildings = [_make_building(i) for i in range(3)]
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_buildings_list_keyboard
            result = get_buildings_list_keyboard(buildings=buildings)
        building_cbs = [c for c in _all_callbacks(result) if c.startswith("addr_building_view:")]
        assert len(building_cbs) == 3

    def test_with_yard_id_back_button_goes_to_yard(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_buildings_list_keyboard
            result = get_buildings_list_keyboard(buildings=[], yard_id=7)
        callbacks = _all_callbacks(result)
        assert any("addr_yard_view:7" in c for c in callbacks)

    def test_without_yard_id_back_goes_to_menu(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_buildings_list_keyboard
            result = get_buildings_list_keyboard(buildings=[], yard_id=None)
        assert "addr_menu" in _all_callbacks(result)

    def test_long_address_truncated(self):
        """Building address > 40 chars should be truncated in button text."""
        long_addr = "A" * 60
        buildings = [_make_building(1, address=long_addr)]
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_buildings_list_keyboard
            result = get_buildings_list_keyboard(buildings=buildings)
        texts = [btn.text for btn in _all_inline_buttons(result)]
        building_btn = next(t for t in texts if "✅" in t or "❌" in t)
        # Should contain "..." since address was truncated
        assert "..." in building_btn


# ---------------------------------------------------------------------------
# get_building_details_keyboard
# ---------------------------------------------------------------------------

class TestGetBuildingDetailsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_building_details_keyboard
            result = get_building_details_keyboard(building_id=3)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_five_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_building_details_keyboard
            result = get_building_details_keyboard(building_id=3)
        assert len(_all_inline_buttons(result)) == 5


# ---------------------------------------------------------------------------
# get_apartments_list_keyboard
# ---------------------------------------------------------------------------

class TestGetApartmentsListKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_apartments_list_keyboard
            result = get_apartments_list_keyboard(apartments=[])
        assert isinstance(result, InlineKeyboardMarkup)

    def test_apartments_appear_as_buttons(self):
        apartments = [_make_apartment(i) for i in range(2)]
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_apartments_list_keyboard
            result = get_apartments_list_keyboard(apartments=apartments)
        apt_cbs = [c for c in _all_callbacks(result) if c.startswith("addr_apartment_view:")]
        assert len(apt_cbs) == 2

    def test_with_building_id_back_goes_to_building(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_apartments_list_keyboard
            result = get_apartments_list_keyboard(apartments=[], building_id=10)
        assert any("addr_building_view:10" in c for c in _all_callbacks(result))

    def test_apartment_with_full_address_attribute(self):
        apt = _make_apartment(99)
        apt.full_address = "ул. Пушкина, д.1, кв.99"
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_apartments_list_keyboard
            result = get_apartments_list_keyboard(apartments=[apt])
        assert isinstance(result, InlineKeyboardMarkup)


# ---------------------------------------------------------------------------
# get_apartment_details_keyboard
# ---------------------------------------------------------------------------

class TestGetApartmentDetailsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_apartment_details_keyboard
            result = get_apartment_details_keyboard(apartment_id=7)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_four_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_apartment_details_keyboard
            result = get_apartment_details_keyboard(apartment_id=7)
        assert len(_all_inline_buttons(result)) == 4


# ---------------------------------------------------------------------------
# get_confirmation_keyboard
# ---------------------------------------------------------------------------

class TestGetConfirmationKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_confirmation_keyboard
            result = get_confirmation_keyboard("confirm_cb", "cancel_cb")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_two_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_confirmation_keyboard
            result = get_confirmation_keyboard("yes_cb", "no_cb")
        assert len(_all_inline_buttons(result)) == 2

    def test_custom_callbacks_used(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_confirmation_keyboard
            result = get_confirmation_keyboard("my_confirm", "my_cancel")
        callbacks = set(_all_callbacks(result))
        assert "my_confirm" in callbacks
        assert "my_cancel" in callbacks


# ---------------------------------------------------------------------------
# get_skip_or_cancel_keyboard
# ---------------------------------------------------------------------------

class TestGetSkipOrCancelKeyboard:
    def test_returns_reply_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_skip_or_cancel_keyboard
            result = get_skip_or_cancel_keyboard()
        assert isinstance(result, ReplyKeyboardMarkup)

    def test_has_two_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_skip_or_cancel_keyboard
            result = get_skip_or_cancel_keyboard()
        texts = [btn.text for row in result.keyboard for btn in row]
        assert len(texts) == 2


# ---------------------------------------------------------------------------
# get_cancel_keyboard_inline
# ---------------------------------------------------------------------------

class TestGetCancelKeyboardInline:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_cancel_keyboard_inline
            result = get_cancel_keyboard_inline()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_one_button_with_cancel_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_cancel_keyboard_inline
            result = get_cancel_keyboard_inline()
        assert _all_callbacks(result) == ["cancel_action"]


# ---------------------------------------------------------------------------
# get_moderation_menu / get_moderation_request_details_keyboard
# ---------------------------------------------------------------------------

class TestGetModerationMenu:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_moderation_menu
            result = get_moderation_menu()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_two_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_moderation_menu
            result = get_moderation_menu()
        assert len(_all_inline_buttons(result)) == 2


class TestGetModerationRequestDetailsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_moderation_request_details_keyboard
            result = get_moderation_request_details_keyboard(user_apartment_id=11)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_four_buttons(self):
        """approve + reject in one row, user_profile, back_to_list = 4 total"""
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_moderation_request_details_keyboard
            result = get_moderation_request_details_keyboard(user_apartment_id=11)
        assert len(_all_inline_buttons(result)) == 4

    def test_approve_and_reject_callbacks(self):
        ua_id = 55
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_moderation_request_details_keyboard
            result = get_moderation_request_details_keyboard(user_apartment_id=ua_id)
        callbacks = set(_all_callbacks(result))
        assert f"addr_moderation_approve:{ua_id}" in callbacks
        assert f"addr_moderation_reject:{ua_id}" in callbacks


# ---------------------------------------------------------------------------
# get_user_apartment_selection_keyboard
# ---------------------------------------------------------------------------

class TestGetUserApartmentSelectionKeyboard:
    def test_yard_type(self):
        yard = MagicMock()
        yard.id = 1
        yard.name = "Двор А"
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_user_apartment_selection_keyboard
            result = get_user_apartment_selection_keyboard([yard], item_type="yard", callback_prefix="sel_yard")
        assert isinstance(result, InlineKeyboardMarkup)
        yard_cbs = [c for c in _all_callbacks(result) if "sel_yard:1" == c]
        assert len(yard_cbs) == 1

    def test_building_type(self):
        building = MagicMock()
        building.id = 2
        building.address = "ул. Ленина, 5"
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_user_apartment_selection_keyboard
            result = get_user_apartment_selection_keyboard([building], item_type="building", callback_prefix="sel_bld")
        assert "sel_bld:2" in _all_callbacks(result)

    def test_apartment_type_with_floor_and_entrance(self):
        apt = MagicMock()
        apt.id = 3
        apt.apartment_number = "10"
        apt.floor = 5
        apt.entrance = 2
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_user_apartment_selection_keyboard
            result = get_user_apartment_selection_keyboard([apt], item_type="apartment", callback_prefix="sel_apt")
        assert "sel_apt:3" in _all_callbacks(result)

    def test_unknown_type_skipped(self):
        item = MagicMock()
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_user_apartment_selection_keyboard
            result = get_user_apartment_selection_keyboard([item], item_type="unknown", callback_prefix="sel")
        # Only cancel button should appear
        assert "cancel_apartment_selection" in _all_callbacks(result)

    def test_cancel_button_always_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.address_management import get_user_apartment_selection_keyboard
            result = get_user_apartment_selection_keyboard([], item_type="yard", callback_prefix="x")
        assert "cancel_apartment_selection" in _all_callbacks(result)
