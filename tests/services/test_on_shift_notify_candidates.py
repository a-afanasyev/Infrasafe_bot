"""П6-хвост / WR-05 — «кто сейчас на смене» одним запросом, а не N+1.

Рассылка «заявку взял другой» тянула ВСЕХ approved-пользователей и отсеивала
их циклом, вызывая `is_on_shift_now_sync` на каждого. Дороже, чем сказано в
пункте: не только полный скан, но и запрос на человека.

Гейт считает запросы к БД: свойство «одним запросом» иначе не проверить, а
именно оно и было предметом.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services.request_handler_service import RequestHandlerService

# `_on_shift_filter` сравнивает с наивным `datetime.now()` — держим тестовое
# окно в той же шкале, иначе сравнение tz-aware с naive упадёт.
NOW = datetime.now()
ON_SHIFT = [1, 2, 3]
OFF_SHIFT = [4, 5, 6, 7, 8]


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    s = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    yield s
    s.close()


@pytest.fixture()
def crew(session):
    for uid in ON_SHIFT + OFF_SHIFT:
        session.add(User(
            id=uid, telegram_id=uid, first_name=f"E{uid}", roles='["executor"]',
            active_role="executor", status="approved", language="ru",
        ))
    # На смене прямо сейчас
    for uid in ON_SHIFT:
        session.add(Shift(user_id=uid, status="active",
                          start_time=NOW - timedelta(hours=1),
                          end_time=NOW + timedelta(hours=7)))
    # Смена уже закончилась — «на смене» такой человек не считается
    session.add(Shift(user_id=OFF_SHIFT[0], status="active",
                      start_time=NOW - timedelta(hours=9),
                      end_time=NOW - timedelta(hours=1)))
    # Запланированная, ещё не начатая
    session.add(Shift(user_id=OFF_SHIFT[1], status="planned",
                      start_time=NOW + timedelta(hours=1),
                      end_time=NOW + timedelta(hours=9)))
    session.commit()


@contextmanager
def count_queries(engine):
    counter = {"n": 0}

    def _on_exec(conn, cursor, statement, params, context, executemany):
        counter["n"] += 1

    event.listen(engine, "after_cursor_execute", _on_exec)
    try:
        yield counter
    finally:
        event.remove(engine, "after_cursor_execute", _on_exec)


def test_returns_exactly_the_people_on_shift_now(session, crew):
    service = RequestHandlerService(session)

    got = {u.id for u in service.list_on_shift_notify_candidates(now=NOW)}

    assert got == set(ON_SHIFT), (
        "в получатели попали не те: закончившаяся и ещё не начатая смены "
        "«на смене» не считаются"
    )


def test_costs_one_query_regardless_of_crew_size(session, crew, engine):
    """Суть WR-05: стоимость не растёт с числом пользователей."""
    service = RequestHandlerService(session)
    session.expire_all()

    with count_queries(engine) as queries:
        service.list_on_shift_notify_candidates(now=NOW)

    assert queries["n"] == 1, (
        f"{queries['n']} запросов на {len(ON_SHIFT) + len(OFF_SHIFT)} человек — "
        "проверка смены осталась в цикле по пользователям"
    )


def test_two_shifts_do_not_duplicate_a_person(session, crew):
    """Дубли получателей = дубли сообщений: `distinct` тут не украшение."""
    session.add(Shift(user_id=ON_SHIFT[0], status="active",
                      start_time=NOW - timedelta(minutes=30),
                      end_time=NOW + timedelta(hours=3)))
    session.commit()
    service = RequestHandlerService(session)

    ids = [u.id for u in service.list_on_shift_notify_candidates(now=NOW)]

    assert len(ids) == len(set(ids)) == len(ON_SHIFT)
