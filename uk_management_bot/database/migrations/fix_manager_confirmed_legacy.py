"""
Миграция legacy-данных: проставляет manager_confirmed=True для заявок,
которые уже прошли стадию менеджерского подтверждения до введения флага.
"""
import logging
from sqlalchemy.orm import Session

from uk_management_bot.database.models.request import Request

logger = logging.getLogger(__name__)


def migrate_legacy_manager_confirmed(db: Session) -> int:
    """
    Заявки в 'Выполнена' без manager_confirmed — legacy-данные до введения флага.
    Также обновляет уже принятые заявки ('Принято').

    Returns:
        int: Количество обновлённых записей
    """
    updated = 0

    # Заявки со статусом "Выполнена", у которых есть completed_at, но нет manager_confirmed
    count = (
        db.query(Request)
        .filter(
            Request.status == "Выполнена",
            Request.manager_confirmed == False,
            Request.completed_at.isnot(None),
        )
        .update({"manager_confirmed": True})
    )
    updated += count

    # Уже принятые заявки — точно были подтверждены менеджером
    count = (
        db.query(Request)
        .filter(
            Request.status == "Принято",
            Request.manager_confirmed == False,
        )
        .update({"manager_confirmed": True})
    )
    updated += count

    db.commit()
    return updated
