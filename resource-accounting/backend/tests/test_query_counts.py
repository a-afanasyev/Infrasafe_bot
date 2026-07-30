"""AUD6-P2-15/16: число SQL-запросов не растёт с числом счётчиков.

Ведомость (и импорт) делали `get_previous_accepted` на каждый счётчик — N+1 на
главной рабочей странице роли. Регресс ловится сравнением счётчиков запросов
для маленькой и большой выборки: любое возвращение per-meter запроса даст рост.
"""

from contextlib import contextmanager

from sqlalchemy import event

from app.db import engine
from tests.conftest import make_meter, make_object, make_period


@contextmanager
def _count_queries():
    counter = {"n": 0}

    def _before(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", _before)


def test_worksheet_query_count_independent_of_meter_count(admin):
    obj = make_object(admin, "QC-объект")
    make_period(admin, "2036-01")
    make_period(admin, "2036-02")

    def _add_meters(prefix: str, n: int) -> None:
        for i in range(n):
            m = make_meter(admin, f"{prefix}{i}", obj["id"])
            admin.put(
                f"/v1/meters/{m['id']}/readings/2036-01",
                json={"value": "10", "read_at": "2036-01-20"},
            )

    _add_meters("QC-A", 2)
    with _count_queries() as small:
        assert admin.get("/v1/periods/2036-02/worksheet").status_code == 200

    _add_meters("QC-B", 6)
    with _count_queries() as big:
        assert admin.get("/v1/periods/2036-02/worksheet").status_code == 200

    assert big["n"] == small["n"], (
        f"ведомость: {small['n']} запросов при малой выборке против {big['n']} "
        "при большой — вернулся per-meter запрос (N+1)"
    )
