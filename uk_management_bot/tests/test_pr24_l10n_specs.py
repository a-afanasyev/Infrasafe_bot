"""PR-24: localization + specialization dedup + cosmetic.

- MGR-06: change-role header localizes roles via format_roles (not raw 'executor').
- MGR-07: employee spec toggle uses the single source AVAILABLE_SPECIALIZATIONS
  (10 keys incl. 'general') + specializations.* labels.
- MGR-05: _return_to_employee_info is render-only (no callback.answer).
- BUG-BOT-039: localize_address RU branch does no i18n lookups.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

import uk_management_bot.handlers.employee_management as emp
from uk_management_bot.utils.helpers import get_text


# --- MGR-07: single-source specialization toggle ----------------------------

def test_employee_spec_toggle_uses_available_specializations():
    from uk_management_bot.keyboards.employee_management import get_specializations_selection_keyboard
    from uk_management_bot.services.specialization_service import SpecializationService

    kb = get_specializations_selection_keyboard([], "ru")
    toggles = [
        b.callback_data for row in kb.inline_keyboard for b in row
        if b.callback_data.startswith("spec_toggle_")
    ]
    expected = {f"spec_toggle_{s}" for s in SpecializationService.AVAILABLE_SPECIALIZATIONS}
    assert set(toggles) == expected
    assert "spec_toggle_general" in toggles  # was missing in the old hardcoded list
    assert len(toggles) == 10


def test_employee_spec_toggle_labels_match_canonical_namespace():
    """Labels come from specializations.* (same as user_management toggle), not the
    dead employee_management.keyboards.spec_* namespace."""
    from uk_management_bot.keyboards.employee_management import get_specializations_selection_keyboard

    kb = get_specializations_selection_keyboard([], "ru")
    texts = [b.text for row in kb.inline_keyboard for b in row if b.callback_data.startswith("spec_toggle_")]
    plumber_label = get_text("specializations.plumber", language="ru")
    assert any(plumber_label in t for t in texts)


# --- MGR-06: localized roles in change-role header ---------------------------

@pytest.mark.asyncio
async def test_change_role_header_localizes_roles(monkeypatch):
    monkeypatch.setattr(emp, "has_admin_access", lambda **kw: True)
    employee = MagicMock()
    employee.id = 5
    employee.roles = '["executor"]'
    employee.first_name, employee.last_name, employee.username = "Иван", "Петров", None
    svc = MagicMock()
    svc.get_user_by_id.return_value = employee
    monkeypatch.setattr(emp, "UserManagementService", lambda db: svc)

    callback = MagicMock()
    callback.data = "change_employee_role_5"
    callback.from_user.id = 1
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    state = AsyncMock()

    await emp.change_employee_role(
        callback, state=state, db=MagicMock(), roles=["manager"], user=MagicMock(), language="ru"
    )

    text = callback.message.edit_text.await_args.args[0]
    localized = get_text("roles.executor", language="ru")
    assert localized != "executor"  # key must exist / be localized
    assert localized in text
    assert "executor" not in text  # no raw DB value leaked


# --- MGR-05: render-only employee card helper --------------------------------

@pytest.mark.asyncio
async def test_return_to_employee_info_is_render_only(monkeypatch):
    employee = MagicMock()
    employee.id, employee.telegram_id = 5, 555
    employee.first_name, employee.last_name, employee.username = "Иван", "Петров", None
    employee.phone = "+998901112233"
    employee.roles = '["executor"]'
    employee.status = "blocked"
    employee.specialization = None
    employee.created_at = MagicMock()
    employee.created_at.strftime.return_value = "01.01.2026 10:00"
    svc = MagicMock()
    svc.get_user_by_id.return_value = employee
    monkeypatch.setattr(emp, "UserManagementService", lambda db: svc)

    callback = MagicMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    result = await emp._return_to_employee_info(callback, MagicMock(), 5, "ru")

    assert result is True
    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_not_awaited()  # render-only: caller owns the answer


@pytest.mark.asyncio
async def test_unblock_re_renders_card_not_list(monkeypatch):
    """MGR-05 follow-up: unblock must re-render the card via _return_to_employee_info,
    not call show_employee_list(callback) (which parsed unblock_employee_<id> as a
    list callback and raised IndexError)."""
    monkeypatch.setattr(emp, "has_admin_access", lambda **kw: True)
    auth = MagicMock()
    auth.approve_user.return_value = True
    monkeypatch.setattr(emp, "AuthService", lambda db: auth)
    render = AsyncMock()
    monkeypatch.setattr(emp, "_return_to_employee_info", render)
    show_list = AsyncMock()
    monkeypatch.setattr(emp, "show_employee_list", show_list)

    callback = MagicMock()
    callback.data = "unblock_employee_41"
    callback.from_user.id = 1
    callback.answer = AsyncMock()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = MagicMock()

    await emp.unblock_employee(
        callback, db=db, roles=["manager"], user=MagicMock(), language="ru"
    )

    render.assert_awaited_once()
    assert render.await_args.args[2] == 41
    show_list.assert_not_awaited()


@pytest.mark.asyncio
async def test_return_to_employee_info_missing_returns_false(monkeypatch):
    svc = MagicMock()
    svc.get_user_by_id.return_value = None
    monkeypatch.setattr(emp, "UserManagementService", lambda db: svc)

    callback = MagicMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    result = await emp._return_to_employee_info(callback, MagicMock(), 999, "ru")

    assert result is False
    callback.message.edit_text.assert_not_awaited()
    callback.answer.assert_not_awaited()


# --- BUG-BOT-039: no dead i18n lookups on RU address render ------------------

def test_localize_address_ru_does_no_i18n_lookups(monkeypatch):
    import uk_management_bot.utils.helpers as helpers
    from uk_management_bot.utils.address_helpers import localize_address

    calls = []
    real = helpers.get_text
    monkeypatch.setattr(helpers, "get_text", lambda *a, **kw: (calls.append(a), real(*a, **kw))[1])

    out = localize_address("кв. 5, д. 14", "ru")
    assert out == "кв. 5, д. 14"  # unchanged
    assert calls == []  # RU branch must not call get_text


def test_localize_address_uz_still_transforms(monkeypatch):
    from uk_management_bot.utils.address_helpers import localize_address

    out = localize_address("кв. 5", "uz")
    assert out != "кв. 5"  # UZ branch still localizes
