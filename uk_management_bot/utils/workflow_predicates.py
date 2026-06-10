"""HF-0: общие предикаты приёмки заявителя (зародыш парных предикатов SSOT-кластера #1).

Источник истины для вопроса «ожидает ли заявка решения заявителя» в ДВУХ
живых кодировках состояния (dual-read):
  - Web/TWA (чисто статусная):  status == "Исполнено"
  - Telegram (композитная):     status == "Выполнена" AND manager_confirmed

Возвращённые заявки (is_returned=True) ИСКЛЮЧЕНЫ в обеих ветках: после
возврата заявка ждёт повторной проверки менеджером (reconfirm), а не
повторной приёмки заявителем.

Право-проверки разделены (HF-0):
  - can_accept: владелец ИЛИ одобренный сосед по квартире заявки —
    сохраняет текущую семантику списка приёмки;
  - can_return: ТОЛЬКО владелец.

Legacy-ветка (Выполнена+manager_confirmed) удаляется в PR4 (contract),
именованные предикаты остаются как канон-форма.
"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from uk_management_bot.database.models.request import Request
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_EXECUTED,
)


def is_awaiting_applicant(request) -> bool:
    """Python-форма: заявка ожидает решения заявителя (принять/вернуть).

    Работает с ORM-объектом или любым объектом с атрибутами
    status / is_returned / manager_confirmed.
    """
    if bool(getattr(request, "is_returned", False)):
        return False
    if request.status == REQUEST_STATUS_COMPLETED:
        return True
    return request.status == REQUEST_STATUS_EXECUTED and bool(
        getattr(request, "manager_confirmed", False)
    )


def awaiting_applicant_clause() -> ColumnElement:
    """SQL-форма того же предиката — для .filter(...) / .where(...)."""
    return and_(
        Request.is_returned.is_(False),
        or_(
            Request.status == REQUEST_STATUS_COMPLETED,
            and_(
                Request.status == REQUEST_STATUS_EXECUTED,
                Request.manager_confirmed.is_(True),
            ),
        ),
    )


def get_approved_apartment_ids(db: Session, user_id: int) -> frozenset[int]:
    """ID квартир, по которым у пользователя одобрено соседство (UserApartment)."""
    from uk_management_bot.database.models.user_apartment import UserApartment

    rows = (
        db.query(UserApartment.apartment_id)
        .filter(
            UserApartment.user_id == user_id,
            UserApartment.status == "approved",
        )
        .all()
    )
    return frozenset(row[0] for row in rows)


def can_accept(request, user, approved_apartment_ids: Iterable[int]) -> bool:
    """Принять может владелец ИЛИ одобренный сосед по квартире заявки."""
    if request.user_id == user.id:
        return True
    return (
        request.apartment_id is not None
        and request.apartment_id in set(approved_apartment_ids)
    )


def can_return(request, user) -> bool:
    """Вернуть может ТОЛЬКО владелец заявки."""
    return request.user_id == user.id
