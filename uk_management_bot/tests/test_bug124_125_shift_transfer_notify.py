"""BUG-124 / BUG-125 — shift_transfer.py + end-shift notification regressions.

BUG-124: `shift_transfer.py` was non-functional — `with get_db() as db:` on a
plain generator (TypeError) ×6 and `await get_user_language(<1 arg>)` against the
sync helper (TypeError) ×9. Every handler fell straight into its `except`.
BUG-125: `shifts.py:end_shift_yes_with_id` did a local
`from ...services.shift_service import async_notify_shift_ended` (wrong module) →
ImportError swallowed by the notification `except`, so no notification was sent.
"""
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Message, User as TgUser


def _callback(user_id=7, data=""):
    tg_user = MagicMock(spec=TgUser)
    tg_user.id = user_id
    msg = MagicMock(spec=Message)
    msg.edit_text = AsyncMock()
    msg.answer = AsyncMock()
    cb = MagicMock(spec=CallbackQuery)
    cb.from_user = tg_user
    cb.message = msg
    cb.answer = AsyncMock()
    cb.data = data
    return cb


# --------------------------------------------------------------------------
# BUG-125 — the notification name resolves (no ImportError path).
# --------------------------------------------------------------------------
def test_shifts_module_exposes_async_notify_shift_ended():
    """`async_notify_shift_ended` must be importable from the handler module
    (module-level import), so `end_shift_yes_with_id` no longer hits the broken
    `from services.shift_service import ...` and silently skips notifications."""
    import uk_management_bot.handlers.shifts as shifts_mod

    assert hasattr(shifts_mod, "async_notify_shift_ended")
    # and the wrong-module local import is gone from the source
    import inspect

    src = inspect.getsource(shifts_mod.end_shift_yes_with_id)
    assert "from uk_management_bot.services.shift_service import async_notify_shift_ended" not in src


# --------------------------------------------------------------------------
# BUG-124 — shift_transfer.py is functional again.
# --------------------------------------------------------------------------
def test_shift_transfer_no_longer_imports_get_db():
    """The file migrated off the plain generator to `session_scope`; the broken
    `with get_db()` pattern (and the `get_db` name) is gone."""
    import uk_management_bot.handlers.shift_transfer as st

    assert not hasattr(st, "get_db")
    assert hasattr(st, "session_scope")


@pytest.mark.asyncio
async def test_reason_selection_renders_next_step_not_error():
    """A representative no-db handler: previously crashed on
    `await get_user_language(...)`; now resolves lang via a sync session and
    advances to the urgency step (does NOT fall into the error branch)."""
    from uk_management_bot.handlers import shift_transfer as st

    cb = _callback(data="transfer_reason:personal")
    state = MagicMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()

    db = MagicMock()

    @contextmanager
    def fake_scope():
        yield db

    with patch.object(st, "session_scope", fake_scope), \
         patch.object(st, "get_user_language", return_value="ru") as p_lang, \
         patch.object(st, "get_text", side_effect=lambda key, language="ru", **kw: key), \
         patch.object(st, "urgency_level_keyboard", return_value=None):
        await st.handle_reason_selection(cb, state)

    # sync helper called with (id, db) — not awaited, not 1-arg
    p_lang.assert_called_once_with(7, db)
    cb.message.edit_text.assert_called_once()
    rendered = cb.message.edit_text.call_args[0][0]
    assert "select_urgency" in rendered          # advanced to next step
    assert "error" not in rendered                # not the except branch
    state.set_state.assert_called_once()


@pytest.mark.asyncio
async def test_shift_selection_uses_session_and_does_not_crash():
    """Handler with a real db block: `session_scope` yields a sync session,
    lang resolved synchronously, shift looked up — reaches the reason step."""
    from uk_management_bot.handlers import shift_transfer as st

    cb = _callback(user_id=42, data="transfer_shift:5")
    state = MagicMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()

    db = MagicMock()
    # shift exists, no existing transfer
    shift = MagicMock(id=5)
    db.query.return_value.filter.return_value.first.side_effect = [shift, None]

    @contextmanager
    def fake_scope():
        yield db

    with patch.object(st, "session_scope", fake_scope), \
         patch.object(st, "get_user_language", return_value="ru"), \
         patch.object(st, "get_text", side_effect=lambda key, language="ru", **kw: key), \
         patch.object(st, "transfer_reason_keyboard", return_value=None):
        await st.handle_shift_selection(cb, state)

    cb.message.edit_text.assert_called_once()
    assert "select_reason" in cb.message.edit_text.call_args[0][0]
    state.set_state.assert_called_once()
