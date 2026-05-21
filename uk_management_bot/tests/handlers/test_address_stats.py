"""
Regression test for BUG-BOT-013 — addr_stats was a silent click (no handler).

The handler now aggregates Yard / Building / Apartment / UserApartment counts
and renders a stats report in the user's language.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_callback(telegram_id: int = 123):
    cb = MagicMock()
    cb.from_user.id = telegram_id
    cb.data = "addr_stats"
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _make_state() -> AsyncMock:
    state = AsyncMock()
    state.clear = AsyncMock()
    return state


def _build_stub_db(*, yards=(10, 8), buildings=(20, 18), apartments=(100, 95),
                   residents_by_status=None):
    """
    Build a MagicMock db whose query chain returns the test values.

    db.query(...).scalar() / db.query(...).filter(...).scalar() are called
    sequentially in this order:
      1. total_yards
      2. active_yards
      3. total_buildings
      4. active_buildings
      5. total_apartments
      6. active_apartments
    Then:
      7. db.query(UserApartment.status, count).group_by(...).all() returns rows.
    """
    if residents_by_status is None:
        residents_by_status = {"approved": 5, "pending": 3, "rejected": 1}

    scalar_values = [
        yards[0], yards[1],
        buildings[0], buildings[1],
        apartments[0], apartments[1],
    ]

    # We need each db.query(...) to return a fresh query object that supports
    # scalar() OR filter().scalar() OR group_by().all().
    # We'll attach .scalar to return the next value from a shared iterator.
    scalar_iter = iter(scalar_values)

    def make_scalar_query():
        q = MagicMock()
        # filter(...) returns the same q (chain), but scalar must still come
        # from the iterator on first call to either path.
        q.filter.return_value = q
        # Each scalar call advances the iterator.
        q.scalar.side_effect = lambda: next(scalar_iter)
        # group_by/.all path for the residents query — see below.
        residents_rows = list(residents_by_status.items())
        q.group_by.return_value = q
        q.all.return_value = residents_rows
        return q

    db = MagicMock()
    db.query = MagicMock(side_effect=lambda *a, **kw: make_scalar_query())
    return db


class TestAddrStatsHandler:
    @pytest.mark.asyncio
    async def test_addr_stats_renders_summary_text(self):
        """The handler must edit the message with a stats report (not silent)."""
        from uk_management_bot.handlers.address_yards import show_address_stats

        cb = _make_callback()
        state = _make_state()
        db = _build_stub_db(
            yards=(10, 8),
            buildings=(20, 18),
            apartments=(100, 95),
            residents_by_status={"approved": 7, "pending": 3, "rejected": 2},
        )

        await show_address_stats(cb, state, language="ru", db=db)

        # Message must be edited (not silent).
        cb.message.edit_text.assert_awaited_once()
        # And callback.answer must be invoked (to dismiss the loading spinner).
        cb.answer.assert_awaited_once()

        rendered_text = cb.message.edit_text.await_args.args[0]

        # Must contain key headers and the numbers we passed.
        assert "Статистика справочника адресов" in rendered_text
        assert "10" in rendered_text  # total yards
        assert "20" in rendered_text  # total buildings
        assert "100" in rendered_text  # total apartments
        # Total residents = 7 + 3 + 2 = 12
        assert "12" in rendered_text
        # Breakdown by status
        assert "7" in rendered_text  # approved
        assert "3" in rendered_text  # pending
        assert "2" in rendered_text  # rejected

    @pytest.mark.asyncio
    async def test_addr_stats_handles_empty_directory(self):
        """All zeros should still render (no division-by-zero or crash)."""
        from uk_management_bot.handlers.address_yards import show_address_stats

        cb = _make_callback()
        state = _make_state()
        db = _build_stub_db(
            yards=(0, 0),
            buildings=(0, 0),
            apartments=(0, 0),
            residents_by_status={},  # no rows at all
        )

        await show_address_stats(cb, state, language="ru", db=db)

        cb.message.edit_text.assert_awaited_once()
        cb.answer.assert_awaited_once()
        rendered_text = cb.message.edit_text.await_args.args[0]
        # Must contain stats header and total zero rendering — no exception.
        assert "Статистика справочника адресов" in rendered_text
        assert "0" in rendered_text
