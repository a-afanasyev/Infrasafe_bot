"""Regression: 'передать дежурному' (assign_duty_*) must resolve to the COMPLETE
admin handler, not the incomplete requests.py duplicate.

Bug: "заявка, переданная дежурному, не оказалась у специалиста с активной сменой".
Root cause — requests_router is included before admin_router in the dispatcher, so
aiogram dispatched assign_duty_* to requests.handle_assign_duty_executor, whose
auto_assign_request_by_category neither commits the group assignment (get_db() does
not auto-commit) nor notifies executors on an active shift. admin.py's complete
handler (commit + notification to active-shift executors) never ran.
"""
import pytest
from aiogram.types import CallbackQuery

from uk_management_bot.handlers.requests import router as requests_router
from uk_management_bot.handlers.admin import router as admin_router
from uk_management_bot.handlers.request_status_management import (
    router as request_status_management_router,
)


async def _matching_handlers(router, data: str) -> list[str]:
    cb = CallbackQuery.model_construct(id="1", data=data, chat_instance="x")
    names: list[str] = []
    for handler in router.callback_query.handlers:
        try:
            ok, _ = await handler.check(cb)
        except Exception:
            ok = False
        if ok:
            names.append(handler.callback.__name__)
    return names


@pytest.mark.asyncio
async def test_requests_router_does_not_shadow_assign_duty():
    """requests_router must NOT handle assign_duty_* (it shadowed the admin handler)."""
    assert await _matching_handlers(requests_router, "assign_duty_250528-001") == []


@pytest.mark.asyncio
async def test_admin_router_owns_assign_duty():
    """The complete admin handler must be the sole owner of assign_duty_*."""
    assert await _matching_handlers(admin_router, "assign_duty_250528-001") == [
        "handle_assign_duty_executor_admin"
    ]


@pytest.mark.asyncio
async def test_requests_router_does_not_shadow_assign_specific():
    """assign_specific_* must route to admin (manual-assign list), not the requests copy."""
    assert await _matching_handlers(requests_router, "assign_specific_250528-001") == []


@pytest.mark.asyncio
async def test_admin_router_owns_assign_specific():
    assert await _matching_handlers(admin_router, "assign_specific_250528-001") == [
        "handle_assign_specific_executor_admin"
    ]


@pytest.mark.asyncio
async def test_requests_router_does_not_shadow_assign_executor():
    """assign_executor_* (final assignment) must route to admin (AssignmentService path)."""
    assert await _matching_handlers(requests_router, "assign_executor_250528-001_42") == []


@pytest.mark.asyncio
async def test_admin_router_owns_assign_executor():
    assert await _matching_handlers(admin_router, "assign_executor_250528-001_42") == [
        "handle_final_executor_assignment_admin"
    ]


# ---------------------------------------------------------------------------
# Manager action callbacks: deny_/complete_/delete_ used to be shadowed by the
# executor/owner handlers in requests.py (registered before admin_router). Moved
# to mgr_* so admin.py owns them unambiguously, independent of router order.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_router_owns_mgr_deny():
    """Manager 'Отклонить' (mgr_deny_*) must reach the admin decline-with-reason flow."""
    assert await _matching_handlers(admin_router, "mgr_deny_250528-001") == [
        "handle_deny_request"
    ]


@pytest.mark.asyncio
async def test_requests_router_does_not_shadow_mgr_deny():
    assert await _matching_handlers(requests_router, "mgr_deny_250528-001") == []


@pytest.mark.asyncio
async def test_admin_router_owns_mgr_complete():
    """Manager 'Завершить' (mgr_complete_*) must reach the admin complete (EXECUTED + audit)."""
    assert await _matching_handlers(admin_router, "mgr_complete_250528-001") == [
        "handle_complete_request"
    ]


@pytest.mark.asyncio
async def test_requests_router_does_not_shadow_mgr_complete():
    assert await _matching_handlers(requests_router, "mgr_complete_250528-001") == []


@pytest.mark.asyncio
async def test_admin_router_owns_mgr_delete():
    """Manager 'Удалить' (mgr_delete_*) must reach the admin cascade delete (ADMIN gate)."""
    assert await _matching_handlers(admin_router, "mgr_delete_250528-001") == [
        "handle_delete_request"
    ]


@pytest.mark.asyncio
async def test_requests_router_does_not_shadow_mgr_delete():
    assert await _matching_handlers(requests_router, "mgr_delete_250528-001") == []


@pytest.mark.asyncio
async def test_complete_work_routes_to_status_management():
    """complete_work_* must reach the dedicated status-management handler, not the
    bare complete_ duplicate that used to swallow it by prefix."""
    assert await _matching_handlers(
        request_status_management_router, "complete_work_250528-001"
    ) == ["handle_complete_work"]
    assert await _matching_handlers(admin_router, "complete_work_250528-001") == []
    assert await _matching_handlers(requests_router, "complete_work_250528-001") == []


@pytest.mark.asyncio
async def test_back_to_assignment_type_owned_by_admin():
    """back_to_assignment_type_* had identical copies in both routers; admin.py keeps it."""
    assert await _matching_handlers(
        admin_router, "back_to_assignment_type_250528-001"
    ) == ["handle_back_to_assignment_type_admin"]
    assert await _matching_handlers(
        requests_router, "back_to_assignment_type_250528-001"
    ) == []


@pytest.mark.asyncio
async def test_executor_complete_still_owned_by_requests():
    """Regression: the executor complete flow must keep working after the mgr_* split."""
    assert await _matching_handlers(
        requests_router, "executor_complete_250528-001"
    ) == ["executor_complete_request"]


@pytest.mark.asyncio
async def test_delete_employee_not_caught_by_manager_delete():
    """Dropping the `~delete_employee_` exclusion from admin's delete filter is safe:
    delete_employee_* (handled in employee_management_router) must NOT reach the
    manager delete handler now that it's gated on the mgr_delete_ prefix."""
    matched = await _matching_handlers(admin_router, "delete_employee_4")
    assert "handle_delete_request" not in matched


def test_deny_fsm_reason_consumer_registered():
    """Second step of the manager deny flow must stay wired: handle_deny_request sets
    ManagerStates.cancel_reason, which handle_cancel_reason_text consumes. Guards
    against silently breaking the reason-input step when touching the deny callback."""
    message_handler_names = [h.callback.__name__ for h in admin_router.message.handlers]
    assert "handle_cancel_reason_text" in message_handler_names


# ---------------------------------------------------------------------------
# PR-25 (BUG-BOT-034/037): accept_/purchase_ used to have bare-prefix duplicates
# in requests.py (registered before admin_router) that shadowed the canonical
# admin handlers. The requests.py copies were removed and the admin filters
# tightened to a strict request-number regex. accept_ in requests.py was a manual
# status flip; purchase_ in requests.py prematurely set "Закуп" without the
# material-input prompt. admin.py is the sole, canonical owner now.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_router_owns_accept():
    assert await _matching_handlers(admin_router, "accept_250528-001") == [
        "handle_accept_request"
    ]


@pytest.mark.asyncio
async def test_requests_router_does_not_shadow_accept():
    assert await _matching_handlers(requests_router, "accept_250528-001") == []


@pytest.mark.asyncio
async def test_admin_router_owns_purchase():
    assert await _matching_handlers(admin_router, "purchase_250528-001") == [
        "handle_purchase_request"
    ]


@pytest.mark.asyncio
async def test_requests_router_does_not_shadow_purchase():
    assert await _matching_handlers(requests_router, "purchase_250528-001") == []


@pytest.mark.asyncio
async def test_accept_request_prefix_not_caught_by_manager_accept():
    """accept_request_* (executor accept, request_acceptance.py) must NOT reach the
    manager accept handler after the strict-regex tightening."""
    assert await _matching_handlers(admin_router, "accept_request_250528-001") == []


@pytest.mark.asyncio
async def test_purchase_materials_not_caught_by_manager_purchase():
    """purchase_materials_* (material-input flow) must NOT reach the manager purchase
    handler."""
    assert await _matching_handlers(admin_router, "purchase_materials_250528-001") == []
