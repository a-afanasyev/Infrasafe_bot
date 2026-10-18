"""Раздел «Жители» — верификация личности (PR-5).

Тонкий HTTP-слой поверх `services/residents/verification_core.py`.

Документы (и ключи шифрования) удаляются в транзакции решения — одобрения и
отказа. Гигиена blob'ов в Media Service идёт ПОСЛЕ commit и best-effort
(`services/document_purge.cleanup_purged_documents`): решение уже
зафиксировано, а без ключа blob нечитаем.
"""
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_action
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.api.residents import notify
from uk_management_bot.api.residents.schemas import (
    ResidentRequestDocumentsIn,
    ResidentVerificationNotesIn,
    ResidentVerificationRejectIn,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.services.document_purge import cleanup_purged_documents
from uk_management_bot.services.residents import verification_core

logger = logging.getLogger(__name__)

router = APIRouter()

_manager_only = require_action("residents.manage")

#: Строже прочих мутаций: КАЖДЫЙ вызов отправляет жителю сообщение в Telegram,
#: то есть сессией менеджера можно завалить чужой чат.
_NOTIFY_LIMIT = "20/minute"


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
    resident, purge = await verification_core.approve_verification(
        db, resident_id=resident_id, actor_id=user.id, notes=body.notes,
    )
    await cleanup_purged_documents(purge)
    await notify.notify_verification_approved(resident)
    return {
        "id": resident.id,
        "verification_status": resident.verification_status,
        "deleted_documents": purge.count,
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
    resident, purge = await verification_core.reject_verification(
        db, resident_id=resident_id, actor_id=user.id, notes=body.notes,
    )
    await cleanup_purged_documents(purge)
    await notify.notify_verification_rejected(resident, body.notes.strip())
    return {
        "id": resident.id,
        "verification_status": resident.verification_status,
        "deleted_documents": purge.count,
    }
