"""BUG-090 — `AddressService.search_apartments` built an unbounded SELECT.

The API router caps results at 50, but the service method itself had no
`.limit()`, so any internal caller (and a wide `query_text` like "1") could
pull the entire apartments table into memory. Fix bounds the query at 100.
"""
from unittest.mock import MagicMock

import pytest

from uk_management_bot.services.address_service import AddressService


class _Result:
    def scalars(self):
        inner = MagicMock()
        inner.all.return_value = []
        return inner


@pytest.mark.asyncio
async def test_search_apartments_query_is_bounded():
    captured = {}

    def _execute(query):
        captured["query"] = query
        return _Result()

    session = MagicMock()
    session.execute.side_effect = _execute

    await AddressService.search_apartments(session, "1")

    compiled = str(captured["query"]).upper()
    assert "LIMIT" in compiled, "search_apartments must apply a LIMIT (BUG-090)"
