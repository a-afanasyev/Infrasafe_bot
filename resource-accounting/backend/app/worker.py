"""Background worker: periodic maintenance (expired launch tickets cleanup)."""

import logging
import time

from sqlalchemy import delete

from app.db import SessionLocal
from app.models import LaunchTicket
from app.models.base import utcnow

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
logger = logging.getLogger("resource_worker")

CLEANUP_INTERVAL_SECONDS = 300


def cleanup_expired_tickets() -> int:
    with SessionLocal() as db:
        result = db.execute(delete(LaunchTicket).where(LaunchTicket.expires_at < utcnow()))
        db.commit()
        return result.rowcount or 0


def main() -> None:
    logger.info("worker started")
    while True:
        try:
            removed = cleanup_expired_tickets()
            if removed:
                logger.info("expired launch tickets removed: %d", removed)
        except Exception:
            logger.exception("worker iteration failed")
        time.sleep(CLEANUP_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
