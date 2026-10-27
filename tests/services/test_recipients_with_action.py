"""`recipients_with_action_*`: адресаты по действию каталога (sqlite)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from uk_management_bot.services import recipients as rcp

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)


def _users(seed):
    return [
        seed.user(1, roles='["executor", "engineer"]', language="uz"),
        seed.user(2, roles='["manager"]'),
        seed.user(3, roles='["executor", "engineer"]', bot_blocked_at=NOW),
        seed.user(4, roles='["executor", "engineer"]', deleted_at=NOW),
        seed.user(5, roles='["executor", "engineer"]', status="pending"),
        seed.user(6, roles='["applicant", "executor", "engineer"]'),
    ]


def test_sync_only_live_approved_holders(el_db, el_seed):
    el_db.add_all(_users(el_seed))
    el_db.commit()

    assert rcp.recipients_with_action_sync(el_db, "requests.engineering") == [
        rcp.Recipient(user_id=1, telegram_id=1001, language="uz"),
        rcp.Recipient(user_id=6, telegram_id=1006, language="ru"),
    ]


def test_action_granted_to_nobody_means_nobody(el_db, el_seed, monkeypatch):
    el_db.add_all(_users(el_seed))
    el_db.commit()
    monkeypatch.setattr(rcp, "get_action", lambda key: SimpleNamespace(roles=frozenset()))

    assert rcp.recipients_with_action_sync(el_db, "requests.engineering") == []


async def test_async_parity(el_async_factory, el_seed):
    async with el_async_factory() as s:
        s.add_all(_users(el_seed))
        await s.commit()
    async with el_async_factory() as s:
        result = await rcp.recipients_with_action_async(s, "requests.engineering")
    assert [r.user_id for r in result] == [1, 6]
