"""Верификация жителя — своя транзакционная граница (PR-5).

Legacy-сервис (`services/user_verification_service.py:approve_verification`)
делает ТРИ независимых commit подряд: статус, авто-одобрение квартир, удаление
документов. Каждый следующий шаг обёрнут в try/except с «продолжаем, ведь
верификация уже одобрена» — то есть сбой на середине оставляет житель
verified, но с pending-квартирами или с висящими записями документов, и
починить это можно только руками.

Здесь то же поведение (parity по эффектам), но ОДНИМ commit: либо житель
verified, квартиры одобрены и записи документов удалены, либо не изменилось
ничего.

Внешние сервисы — строго ПОСЛЕ commit и best-effort: удаление файлов из Media
Service не имеет права откатывать решение менеджера.

Две оси статусов, которые нельзя смешивать:
  * `User.verification_status` ∈ pending | requested | verified | rejected;
  * `UserVerification.status`  ∈ PENDING | REQUESTED | APPROVED | REJECTED.
Соответствие: request-documents → requested/REQUESTED, approve →
verified/APPROVED, reject → rejected/REJECTED.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import (
    UserApartment, UserApartmentStatus,
)
from uk_management_bot.database.models.user_verification import (
    UserDocument, UserVerification, VerificationStatus,
)
from uk_management_bot.services.residents import core, queries
from uk_management_bot.services.residents.exceptions import (
    ResidentConflict, ResidentValidationError,
)

logger = logging.getLogger(__name__)

#: Типы документов, которые менеджер может запросить (значения DocumentType).
REQUESTABLE_DOCUMENT_TYPES = (
    "passport", "property_deed", "rental_agreement", "utility_bill", "other",
)

#: Из каких состояний оси верификации допустимо решение (Т13).
_DECIDABLE_FROM = frozenset({"pending", "requested"})

AUTO_APPROVE_COMMENT = "Автоматически одобрено при верификации пользователя"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _open_verification(db: AsyncSession, user_id: int) -> UserVerification | None:
    """Последняя запись, если она ещё открыта (PENDING/REQUESTED).

    «Последняя» определяется ЕДИНСТВЕННОЙ точкой — `queries.get_latest_verification`
    (created_at DESC, id DESC): unique(user_id) на таблице нет, записей у жителя
    может быть много, и любая вторая трактовка «последней» разъехалась бы с
    чтением карточки.
    """
    latest = await queries.get_latest_verification(db, user_id)
    if latest is None:
        return None
    if latest.status in (VerificationStatus.PENDING, VerificationStatus.REQUESTED):
        return latest
    return None


async def request_documents(
    db: AsyncSession, *, resident_id: int, actor_id: int,
    document_types: list[str], comment: str,
) -> User:
    """Запросить у жителя документы.

    Разрешено из ЛЮБОГО состояния оси верификации, включая `verified` и
    `rejected` — осознанное переоткрытие: менеджер вправе потребовать
    документы повторно, например при смене паспорта.
    """
    comment = (comment or "").strip()
    if not 3 <= len(comment) <= 1000:
        raise ResidentValidationError("Комментарий — от 3 до 1000 символов")

    types = list(dict.fromkeys(document_types or []))
    if not types:
        raise ResidentValidationError("Укажите хотя бы один тип документа")
    unknown = [t for t in types if t not in REQUESTABLE_DOCUMENT_TYPES]
    if unknown:
        raise ResidentValidationError(f"Неизвестные типы документов: {', '.join(unknown)}")

    resident = await core._lock_and_require_resident(db, resident_id)

    record = await _open_verification(db, resident_id)
    requested_info = {
        "type": "multiple_documents",
        "document_types": types,
        "request_text": comment,
        "requested_at": _now().isoformat(),
    }
    if record is None:
        record = UserVerification(user_id=resident_id)
        db.add(record)
    record.status = VerificationStatus.REQUESTED
    record.requested_info = requested_info
    record.requested_by = actor_id
    record.requested_at = _now()

    resident.verification_status = "requested"
    await db.flush()

    core._audit(db, action="resident_documents_requested", actor_id=actor_id,
                resident=resident,
                details={"document_types": types, "comment": comment})
    await core._finish(db, event=None, payload=None)
    logger.info("Запрошены документы %s у жителя %s менеджером %s",
                types, resident_id, actor_id)
    return resident


async def approve_verification(
    db: AsyncSession, *, resident_id: int, actor_id: int, notes: str | None = None,
) -> tuple[User, list[int]]:
    """Подтвердить личность жителя.

    Побочные эффекты — те же, что у бот-пути, но одной транзакцией:
      * `User.verification_status = 'verified'` + кто и когда;
      * закрытие открытой записи `UserVerification` (APPROVED);
      * авто-одобрение всех pending-привязок к квартирам (с инвариантом Т6:
        основная остаётся у прежней, иначе ею становится самая старая);
      * удаление строк `UserDocument`.

    → (житель, id удалённых документов). Файлы в Media Service чистит
    вызывающий ПОСЛЕ commit — внешний сервис не должен откатывать решение.
    """
    resident = await core._lock_and_require_resident(db, resident_id)
    if resident.verification_status not in _DECIDABLE_FROM:
        raise ResidentConflict(
            f"Верификация уже завершена (статус: {resident.verification_status})",
            code="verification_closed",
        )

    resident.verification_status = "verified"
    resident.verification_notes = notes
    resident.verification_date = _now()
    resident.verified_by = actor_id

    record = await _open_verification(db, resident_id)
    if record is not None:
        record.status = VerificationStatus.APPROVED
        record.verified_by = actor_id
        record.verified_at = _now()
        record.admin_notes = notes

    pending = list((await db.execute(
        select(UserApartment)
        .where(
            UserApartment.user_id == resident_id,
            UserApartment.status == UserApartmentStatus.PENDING.value,
        )
        .execution_options(populate_existing=True)
    )).scalars().all())
    for ua in pending:
        ua.status = UserApartmentStatus.APPROVED.value
        ua.reviewed_at = _now()
        ua.reviewed_by = actor_id
        ua.admin_comment = AUTO_APPROVE_COMMENT
    await db.flush()
    await core._ensure_single_primary(db, resident_id, keep_ua_id=None)

    documents = list((await db.execute(
        select(UserDocument).where(UserDocument.user_id == resident_id)
    )).scalars().all())
    deleted_ids = [d.id for d in documents]
    for doc in documents:
        await db.delete(doc)

    core._audit(db, action="resident_verification_approved", actor_id=actor_id,
                resident=resident,
                details={"auto_approved_apartments": len(pending),
                         "deleted_documents": len(deleted_ids), "notes": notes})
    await core._finish(db, event=None, payload=None)
    logger.info(
        "Житель %s верифицирован менеджером %s: авто-одобрено квартир %s, "
        "удалено записей документов %s",
        resident_id, actor_id, len(pending), len(deleted_ids),
    )
    return resident, deleted_ids


async def reject_verification(
    db: AsyncSession, *, resident_id: int, actor_id: int, notes: str,
) -> User:
    """Отклонить верификацию. Причина обязательна — житель её увидит.

    Меняется ТОЛЬКО ось верификации: `User.status` не трогается, иначе
    отклонённый по документам житель вылетел бы из очереди активации
    аккаунта (та смотрит на `status`).
    """
    notes = (notes or "").strip()
    if not 3 <= len(notes) <= 1000:
        raise ResidentValidationError("Причина — от 3 до 1000 символов")

    resident = await core._lock_and_require_resident(db, resident_id)
    if resident.verification_status not in _DECIDABLE_FROM:
        raise ResidentConflict(
            f"Верификация уже завершена (статус: {resident.verification_status})",
            code="verification_closed",
        )

    resident.verification_status = "rejected"
    resident.verification_notes = notes
    resident.verification_date = _now()
    resident.verified_by = actor_id

    record = await _open_verification(db, resident_id)
    if record is not None:
        record.status = VerificationStatus.REJECTED
        record.verified_by = actor_id
        record.verified_at = _now()
        record.admin_notes = notes
    await db.flush()

    core._audit(db, action="resident_verification_rejected", actor_id=actor_id,
                resident=resident, details={"notes": notes})
    await core._finish(db, event=None, payload=None)
    logger.info("Верификация жителя %s отклонена менеджером %s", resident_id, actor_id)
    return resident


def format_requested_documents(types: list[str], lang: str) -> str:
    """Человекочитаемый список типов для текста уведомления."""
    from uk_management_bot.utils.helpers import get_text

    return ", ".join(
        get_text(f"web_notifications.document_types.{t}", language=lang) or t
        for t in types
    )


__all__ = [
    "AUTO_APPROVE_COMMENT",
    "REQUESTABLE_DOCUMENT_TYPES",
    "approve_verification",
    "format_requested_documents",
    "reject_verification",
    "request_documents",
]
