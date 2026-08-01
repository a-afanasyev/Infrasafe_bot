"""AUD6-P2-05: межворкерная координация work-reports (эпоха кэша, reconcile-слот).

При uvicorn --workers 2 module-level кэш/троттлы у каждого воркера свои:
ревокация в одном воркере не сбрасывала публичный кэш другого. Redis-примитивы
обязаны деградировать к None при недоступном Redis — вызывающие тогда падают
на прежнее процессное поведение.
"""
import pytest

from uk_management_bot.api.work_reports import coordination


class FakeRedis:
    def __init__(self):
        self.store: dict = {}

    async def get(self, key):
        return self.store.get(key)

    async def incr(self, key):
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True


@pytest.fixture
def fake_redis(monkeypatch):
    r = FakeRedis()

    async def _get():
        return r

    monkeypatch.setattr(coordination, "get_pubsub_redis", _get)
    return r


@pytest.mark.asyncio
async def test_epoch_starts_at_zero_and_bumps(fake_redis):
    assert await coordination.cache_epoch() == 0
    assert await coordination.bump_cache_epoch() == 1
    assert await coordination.cache_epoch() == 1


@pytest.mark.asyncio
async def test_reconcile_slot_has_single_holder_per_window(fake_redis):
    assert await coordination.try_acquire_reconcile_slot(300) is True
    # Второй претендент того же окна (другой воркер) слота не получает.
    assert await coordination.try_acquire_reconcile_slot(300) is False


@pytest.mark.asyncio
async def test_redis_down_degrades_to_none(monkeypatch):
    async def _boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(coordination, "get_pubsub_redis", _boom)
    assert await coordination.cache_epoch() is None
    assert await coordination.bump_cache_epoch() is None
    assert await coordination.try_acquire_reconcile_slot(300) is None
