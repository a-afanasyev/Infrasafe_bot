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

from app.db.database import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("media_migrate")

MIGRATIONS_DIR = pathlib.Path(__file__).parent / "migrations"


def main() -> None:
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        logger.warning("No migration files found in %s", MIGRATIONS_DIR)
        return
    with engine.begin() as conn:
        for path in sql_files:
            logger.info("Applying %s", path.name)
            conn.execute(text(path.read_text()))
    logger.info("Applied %d migration file(s)", len(sql_files))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("media_service migration failed")
        sys.exit(1)
