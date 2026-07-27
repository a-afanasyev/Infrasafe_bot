"""П6d / AUD5-CODE-11 — страницу режет БД, а не Python.

`handle_pagination` показывает пять строк, а грузил в память ВСЕ заявки
пользователя. Соседний `handle_back_to_list` уже давно на БД-пагинации.

Гейт смотрит не на форму запроса, а на наблюдаемое следствие: сколько строк
`Request` реально материализовалось в сессии. При срезе в Python их столько
же, сколько у пользователя всего.

Отдельно закреплена семантика, которую легко «причесать» к соседу и молча
сломать: здесь status-фильтр применяется для ОБЕИХ ролей, а сортировка всегда
по created_at desc — без case-приоритета для «all».
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services.request_handler_service import RequestHandlerService

TOTAL = 50
PAGE = 5
BASE_TIME = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    yield s
    s.close()
    engine.dispose()


@pytest.fixture()
def applicant(session):
    user = User(
        id=1, telegram_id=1, first_name="Resident", roles='["applicant"]',
        active_role="applicant", status="approved", language="ru",
    )
    session.add(user)
    # created_at убывает с номером: 001 — самая свежая.
    for i in range(1, TOTAL + 1):
        session.add(Request(
            request_number=f"260601-{i:03d}",
            user_id=1, category="plumbing", description="d", urgency="low",
            status="Новая" if i % 2 else "Закрыта",
            created_at=BASE_TIME - timedelta(minutes=i),
        ))
    session.commit()
    return user


@contextmanager
def count_loaded_requests(session):
    """Считает строки `Request`, реально поднятые из БД за время блока.

    ⚠️ Наивная версия этого счётчика (размер `identity_map` после вызова) была
    ПУСТЫШКОЙ: карта хранит слабые ссылки, и лишние 45 объектов успевали
    исчезнуть до проверки — тест зеленел на срезе в Python. Событие
    `loaded_as_persistent` срабатывает в момент загрузки и от сборщика мусора
    не зависит.
    """
    counter = {"n": 0}

    def _on_load(_session, instance):
        if isinstance(instance, Request):
            counter["n"] += 1

    # Отсоединяем только заявки: иначе уже загруженные строки не поднимутся
    # заново и счётчик покажет ноль. `expunge_all()` здесь нельзя — он отцепит
    # и пользователя, которого запрос читает.
    for obj in list(session.identity_map.values()):
        if isinstance(obj, Request):
            session.expunge(obj)
    event.listen(session, "loaded_as_persistent", _on_load)
    try:
        yield counter
    finally:
        event.remove(session, "loaded_as_persistent", _on_load)


class TestDatabaseDoesTheSlicing:
    def test_only_one_page_of_rows_is_loaded(self, session, applicant):
        """Главный гейт: из БД поднимается страница, а не весь список."""
        service = RequestHandlerService(session)

        with count_loaded_requests(session) as loaded:
            total, page = service.paginate_pagination_requests(
                applicant, "applicant", None, offset=PAGE, limit=PAGE
            )

        assert total == TOTAL
        assert len(page) == PAGE
        assert loaded["n"] == PAGE, (
            f"из БД поднято {loaded['n']} заявок из {TOTAL} ради пяти строк "
            "экрана — срез делает Python, а не БД"
        )

    def test_page_content_matches_the_requested_offset(self, session, applicant):
        """Страница 2 — это записи 6..10 по той же сортировке, что и раньше."""
        service = RequestHandlerService(session)

        _, page = service.paginate_pagination_requests(
            applicant, "applicant", None, offset=PAGE, limit=PAGE
        )

        assert [r.request_number for r in page] == [
            f"260601-{i:03d}" for i in range(6, 11)
        ]

    def test_last_page_is_short_and_beyond_is_empty(self, session, applicant):
        service = RequestHandlerService(session)

        total, last = service.paginate_pagination_requests(
            applicant, "applicant", None, offset=TOTAL - 2, limit=PAGE
        )
        assert (total, len(last)) == (TOTAL, 2)

        total, beyond = service.paginate_pagination_requests(
            applicant, "applicant", None, offset=TOTAL + PAGE, limit=PAGE
        )
        assert (total, beyond) == (TOTAL, [])


class TestSemanticsUnchanged:
    """Сортировка и фильтры — ровно те, что были у полного списка."""

    def test_sorted_by_created_at_desc_without_status_priority(self, session, applicant):
        service = RequestHandlerService(session)

        _, page = service.paginate_pagination_requests(
            applicant, "applicant", "all", offset=0, limit=PAGE
        )

        # Первая — самая свежая, и «Закрыта» НЕ уезжает вниз: case-приоритета
        # здесь нет (в отличие от paginate_back_to_list с фильтром «all»).
        assert [r.request_number for r in page] == [
            f"260601-{i:03d}" for i in range(1, 6)
        ]
        assert any(r.status == "Закрыта" for r in page)

    def test_active_filter_narrows_the_total_too(self, session, applicant):
        service = RequestHandlerService(session)

        total, page = service.paginate_pagination_requests(
            applicant, "applicant", "active", offset=0, limit=PAGE
        )

        assert total == TOTAL // 2, "count обязан считать по тому же фильтру"
        assert all(r.status == "Новая" for r in page)
