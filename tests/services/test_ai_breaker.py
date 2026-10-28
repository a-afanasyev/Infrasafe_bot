"""Предохранитель ИИ-триажа (services/ai_manager/breaker.py) — общий через Redis.

Бот и API идут разными путями dispatch, поэтому счётчик per-process
разошёлся бы; состояние — в Redis. Недоступный Redis = предохранитель
закрыт (LLM вызываем), уведомление менеджеру — одно на окно (SET NX).
"""
import pytest

from uk_management_bot.services.ai_manager import breaker


class FakeRedis:
    """Минимальный dict-двойник: exists/incr/ttl/expire/set(nx, ex)/delete."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttl_store: dict[str, int] = {}

    def exists(self, key):
        return 1 if key in self.store else 0

    def incr(self, key):
        self.store[key] = str(int(self.store.get(key, "0")) + 1)
        return int(self.store[key])

    def ttl(self, key):
        return self.ttl_store.get(key, -1)

    def expire(self, key, seconds):
        self.ttl_store[key] = seconds
        return True

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = str(value)
        if ex is not None:
            self.ttl_store[key] = ex
        return True

    def get(self, key):
        return self.store.get(key)

    def delete(self, *keys):
        for key in keys:
            self.store.pop(key, None)
            self.ttl_store.pop(key, None)
        return len(keys)


class BrokenRedis:
    def __getattr__(self, name):
        def _boom(*a, **k):
            raise ConnectionError("redis down")
        return _boom


@pytest.fixture
def fake(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(breaker, "_get_client", lambda: client)
    return client


def test_closed_by_default(fake):
    assert breaker.is_open() is False


def test_opens_after_threshold_and_notifies_once(fake):
    assert breaker.record_failure() is False
    assert breaker.record_failure() is False
    assert breaker.is_open() is False
    # третий сбой открывает окно и даёт право на ОДНО уведомление
    assert breaker.record_failure() is True
    assert breaker.is_open() is True
    assert fake.ttl_store[breaker.OPEN_KEY] == breaker.OPEN_TTL
    # дальнейшие сбои в том же окне уведомление не повторяют
    assert breaker.record_failure() is False


def test_failure_counter_has_ttl(fake):
    breaker.record_failure()
    assert fake.ttl_store[breaker.FAIL_KEY] == breaker.FAIL_TTL


def test_success_resets_counter(fake):
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    assert breaker.record_failure() is False
    assert breaker.is_open() is False


def test_redis_down_means_closed_and_silent(monkeypatch):
    monkeypatch.setattr(breaker, "_get_client", lambda: BrokenRedis())
    assert breaker.is_open() is False
    assert breaker.record_failure() is False
    breaker.record_success()  # не бросает


# ───────────── статус и сброс (страница «Правила ИИ») ─────────────


def test_status_reports_open_ttl_and_failures(fake):
    assert breaker.status() == {"open": False, "open_ttl": 0, "failures": 0}
    for _ in range(3):
        breaker.record_failure()
    assert breaker.status() == {"open": True, "open_ttl": breaker.OPEN_TTL, "failures": 3}


def test_reset_clears_everything(fake):
    for _ in range(3):
        breaker.record_failure()
    assert breaker.reset() is True
    assert breaker.is_open() is False and breaker.status() == {"open": False, "open_ttl": 0, "failures": 0}
    assert breaker.NOTIFIED_KEY not in fake.store


def test_status_and_reset_when_redis_down(monkeypatch):
    monkeypatch.setattr(breaker, "_get_client", lambda: BrokenRedis())
    assert breaker.status() is None and breaker.reset() is False
