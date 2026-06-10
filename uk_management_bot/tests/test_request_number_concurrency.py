"""PR5: конкурентность генератора номеров — только реальный PostgreSQL.

SQLite-тесты (test_request_number_service.py) проверяют семантику, но
advisory/row-locks там не работают (single-writer). Этот контур гоняет
параллельные транзакции против того же DATABASE_URL, что у бота:
N конкурентных созданий → номера уникальны и непрерывны; rollover 999→1000.

Используется фиктивный день 990101 (2099-01-01) — не пересекается с
реальными данными; всё созданное удаляется в teardown.
"""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from uk_management_bot.services.request_number_service import RequestNumberService

FAKE_DAY = date(2099, 1, 1)
FAKE_PREFIX = "990101"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url or not url.startswith("postgresql"):
        pytest.skip("postgres-only concurrency test (DATABASE_URL not postgres)")
    return url


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(_database_url(), future=True, pool_size=12, max_overflow=4)
    # Таблица счётчика: в dev-БД миграция 017 может быть ещё не применена —
    # тест самодостаточен (DDL идентичен модели/миграции).
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS request_number_counters ("
            " day_prefix VARCHAR(6) PRIMARY KEY,"
            " last_seq INTEGER NOT NULL)"
        ))
    yield eng
    eng.dispose()


@pytest.fixture()
def clean_fake_day(engine):
    def _wipe():
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM requests WHERE request_number LIKE :p"),
                         {"p": f"{FAKE_PREFIX}-%"})
            conn.execute(text("DELETE FROM request_number_counters WHERE day_prefix = :p"),
                         {"p": FAKE_PREFIX})
            conn.execute(text("DELETE FROM users WHERE username LIKE 'pr5-test-%'"))
    _wipe()
    yield
    _wipe()


@pytest.fixture()
def test_user_id(engine, clean_fake_day):
    with engine.begin() as conn:
        return conn.execute(text(
            "INSERT INTO users (telegram_id, username, first_name, role, roles,"
            " active_role, status, language, verification_status, created_at)"
            " VALUES (:tg, :un, 'PR5', 'applicant', '[\"applicant\"]',"
            " 'applicant', 'approved', 'ru', 'pending', now()) RETURNING id"
        ), {"tg": int(uuid.uuid4().int % 10**9) + 10**10,
            "un": f"pr5-test-{uuid.uuid4().hex[:8]}"}).scalar_one()


def test_parallel_creates_unique_and_contiguous(engine, test_user_id):
    """N параллельных транзакций (номер + INSERT заявки в одной транзакции):
    все номера уникальны и непрерывны 001..N — counter сериализует."""
    N = 24
    Session = sessionmaker(bind=engine, future=True)

    def create_one(_):
        s = Session()
        try:
            number = RequestNumberService.next_number(s, FAKE_DAY)
            s.execute(text(
                "INSERT INTO requests (request_number, user_id, category, status,"
                " description, urgency, is_returned, manager_confirmed, created_at)"
                " VALUES (:n, :u, 'c', 'Новая', 'd', 'low', false, false, now())"
            ), {"n": number, "u": test_user_id})
            s.commit()
            return number
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        numbers = list(pool.map(create_one, range(N)))

    assert len(set(numbers)) == N, f"duplicates: {sorted(numbers)}"
    suffixes = sorted(int(n.split("-")[1]) for n in numbers)
    assert suffixes == list(range(1, N + 1)), f"gaps/holes: {suffixes}"


def test_rollover_999_to_1000_under_postgres(engine, test_user_id):
    """Числовой rollover: счётчик на 999 → следующие 1000, 1001 (лексикографический
    MAX здесь выдал бы повтор 999+1 от '999' < '1000' порядка)."""
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO request_number_counters (day_prefix, last_seq)"
            " VALUES (:p, 999) ON CONFLICT (day_prefix)"
            " DO UPDATE SET last_seq = 999"
        ), {"p": FAKE_PREFIX})

    Session = sessionmaker(bind=engine, future=True)
    s = Session()
    try:
        n1 = RequestNumberService.next_number(s, FAKE_DAY)
        n2 = RequestNumberService.next_number(s, FAKE_DAY)
        s.commit()
    finally:
        s.close()
    assert (n1, n2) == (f"{FAKE_PREFIX}-1000", f"{FAKE_PREFIX}-1001")


def test_no_reuse_after_delete_max_postgres(engine, test_user_id):
    """Gap-safe на реальном Postgres: удаление заявки с MAX-суффиксом не
    приводит к повторной выдаче (смертельный кейс COUNT(*)+1 стратегии)."""
    Session = sessionmaker(bind=engine, future=True)
    s = Session()
    try:
        n1 = RequestNumberService.next_number(s, FAKE_DAY)
        s.execute(text(
            "INSERT INTO requests (request_number, user_id, category, status,"
            " description, urgency, is_returned, manager_confirmed, created_at)"
            " VALUES (:n, :u, 'c', 'Новая', 'd', 'low', false, false, now())"
        ), {"n": n1, "u": test_user_id})
        s.commit()

        s.execute(text("DELETE FROM requests WHERE request_number = :n"), {"n": n1})
        s.commit()

        n2 = RequestNumberService.next_number(s, FAKE_DAY)
        s.commit()
    finally:
        s.close()
    assert n2 != n1
    assert int(n2.split("-")[1]) == int(n1.split("-")[1]) + 1
