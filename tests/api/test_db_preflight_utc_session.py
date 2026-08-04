"""ARCH-137 A7: preflight-инвариант «сессия БД в UTC».

Пока сессия UTC, naive/aware-расхождение драйверов (psycopg2 читает session
TimeZone, asyncpg игнорирует) не имеет почвы — гейт стоит от тихой смены
`TimeZone` на хосте/в образе Postgres.

Два уровня:
  * юнит на allowlist: сравнение НЕ строкой с одним написанием (прод отдаёт
    `UTC`, бэклог ожидал `Etc/UTC` — оба валидны), и НЕ «смещением сейчас»
    (Europe/London зимой даёт ноль и прошёл бы);
  * живой Postgres (`POSTGRES_TEST_URL`, skip без него — паттерн
    test_webhook_outbox_pg_concurrency): дефолтная сессия CI-постгреса обязана
    проходить гейт, а сессия с подменённой зоной — обязана падать.
"""

import os

import pytest
from sqlalchemy import create_engine, text

from uk_management_bot.dbops.db_preflight import session_timezone_ok


@pytest.mark.parametrize("tz", ["UTC", "Etc/UTC", "GMT", "Etc/GMT", "UCT", "Universal", "Zulu", "utc", " UTC "])
def test_utc_aliases_pass(tz):
    assert session_timezone_ok(tz)


@pytest.mark.parametrize("tz", ["Asia/Tashkent", "Europe/London", "Etc/GMT-5", "localtime", ""])
def test_non_utc_zones_fail(tz):
    """Europe/London — главный контрпример: зимой offset 0, но это НЕ UTC."""
    assert not session_timezone_ok(tz)


def _pg_url() -> str | None:
    url = os.getenv("POSTGRES_TEST_URL", "")
    return url if url.startswith("postgresql") else None


def test_live_pg_session_timezone_is_utc():
    url = _pg_url()
    if not url:
        pytest.skip("нет POSTGRES_TEST_URL — PG-инвариант проверяется в CI")
    engine = create_engine(url, pool_pre_ping=False)
    try:
        with engine.connect() as conn:
            tz = conn.execute(text("SHOW TimeZone")).scalar_one()
            assert session_timezone_ok(tz), f"сессия CI-постгреса не UTC: {tz!r}"
            # Контроль чувствительности гейта: подменённая зона обязана падать.
            conn.execute(text("SET TIME ZONE 'Asia/Tashkent'"))
            spoofed = conn.execute(text("SHOW TimeZone")).scalar_one()
            assert not session_timezone_ok(spoofed)
    finally:
        engine.dispose()
