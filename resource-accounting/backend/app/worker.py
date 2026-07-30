"""Background worker: periodic maintenance (expired launch tickets cleanup)."""

import logging
import os
import time
from pathlib import Path

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
# Пульс для docker-healthcheck (compose проверяет свежесть файла через find -mmin):
# касание ТОЛЬКО на успешной итерации — зависший цикл или лежащая БД дают unhealthy.
HEARTBEAT_PATH = Path(os.environ.get("RESOURCE_WORKER_HEARTBEAT", "/tmp/resource-worker-heartbeat"))


def cleanup_expired_tickets() -> int:
    with SessionLocal() as db:
        result = db.execute(delete(LaunchTicket).where(LaunchTicket.expires_at < utcnow()))
        db.commit()
        return result.rowcount or 0


def run_iteration() -> None:
    removed = cleanup_expired_tickets()
    if removed:
        logger.info("expired launch tickets removed: %d", removed)
    HEARTBEAT_PATH.touch()


def main() -> None:
    logger.info("worker started")
    while True:
        try:
            run_iteration()
        except Exception:
            logger.exception("worker iteration failed")
        time.sleep(CLEANUP_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
