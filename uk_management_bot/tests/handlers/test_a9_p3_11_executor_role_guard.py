"""A9-P3-11 (ревью): назначение на смену — только по роли `executor` из `roles`.

Список кандидатов (`handle_select_shift_for_assignment`) пускал пользователя по
одному `active_role == 'executor'`, а гварды назначения (обычное и
принудительное) роль не проверяли вовсе — `callback_data` шлёт клиент, и
`executor_id` в нём произвольный. Канон — `utils.auth_helpers.get_user_roles`.
"""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from uk_management_bot.database.models.shift import Shift


def _user(roles, active_role):
    u = MagicMock()
    u.id = 10
    u.telegram_id = 1010
    u.first_name = "Тест"
    u.last_name = "Исполнителев"
    u.status = "approved"
    u.roles = roles
    u.active_role = active_role
    u.specialization = json.dumps(["electrician"])
    return u


def _shift():
    s = MagicMock(spec=Shift)
    s.id = 1
    s.specialization_focus = ["electrician"]
    s.can_handle_specialization = Shift.can_handle_specialization.__get__(s)
    s.start_time = datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)
    s.end_time = datetime(2026, 8, 17, 18, 0, tzinfo=timezone.utc)
    s.geographic_zone = None
    s.user_id = None
    return s


def _callback(data):
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = 1
    cb.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    return cb


def _env(monkeypatch, executor):
    from uk_management_bot.handlers.shift_management import assignment_b as mod

    service = MagicMock()
    service.get_shift.return_value = _shift()
    service.get_user.return_value = executor
    service.list_approved_users.return_value = [executor]
    service.count_shifts_for_user_on_day.return_value = 0
    service.list_overlapping_shifts.return_value = []
    service.assign_executor.return_value = True
    monkeypatch.setattr(mod, "ShiftManagementService", lambda db: service)
    monkeypatch.setattr(mod, "get_user_language", lambda *a, **kw: "ru")
    return mod, service


FAKE_EXECUTOR = ('["applicant"]', "executor")  # active_role без роли в roles
REAL_EXECUTOR = ('["applicant", "executor"]', "applicant")


def _assign_buttons(callback):
    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    return [b.callback_data for row in markup.inline_keyboard for b in row
            if b.callback_data.startswith("assign_executor_to_shift:")]


@pytest.mark.asyncio
@pytest.mark.parametrize("roles,active,listed", [(*FAKE_EXECUTOR, False), (*REAL_EXECUTOR, True)])
async def test_candidate_list_requires_executor_in_roles(monkeypatch, roles, active, listed):
    mod, _ = _env(monkeypatch, _user(roles, active))
    callback = _callback("select_shift_for_assignment:1")
    await mod.handle_select_shift_for_assignment(
        callback, MagicMock(set_state=AsyncMock()),
        db=MagicMock(), user=MagicMock(), roles=["manager"])
    callback.message.edit_text.assert_awaited_once()
    assert bool(_assign_buttons(callback)) is listed


@pytest.mark.asyncio
@pytest.mark.parametrize("roles,active,assigned", [(*FAKE_EXECUTOR, False), (*REAL_EXECUTOR, True)])
async def test_assign_requires_executor_in_roles(monkeypatch, roles, active, assigned):
    mod, service = _env(monkeypatch, _user(roles, active))
    callback = _callback("assign_executor_to_shift:1:10")
    await mod.handle_assign_executor_to_shift(
        callback, MagicMock(clear=AsyncMock()),
        db=MagicMock(), user=MagicMock(), roles=["manager"])
    assert service.assign_executor.called is assigned
    if not assigned:
        callback.answer.assert_awaited()
        assert callback.answer.await_args.kwargs.get("show_alert") is True


@pytest.mark.asyncio
@pytest.mark.parametrize("roles,active,assigned", [(*FAKE_EXECUTOR, False), (*REAL_EXECUTOR, True)])
async def test_force_assign_requires_executor_in_roles(monkeypatch, roles, active, assigned):
    mod, service = _env(monkeypatch, _user(roles, active))
    callback = _callback("force_assign:1:10")
    await mod.handle_force_assign(
        callback, MagicMock(clear=AsyncMock()),
        db=MagicMock(), user=MagicMock(), roles=["manager"])
    assert service.force_assign_executor.called is assigned
    if not assigned:
        callback.answer.assert_awaited()
        assert callback.answer.await_args.kwargs.get("show_alert") is True
