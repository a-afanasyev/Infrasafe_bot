"""Атомарное «Готово» исполнителя: валидация фото и Redis-идемпотентность.

Путь целиком (preflight → загрузка → EXECUTOR_COMPLETE) проверяет интеграционный
`tests/api/test_request_complete_with_photo.py`; здесь — чистые части без БД.
"""
import pytest

from uk_management_bot.services import completion_idempotency as idem
from uk_management_bot.services.executor_completion import (
    COMPLETION_PHOTO_MAX_BYTES,
    CompletionRefused,
    parse_idempotency_key,
    validate_completion_photo,
)

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"0" * 64


class FakeRedis:
    """Минимум redis.asyncio, который трогает хранилище: get/set(nx, ex)/delete."""

    def __init__(self):
        self.data: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return None
        self.data[key] = value
        self.ttl[key] = ex
        return True

    async def delete(self, key):
        return 1 if self.data.pop(key, None) is not None else 0

    async def eval(self, script, numkeys, *args):
        """Эмуляция compare-and-delete-скрипта лока (единственный EVAL хранилища)."""
        assert numkeys == 1 and "redis.call('get'" in script and "redis.call('del'" in script
        key, token = args
        if self.data.get(key) == token:
            del self.data[key]
            return 1
        return 0


class BrokenRedis:
    async def _boom(self, *a, **k):
        raise ConnectionError("redis down")

    get = set = delete = eval = _boom


def _use(monkeypatch, redis):
    async def getter():
        return redis
    monkeypatch.setattr(idem, "get_redis", getter)


# ── validate_completion_photo ──────────────────────────────────────────


@pytest.mark.parametrize("data, mime", [(JPEG, "image/jpeg"), (PNG, "image/png")])
def test_accepts_jpeg_and_png_by_magic_bytes(data, mime):
    assert validate_completion_photo(data) == mime


def test_empty_photo_is_422():
    with pytest.raises(CompletionRefused) as e:
        validate_completion_photo(b"")
    assert (e.value.code, e.value.http_status) == ("photo_empty", 422)


def test_oversized_photo_is_413():
    with pytest.raises(CompletionRefused) as e:
        validate_completion_photo(JPEG + b"0" * COMPLETION_PHOTO_MAX_BYTES)
    assert (e.value.code, e.value.http_status) == ("photo_too_large", 413)


def test_limit_fits_edge_body_limit():
    """Edge (profk nginx) режет тело запроса на 10 МБ; фото + multipart-обвязка
    обязаны пролезать, иначе 413 придёт от edge, мимо логов API."""
    assert COMPLETION_PHOTO_MAX_BYTES <= 9 * 1024 * 1024


@pytest.mark.parametrize("data", [WEBP, b"<svg onload=alert(1)>", b"GIF89a" + b"0" * 10])
def test_non_jpeg_png_is_415(data):
    """webp распознаётся, но media-service его не хранит (BUG-132); gif/svg —
    не фото «после»."""
    with pytest.raises(CompletionRefused) as e:
        validate_completion_photo(data)
    assert (e.value.code, e.value.http_status) == ("unsupported_photo_type", 415)


# ── parse_idempotency_key ──────────────────────────────────────────────


def test_idempotency_key_is_normalized_uuid():
    raw = "6F9619FF-8B86-D011-B42D-00C04FC964FF"
    assert parse_idempotency_key(raw) == raw.lower()


@pytest.mark.parametrize("raw", ["", "abc", "x" * 36, None])
def test_bad_idempotency_key_is_422(raw):
    with pytest.raises(CompletionRefused) as e:
        parse_idempotency_key(raw)
    assert (e.value.code, e.value.http_status) == ("invalid_idempotency_key", 422)


# ── completion_idempotency ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_roundtrip_with_day_ttl(monkeypatch):
    redis = FakeRedis()
    _use(monkeypatch, redis)
    assert await idem.load(41, "260925-001", "k") is None

    await idem.save(41, "260925-001", "k", idem.STATE_UPLOADED, 501)
    rec = await idem.load(41, "260925-001", "k")
    assert rec == idem.Record(state=idem.STATE_UPLOADED, media_id=501)
    assert set(redis.ttl.values()) == {idem.RECORD_TTL_SECONDS}
    assert idem.RECORD_TTL_SECONDS == 24 * 3600


@pytest.mark.asyncio
async def test_record_is_scoped_by_executor_and_request(monkeypatch):
    """Чужой ключ не «воспроизводит» результат: ключ клиента — только часть
    Redis-ключа, рядом с исполнителем и номером заявки."""
    _use(monkeypatch, FakeRedis())
    await idem.save(41, "260925-001", "k", idem.STATE_DONE, 501)
    assert await idem.load(42, "260925-001", "k") is None
    assert await idem.load(41, "260925-002", "k") is None


@pytest.mark.asyncio
async def test_lock_is_exclusive_per_request_and_released(monkeypatch):
    _use(monkeypatch, FakeRedis())
    first = await idem.acquire_lock("260925-001")
    assert first.acquired and not first.degraded

    second = await idem.acquire_lock("260925-001")
    assert not second.acquired and not second.degraded

    await idem.release_lock(first)
    third = await idem.acquire_lock("260925-001")
    assert third.acquired


@pytest.mark.asyncio
async def test_release_does_not_drop_foreign_lock(monkeypatch):
    """Лок истёк по TTL и его взял другой запрос — наш release его не снимает."""
    redis = FakeRedis()
    _use(monkeypatch, redis)
    mine = await idem.acquire_lock("260925-001")
    redis.data.clear()  # TTL истёк
    theirs = await idem.acquire_lock("260925-001")
    await idem.release_lock(mine)
    assert not (await idem.acquire_lock("260925-001")).acquired
    await idem.release_lock(theirs)


@pytest.mark.asyncio
async def test_redis_down_is_fail_open(monkeypatch, caplog):
    """Redis недоступен → хранилище не мешает закрыть заявку (degraded-лок,
    записи нет), а в лог уходит класс ошибки без сырого исключения."""
    _use(monkeypatch, BrokenRedis())
    lock = await idem.acquire_lock("260925-001")
    assert lock.acquired and lock.degraded
    assert await idem.load(41, "260925-001", "k") is None
    await idem.save(41, "260925-001", "k", idem.STATE_DONE, 1)
    await idem.release_lock(lock)
    assert "ConnectionError" in caplog.text
    assert "redis down" not in caplog.text


@pytest.mark.asyncio
async def test_garbage_record_is_ignored(monkeypatch):
    redis = FakeRedis()
    _use(monkeypatch, redis)
    redis.data[idem.record_key(41, "260925-001", "k")] = "{not json"
    assert await idem.load(41, "260925-001", "k") is None


@pytest.mark.asyncio
async def test_release_is_single_atomic_compare_and_delete(monkeypatch):
    """Снятие лока — один EVAL (if get == token then del), а не GET+DEL двумя
    командами: между ними лок мог истечь и достаться другому запросу."""
    from unittest.mock import AsyncMock

    redis = FakeRedis()
    _use(monkeypatch, redis)
    lock = await idem.acquire_lock("260925-001")

    spy = AsyncMock(wraps=redis.eval)
    redis.eval = spy
    redis.get = AsyncMock(side_effect=AssertionError("GET при снятии лока"))
    redis.delete = AsyncMock(side_effect=AssertionError("DEL при снятии лока"))
    await idem.release_lock(lock)

    spy.assert_awaited_once()
    _script, numkeys, key, token = spy.await_args.args
    assert (numkeys, key, token) == (1, "exec_complete:lock:260925-001", lock.token)
    assert "exec_complete:lock:260925-001" not in redis.data
