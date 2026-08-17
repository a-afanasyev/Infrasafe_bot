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
    REQUEST_STATUS_APPROVED,
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_EXECUTED,
    REQUEST_STATUS_RETURNED,
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


def terminal_status_clause() -> ColumnElement:
    """SQL-форма `request_workflow.is_terminal` — заявка финализирована.

    Python-форма живёт в `utils/request_workflow.py` (`is_terminal` +
    `TERMINAL_STATUSES`); здесь только её SQL-пара, чтобы набор статусов не
    появился в запросах третьей рукописной копией (AUD5-APIFE-3).

    Нормализацию (`normalize_status`) воспроизводить не нужно: она не делает
    терминальный статус из нетерминального и не превращает терминальный в
    другой, поэтому предикат по колонке совпадает с канон-разбиением точно.
    """
    from uk_management_bot.utils.request_workflow import TERMINAL_STATUSES

    return Request.status.in_(TERMINAL_STATUSES)


def active_status_clause() -> ColumnElement:
    """Дополнение `terminal_status_clause`: работа ещё в процессе."""
    from uk_management_bot.utils.request_workflow import TERMINAL_STATUSES

    return Request.status.notin_(TERMINAL_STATUSES)


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


# ---------------------------------------------------------------------------
# PR2-pre: полный набор парных предикатов (Python-форма + SQL-clause).
# Каждое ИМЕНОВАННОЕ состояние читается только через пару — сырые сравнения
# status/manager_confirmed/is_returned в чтениях ловит read-инвентаризация
# (tests/services/test_workflow_read_inventory.py).
# ---------------------------------------------------------------------------

def is_awaiting_manager(request) -> bool:
    """Ждёт проверки менеджером: Выполнена и НЕ подтверждена.

    Канон-записи (canonical-write, PR2a-c) выглядят так же: MANAGER_CONFIRM
    сразу продвигает в Исполнено, поэтому Выполнена всегда «ждёт менеджера».
    """
    return (request.status == REQUEST_STATUS_EXECUTED
            and not bool(getattr(request, "manager_confirmed", False)))


def awaiting_manager_clause() -> ColumnElement:
    return and_(
        Request.status == REQUEST_STATUS_EXECUTED,
        Request.manager_confirmed.is_(False),
    )


def is_returned_for_review(request) -> bool:
    """Канон «Возвращена»: возвращена заявителем, ждёт разбора менеджером.

    После cutover (PR3+4): status == «Возвращена» напрямую.
    Legacy-кодировка (до cutover, страховка): Исполнено + is_returned=True.
    """
    if request.status == REQUEST_STATUS_RETURNED:
        return True
    return (request.status == REQUEST_STATUS_COMPLETED
            and bool(getattr(request, "is_returned", False)))


def returned_for_review_clause() -> ColumnElement:
    return or_(
        Request.status == REQUEST_STATUS_RETURNED,
        and_(
            Request.status == REQUEST_STATUS_COMPLETED,
            Request.is_returned.is_(True),
        ),
    )


def is_report_eligible(request) -> bool:
    """Заявка подходит для визуального отчёта «до/после» (work_report_service):
    прошла проверку менеджером (Исполнено) или уже принята заявителем
    (Принято), и не возвращена.

    "Выполнена" (самозаявление исполнителя, ДО проверки менеджером)
    намеренно исключена — публичная витрина показывает только работы,
    прошедшие ревью.
    """
    return (
        request.status in (REQUEST_STATUS_COMPLETED, REQUEST_STATUS_APPROVED)
        and not bool(getattr(request, "is_returned", False))
    )


def report_eligible_clause() -> ColumnElement:
    return and_(
        Request.status.in_((REQUEST_STATUS_COMPLETED, REQUEST_STATUS_APPROVED)),
        Request.is_returned.is_(False),
    )


# ── Инвариант «В работе ⟺ есть исполнитель» (решение владельца 2026-08-17) ──
# Пара для одного вопроса: «заявку уже кто-то ведёт» и «заявка ещё может
# ждать дежурного». Раньше эти два состояния различались сырым сравнением
# статуса в двух разных файлах, и они разъехались: групповое назначение
# перестало двигать статус, а очередь авто-менеджера продолжала искать
# групповые заявки ТОЛЬКО в «В работе» — и не находила ни одной.

def is_in_progress(request) -> bool:
    """Заявку ведут прямо сейчас (канон-статус «В работе»)."""
    from uk_management_bot.utils.constants import REQUEST_STATUS_IN_PROGRESS
    from uk_management_bot.utils.request_workflow import normalize_status

    return normalize_status(request) == REQUEST_STATUS_IN_PROGRESS


def pending_or_in_progress_clause() -> ColumnElement:
    """Статусы, в которых групповая заявка ещё ждёт исполнителя.

    «Новая» — штатное состояние после `ASSIGN_GROUP` (статус не двигается);
    «В работе» — legacy-строки, накопившиеся до миграции 011.
    """
    from uk_management_bot.utils.constants import (
        REQUEST_STATUS_IN_PROGRESS,
        REQUEST_STATUS_NEW,
    )

    return Request.status.in_([REQUEST_STATUS_NEW, REQUEST_STATUS_IN_PROGRESS])
