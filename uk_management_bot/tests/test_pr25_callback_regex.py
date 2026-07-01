"""PR-25 (BUG-BOT-034 / BUG-BOT-037): strict request-number regex on the
edit_/approve_/accept_/purchase_ manager-action callbacks.

These callbacks previously used open-set prefix/exclusion-list filters
(``startswith("edit_") & ~startswith("edit_employee_") & ...``) which caught any
future ``<prefix>_*`` callback. They are now bound to the shared request-number
core (``\\d{6}-\\d{3,}``), so only ``<prefix>_<YYMMDD-NNN>`` matches and unrelated
callbacks (edit_employee_, approve_user_, accept_request_, purchase_materials_)
fall through to their own handlers.
"""
import pytest
from aiogram.types import CallbackQuery

from uk_management_bot.handlers.requests import router as requests_router
from uk_management_bot.handlers.admin import router as admin_router


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


# --- edit_ (owner request edit, requests.py) ---------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("data", ["edit_250528-001", "edit_250528-1000"])
async def test_edit_matches_request_number(data):
    assert await _matching_handlers(requests_router, data) == ["handle_edit_request"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data",
    [
        "edit_employee_5",
        "edit_profile",
        "edit_first_name_x",
        "edit_last_name_x",
        "edit_settings",  # arbitrary future edit_* must NOT be swallowed (open-set bug)
        "edit_abc",
    ],
)
async def test_edit_does_not_match_non_request(data):
    assert "handle_edit_request" not in await _matching_handlers(requests_router, data)


# --- approve_ (applicant rated-accept, requests.py) --------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("data", ["approve_250528-001", "approve_250528-1000"])
async def test_approve_matches_request_number(data):
    assert await _matching_handlers(requests_router, data) == ["handle_approve_request"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data", ["approve_user_5", "approve_employee_5", "approve_all", "approve_abc"]
)
async def test_approve_does_not_match_non_request(data):
    assert "handle_approve_request" not in await _matching_handlers(requests_router, data)


# --- accept_ / purchase_ (manager actions, admin.py) -------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("data", ["accept_250528-001", "accept_250528-1000"])
async def test_accept_matches_request_number(data):
    assert await _matching_handlers(admin_router, data) == ["handle_accept_request"]


@pytest.mark.asyncio
@pytest.mark.parametrize("data", ["purchase_250528-001", "purchase_250528-1000"])
async def test_purchase_matches_request_number(data):
    assert await _matching_handlers(admin_router, data) == ["handle_purchase_request"]


# --- behavioral: canonical purchase opens material input, no status change ---

@pytest.mark.asyncio
async def test_admin_purchase_opens_materials_without_status_change(monkeypatch):
    """The canonical manager purchase handler must open the material-input FSM and
    NOT flip the request status (the removed requests.py duplicate set 'Закуп'
    immediately, skipping material entry)."""
    from unittest.mock import AsyncMock, MagicMock
    import uk_management_bot.handlers.admin.actions as admin
    from uk_management_bot.states.request_status import RequestStatusStates

    monkeypatch.setattr(admin, "has_admin_access", lambda **kwargs: True)
    # Guard: the canonical purchase handler must not run any status-update service.
    # raising=False: RequestService is no longer imported in admin.py (it was dead,
    # removed in PRAC-01-FU1) — the guard still catches a regression that re-imports
    # AND calls it, since the patch would then shadow that import.
    status_service = MagicMock()
    monkeypatch.setattr(admin, "RequestService", status_service, raising=False)

    request = MagicMock()
    request.request_number = "250528-001"
    request.purchase_history = None
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = request

    callback = MagicMock()
    callback.data = "purchase_250528-001"
    callback.from_user.id = 123
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    state = AsyncMock()

    await admin.handle_purchase_request(
        callback, state=state, db=db, roles=["manager"], user=MagicMock(), language="ru"
    )

    # Opened the material-input flow ...
    state.set_state.assert_awaited_once_with(RequestStatusStates.waiting_for_materials)
    callback.message.edit_text.assert_awaited_once()
    # ... and never invoked a status-update service (no premature "Закуп").
    status_service.assert_not_called()
