"""Сервисный слой управления сменами (manager-side).

ARCH-01 (PR-29.1): весь прямой ORM из `handlers/shift_management.py` вынесен
сюда. Хендлер остаётся тонким: FSM-переходы, клавиатуры, i18n, auth, роутинг
коллбэков. Сервис получает ``db`` (Session) и выполняет ORM на нём — сессией
по-прежнему владеет хендлер (`session_scope()` или инъекция в тестах), поэтому
семантика транзакций не меняется: каждый явный ``commit`` сохранён ровно на той
же логической границе, что и в исходном коде.

Домен этого сервиса (планирование/шаблоны/назначение исполнителей менеджером)
отделён от ``ShiftService`` (личный жизненный цикл смены исполнителя:
start/end/list), поэтому это отдельный модуль — высокая когезия, низкая связность.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_template import ShiftTemplate
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.auth_helpers import legacy_role_filter

logger = logging.getLogger(__name__)


class ShiftManagementService:
    """ORM-операции для manager-интерфейса управления сменами."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── Шаблоны ──────────────────────────────────────────────────────────────

    def get_template(self, template_id: int) -> Optional[ShiftTemplate]:
        return (
            self.db.query(ShiftTemplate)
            .filter(ShiftTemplate.id == template_id)
            .first()
        )

    def list_auto_create_templates(self) -> List[ShiftTemplate]:
        """Активные шаблоны с включённым авто-созданием смен."""
        return (
            self.db.query(ShiftTemplate)
            .filter(
                ShiftTemplate.is_active.is_(True),
                ShiftTemplate.auto_create.is_(True),
            )
            .all()
        )

    def set_template_active(self, template_id: int, is_active: bool) -> bool:
        """Переключить активность шаблона. ``True`` при успешном commit."""
        template = self.get_template(template_id)
        if not template:
            return False
        template.is_active = is_active
        try:
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка обновления шаблона: {e}")
            return False

    def set_template_specializations(
        self, template_id: int, specializations: list
    ) -> None:
        """Сохранить список специализаций шаблона (с flag_modified для JSON)."""
        template = self.get_template(template_id)
        if not template:
            return
        template.required_specializations = specializations
        flag_modified(template, "required_specializations")
        self.db.commit()

    # ── Расписание (чтение) ──────────────────────────────────────────────────

    def get_shifts_for_date(self, target_date: date) -> List[Shift]:
        return (
            self.db.query(Shift)
            .filter(func.date(Shift.planned_start_time) == target_date)
            .order_by(Shift.planned_start_time)
            .all()
        )

    def get_shifts_in_month(self, month_start: date) -> List[Shift]:
        if month_start.month < 12:
            month_end = month_start.replace(month=month_start.month + 1)
        else:
            month_end = month_start.replace(year=month_start.year + 1, month=1)
        return (
            self.db.query(Shift)
            .filter(
                func.date(Shift.planned_start_time) >= month_start,
                func.date(Shift.planned_start_time) < month_end,
            )
            .all()
        )

    def get_user(self, user_id: int) -> Optional[User]:
        return self.db.query(User).filter(User.id == user_id).first()

    # ── Назначение исполнителей (чтение) ─────────────────────────────────────

    def list_unassigned_planned_shifts_between(
        self, start: datetime, end: datetime, limit: int = 10
    ) -> List[Shift]:
        """Неназначенные запланированные смены в окне [start, end] по start_time."""
        return (
            self.db.query(Shift)
            .filter(
                Shift.user_id.is_(None),
                Shift.status == "planned",
                Shift.start_time.between(start, end),
            )
            .order_by(Shift.start_time)
            .limit(limit)
            .all()
        )

    def list_unassigned_planned_shifts_range(
        self, start: datetime, end: datetime, limit: int = 10
    ) -> List[Shift]:
        """Неназначенные запланированные смены start <= start_time <= end."""
        return (
            self.db.query(Shift)
            .filter(
                Shift.user_id.is_(None),
                Shift.status == "planned",
                Shift.start_time >= start,
                Shift.start_time <= end,
            )
            .order_by(Shift.start_time)
            .limit(limit)
            .all()
        )

    def count_unassigned_shifts_from(self, start: datetime) -> int:
        return (
            self.db.query(Shift)
            .filter(Shift.user_id.is_(None), Shift.start_time >= start)
            .count()
        )

    def count_available_executors(self) -> int:
        return (
            self.db.query(User)
            .filter(User.active_role == "executor", User.status == "approved")
            .count()
        )

    def list_unassigned_shifts_from(self, start: datetime) -> List[Shift]:
        return (
            self.db.query(Shift)
            .filter(Shift.user_id.is_(None), Shift.start_time >= start)
            .all()
        )

    def list_unassigned_shifts_from_ordered(self, start: datetime) -> List[Shift]:
        return (
            self.db.query(Shift)
            .filter(Shift.user_id.is_(None), Shift.start_time >= start)
            .order_by(Shift.start_time.asc())
            .all()
        )

    def list_unassigned_shifts_window(
        self, start: datetime, end: datetime
    ) -> List[Shift]:
        return (
            self.db.query(Shift)
            .filter(
                Shift.user_id.is_(None),
                Shift.start_time >= start,
                Shift.start_time < end,
            )
            .all()
        )

    # ── Аналитика загруженности / конфликты ──────────────────────────────────

    def get_executor_workload_stats(self, start: datetime, end: date) -> list:
        """Статистика смен/часов по исполнителям за период (join Shift↔User)."""
        return (
            self.db.query(
                User.id,
                User.first_name,
                User.last_name,
                func.count(Shift.id).label("shift_count"),
                func.sum(
                    func.extract("epoch", Shift.end_time - Shift.start_time) / 3600
                ).label("total_hours"),
            )
            .join(Shift, Shift.user_id == User.id)
            .filter(
                User.active_role == "executor",
                Shift.start_time.between(start, end),
            )
            .group_by(User.id, User.first_name, User.last_name)
            .order_by(func.count(Shift.id).desc())
            .all()
        )

    def list_executors_without_shifts(self, assigned_ids: list) -> List[User]:
        return (
            self.db.query(User)
            .filter(
                legacy_role_filter("executor"),
                User.is_active.is_(True),
                ~User.id.in_(assigned_ids),
            )
            .all()
        )

    def list_assigned_shifts_between(self, start: datetime, end: date) -> List[Shift]:
        """Назначенные смены в окне, упорядоченные по исполнителю и времени."""
        return (
            self.db.query(Shift)
            .filter(
                Shift.user_id.is_not(None),
                Shift.start_time.between(start, end),
            )
            .order_by(Shift.user_id, Shift.start_time)
            .all()
        )

    # ── Назначение исполнителя на смену ──────────────────────────────────────

    def get_shift(self, shift_id: int) -> Optional[Shift]:
        return self.db.query(Shift).filter(Shift.id == shift_id).first()

    def list_approved_users(self) -> List[User]:
        return self.db.query(User).filter(User.status == "approved").all()

    def count_shifts_for_user_on_day(
        self, user_id: int, day_start: datetime, day_end: datetime
    ) -> int:
        return (
            self.db.query(Shift)
            .filter(
                Shift.user_id == user_id,
                Shift.start_time >= day_start,
                Shift.start_time < day_end,
            )
            .count()
        )

    def list_overlapping_shifts(
        self, user_id: int, exclude_shift_id: int, start: datetime, end: datetime
    ) -> List[Shift]:
        """Смены исполнителя, пересекающиеся с интервалом [start, end)."""
        return (
            self.db.query(Shift)
            .filter(
                Shift.user_id == user_id,
                Shift.id != exclude_shift_id,
                Shift.start_time < end,
                Shift.end_time > start,
            )
            .all()
        )

    def assign_executor(self, shift: Shift, executor_id: int) -> None:
        """Назначить исполнителя на смену и активировать её (один commit)."""
        shift.user_id = executor_id
        shift.status = "active"
        self.db.commit()

    def force_assign_executor(self, shift: Shift, executor_id: int, note: str) -> None:
        """Принудительно назначить исполнителя с пометкой в notes (один commit)."""
        shift.user_id = executor_id
        shift.notes = (shift.notes or "") + note
        self.db.commit()

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()
