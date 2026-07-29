"""Раздел «Жители» — верификация личности (PR-5).

Тонкий HTTP-слой поверх `services/residents/verification_core.py`.

Зачистка файлов в Media Service идёт ПОСЛЕ commit и best-effort: решение
менеджера уже зафиксировано, недоступный внешний сервис не имеет права его
откатывать. Подробнее про деградацию — в `_cleanup_media`.
"""
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.api.residents import notify
from uk_management_bot.api.residents.schemas import (
    ResidentRequestDocumentsIn,
    ResidentVerificationNotesIn,
    ResidentVerificationRejectIn,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.services.residents import verification_core

logger = logging.getLogger(__name__)

router = APIRouter()

_manager_only = require_roles("manager")

#: Строже прочих мутаций: КАЖДЫЙ вызов отправляет жителю сообщение в Telegram,
#: то есть сессией менеджера можно завалить чужой чат.
_NOTIFY_LIMIT = "20/minute"


async def _cleanup_media(resident: User, deleted_ids: list[int]) -> None:
    """Best-effort зачистка файлов документов в Media Service.

    ⚠ Осознанная деградация. Хелпер `media_helpers` считает недоступный Media
    Service УСПЕХОМ (возвращает True), поэтому отличить «удалено» от «сервис
    лежал» по его результату нельзя. Если удаление не состоялось, файлы
    остаются в Media Service и в Telegram, тогда как записи в нашей БД уже
    удалены — то есть из карточки они исчезли, а физически могли остаться.
    Именно так и написано в предупреждении на кнопке верификации, чтобы
    менеджер не считал это гарантированным стиранием.

    В лог пишется количество и id ЗАПИСЕЙ, но НЕ Telegram `file_id`: file_id —
    это готовый токен скачивания файла, и логи не то место, где его хранить.
    """
    if not deleted_ids:
        return
    try:
        from uk_management_bot.utils.media_helpers import (
            delete_user_documents_from_media_service,
        )
        await delete_user_documents_from_media_service(resident.telegram_id)
        logger.info("Запрошено удаление %s документов жителя %s из Media Service",
                    len(deleted_ids), resident.id)
    except Exception as e:  # noqa: BLE001 — не роняем уже зафиксированное решение
        logger.warning(
            "Не удалось удалить документы жителя %s из Media Service "
            "(записей: %s, id: %s): %s — файлы могли остаться в Media Service "
            "и Telegram",
            resident.id, len(deleted_ids), deleted_ids, e,
        )


@router.post("/{resident_id}/verification/request-documents")
@limiter.limit(_NOTIFY_LIMIT)
async def request_documents(
    request: Request,
    resident_id: int,
    body: ResidentRequestDocumentsIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    resident = await verification_core.request_documents(
        db, resident_id=resident_id, actor_id=user.id,
        document_types=body.document_types, comment=body.comment,
    )
    await notify.notify_documents_requested(
        resident, document_types=body.document_types, comment=body.comment.strip(),
    )
    return {"id": resident.id, "verification_status": resident.verification_status}


@router.post("/{resident_id}/verification/approve")
@limiter.limit(_NOTIFY_LIMIT)
async def approve_verification(
    request: Request,
    resident_id: int,
    body: ResidentVerificationNotesIn = ResidentVerificationNotesIn(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    resident, deleted_ids = await verification_core.approve_verification(
        db, resident_id=resident_id, actor_id=user.id, notes=body.notes,
    )
    await _cleanup_media(resident, deleted_ids)
    await notify.notify_verification_approved(resident)
    return {
        "id": resident.id,
        "verification_status": resident.verification_status,
        "deleted_documents": len(deleted_ids),
    }


@router.post("/{resident_id}/verification/reject")
@limiter.limit(_NOTIFY_LIMIT)
async def reject_verification(
    request: Request,
    resident_id: int,
    body: ResidentVerificationRejectIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    resident = await verification_core.reject_verification(
        db, resident_id=resident_id, actor_id=user.id, notes=body.notes,
    )
    await notify.notify_verification_rejected(resident, body.notes.strip())
    return {"id": resident.id, "verification_status": resident.verification_status}
