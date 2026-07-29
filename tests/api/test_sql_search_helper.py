"""Общий хелпер регистронезависимого поиска (`utils/sql_search.py`).

Предыстория — `docs/bugs-2026-07-28.md`, BUG-1: прод-кластер создан с
`lc_ctype=C`, а в этой локали `lower()`/`ILIKE` сворачивают регистр ТОЛЬКО для
ASCII. Русскоязычная система с поиском по ФИО в такой локали просто не находит
русские имена. Сначала это чинилось точечно в домене «Жители»; здесь та же
логика вынесена в один хелпер и раскатана на ВСЕ поиски по пользовательскому
тексту (см. `test_search_no_raw_ilike.py`).

Сьют гоняется на sqlite, где ICU нет и не нужна, поэтому проверяются ДВЕ разные
вещи: поведение (на sqlite) и **форма скомпилированного SQL** под postgresql —
именно она и была сломана, а sqlite-прогон её не ловит.
"""

from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite

from uk_management_bot.database.models.user import User
from uk_management_bot.utils import sql_search


def _sql(clause, dialect) -> str:
    return str(
        select(User).where(clause).compile(
            dialect=dialect, compile_kwargs={"literal_binds": True},
        )
    )


class TestGeneratedSql:

    def test_postgres_folds_case_via_icu_collation(self):
        """На PG регистр сворачивает lower() ПОД ICU-коллацией, не голый ILIKE."""
        sql = _sql(
            sql_search.ci_contains(User.first_name, "%Админ%", is_postgres=True),
            postgresql.dialect(),
        )
        assert 'COLLATE "und-x-icu"' in sql
        assert "lower(" in sql.lower()
        # Голый ILIKE — ровно то, что не работало в локали C.
        assert "ILIKE" not in sql.upper()

    def test_postgres_lowercases_both_sides(self):
        """Шаблон опускается тоже — иначе сравнение никогда не сойдётся."""
        sql = _sql(
            sql_search.ci_contains(User.first_name, "%Админ%", is_postgres=True),
            postgresql.dialect(),
        )
        assert "%админ%" in sql
        assert "%Админ%" not in sql

    def test_sqlite_keeps_ilike_and_original_case(self):
        """На sqlite ICU нет: ILIKE эмулируется слоем SQLAlchemy, и шаблон
        НЕ опускается — тамошний lower() тоже ASCII-only, опущенный заранее
        шаблон перестал бы находить кириллицу вообще."""
        sql = _sql(
            sql_search.ci_contains(User.first_name, "%Админ%", is_postgres=False),
            sqlite.dialect(),
        )
        assert "und-x-icu" not in sql
        assert "%Админ%" in sql

    def test_escape_hatch_survives_the_fix(self):
        """`%` от пользователя остаётся литералом, а не «совпадает со всем»."""
        pattern = f"%{sql_search.escape_like('%')}%"
        sql = _sql(
            sql_search.ci_contains(User.first_name, pattern, is_postgres=True),
            postgresql.dialect(),
        )
        assert r"\%" in sql


class TestEscapeLike:

    def test_escapes_all_three_metacharacters(self):
        assert sql_search.escape_like("100%_a\\b") == "100\\%\\_a\\\\b"

    def test_leaves_plain_text_alone(self):
        assert sql_search.escape_like("Иванов") == "Иванов"


class TestDialectDetection:
    """`is_postgres` обязан работать И на AsyncSession (API), И на sync Session
    (бот) — хелпер применяется в обоих слоях."""

    class _Dialect:
        def __init__(self, name):
            self.name = name

    class _Bind:
        def __init__(self, name):
            self.dialect = TestDialectDetection._Dialect(name)

    class _SessionWithBind:
        def __init__(self, name):
            self.bind = TestDialectDetection._Bind(name)

    class _SessionWithGetBind:
        """Сессия из sessionmaker(binds=...) — атрибута `bind` нет."""
        bind = None

        def __init__(self, name):
            self._name = name

        def get_bind(self):
            return TestDialectDetection._Bind(self._name)

    def test_detects_postgres_via_bind(self):
        assert sql_search.is_postgres(self._SessionWithBind("postgresql")) is True

    def test_detects_sqlite_via_bind(self):
        assert sql_search.is_postgres(self._SessionWithBind("sqlite")) is False

    def test_falls_back_to_get_bind(self):
        assert sql_search.is_postgres(self._SessionWithGetBind("postgresql")) is True

    def test_unknown_session_is_not_postgres(self):
        """Неизвестная форма сессии = НЕ postgres: безопасный дефолт, поведение
        остаётся прежним (ILIKE), а не падение запроса."""
        assert sql_search.is_postgres(object()) is False
