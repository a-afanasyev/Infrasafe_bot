"""Сверка «Инженерного разбора»: подбирает неназначенные, без инженера — одно
уведомление менеджерам за TTL (sqlite)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import uk_management_bot.services.dispatch as dispatch_mod
from uk_management_bot.services import engineering_reconcile as rec
from uk_management_bot.services.dispatch import DispatchResult

pytestmark = pytest.mark.integration


class _FakeRedis:
    def __init__(self):
        self.keys = set()

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return None
        self.keys.add(key)
        return True

    async def delete(self, key):
        self.keys.discard(key)


class _FakeBot:
    def __init__(self):
        self.sent = []
        self.down = False

    async def send_message(self, chat_id, text, **kw):
        if self.down:
            raise RuntimeError("telegram down")
        self.sent.append((chat_id, text))


def _request(number, category, status="Новая", executor_id=None):
    from uk_management_bot.database.models.request import Request

    return Request(request_number=number, user_id=1, category=category, description="d",
                   status=status, executor_id=executor_id)


@pytest.fixture
def harness(monkeypatch):
    redis, bot, dispatched = _FakeRedis(), _FakeBot(), []
    kinds = {}

    async def _dispatch(number, category, **kw):
        dispatched.append((number, category))
        return DispatchResult(kinds.get(number, "assigned"), "repair")

    async def _redis():
        return redis

    monkeypatch.setattr(dispatch_mod, "auto_dispatch_new_request_async", _dispatch)
    monkeypatch.setattr("uk_management_bot.services.redis_pubsub.get_pubsub_redis", _redis)
    monkeypatch.setattr("uk_management_bot.services.notification_service._get_shared_bot", lambda: bot)
    return SimpleNamespace(bot=bot, dispatched=dispatched, kinds=kinds)


async def _seed(factory, seed, *rows):
    async with factory() as s:
        s.add_all([seed.user(1), seed.user(2, roles='["manager"]'), *rows])
        await s.commit()


async def test_picks_only_new_unassigned_engineering(el_async_factory, el_seed, harness):
    await _seed(el_async_factory, el_seed,
                _request("261027-001", "Инженерный разбор"),
                _request("261027-002", "engineering"),
                _request("261027-003", "plumbing"),
                _request("261027-004", "Инженерный разбор", status="В работе", executor_id=2))
    assigned = await rec.reconcile_once(el_async_factory)
    assert assigned == 2
    assert sorted(n for n, _ in harness.dispatched) == ["261027-001", "261027-002"]
    assert harness.bot.sent == []


async def test_no_engineer_notifies_managers_once(el_async_factory, el_seed, harness):
    await _seed(el_async_factory, el_seed, _request("261027-001", "Инженерный разбор"))
    harness.kinds["261027-001"] = "no_engineer"
    await rec.reconcile_once(el_async_factory)
    await rec.reconcile_once(el_async_factory)  # следующий тик — без повтора
    assert [chat for chat, _ in harness.bot.sent] == [1002]
    assert "261027-001" in harness.bot.sent[0][1]


async def test_undelivered_notification_is_retried_next_tick(el_async_factory, el_seed, harness):
    await _seed(el_async_factory, el_seed, _request("261027-001", "Инженерный разбор"))
    harness.kinds["261027-001"] = "no_engineer"
    harness.bot.down = True
    await rec.reconcile_once(el_async_factory)
    harness.bot.down = False
    await rec.reconcile_once(el_async_factory)
    assert [chat for chat, _ in harness.bot.sent] == [1002]
