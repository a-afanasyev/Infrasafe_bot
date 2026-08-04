"""Read-only startup preflight (PR-7 / F-01).

Сравнивает применённую ревизию Alembic (``alembic_version`` в БД) с ревизией,
зашитой в образ на этапе сборки (``EXPECTED_ALEMBIC_HEAD``, см. Dockerfile.*).
Если они расходятся — значит `migrate`-job перед этим деплоем не запускали
(или запускали не тот образ), и раннему обрыву тут дешевле, чем падению
первого прод-запроса, дошедшего до отсутствующей колонки/таблицы, через
неопределённое время после старта.

Подключается runtime credential'ом контейнера (только SELECT, DDL не нужен) —
не импортирует uk_management_bot.database.session/config.settings, чтобы не
тянуть полный движок приложения и валидацию прочих секретов ради одной проверки.
"""
import os
import sys

from sqlalchemy import create_engine, text

EXPECTED_HEAD_FILE = os.getenv("EXPECTED_ALEMBIC_HEAD_FILE", "/app/EXPECTED_ALEMBIC_HEAD")

# ARCH-137 A7: инвариант «сессия БД в UTC». Пока он держится, naive/aware-
# расхождения драйверов (psycopg2 читает session TimeZone, asyncpg игнорирует)
# не имеют почвы. Сравнение НЕ строкой с одним написанием: прод отдаёт `UTC`,
# бэклог ожидал `Etc/UTC` — оба канонические алиасы нулевой зоны. Проверка
# «смещение сейчас 0» не годится: Europe/London зимой тоже даёт ноль.
_UTC_SESSION_ALIASES = frozenset(
    a.lower() for a in ("UTC", "Etc/UTC", "GMT", "Etc/GMT", "UCT", "Universal", "Zulu")
)


def session_timezone_ok(tz: str) -> bool:
    return tz.strip().lower() in _UTC_SESSION_ALIASES


def _read_expected_head() -> str:
    try:
        with open(EXPECTED_HEAD_FILE, "r") as f:
            head = f.read().strip()
    except OSError as exc:
        print(f"db_preflight: cannot read {EXPECTED_HEAD_FILE}: {exc}", file=sys.stderr)
        sys.exit(1)
    if not head:
        print(f"db_preflight: {EXPECTED_HEAD_FILE} is empty", file=sys.stderr)
        sys.exit(1)
    return head


def _read_actual_head_and_tz(database_url: str) -> tuple[str, str]:
    engine = create_engine(database_url, pool_pre_ping=False)
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT version_num FROM alembic_version")).first()
            tz_row = conn.execute(text("SHOW TimeZone")).first()
    except Exception as exc:  # noqa: BLE001 — любая ошибка здесь = fail-closed preflight
        print(f"db_preflight: failed to read alembic_version: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        engine.dispose()
    if row is None:
        print("db_preflight: alembic_version table is empty", file=sys.stderr)
        sys.exit(1)
    if tz_row is None:
        print("db_preflight: SHOW TimeZone returned nothing", file=sys.stderr)
        sys.exit(1)
    return row[0], tz_row[0]


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("db_preflight: DATABASE_URL is not set", file=sys.stderr)
        sys.exit(1)

    expected = _read_expected_head()
    actual, session_tz = _read_actual_head_and_tz(database_url)

    if actual != expected:
        print(
            "db_preflight: schema drift detected — migrate job was not run before "
            f"this deploy (expected={expected!r}, actual={actual!r})",
            file=sys.stderr,
        )
        sys.exit(1)

    if not session_timezone_ok(session_tz):
        print(
            "db_preflight: DB session TimeZone is not UTC "
            f"(got {session_tz!r}) — драйверы psycopg2/asyncpg расходятся на "
            "naive-значениях при не-UTC сессии (ARCH-137); верни TimeZone=UTC",
            file=sys.stderr,
        )
        sys.exit(1)

    print(
        f"db_preflight: schema up to date (alembic head={actual!r}, "
        f"session tz={session_tz!r})"
    )


if __name__ == "__main__":
    main()
