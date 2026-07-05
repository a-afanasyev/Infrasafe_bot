"""Сервисный слой resident/executor-хендлера заявок.

ARCH-01 + CODE-04 (PR-29.2): весь прямой ORM из `handlers/requests.py` вынесен
сюда. Хендлер остаётся тонким: FSM-переходы, клавиатуры, i18n, auth, роутинг
коллбэков и UI-ветвление по статусу УЖЕ ЗАГРУЖЕННОГО объекта (``request.status
== ...`` — это не ORM, а выбор клавиатуры). Сервис получает ``db`` (Session) и
выполняет ORM на нём — сессией по-прежнему владеет хендлер (``session_scope()``
или инъекция в тестах), поэтому семантика транзакций не меняется: каждый явный
``commit`` сохранён ровно на той же логической границе, что и в исходном коде.

Это отдельный модуль (не расширение ``RequestService``): ``RequestService`` —
широкий доменный сервис, используемый хендлерами И API (create_request,
update_status_by_actor, метрики). Resident/executor-view-запросы списков и
пул-логика — узкая презентационная грань именно этого хендлера; держим её
изолированно (высокая когезия, низкая связность), как ``ShiftManagementService``
для PR-29.1.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import case, false, or_
from sqlalchemy.orm import Session, aliased

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment

logger = logging.getLogger(__name__)

# Наборы статусов фильтров «Мои заявки» — единый источник внутри view-слоя
# (значения статусов идентичны исходному коду хендлера, перенесены дословно).
ACTIVE_STATUSES = ["Новая", "В работе", "Закуп", "Уточнение"]
ARCHIVE_STATUSES = ["Выполнена", "Исполнено", "Принято", "Отменена"]
EXECUTOR_ACTIVE_STATUSES = ["В работе", "Закуп", "Уточнение"]


class RequestHandlerService:
    """ORM-операции для resident/executor-хендлера заявок (handlers/requests.py)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── Пользователь ─────────────────────────────────────────────────────────

    def get_user_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        return self.db.query(User).filter(User.telegram_id == telegram_id).first()

    # ── Заявка (одиночная) ───────────────────────────────────────────────────

    def get_request_by_number(self, request_number: str) -> Optional[Request]:
        return (
            self.db.query(Request)
            .filter(Request.request_number == request_number)
            .first()
        )

    def expire_all(self) -> None:
        """Сбросить identity-map сессии (run_command коммитит в отдельной)."""
        self.db.expire_all()

    # ── save_request: создание заявки (ctor:Request) ─────────────────────────

    def create_request_record(
        self,
        *,
        request_number: str,
        category: str,
        address: str,
        description: str,
        urgency: str,
        apartment_id,
        building_id,
        yard_id,
        address_type,
        media_files: list,
        user_id: int,
        source: str,
        status: str = "Новая",
    ) -> Request:
        """Создать строку заявки и положить в сессию (без commit — коммитит
        вызывающий после emit, как в исходном коде)."""
        request = Request(
            request_number=request_number,
            category=category,
            address=address,
            description=description,
            urgency=urgency,
            apartment_id=apartment_id,
            building_id=building_id,
            yard_id=yard_id,
            address_type=address_type,
            media_files=media_files,
            user_id=user_id,
            source=source,
            status=status,
        )
        self.db.add(request)
        return request

    def commit(self) -> None:
        self.db.commit()

    # ── Доступ к заявке (view) ───────────────────────────────────────────────

    def get_active_assignment(self, request_number: str) -> Optional[RequestAssignment]:
        return (
            self.db.query(RequestAssignment)
            .filter(
                RequestAssignment.request_number == request_number,
                RequestAssignment.status == "active",
            )
            .first()
        )

    def is_apartment_resident(self, user_id: int, apartment_id: int) -> bool:
        return (
            self.db.query(UserApartment)
            .filter(
                UserApartment.user_id == user_id,
                UserApartment.apartment_id == apartment_id,
                UserApartment.status == "approved",
            )
            .first()
            is not None
        )

    # ── Запросы списков заявок исполнителя / пула ────────────────────────────

    def get_executor_requests_query(self, user: User):
        """Заявки исполнителя — ТОЛЬКО его персональные (individual / взятые).

        FEAT-группы: непривязанные group-назначения здесь больше НЕ показываем —
        они в отдельном «пуле свободных» (``get_group_pool_query``). Сюда заявка
        попадает лишь ПОСЛЕ взятия (EXECUTOR_CLAIM конвертирует group→individual,
        executor_id := взявший).
        """
        assignment_alias = aliased(RequestAssignment)

        query = self.db.query(Request).outerjoin(
            assignment_alias, Request.request_number == assignment_alias.request_number
        )
        conditions = [
            # активное individual-назначение на меня
            (assignment_alias.status == "active") & (assignment_alias.executor_id == user.id),
            # fallback: прямое Request.executor_id (заявки без RequestAssignment)
            Request.executor_id == user.id,
        ]
        query = query.filter(or_(*conditions))

        # Дедупликация: подзапрос по request_number, т.к. DISTINCT на всех колонках
        # не работает с JSON полями в PostgreSQL
        request_numbers_subq = query.with_entities(Request.request_number).distinct().subquery()
        return self.db.query(Request).filter(
            Request.request_number.in_(self.db.query(request_numbers_subq.c.request_number))
        )

    def get_group_pool_query(self, user: User):
        """FEAT-группы: пул «свободных» group-заявок для исполнителя.

        Видны ТОЛЬКО дежурному сейчас (on-shift): заявки «В работе» с активным
        group-назначением по его специализации и БЕЗ исполнителя (executor_id
        NULL). Не на смене / без специализаций → пустой набор.
        """
        from uk_management_bot.utils.shifts import is_on_shift_now_sync
        from uk_management_bot.utils.specializations import parse_specializations

        specs = parse_specializations(user)
        if not specs or not is_on_shift_now_sync(self.db, user.id):
            return self.db.query(Request).filter(false())

        assignment_alias = aliased(RequestAssignment)
        query = self.db.query(Request).join(
            assignment_alias, Request.request_number == assignment_alias.request_number
        ).filter(
            Request.status.in_(["В работе"]),
            assignment_alias.status == "active",
            assignment_alias.assignment_type == "group",
            assignment_alias.executor_id.is_(None),
            assignment_alias.group_specialization.in_(specs),
        )
        request_numbers_subq = query.with_entities(Request.request_number).distinct().subquery()
        return self.db.query(Request).filter(
            Request.request_number.in_(self.db.query(request_numbers_subq.c.request_number))
        )

    def list_group_pool(self, user: User) -> List[Request]:
        return self.get_group_pool_query(user).order_by(Request.created_at.desc()).all()

    # ── «Мои заявки» (applicant/other + executor) ────────────────────────────

    def _applicant_requests_query(self, user_id: int):
        return self.db.query(Request).filter(Request.user_id == user_id)

    @staticmethod
    def _apply_status_filter(query, active_status: Optional[str], is_executor: bool):
        """Status-фильтр списка «Мои заявки» — дословно из хендлера."""
        if active_status == "active":
            if is_executor:
                return query.filter(Request.status.in_(EXECUTOR_ACTIVE_STATUSES))
            return query.filter(Request.status.in_(ACTIVE_STATUSES))
        if active_status == "archive":
            return query.filter(Request.status.in_(ARCHIVE_STATUSES))
        return query

    @staticmethod
    def _order_my_requests(query, active_role: str, active_status: Optional[str]):
        if active_role != "executor" and active_status == "all":
            status_priority = case(
                (Request.status.in_(ACTIVE_STATUSES), 0),  # Активные
                else_=1,  # Архивные
            )
            return query.order_by(status_priority, Request.created_at.desc())
        return query.order_by(Request.created_at.desc())

    def list_my_requests(
        self, user: User, active_role: str, active_status: Optional[str]
    ) -> List[Request]:
        """Полный список «Мои заявки» (для in-memory пагинации в хендлере)."""
        is_executor = active_role == "executor"
        if is_executor:
            query = self.get_executor_requests_query(user)
        else:
            query = self._applicant_requests_query(user.id)
        query = self._apply_status_filter(query, active_status, is_executor)
        return self._order_my_requests(query, active_role, active_status).all()

    def list_pagination_requests(
        self, user: User, active_role: str, active_status: Optional[str]
    ) -> List[Request]:
        """Список для handle_pagination — дословная семантика исходного хендлера.

        Отличается от ``list_my_requests``: status-фильтр БЕЗ executor-специфики
        и сортировка ВСЕГДА по created_at desc (без case-приоритета). Поведение
        сохранено как было.
        """
        if active_role == "executor":
            query = self.get_executor_requests_query(user)
        else:
            query = self._applicant_requests_query(user.id)
        if active_status == "active":
            query = query.filter(Request.status.in_(ACTIVE_STATUSES))
        elif active_status == "archive":
            query = query.filter(Request.status.in_(ARCHIVE_STATUSES))
        return query.order_by(Request.created_at.desc()).all()

    def list_applicant_requests_filtered(
        self, user_id: int, choice: Optional[str]
    ) -> List[Request]:
        """Список заявок заявителя по фильтру status_filter-коллбэка."""
        query = self._applicant_requests_query(user_id)
        if choice in ("active", "В работе"):
            query = query.filter(Request.status.in_(ACTIVE_STATUSES))
        elif choice == "archive":
            query = query.filter(Request.status.in_(ARCHIVE_STATUSES))
        if choice == "all":
            status_priority = case(
                (Request.status.in_(ACTIVE_STATUSES), 0),
                else_=1,
            )
            return query.order_by(status_priority, Request.created_at.desc()).all()
        return query.order_by(Request.created_at.desc()).all()

    # ── handle_back_to_list: пагинированный список + active-shift ────────────

    def get_active_shift(self, user_id: int, now) -> Optional[Shift]:
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

    def _executor_back_to_list_query(
        self, user: User, has_active_shift: bool, executor_specializations: list
    ):
        query = self.db.query(Request).join(RequestAssignment).filter(
            RequestAssignment.status == "active"
        )
        assignment_conditions = [RequestAssignment.executor_id == user.id]
        if has_active_shift and executor_specializations:
            for spec in executor_specializations:
                assignment_conditions.append(
                    (RequestAssignment.assignment_type == "group")
                    & (RequestAssignment.group_specialization == spec)
                )
        if assignment_conditions:
            return query.filter(or_(*assignment_conditions))
        return query.filter(RequestAssignment.executor_id == user.id)

    def paginate_back_to_list(
        self,
        user: User,
        active_role: str,
        active_status: str,
        has_active_shift: bool,
        executor_specializations: list,
        offset: int,
        limit: int,
    ):
        """(total_count, page_items) для handle_back_to_list — БД-пагинация."""
        if active_role == "executor":
            query = self._executor_back_to_list_query(
                user, has_active_shift, executor_specializations
            )
        else:
            query = self._applicant_requests_query(user.id)

        if active_role != "executor":
            if active_status == "active":
                query = query.filter(Request.status.in_(ACTIVE_STATUSES))
            elif active_status == "archive":
                query = query.filter(Request.status.in_(ARCHIVE_STATUSES))

        if active_role != "executor" and active_status == "all":
            status_priority = case(
                (Request.status.in_(ACTIVE_STATUSES), 0),
                else_=1,
            )
            query = query.order_by(status_priority, Request.created_at.desc())
        else:
            query = query.order_by(Request.created_at.desc())

        total = query.count()
        page = query.offset(offset).limit(limit).all()
        return total, page

    # ── Диагностический тестовый запрос (show_my_requests) ───────────────────

    def count_plumber_group_test_requests(self) -> int:
        """Диагностика (лог): сколько group-назначений сантехникам в работе."""
        return (
            self.db.query(Request)
            .join(RequestAssignment)
            .filter(
                RequestAssignment.status == "active",
                RequestAssignment.assignment_type == "group",
                RequestAssignment.group_specialization == "plumber",
                Request.status.in_(EXECUTOR_ACTIVE_STATUSES),
            )
            .count()
        )

    # ── replyclarify: сохранение ответа в notes ──────────────────────────────

    def append_clarify_reply(self, request: Request, new_notes: str) -> None:
        """Сохранить новый текст диалога уточнения (один commit)."""
        request.notes = new_notes
        self.db.commit()

    # ── claim-notify: рассылка остальным дежурным ────────────────────────────

    def list_approved_users(self) -> List[User]:
        return self.db.query(User).filter(User.status == "approved").all()


# ── Складской учёт: guard и атомарное списание для бот-хендлера ──────
# ARCH-01: ORM бот-сценария списания живёт здесь (не в хендлере и не в
# доменно-чистом material_service — тот не знает про RequestComment/commit).

def guard_executor_issue(db: Session, *, request_number: str,
                         telegram_id: int):
    """Guard списания материалов исполнителем.

    Returns:
        (request, user, err_key): err_key — ключ локали при отказе, иначе None.
        Проверки: заявка существует; статус «В работе»; актор — назначенный
        исполнитель заявки.
    """
    from uk_management_bot.utils.constants import REQUEST_STATUS_IN_PROGRESS

    request = (db.query(Request)
               .filter(Request.request_number == request_number).first())
    if request is None:
        return None, None, "errors.request_not_found"
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if user is None:
        return request, None, "common.user_not_found"
    if request.status != REQUEST_STATUS_IN_PROGRESS:
        return request, user, "materials.issue.wrong_status"
    if request.executor_id != user.id:
        return request, user, "materials.issue.not_executor"
    return request, user, None


def issue_material_with_comment(db: Session, *, material_id: int, qty,
                                created_by: int, request_number: str,
                                comment_text: str):
    """Списание + RequestComment(type='material') + commit — ОДНА транзакция
    (упало что-то одно → откатилось всё).

    Обёртка поверх доменно-чистого ``material_service.issue_material_sync``
    (тот комментариев не пишет и не коммитит).
    """
    from uk_management_bot.database.models.request_comment import RequestComment
    from uk_management_bot.services.material_service import issue_material_sync

    try:
        issue = issue_material_sync(
            db, material_id=material_id, qty=qty, created_by=created_by,
            doc_type="request", request_number=request_number,
        )
        db.add(RequestComment(
            request_number=request_number,
            user_id=created_by,
            comment_text=comment_text,
            comment_type="material",
        ))
        db.commit()
        return issue
    except Exception:
        db.rollback()
        raise
