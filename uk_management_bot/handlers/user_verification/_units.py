"""DTO и sync unit-of-work верификации пользователей (AUD3-07, канон B1/B4).

AUD5-ARCH-3 (волна 11): файл — часть пакета ``user_verification`` (разбит
плоский Router-файл); здесь живут DTO и sync-юниты, хендлеры — в соседних
под-модулях. Код перенесён 1:1 из handlers/user_verification.py.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from uk_management_bot.services.user_verification_service import UserVerificationService
from uk_management_bot.services.notification_service import NotificationService
from uk_management_bot.database.models.user_verification import (
    VerificationStatus
)
from uk_management_bot.utils.address_helpers import apartment_address
from uk_management_bot.utils.user_names import display_name

logger = logging.getLogger(__name__)

# ==========================================================================
# DTO + sync-юниты (AUD3-07). Сессия живёт только внутри юнита.
# ==========================================================================


@dataclass(frozen=True)
class _ApartmentRow:
    address: str
    is_primary: bool
    is_owner: bool


@dataclass(frozen=True)
class _DocumentRow:
    id: int
    type_value: str
    status: VerificationStatus
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    created_at: Optional[datetime] = None
    notes: Optional[str] = None


@dataclass(frozen=True)
class _AccessRightRow:
    level_value: str
    apartment_number: Optional[str]
    house_number: Optional[str]
    yard_name: Optional[str]


@dataclass(frozen=True)
class _UserCard:
    first_name: Optional[str]
    last_name: Optional[str]
    username: Optional[str]
    phone: Optional[str]
    verification_status: str
    verification_notes: Optional[str]
    has_apartment_links: bool
    approved_apartments: List[_ApartmentRow] = field(default_factory=list)
    documents: List[_DocumentRow] = field(default_factory=list)
    access_rights: List[_AccessRightRow] = field(default_factory=list)


def _fmt_created_at(created_at: Optional[datetime]) -> str:
    """BUG-144: created_at в модели Optional — NULL не должен ронять хендлер."""
    return created_at.strftime('%d.%m.%Y %H:%M') if created_at else '—'


def _document_row(doc) -> _DocumentRow:
    return _DocumentRow(
        id=doc.id,
        type_value=doc.document_type.value,
        status=doc.verification_status,
        file_name=doc.file_name,
        file_size=doc.file_size,
        created_at=doc.created_at,
        notes=doc.verification_notes,
    )


def _load_verification_stats(db) -> dict:
    return UserVerificationService(db).get_verification_stats()


def _load_user_card(db, user_id: int, lang: str) -> Optional[_UserCard]:
    """Пользователь + approved-квартиры + документы + активные права — одним юнитом."""
    from uk_management_bot.database.models.user import User
    from uk_management_bot.database.models.user_verification import UserDocument, AccessRights

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None

    documents = db.query(UserDocument).filter(UserDocument.user_id == user_id).all()
    access_rights = db.query(AccessRights).filter(
        AccessRights.user_id == user_id,
        AccessRights.is_active.is_(True)
    ).all()

    approved = []
    has_links = bool(user.user_apartments)
    if has_links:
        for ua in user.user_apartments:
            if ua.status == 'approved':
                approved.append(_ApartmentRow(
                    address=apartment_address(ua.apartment, lang),
                    is_primary=ua.is_primary,
                    is_owner=ua.is_owner,
                ))

    return _UserCard(
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        phone=user.phone,
        verification_status=user.verification_status,
        verification_notes=user.verification_notes,
        has_apartment_links=has_links,
        approved_apartments=approved,
        documents=[_document_row(d) for d in documents],
        access_rights=[
            _AccessRightRow(
                level_value=r.access_level.value,
                apartment_number=r.apartment_number,
                house_number=r.house_number,
                yard_name=r.yard_name,
            )
            for r in access_rights
        ],
    )


def _load_documents_page(db, user_id: int):
    """→ (display_name_источники, [документы новые→старые]) | None."""
    from uk_management_bot.database.models.user import User
    from uk_management_bot.database.models.user_verification import UserDocument

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    documents = (
        db.query(UserDocument)
        .filter(UserDocument.user_id == user_id)
        .order_by(UserDocument.created_at.desc())
        .all()
    )
    return (user.first_name, user.username), [_document_row(d) for d in documents]


def _create_request_and_collect_notify(db, user_id: int, admin_id: int, requested_info: dict):
    """Создание запроса верификации + fetch-фаза уведомления (сеть — у вызывающего)."""
    UserVerificationService(db).create_verification_request(
        user_id=user_id,
        admin_id=admin_id,
        requested_info=requested_info,
    )
    return NotificationService(db).collect_verification_request_message(
        user_id, requested_info['type'], requested_info['comment']
    )


def _load_access_rights_card(db, user_id: int):
    """→ (имя, [права]) | None."""
    from uk_management_bot.database.models.user import User
    from uk_management_bot.database.models.user_verification import AccessRights

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    current_rights = db.query(AccessRights).filter(
        AccessRights.user_id == user_id,
        AccessRights.is_active.is_(True)
    ).all()
    name = display_name(user)
    return name, [
        _AccessRightRow(
            level_value=r.access_level.value,
            apartment_number=r.apartment_number,
            house_number=r.house_number,
            yard_name=r.yard_name,
        )
        for r in current_rights
    ]





def _approve_user_db(db, user_id: int, admin_telegram_id: int):
    """Одобрение одним commit + fetch уведомлений. → (purge | None, notify_pair,
    restart_target). Сеть (гигиена медиа, отправки) — у вызывающего.

    Решение уже закоммичено к моменту fetch'а: его сбой не должен терять purge
    (иначе media_id не дойдут до гигиены) — уведомления просто не уйдут.
    """
    from uk_management_bot.database.models.user import User

    purge = UserVerificationService(db).approve_verification_db(user_id, admin_telegram_id)
    if purge is None:
        return None, None, None
    try:
        notify_pair = NotificationService(db).collect_verification_approved_message(user_id)
        target_user = db.query(User).filter(User.id == user_id).first()
        restart_target = (target_user.telegram_id, target_user.language or "ru") if target_user else None
    except Exception as e:  # noqa: BLE001
        logger.error("Уведомления об одобрении %s не собраны: %s", user_id, type(e).__name__)
        return purge, None, None
    return purge, notify_pair, restart_target


def _reject_user_db(db, user_id: int, admin_telegram_id: int, notes: str):
    """Отклонение одним commit (документы удаляются) + fetch уведомления.
    → (purge | None, notify_pair, язык жителя для кнопки переподачи | None).

    Язык None — кнопку не показывать: переподача доступна только «чистому»
    жителю (у сотрудника своя очередь, кнопка ответила бы «недоступна»).
    """
    from uk_management_bot.database.models.user import User
    from uk_management_bot.services.residents.core import PURE_APPLICANT_ROLES
    from uk_management_bot.utils.auth_helpers import parse_roles_safe

    purge = UserVerificationService(db).reject_verification(user_id, admin_telegram_id, notes)
    if purge is None:
        return None, None, None
    try:
        resident = db.query(User).filter(User.id == user_id).first()
        pure = resident is not None and not set(parse_roles_safe(resident.roles)) - PURE_APPLICANT_ROLES
        lang = ((resident.language or "ru") if pure else None)
        return purge, NotificationService(db).collect_verification_rejected_message(user_id), lang
    except Exception as e:  # noqa: BLE001 — решение закоммичено, purge не теряем
        logger.error("Уведомление об отказе %s не собрано: %s", user_id, type(e).__name__)
        return purge, None, None
