"""One-shot runner for media_service/migrations/*.sql.

Applies each file in filename-sorted order via a single connection. Each
migration file is itself idempotent (IF NOT EXISTS guards) — safe to re-run
on an already-migrated database, which is what makes this safe to invoke on
every deploy rather than needing a migrations-tracking table (only one
migration file exists today; if this grows into a real sequence, revisit
whether a tracking table becomes worth the complexity).
"""
import logging
import pathlib
import sys

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.db.database import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("media_migrate")

MIGRATIONS_DIR = pathlib.Path(__file__).parent / "migrations"


def apply_migrations(conn: Connection) -> int:
    """Применяет migrations/*.sql в порядке имён на переданном соединении.

    Вынесено из main() ради дрейф-гейта (test_schema_drift_pg.py, A9-P2-21):
    гейт гоняет ровно этот код на своих схемах, а не копию логики.
    """
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        logger.warning("No migration files found in %s", MIGRATIONS_DIR)
        return 0
    for path in sql_files:
        logger.info("Applying %s", path.name)
        conn.execute(text(path.read_text()))
    return len(sql_files)


def main() -> None:
    if not any(MIGRATIONS_DIR.glob("*.sql")):
        # Как до выноса apply_migrations: без файлов к БД не подключаемся.
        logger.warning("No migration files found in %s", MIGRATIONS_DIR)
        return
    with engine.begin() as conn:
        applied = apply_migrations(conn)
    logger.info("Applied %d migration file(s)", applied)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("media_service migration failed")
        sys.exit(1)
