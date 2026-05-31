"""ARCH-013 — per-handler session-cleanup regressions.

These pin the three fix patterns applied across the bot handlers so a future
edit can't silently reintroduce the leak (or the inverse over-close bug):

* Pattern A — handler opens its own session: it must ``close()`` it on BOTH the
  happy path and the exception path, and must NOT open a second session in its
  ``except`` branch.
* Pattern B — handler accepts a middleware-injected ``db``: it must close a
  session it opened itself (fallback) but must NOT close the injected one
  (middleware owns its lifecycle and commits after the handler returns).
* Pattern C — handler already has a required injected ``db``: it must reuse it
  and open NO extra session.

The companion ``test_session_scope.py`` covers the ``session_scope()`` helper
itself; this file covers the call sites.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Message, User as TgUser


def _callback(user_id=7):
    tg_user = MagicMock(spec=TgUser)
    tg_user.id = user_id
    msg = MagicMock(spec=Message)
    msg.edit_text = AsyncMock()
    msg.answer = AsyncMock()
    cb = MagicMock(spec=CallbackQuery)
    cb.from_user = tg_user
    cb.message = msg
    cb.answer = AsyncMock()
    cb.data = ""
    cb.bot = MagicMock()
    return cb


def _message(user_id=7):
    tg_user = MagicMock(spec=TgUser)
    tg_user.id = user_id
    msg = MagicMock(spec=Message)
    msg.from_user = tg_user
    msg.answer = AsyncMock()
    return msg


# --------------------------------------------------------------------------
# Pattern A — requests.py filter handler (db_session = None + finally, no
# second session in the except branch).
# --------------------------------------------------------------------------
@pytest.mark.asyncio
class TestPatternA_RequestsCategoryFilter:
    async def test_happy_path_closes_single_session(self):
        from uk_management_bot.handlers import requests as mod

        cb = _callback()
        cb.data = "categoryfilter_electricity"
        db = MagicMock()
        gen = MagicMock(side_effect=lambda: iter([db]))

        with patch.object(mod, "get_db", side_effect=lambda: iter([db])) as p_get_db, \
             patch.object(mod, "get_user_language", return_value="ru"), \
             patch.object(mod, "show_my_requests", new=AsyncMock()):
            await mod.handle_category_filter(cb, state=MagicMock())

        assert p_get_db.call_count == 1          # opened exactly once
        db.close.assert_called_once()            # and closed

    async def test_exception_path_closes_and_opens_no_second_session(self):
        from uk_management_bot.handlers import requests as mod

        cb = _callback()
        cb.data = "categoryfilter_electricity"
        db = MagicMock()

        with patch.object(mod, "get_db", side_effect=lambda: iter([db])) as p_get_db, \
             patch.object(mod, "get_user_language", return_value="ru"), \
             patch.object(mod, "show_my_requests", new=AsyncMock(side_effect=RuntimeError("boom"))), \
             patch.object(mod, "get_text", side_effect=lambda key, language="ru", **kw: key):
            await mod.handle_category_filter(cb, state=MagicMock())

        # Leak invariant: still exactly one session, and it was closed.
        assert p_get_db.call_count == 1
        db.close.assert_called_once()


# --------------------------------------------------------------------------
# Pattern A — shifts.py:end_shift_yes (converted to `with session_scope()`).
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pattern_a_shifts_end_shift_yes_uses_session_scope_and_closes():
    from uk_management_bot.handlers import shifts as mod
    from contextlib import contextmanager

    cb = _callback()
    db = MagicMock()
    closed = {"v": False}

    @contextmanager
    def fake_scope():
        try:
            yield db
        finally:
            closed["v"] = True

    service = MagicMock()
    service.end_shift.return_value = {"success": False, "message": "nope"}

    with patch.object(mod, "session_scope", fake_scope), \
         patch.object(mod, "ShiftService", return_value=service), \
         patch.object(mod, "get_user_language", return_value="ru"), \
         patch.object(mod, "get_text", side_effect=lambda key, language="ru", **kw: key):
        await mod.end_shift_yes(cb, user_status=None, language="ru")

    assert closed["v"] is True  # session_scope exited → session closed (even on early return)


# --------------------------------------------------------------------------
# Pattern B — over-close: handler must NOT close an injected session, but MUST
# close one it opened itself.
# --------------------------------------------------------------------------
@pytest.mark.asyncio
class TestPatternB_CmdMyShifts:
    async def test_injected_session_not_closed(self):
        from uk_management_bot.handlers import my_shifts as mod

        msg = _message()
        injected = MagicMock()
        state = MagicMock()
        state.set_state = AsyncMock()

        with patch.object(mod, "get_text", side_effect=lambda key, language="ru", **kw: key), \
             patch.object(mod, "get_my_shifts_menu", return_value=None):
            await mod.cmd_my_shifts(msg, state=state, language="ru", db=injected)

        injected.close.assert_not_called()  # middleware owns the injected session

    async def test_fallback_session_is_closed(self):
        from uk_management_bot.handlers import my_shifts as mod

        msg = _message()
        own = MagicMock()
        state = MagicMock()
        state.set_state = AsyncMock()

        with patch.object(mod, "get_db", side_effect=lambda: iter([own])), \
             patch.object(mod, "get_text", side_effect=lambda key, language="ru", **kw: key), \
             patch.object(mod, "get_my_shifts_menu", return_value=None):
            await mod.cmd_my_shifts(msg, state=state, language="ru", db=None)

        own.close.assert_called_once()


@pytest.mark.asyncio
async def test_pattern_b_request_acceptance_does_not_close_injected_session():
    from uk_management_bot.handlers import request_acceptance as mod

    msg = _message()
    injected = MagicMock()
    # No requests → handler returns early after the no-pending answer.
    injected.query.return_value.filter.return_value.first.return_value = MagicMock(id=1)
    injected.query.return_value.filter.return_value.all.return_value = []
    injected.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

    with patch.object(mod, "get_text", side_effect=lambda key, language="ru", **kw: key), \
         patch("uk_management_bot.utils.helpers.get_user_language", return_value="ru"):
        await mod.show_pending_acceptance_requests(msg, db=injected)

    injected.close.assert_not_called()  # injected = middleware's, must survive


# --------------------------------------------------------------------------
# Pattern C — user_yards handler reuses the injected db, opens NO new session.
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pattern_c_user_yards_opens_no_extra_session():
    from uk_management_bot.handlers import user_yards_management as mod

    cb = _callback()
    cb.data = "manage_user_yards_123"
    injected = MagicMock()
    injected.query.return_value.filter.return_value.first.return_value = MagicMock(
        telegram_id=123, first_name="A", last_name="B"
    )

    def _boom():
        raise AssertionError("handler must not open its own session (Pattern C)")

    with patch.object(mod, "get_db", side_effect=_boom), \
         patch.object(mod, "get_user_language", return_value="ru"), \
         patch.object(mod, "has_admin_access", return_value=True), \
         patch.object(mod, "get_text", side_effect=lambda key, language="ru", **kw: key), \
         patch.object(mod, "get_user_yards_keyboard", return_value=None):
        await mod.handle_manage_user_yards(cb, db=injected, roles=["manager"], user=MagicMock(id=1))

    # get_db never called (asserted via _boom); injected session used, not closed by handler.
    injected.close.assert_not_called()
