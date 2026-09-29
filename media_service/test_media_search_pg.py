"""Ручной поиск фото (владелец, через VPN) — на настоящем PostgreSQL.

Ревью медиасервиса 2026-09-28: юнит-тестов у поиска не было, а на sqlite
видно не всё.
- `?tags=` падал 500: колонка tags — `json`, у json в PG нет оператора `@>`;
- текст искался ILIKE — в локали C он не сворачивает кириллицу;
- timeline падал 500 целиком из-за одной строки с NULL в file_size/имени.

Запуск как у дрейф-гейта: MEDIA_PG_DRIFT_URL=postgresql+psycopg2://... pytest
(без URL — skip; с MEDIA_REQUIRE_PG_TESTS=1 — ошибка сбора).
"""
from __future__ import annotations

import os
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

PG_URL = os.environ.get("MEDIA_PG_DRIFT_URL")
if not PG_URL:
    if os.environ.get("MEDIA_REQUIRE_PG_TESTS") == "1":
        raise RuntimeError("MEDIA_REQUIRE_PG_TESTS=1, но MEDIA_PG_DRIFT_URL не задан")
    pytest.skip("MEDIA_PG_DRIFT_URL не задан (тест только для PostgreSQL)", allow_module_level=True)

from app.models.media import Base, MediaFile  # noqa: E402
from app.schemas.media import MediaTimelineItem  # noqa: E402
from app.services import media_search  # noqa: E402
from app.services.media_search import MediaSearchService  # noqa: E402

C_DB = "uk_media_search_c"


def _c_locale_url() -> str:
    """Отдельная БД с LC_COLLATE/LC_CTYPE = C — как uk_media на проде: в такой
    базе ILIKE/lower() не сворачивают кириллицу, и поиск «течёт» не находил
    «ТЕЧЁТ». В en_US-базе CI баг был бы невидим."""
    admin = create_engine(PG_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{C_DB}"'))
        conn.execute(text(
            f"CREATE DATABASE \"{C_DB}\" TEMPLATE template0 LC_COLLATE 'C' LC_CTYPE 'C'"
        ))
    admin.dispose()
    return PG_URL.rsplit("/", 1)[0] + f"/{C_DB}"


@pytest.fixture
def pg_session_factory(monkeypatch):
    engine = create_engine(_c_locale_url())
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    @contextmanager
    def _ctx():
        db = factory()
        try:
            yield db
            db.commit()
        finally:
            db.close()

    monkeypatch.setattr(media_search, "get_db_context", _ctx)
    yield factory
    engine.dispose()


def _add(factory, **overrides):
    n = overrides.pop("n")
    row = dict(
        telegram_channel_id=-100, telegram_message_id=n, telegram_file_id=f"F{n}",
        file_type="photo", original_filename=f"p{n}.jpg", file_size=100,
        mime_type="image/jpeg", request_number="260928-001", uploaded_by_user_id=1,
        category="request_photo", tags=[], upload_source="api", status="active",
    )
    row.update(overrides)
    with factory() as db:
        db.add(MediaFile(**row))
        db.commit()


async def test_tag_filter_works_on_postgres(pg_session_factory):
    _add(pg_session_factory, n=1, tags=["протечка", "кухня"])
    _add(pg_session_factory, n=2, tags=["свет"])
    res = await MediaSearchService().search_media(tags=["протечка"])
    assert [r["telegram_file_id"] for r in res["results"]] == ["F1"]


async def test_text_search_is_case_insensitive_for_cyrillic(pg_session_factory):
    _add(pg_session_factory, n=1, description="ТЕЧЁТ кран на кухне")
    _add(pg_session_factory, n=2, description="нет света")
    res = await MediaSearchService().search_media(query="течёт")
    assert [r["telegram_file_id"] for r in res["results"]] == ["F1"]


async def test_text_search_escapes_like_wildcards(pg_session_factory):
    _add(pg_session_factory, n=1, description="скидка 50%")
    _add(pg_session_factory, n=2, description="скидка 500")
    res = await MediaSearchService().search_media(query="50%")
    assert [r["telegram_file_id"] for r in res["results"]] == ["F1"]


async def test_timeline_tolerates_null_size_and_name(pg_session_factory):
    _add(pg_session_factory, n=1, file_size=None, original_filename=None)
    _add(pg_session_factory, n=2)
    timeline = await MediaSearchService().get_request_media_timeline("260928-001")
    items = [MediaTimelineItem(**item) for item in timeline]
    assert [i.id for i in items] and items[0].file_size is None


async def test_statistics_on_postgres(pg_session_factory):
    _add(pg_session_factory, n=1)
    stats = await MediaSearchService().get_media_statistics()
    assert stats["total_files"] == 1
