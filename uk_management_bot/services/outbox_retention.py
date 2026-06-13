"""OPS-105: webhook_outbox retention.

Транзакционный outbox растёт линейно — `sent`-записи накапливаются и никогда
не чистятся. Эта задача раз в сутки удаляет успешно доставленные записи
старше окна retention. `failed`/`pending`/`in_flight` НЕ трогаются: failed
нужны для аудита/разбора, pending/in_flight — живые.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from uk_management_bot.database.models.webhook_outbox import WebhookOutbox

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 30


async def purge_old_sent_outbox(retention_days: int = DEFAULT_RETENTION_DAYS) -> dict:
    """Удалить `sent`-записи outbox старше `retention_days`.

    Возвращает `{"deleted": N}` или `{"error": ...}` — НИКОГДА не бросает
    (вызывается из background-loop, исключение не должно ронять цикл).
    Удаляются только `status='sent' AND sent_at < cutoff`.
    """
    from uk_management_bot.database.session import AsyncSessionLocal

    if AsyncSessionLocal is None:
        return {"deleted": 0, "error": "db_unavailable"}

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                delete(WebhookOutbox).where(
                    WebhookOutbox.status == "sent",
                    WebhookOutbox.sent_at.is_not(None),
                    WebhookOutbox.sent_at < cutoff,
                )
            )
            await db.commit()
            deleted = result.rowcount or 0
        if deleted:
            logger.info(
                "Outbox retention: purged %d sent records older than %d days",
                deleted, retention_days,
            )
        return {"deleted": deleted}
    except Exception:
        logger.exception("Outbox retention purge failed")
        return {"deleted": 0, "error": "internal_error"}
