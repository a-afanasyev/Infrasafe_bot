"""AUD7-SEC-05: проверка и потребление OTP — одна атомарная операция в Redis.

Раньше `verify_otp` делал HGETALL → сравнение → HINCRBY/DEL тремя запросами:
два параллельных верных кода давали два успеха, а параллельные неверные
читали один и тот же счётчик и все получали «N attempts remaining» по
устаревшему значению. Тест идёт на НАСТОЯЩИЙ Redis (локальный uk-redis /
сервис CI) — двойник Lua не исполняет и проверял бы только себя.
"""
from __future__ import annotations

import asyncio
import re
import uuid

import pytest
import redis.asyncio as aioredis

from uk_management_bot.api.auth import service as auth_service
from uk_management_bot.config.settings import settings

pytestmark = pytest.mark.asyncio


async def _redis_available() -> bool:
    r = aioredis.from_url(getattr(settings, "REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
    try:
        return bool(await r.ping())
    except Exception:  # noqa: BLE001 — любая сетевая ошибка = Redis нет, тест пропускаем
        return False
    finally:
        await r.aclose()


@pytest.fixture()
async def user_id():
    if not await _redis_available():
        pytest.skip("Redis недоступен — тест атомарности OTP требует настоящий Redis")
    uid = 900_000_000 + uuid.uuid4().int % 1_000_000
    yield uid
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    await r.delete(f"mfa:otp:{uid}")
    await r.aclose()


async def test_concurrent_correct_codes_yield_exactly_one_success(user_id):
    await auth_service.store_otp(user_id, "123456")
    results = await asyncio.gather(
        auth_service.verify_otp(user_id, "123456"),
        auth_service.verify_otp(user_id, "123456"),
    )
    assert [ok for ok, _ in results].count(True) == 1, results


async def test_concurrent_wrong_codes_consume_distinct_attempts(user_id):
    await auth_service.store_otp(user_id, "123456")
    n = auth_service.MFA_MAX_ATTEMPTS
    results = await asyncio.gather(*[auth_service.verify_otp(user_id, "000000") for _ in range(n)])
    assert all(ok is False for ok, _ in results)
    remaining = sorted(
        int(m.group(1)) if (m := re.search(r"(\d+) attempts remaining", msg)) else 0
        for _, msg in results
    )
    # Каждая попытка обязана видеть СВОЙ остаток: n-1, …, 1, 0 — а не один и тот же.
    assert remaining == list(range(n)), results
    # Исчерпанный OTP удаляется — верный код после этого уже не проходит.
    ok, _ = await auth_service.verify_otp(user_id, "123456")
    assert ok is False
