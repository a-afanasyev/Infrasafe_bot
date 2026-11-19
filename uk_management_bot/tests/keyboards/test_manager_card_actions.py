"""Карточка заявки менеджера: только допустимые действия + цвет кнопок.

Раньше карточка показывала все шесть действий при любом статусе, и недоступное
отвечало окном-отказом. Набор кнопок выводится из канона workflow
(`ACTION_TABLE[...].from_statuses`), а не из своего списка статусов.
"""
import pytest

from uk_management_bot.keyboards.admin import (
    MANAGER_CARD_ACTIONS,
    get_manager_request_actions_keyboard,
)
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_CLARIFICATION,
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_NEW,
    REQUEST_STATUS_PURCHASE,
)
from uk_management_bot.utils.request_workflow.specs import ACTION_TABLE

NUM = "261101-001"
PREFIXES = ("accept_", "mgr_deny_", "clarify_", "purchase_", "mgr_complete_", "mgr_delete_", "media_")


def _buttons(**kwargs) -> dict:
    markup = get_manager_request_actions_keyboard(NUM, **kwargs)
    found = {}
    for row in markup.inline_keyboard:
        for btn in row:
            prefix = next(p for p in PREFIXES if btn.callback_data.startswith(p))
            found[prefix] = btn
    return found


@pytest.mark.parametrize("status,assigned,expected", [
    (REQUEST_STATUS_NEW, False, {"accept_", "mgr_deny_", "clarify_", "purchase_"}),
    (REQUEST_STATUS_IN_PROGRESS, True, {"mgr_deny_", "clarify_", "purchase_", "mgr_complete_"}),
    (REQUEST_STATUS_PURCHASE, True, {"mgr_deny_", "clarify_", "mgr_complete_"}),
    (REQUEST_STATUS_CLARIFICATION, True, {"mgr_deny_", "mgr_complete_"}),
])
def test_only_actions_valid_for_status_are_shown(status, assigned, expected):
    assert set(_buttons(status=status, assigned=assigned)) == expected


def test_to_work_hidden_once_request_is_assigned():
    """Назначенную заявку ведёт строка «Переназначить», а не «В работу»."""
    assert "accept_" not in _buttons(status=REQUEST_STATUS_NEW, assigned=True)


def test_delete_only_for_delete_admin_and_media_only_with_media():
    plain = _buttons(status=REQUEST_STATUS_NEW)
    assert "mgr_delete_" not in plain and "media_" not in plain
    full = _buttons(status=REQUEST_STATUS_NEW, can_delete=True, has_media=True)
    assert {"mgr_delete_", "media_"} <= set(full)


def test_button_styles():
    btns = _buttons(status=REQUEST_STATUS_NEW, can_delete=True)
    assert btns["accept_"].style == "success"
    assert btns["mgr_deny_"].style == "danger"
    assert btns["mgr_delete_"].style == "danger"
    assert getattr(btns["clarify_"], "style", None) is None
    done = _buttons(status=REQUEST_STATUS_IN_PROGRESS, assigned=True)
    assert done["mgr_complete_"].style == "success"


def test_card_actions_follow_workflow_canon():
    """Гейт от расхождения: кнопка видна ровно там, где канон пускает действие."""
    for prefix, action, _key, _style in MANAGER_CARD_ACTIONS:
        for status in ACTION_TABLE[action].from_statuses:
            shown = _buttons(status=status, assigned=False)
            assert prefix in shown, f"{prefix} must be offered in {status!r}"
