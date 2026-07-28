"""Регистронезависимый поиск жителей честен для кириллицы (локаль `C` у прода).

Найдено прод-проверкой раздела на profk 2026-07-28: `?q=Админ` находил
«Администратор», `?q=админ` — нет, при том что латиница (`nazya`/`NAZYA`)
искалась в обоих регистрах. Причина не в коде поиска, а в кластере: он создан
с `lc_ctype=C`, а в этой локали `lower()`/`ILIKE` сворачивают регистр ТОЛЬКО
для ASCII:

    profk_management=# SELECT lower('АДМИН');            -- → 'АДМИН'
    profk_management=# SELECT 'Администратор' ILIKE '%админ%';  -- → false

Система русскоязычная, поэтому «поиск по ФИО» без кириллицы — нерабочая
функция. Лечится ICU-коллацией в самом выражении (`und-x-icu` есть в
postgres:15), без миграции и без пересоздания кластера.

Сьют `tests/api` гоняется на sqlite, где ICU нет и не нужна, поэтому здесь
проверяются ДВЕ разные вещи:
  * поведение — на sqlite (регистронезависимость как таковая);
  * форма SQL — компиляцией под диалект postgresql, потому что именно она и
    была сломана на проде, а sqlite-прогон её не поймал бы.
"""
import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.user import User
from uk_management_bot.services.residents import queries

BASE = "/api/v2/residents"


def _compile(is_postgres: bool, dialect) -> str:
    q = queries._apply_list_filters(
        select(User),
        status=None, verification_status=None,
        yard_id=None, building_id=None, apartment_id=None,
        q="Админ", is_postgres=is_postgres,
    )
    return str(q.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))


class TestGeneratedSql:

    def test_postgres_path_folds_case_via_icu_collation(self):
        """На PG регистр сворачивает lower() ПОД ICU-коллацией, не голый ILIKE."""
        sql = _compile(True, postgresql.dialect())
        assert 'COLLATE "und-x-icu"' in sql
        assert "lower(" in sql.lower()
        # Голый ILIKE — ровно то, что не работало в локали C.
        assert "ILIKE" not in sql.upper()

    def test_postgres_pattern_is_lowercased(self):
        """Обе стороны сравнения приводятся к нижнему регистру, не только колонка."""
        sql = _compile(True, postgresql.dialect())
        assert "%админ%" in sql
        assert "%Админ%" not in sql

    def test_sqlite_pattern_keeps_original_case(self):
        """На sqlite шаблон НЕ опускается: тамошний lower() тоже ASCII-only,
        и предварительно опущенный шаблон перестал бы находить кириллицу."""
        sql = _compile(False, sqlite.dialect())
        assert "%Админ%" in sql.replace("АДМИН", "")

    def test_sqlite_path_keeps_ilike(self):
        """На sqlite ICU-коллации нет — там ILIKE эмулируется слоем SQLAlchemy."""
        sql = _compile(False, sqlite.dialect())
        assert "und-x-icu" not in sql

    def test_escaping_survives_the_fix(self):
        """`%` от пользователя остаётся литералом, а не «совпадает со всем»."""
        q = queries._apply_list_filters(
            select(User),
            status=None, verification_status=None,
            yard_id=None, building_id=None, apartment_id=None,
            q="%", is_postgres=True,
        )
        sql = str(q.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        assert r"\%" in sql


@pytest.mark.asyncio
class TestBehaviourOnSqlite:

    async def test_case_insensitive_latin(self, client, db_session: AsyncSession):
        u = User(telegram_id=7701, first_name="Nazya", last_name="Karimova",
                 roles='["applicant"]', status="approved")
        db_session.add(u)
        await db_session.commit()

        for term in ("nazya", "NAZYA", "Nazya"):
            data = (await client.get(f"{BASE}?q={term}")).json()
            assert data["total"] == 1, term

    async def test_dialect_detection_defaults_to_non_postgres(self, db_session):
        """Санити: sqlite-сессия не должна уходить в PG-ветку."""
        assert queries._is_postgres(db_session) is False
