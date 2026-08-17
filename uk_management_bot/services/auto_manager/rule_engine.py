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

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import func, or_
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
from uk_management_bot.utils.specializations import (
    matches_required_specs,
    parse_specializations,
)

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


@dataclass
class DutySnapshot:
    """Срез дежурства на момент тика (AUD6-P2-14).

    Всё, что нужно для выбора исполнителя, собирается ТРЕМЯ запросами один раз
    на тик, а не парой запросов (смены + COUNT нагрузки) на каждого кандидата
    каждой заявки: при max_requests_per_run=50 старая схема давала тысячи
    запросов за тик.

    `load_by_user` НАМЕРЕННО мутабелен: срез снят в начале тика, и оркестратор
    инкрементирует нагрузку после каждого успешного назначения — иначе пачка
    однотипных заявок в одном тике ушла бы одному «наименее загруженному».
    """

    approved_users: list[User] = field(default_factory=list)
    shifts_by_user: dict[int, list[Shift]] = field(default_factory=dict)
    load_by_user: dict[int, int] = field(default_factory=dict)


def build_duty_snapshot(db: Session, now: datetime) -> DutySnapshot:
    """Три запроса: approved-пользователи, активные смены, нагрузка GROUP BY."""
    svc = AdminHandlerService(db)
    approved_users = svc.list_approved_users()
    executor_ids = [
        u.id for u in approved_users if ROLE_EXECUTOR in get_user_roles(u)
    ]
    shifts_by_user: dict[int, list[Shift]] = {}
    load_by_user: dict[int, int] = {}
    if executor_ids:
        shift_rows = (
            db.query(Shift)
            .filter(
                Shift.user_id.in_(executor_ids),
                Shift.status == "active",
                Shift.start_time <= now,
                or_(Shift.end_time.is_(None), Shift.end_time >= now),
            )
            .all()
        )
        for shift in shift_rows:
            shifts_by_user.setdefault(shift.user_id, []).append(shift)
        load_rows = (
            db.query(Request.executor_id, func.count())
            .filter(
                Request.executor_id.in_(executor_ids),
                Request.status.in_(OPEN_LOAD_STATUSES),
            )
            .group_by(Request.executor_id)
            .all()
        )
        load_by_user = {executor_id: count for executor_id, count in load_rows}
    return DutySnapshot(approved_users, shifts_by_user, load_by_user)


def _has_matching_active_shift(snapshot: DutySnapshot, executor_id: int,
                               specialization: str) -> bool:
    """Есть ли у исполнителя активная СЕЙЧАС смена, покрывающая `specialization`.

    НЕ переиспользует `AdminHandlerService.get_active_shift_for` — тот берёт
    ОДНУ произвольную активную смену через `.first()`, что для этой проверки
    неверно: проект допускает перекрывающиеся активные смены разных
    специализаций (напр. electric + plumber одновременно), и `.first()` мог бы
    вернуть смену НЕ той специализации, ложно исключая исполнителя, у которого
    подходящая смена на самом деле есть. Здесь проверяются ВСЕ активные смены —
    подходит любая одна.
    """
    return any(
        shift.can_handle_specialization(specialization)
        for shift in snapshot.shifts_by_user.get(executor_id, [])
    )


def select_executor(db: Session, specialization: str, now: datetime,
                    snapshot: Optional[DutySnapshot] = None) -> Optional[User]:
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
    # AUD6-P2-14: srez можно передать готовым (оркестратор строит его один раз
    # на тик); без него собирается на месте — семантика одиночного вызова
    # сохранена 1:1 для остальных колл-сайтов.
    snap = snapshot if snapshot is not None else build_duty_snapshot(db, now)

    # BUG-166: вердикт — общий предикат. Голое `specialization in ...` не знало
    # джокера `universal`, а шаг ниже (`can_handle_specialization`) знал: одна
    # функция отвечала на вопрос «джокер ли universal» по-разному в зависимости
    # от стороны — ровно тот класс расхождения, который BUG-166 и закрывает.
    candidates = [
        user
        for user in snap.approved_users
        if ROLE_EXECUTOR in get_user_roles(user)
        and matches_required_specs(parse_specializations(user), {specialization})
    ]

    on_duty = [
        candidate for candidate in candidates
        if _has_matching_active_shift(snap, candidate.id, specialization)
    ]

    if not on_duty:
        return None

    ranked = sorted(on_duty, key=lambda user: (snap.load_by_user.get(user.id, 0), user.id))
    return ranked[0]
