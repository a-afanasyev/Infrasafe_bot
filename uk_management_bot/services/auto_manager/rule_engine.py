"""Правило (не-AI) выбора дежурного исполнителя для авто-менеджера.

`select_executor` подбирает ОДНОГО наименее загруженного исполнителя,
имеющего нужную специализацию и активную смену прямо сейчас — не назначает
заявку, только выбирает кандидата (назначение/запись — забота вызывающего
оркестратора, вне этого модуля).

Кандидат-фильтр (approved + роль executor + специализация) мирроит
`handlers/admin/shared.py::auto_assign_request_by_category` дословно: та же
пара `get_user_roles`/`parse_specializations` поверх `list_approved_users()`
(не `list_approved_executors()` — см. docstring `select_executor`).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.services.admin_handler_service import AdminHandlerService
from uk_management_bot.utils.auth_helpers import get_user_roles
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_CLARIFICATION,
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_PURCHASE,
    ROLE_EXECUTOR,
)
from uk_management_bot.utils.specializations import parse_specializations

# «Открытые» статусы заявки для ranking'а нагрузки исполнителя авто-менеджером.
# Локальный набор именно для этого модуля (least-loaded ranking) — НЕ общий
# канон workflow-переходов статусов (тот живёт в utils/request_workflow.py и
# решает совсем другую задачу — допустимые переходы, а не «что считать
# открытой заявкой для балансировки нагрузки»). Совпадает с ACTIVE_STATUSES
# manager-view (services/admin_handler_service.py) на момент написания.
OPEN_LOAD_STATUSES = frozenset(
    {
        REQUEST_STATUS_IN_PROGRESS,
        REQUEST_STATUS_PURCHASE,
        REQUEST_STATUS_CLARIFICATION,
    }
)


def _current_load(db: Session, executor_id: int) -> int:
    """Количество открытых (см. OPEN_LOAD_STATUSES) заявок исполнителя."""
    return (
        db.query(Request)
        .filter(
            Request.executor_id == executor_id,
            Request.status.in_(OPEN_LOAD_STATUSES),
        )
        .count()
    )


def _has_matching_active_shift(db: Session, executor_id: int, specialization: str,
                               now: datetime) -> bool:
    """Есть ли у исполнителя активная СЕЙЧАС смена, покрывающая `specialization`.

    НЕ переиспользует `AdminHandlerService.get_active_shift_for` — тот берёт
    ОДНУ произвольную активную смену через `.first()`, что для этой проверки
    неверно: проект допускает перекрывающиеся активные смены разных
    специализаций (напр. electric + plumber одновременно), и `.first()` мог бы
    вернуть смену НЕ той специализации, ложно исключая исполнителя, у которого
    подходящая смена на самом деле есть. Здесь проверяются ВСЕ активные смены —
    подходит любая одна.
    """
    shifts = (
        db.query(Shift)
        .filter(
            Shift.user_id == executor_id,
            Shift.status == "active",
            Shift.start_time <= now,
            or_(Shift.end_time.is_(None), Shift.end_time >= now),
        )
        .all()
    )
    return any(shift.can_handle_specialization(specialization) for shift in shifts)


def select_executor(db: Session, specialization: str, now: datetime) -> Optional[User]:
    """Выбрать наименее загруженного дежурного исполнителя под `specialization`.

    Args:
        db: sync-сессия (тот же sync-мир, что и AdminHandlerService/шедулер).
        specialization: искомая специализация (напр. "plumber").
        now: момент времени для проверки активности смены.

    Алгоритм:
        1. Кандидаты — approved-пользователи с ролью executor
           (`get_user_roles`) и `specialization` среди распарсенных
           специализаций (`parse_specializations`). Используем
           `AdminHandlerService.list_approved_users()` + этот же ручной
           Python-фильтр, а не `list_approved_executors()`: последний матчит
           роль SQL-уровня ("executor" as quoted JSON-токен через
           `.cast(String).contains`), что не эквивалентно каноническому
           парсеру ролей (`get_user_roles`/`parse_roles_safe`, который
           понимает и JSON-список, и CSV-строку). Задача явно требует
           мирроить `auto_assign_request_by_category`, которая построена
           именно на `list_approved_users()` + ручном фильтре — сохраняем ту
           же семантику 1:1, а не более широкий/узкий SQL-вариант.
        2. Кандидат допускается, только если хотя бы ОДНА из его активных
           СЕЙЧАС смен (статус "active" + start_time<=now<=end_time/NULL)
           может обработать `specialization` (`Shift.can_handle_specialization`
           — универсальная смена без `specialization_focus`, либо
           специализация/«universal» в фокусе). Проверяются ВСЕ активные смены
           исполнителя, а не одна произвольная (`get_active_shift_for`'s
           `.first()` не годится здесь — проект допускает перекрывающиеся
           активные смены разных специализаций одновременно; см.
           `_has_matching_active_shift`).
        3. Среди выживших — ranking по нагрузке: количество открытых заявок
           (`OPEN_LOAD_STATUSES`) с `executor_id == candidate.id`. Тай-брейк —
           наименьший `executor_id` (детерминированность).

    Returns:
        User с наименьшей нагрузкой среди дежурных кандидатов, либо None,
        если ни один кандидат не прошёл фильтрацию.
    """
    svc = AdminHandlerService(db)

    approved_users = svc.list_approved_users()
    candidates = [
        user
        for user in approved_users
        if ROLE_EXECUTOR in get_user_roles(user)
        and specialization in parse_specializations(user)
    ]

    on_duty = [
        candidate for candidate in candidates
        if _has_matching_active_shift(db, candidate.id, specialization, now)
    ]

    if not on_duty:
        return None

    ranked = sorted(on_duty, key=lambda user: (_current_load(db, user.id), user.id))
    return ranked[0]
