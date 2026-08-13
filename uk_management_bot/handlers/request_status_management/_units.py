"""DTO и sync unit-of-work управления статусами заявок (AUD3-07, канон B1/B4).

AUD5-ARCH-3 (волна 12): файл — часть пакета ``request_status_management``
(разбит плоский Router-файл); здесь живут DTO и sync-юниты, хендлеры — в
соседних под-модулях. Код перенесён 1:1 из handlers/request_status_management.py.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.services.request_service import RequestService
from uk_management_bot.services.comment_service import CommentService
from uk_management_bot.utils.helpers import get_user_language
from uk_management_bot.utils.auth_helpers import check_user_role_sync
from uk_management_bot.utils.constants import (
    ROLE_EXECUTOR,
    REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_PURCHASE,
    REQUEST_STATUS_CLARIFICATION, REQUEST_STATUS_EXECUTED
)

from .availability import get_available_statuses

# ==========================================================================
# DTO + sync-юниты (AUD3-07). Сессия живёт только внутри юнита.
# ==========================================================================


@dataclass(frozen=True)
class _ActiveRow:
    request_number: str
    status: str
    category: str
    address: str


def _load_status_change_context(db, request_number: str, actor_id: int):
    """→ ("no_request"|"no_user"|"ok", current_status, user_roles, available)."""
    request = db.query(Request).filter(Request.request_number == request_number).first()
    if not request:
        return "no_request", None, None, None

    user = db.query(User).filter(User.id == actor_id).first()
    if not user:
        return "no_user", None, None, None

    available = get_available_statuses(user, request)
    return "ok", request.status, user.roles, available


def _request_exists(db, request_number: str) -> bool:
    return db.query(Request).filter(
        Request.request_number == request_number
    ).first() is not None


def _load_confirmation_context(db, request_number: str, from_user_id: int, need_db_lang: bool):
    """→ (found, category, address, db_lang|None) для show_status_confirmation."""
    request = db.query(Request).filter(Request.request_number == request_number).first()
    if not request:
        return False, None, None, None
    db_lang = get_user_language(from_user_id, db) if need_db_lang else None
    return True, request.category, request.address, db_lang


def _apply_status_change(db, request_number: str, new_status: str, actor_tg: int,
                         current_status: Optional[str], comment: Optional[str],
                         commenter_id: Optional[int]):
    """Канон-переход + комментарий-лог (оба сервиса коммитят сами). → result dict."""
    result = RequestService(db).update_status_by_actor(
        request_number=request_number,
        new_status=new_status,
        actor_telegram_id=actor_tg
    )
    if not result["success"]:
        return result

    if commenter_id is not None:
        comment_service = CommentService(db)
        if comment:
            comment_service.add_status_change_comment(
                request_number=request_number,
                user_id=commenter_id,
                previous_status=current_status,
                new_status=new_status,
                additional_comment=comment
            )
        else:
            comment_service.add_status_change_comment(
                request_number=request_number,
                user_id=commenter_id,
                previous_status=current_status,
                new_status=new_status
            )
    return result


def _take_to_work(db, request_number: str, actor_tg: int):
    """→ ("no_role"|"not_assigned"|("fail", msg)|"ok")."""
    if not check_user_role_sync(actor_tg, ROLE_EXECUTOR, db):
        return "no_role", None

    request = db.query(Request).filter(Request.request_number == request_number).first()
    if not request or request.executor_id != actor_tg:
        return "not_assigned", None

    result = RequestService(db).update_status_by_actor(
        request_number=request_number,
        new_status=REQUEST_STATUS_IN_PROGRESS,
        actor_telegram_id=actor_tg
    )
    if not result["success"]:
        return "fail", result["message"]

    # ⚠️ Исторический вызов сохранён 1:1: у add_status_change_comment НЕТ
    # параметра actor_telegram_id — вызов всегда падает TypeError, который
    # ловит except хендлера (наблюдаемое поведение: статус уже переведён,
    # пользователю показывается error_occurred). Дефект зафиксирован в
    # бэклоге при конвертации (AUD3-07 волна 2) — здесь НЕ чинится, чтобы
    # рефакторинг остался поведенчески эквивалентным.
    CommentService(db).add_status_change_comment(
        request_number=request_number,
        actor_telegram_id=actor_tg,
        previous_status=request.status,
        new_status=REQUEST_STATUS_IN_PROGRESS,
        additional_comment="Исполнитель взял заявку в работу"
    )

    return "ok", None


def _has_role(db, actor_tg: int, role: str) -> bool:
    return check_user_role_sync(actor_tg, role, db)


@dataclass(frozen=True)
class _PurchaseOutcome:
    outcome: str  # "no_request" | "fail" | "ok"
    fail_message: Optional[str] = None
    requested_materials: Optional[str] = None
    manager_comment: Optional[str] = None
    active_requests: List[_ActiveRow] = field(default_factory=list)


def _apply_purchase(db, request_number: str, materials: str, actor_tg: int,
                    commenter_id: Optional[int]) -> _PurchaseOutcome:
    """Полная DB-фаза handle_materials_input (порядок 1:1 с историческим телом)."""
    request = db.query(Request).filter(Request.request_number == request_number).first()
    if not request:
        return _PurchaseOutcome("no_request")

    # PR2c: requested_materials — workflow-поле канона. Итоговый список
    # (восстановление из purchase_history при повторном заходе в Закуп +
    # докладка нового) вычисляем ЛОКАЛЬНО (только чтение) и передаём в
    # payload канон-команды; прямую ORM-запись requested_materials убрали.
    restored_comment = None
    base_materials = request.requested_materials
    if request.purchase_history and not base_materials:
        history_lines = request.purchase_history.split('\n')
        last_requested = None
        last_comment = None
        for i in range(len(history_lines) - 1, -1, -1):
            line = history_lines[i].strip()
            if line.startswith("Запрошенные материалы:"):
                last_requested = line.replace("Запрошенные материалы:", "").strip()
            elif line.startswith("Комментарий менеджера:") and not last_comment:
                last_comment = line.replace("Комментарий менеджера:", "").strip()
            if last_requested and last_comment:
                break
        if last_requested and last_requested != "Не указано":
            base_materials = last_requested
        if last_comment and last_comment != "Без комментариев":
            restored_comment = last_comment

    final_materials = f"{base_materials}\n{materials}" if base_materials else materials

    # Канон-переход В работе→Закуп с материалами в payload
    # (EXECUTOR_PURCHASE / MANAGER_PURCHASE). requested_materials пишет
    # run_command (SET) в своей tx.
    result = RequestService(db).update_status_by_actor(
        request_number=request_number,
        new_status=REQUEST_STATUS_PURCHASE,
        actor_telegram_id=actor_tg,
        requested_materials=final_materials,
    )
    if not result["success"]:
        return _PurchaseOutcome("fail", fail_message=result["message"])

    # Post-commit: НЕ-workflow поля (legacy-зеркало + восстановленный
    # комментарий) + комментарий-лог. run_command писал в своей сессии →
    # перечитываем заявку свежей.
    request = db.query(Request).filter(Request.request_number == request_number).first()
    if request is None:
        # BUG-145: заявка удалена конкурентно между канон-переходом и
        # перечиткой — раньше падали AttributeError на None.
        return _PurchaseOutcome("no_request")
    if restored_comment:
        request.manager_materials_comment = restored_comment
    request.purchase_materials = materials  # legacy-зеркало (вне workflow-полей)

    if commenter_id is not None:
        CommentService(db).add_purchase_comment(
            request_number=request_number,
            user_id=commenter_id,
            materials=materials
        )

    db.commit()

    active_statuses = [REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_PURCHASE, REQUEST_STATUS_CLARIFICATION]
    q = (
        db.query(Request)
        .filter(Request.status.in_(active_statuses))
        .order_by(Request.updated_at.desc().nullslast(), Request.created_at.desc())
    )
    rows = q.limit(10).all()

    return _PurchaseOutcome(
        "ok",
        requested_materials=request.requested_materials,
        manager_comment=request.manager_materials_comment,
        active_requests=[
            _ActiveRow(
                request_number=r.request_number,
                status=r.status,
                category=r.category,
                address=r.address,
            )
            for r in rows
        ],
    )


def _apply_completion(db, request_number: str, full_report: str, actor_tg: int,
                      commenter_id: Optional[int]):
    """DB-фаза handle_completion_report_input. → ("no_request"|"fail"|"ok", msg, user_id)."""
    request = db.query(Request).filter(Request.request_number == request_number).first()
    if not request:
        return "no_request", None, None

    # Канон-переход →Выполнена (EXECUTOR_COMPLETE / MANAGER_COMPLETE);
    # completion_report пишет run_command.
    result = RequestService(db).update_status_by_actor(
        request_number=request_number,
        new_status=REQUEST_STATUS_EXECUTED,
        actor_telegram_id=actor_tg,
        completion_report=full_report,
    )
    if not result["success"]:
        return "fail", result["message"], None

    # Post-commit: комментарий-лог (run_command писал в своей сессии).
    request = db.query(Request).filter(Request.request_number == request_number).first()
    if commenter_id is not None:
        CommentService(db).add_completion_report_comment(
            request_number=request_number,
            user_id=commenter_id,
            report=full_report
        )

    db.commit()
    return "ok", None, request.user_id


def _notify_request_completed(db, request_number: str, user_id: int) -> None:
    """⚠️ Исторический вызов сохранён 1:1: метода notify_request_completed у
    NotificationService НЕ СУЩЕСТВУЕТ (git -S подтверждает: не существовал как
    минимум с baseline-сквоша) — обращение всегда даёт AttributeError, который
    ловит except хендлера. Дефект зафиксирован в бэклоге при конвертации
    (AUD3-07 волна 2) — здесь НЕ чинится (эквивалентность рефакторинга)."""
    from uk_management_bot.services.notification_service import NotificationService
    NotificationService(db).notify_request_completed(request_number, user_id)

