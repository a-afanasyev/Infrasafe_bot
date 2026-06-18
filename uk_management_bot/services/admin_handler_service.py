"""Сервисный слой manager/admin-хендлера заявок (handlers/admin.py).

ARCH-01 (PR-29.3): весь прямой ORM из `handlers/admin.py` вынесен сюда. Хендлер
остаётся тонким: FSM-переходы, клавиатуры, i18n, auth, роутинг коллбэков и
UI-ветвление по статусу/флагам УЖЕ ЗАГРУЖЕННОГО объекта (``request.status ==
...`` / ``if r.is_returned`` — это не ORM, а выбор клавиатуры/текста; остаётся в
хендлере). Сервис получает ``db`` (Session) и выполняет ORM на нём — сессией
по-прежнему владеет хендлер (через middleware-инъекцию), поэтому семантика
транзакций не меняется: каждый явный ``commit`` сохранён ровно на той же
логической границе, что и в исходном коде.

В admin.py НЕТ ``next(get_db())``/``SessionLocal()`` для middleware-сессии — она
инъецируется. Канонические переходы статусов идут через отдельный
``workflow_runner.run_command_sync`` (своя транзакция, FOR UPDATE) и НЕ
относятся к этому слою — этот сервис покрывает только сырой ORM, который раньше
жил прямо в хендлере (чтения списков/счётчиков, точечные lookup'ы, каскадное
удаление и best-effort post-commit правки полей вне workflow-канона).

Это отдельный модуль (не расширение ``RequestService``): ``RequestService`` —
широкий доменный сервис, используемый хендлерами И API. Manager-view-запросы
(списки заявок по статусам, счётчики дашборда, назначение/удаление) — узкая
презентационная грань именно admin-хендлера; держим её изолированно (высокая
когезия, низкая связность), как ``ShiftManagementService`` (PR-29.1) и
``RequestHandlerService`` (PR-29.2).
"""

from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import String, or_
from sqlalchemy.orm import Session

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_APPROVED,
    REQUEST_STATUS_CANCELLED,
    REQUEST_STATUS_CLARIFICATION,
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_EXECUTED,
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_NEW,
    REQUEST_STATUS_PURCHASE,
)
from uk_management_bot.utils.workflow_predicates import (
    awaiting_applicant_clause,
    awaiting_manager_clause,
    returned_for_review_clause,
)

logger = logging.getLogger(__name__)

# Наборы статусов фильтров manager-view — единый источник внутри view-слоя
# (значения статусов перенесены дословно из хендлера).
ACTIVE_STATUSES = [
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_PURCHASE,
    REQUEST_STATUS_CLARIFICATION,
]
ARCHIVE_STATUSES = [
    REQUEST_STATUS_EXECUTED,
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_APPROVED,
    REQUEST_STATUS_CANCELLED,
]


class AdminHandlerService:
    """ORM-операции для manager/admin-хендлера заявок (handlers/admin.py)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── Точечные lookup'ы ────────────────────────────────────────────────────

    def get_request_by_number(self, request_number) -> Optional[Request]:
        if not request_number:
            return None
        return (
            self.db.query(Request)
            .filter(Request.request_number == request_number)
            .first()
        )

    def get_user_by_id(self, user_id) -> Optional[User]:
        return self.db.query(User).filter(User.id == user_id).first()

    def get_user_by_telegram_id(self, telegram_id) -> Optional[User]:
        return self.db.query(User).filter(User.telegram_id == telegram_id).first()

    def expire_all(self) -> None:
        """Сбросить identity-map сессии (run_command коммитит в отдельной)."""
        self.db.expire_all()

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()

    def refresh(self, instance) -> None:
        self.db.refresh(instance)

    # ── Назначения ───────────────────────────────────────────────────────────

    def get_active_assignment(self, request_number) -> Optional[RequestAssignment]:
        return (
            self.db.query(RequestAssignment)
            .filter(
                RequestAssignment.request_number == request_number,
                RequestAssignment.status == "active",
            )
            .first()
        )

    def get_active_group_assignment(
        self, request_number, specialization
    ) -> Optional[RequestAssignment]:
        return (
            self.db.query(RequestAssignment)
            .filter(
                RequestAssignment.request_number == request_number,
                RequestAssignment.assignment_type == "group",
                RequestAssignment.group_specialization == specialization,
                RequestAssignment.status == "active",
            )
            .first()
        )

    # ── Смены / исполнители ──────────────────────────────────────────────────

    def get_active_shift_for(self, user_id, now) -> Optional[Shift]:
        return (
            self.db.query(Shift)
            .filter(
                Shift.user_id == user_id,
                Shift.status == "active",
                Shift.start_time <= now,
                or_(Shift.end_time.is_(None), Shift.end_time >= now),
            )
            .first()
        )

    def list_approved_users(self) -> List[User]:
        return self.db.query(User).filter(User.status == "approved").all()

    def list_approved_executors(self) -> List[User]:
        """Approved-пользователи с ролью executor (JSONB-contains по roles)."""
        return (
            self.db.query(User)
            .filter(
                User.roles.cast(String).contains('"executor"'),
                User.status == "approved",
            )
            .all()
        )

    # ── Списки заявок (manager-view) ─────────────────────────────────────────

    def list_active_requests(self, limit: int = 10) -> List[Request]:
        return (
            self.db.query(Request)
            .filter(Request.status.in_(ACTIVE_STATUSES))
            .order_by(
                Request.updated_at.desc().nullslast(), Request.created_at.desc()
            )
            .limit(limit)
            .all()
        )

    def count_active_requests(self) -> int:
        return (
            self.db.query(Request)
            .filter(Request.status.in_(ACTIVE_STATUSES))
            .count()
        )

    def page_active_requests(self, offset: int, limit: int) -> List[Request]:
        return (
            self.db.query(Request)
            .filter(Request.status.in_(ACTIVE_STATUSES))
            .order_by(
                Request.updated_at.desc().nullslast(), Request.created_at.desc()
            )
            .offset(offset)
            .limit(limit)
            .all()
        )

    def list_new_requests(self, limit: int = 10) -> List[Request]:
        return (
            self.db.query(Request)
            .filter(Request.status == REQUEST_STATUS_NEW)
            .order_by(Request.created_at.desc())
            .limit(limit)
            .all()
        )

    def list_executed_requests(self, limit: int = 10) -> List[Request]:
        return (
            self.db.query(Request)
            .filter(Request.status == REQUEST_STATUS_EXECUTED)
            .order_by(
                Request.is_returned.desc(),
                Request.updated_at.desc().nullslast(),
                Request.created_at.desc(),
            )
            .limit(limit)
            .all()
        )

    def list_archive_requests(self, limit: int = 10) -> List[Request]:
        return (
            self.db.query(Request)
            .filter(Request.status.in_(ARCHIVE_STATUSES))
            .order_by(
                Request.updated_at.desc().nullslast(), Request.created_at.desc()
            )
            .limit(limit)
            .all()
        )

    def list_purchase_requests(self, limit: int = 10) -> List[Request]:
        return (
            self.db.query(Request)
            .filter(Request.status == REQUEST_STATUS_PURCHASE)
            .order_by(
                Request.updated_at.desc().nullslast(), Request.created_at.desc()
            )
            .limit(limit)
            .all()
        )

    # ── Списки/счётчики «исполненных» (workflow-предикаты) ───────────────────

    def count_awaiting_manager(self) -> int:
        return self.db.query(Request).filter(awaiting_manager_clause()).count()

    def count_returned_for_review(self) -> int:
        return self.db.query(Request).filter(returned_for_review_clause()).count()

    def count_awaiting_applicant(self) -> int:
        return self.db.query(Request).filter(awaiting_applicant_clause()).count()

    def list_awaiting_manager(self, limit: int = 10) -> List[Request]:
        return (
            self.db.query(Request)
            .filter(awaiting_manager_clause())
            .order_by(
                Request.is_returned.desc(),
                Request.updated_at.desc().nullslast(),
                Request.created_at.desc(),
            )
            .limit(limit)
            .all()
        )

    def list_returned_for_review(self, limit: int = 10) -> List[Request]:
        return (
            self.db.query(Request)
            .filter(returned_for_review_clause())
            .order_by(
                Request.returned_at.desc().nullslast(),
                Request.updated_at.desc().nullslast(),
                Request.created_at.desc(),
            )
            .limit(limit)
            .all()
        )

    def list_awaiting_applicant(self, limit: int = 20) -> List[Request]:
        return (
            self.db.query(Request)
            .filter(awaiting_applicant_clause())
            .order_by(
                Request.completed_at.desc().nullslast(),
                Request.updated_at.desc().nullslast(),
                Request.created_at.desc(),
            )
            .limit(limit)
            .all()
        )

    # ── Best-effort post-commit правки полей вне workflow-канона ─────────────
    # (мутация + commit ровно на той же границе, что и в исходном хендлере)

    def append_clarification_note(self, request: Request, new_note: str, now) -> None:
        """Дописать примечание уточнения вне канон-перехода (статус не трогаем)."""
        if request.notes and request.notes.strip():
            request.notes = request.notes.strip() + "\n\n" + new_note
        else:
            request.notes = new_note
        request.updated_at = now
        self.db.commit()

    def append_purchase_history(self, request: Request, history_entry: str) -> None:
        """Post-commit (вне workflow-полей): дописать историю закупа."""
        if request.purchase_history:
            request.purchase_history += f"\n\n===\n\n{history_entry}"
        else:
            request.purchase_history = history_entry
        self.db.commit()

    def update_materials_comment(
        self, request: Request, new_comment: str, history_entry: str, now
    ) -> None:
        """Обновить комментарий менеджера к материалам + история (один commit)."""
        request.manager_materials_comment = new_comment
        request.updated_at = now
        if request.purchase_history:
            request.purchase_history += f"\n\n---\n\n{history_entry}"
        else:
            request.purchase_history = history_entry
        self.db.commit()

    # ── Каскадное удаление заявки (один commit, как в хендлере) ───────────────

    def delete_request_cascade(self, request: Request, request_number) -> None:
        """Удалить рейтинги/комментарии/назначения и саму заявку (один commit)."""
        from uk_management_bot.database.models.rating import Rating
        from uk_management_bot.database.models.request_comment import RequestComment

        self.db.query(Rating).filter(
            Rating.request_number == request_number
        ).delete()
        self.db.query(RequestComment).filter(
            RequestComment.request_number == request_number
        ).delete()
        self.db.query(RequestAssignment).filter(
            RequestAssignment.request_number == request_number
        ).delete()
        self.db.delete(request)
        self.db.commit()
