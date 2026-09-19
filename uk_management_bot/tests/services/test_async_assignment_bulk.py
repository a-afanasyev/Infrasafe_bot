"""AUD8-DB-01: массовая переброска исполнителя (soft-delete сотрудника) — один
запрос активных назначений на весь список заявок, а не пара запросов на строку.
Правило переброски остаётся единым (`assignment_service.apply_executor_reassign`)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from uk_management_bot.services.async_assignment_service import AsyncAssignmentService
from uk_management_bot.utils.constants import ASSIGNMENT_TYPE_INDIVIDUAL


def _db_returning(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
async def test_bulk_reassign_uses_one_query_for_many_requests() -> None:
    active_a = SimpleNamespace(request_number="A", assignment_type=ASSIGNMENT_TYPE_INDIVIDUAL, executor_id=1)
    db = _db_returning([active_a])
    reqs = [SimpleNamespace(request_number=n, executor_id=1) for n in ("A", "B", "C")]

    moved = await AsyncAssignmentService(db).reassign_executor_bulk(reqs, 42)

    assert moved == 3
    db.execute.assert_awaited_once()  # K заявок → ровно один SELECT назначений
    assert [r.executor_id for r in reqs] == [42, 42, 42]
    assert active_a.executor_id == 42  # активное индивидуальное назначение переброшено


@pytest.mark.asyncio
async def test_bulk_reassign_empty_list_makes_no_query() -> None:
    db = _db_returning([])
    assert await AsyncAssignmentService(db).reassign_executor_bulk([], 42) == 0
    db.execute.assert_not_awaited()
