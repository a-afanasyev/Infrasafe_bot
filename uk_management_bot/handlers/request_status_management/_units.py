"""DTO и sync unit-of-work живого пути «Закуп» (AUD3-07, канон B1/B4).

AUD5-ARCH-3 (волна 12): файл — часть пакета ``request_status_management``
(разбит плоский Router-файл). Код перенесён 1:1 из handlers/request_status_management.py.
BUG-137: юниты мёртвого FSM-флоу смены статусов ретайрены; остались только
``_apply_purchase`` и его DTO (живой путь handle_materials_input).
"""

from dataclasses import dataclass, field
from typing import List, Optional

from uk_management_bot.database.models.request import Request
from uk_management_bot.services.request_service import RequestService
from uk_management_bot.services.comment_service import CommentService
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_PURCHASE,
    REQUEST_STATUS_CLARIFICATION
)

# ==========================================================================
# DTO + sync-юниты (AUD3-07). Сессия живёт только внутри юнита.
# ==========================================================================


@dataclass(frozen=True)
class _ActiveRow:
    request_number: str
    status: str
    category: str
    address: str


@dataclass(frozen=True)
class _PurchaseOutcome:
    outcome: str  # "no_request" | "fail" | "ok"
    fail_message: Optional[str] = None
    requested_materials: Optional[str] = None
    manager_comment: Optional[str] = None
    active_requests: List[_ActiveRow] = field(default_factory=list)
    # BUG-174: notices о комментарии закупки — шлёт async-слой хендлера
    notices: List = field(default_factory=list)


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

    notices = []
    if commenter_id is not None:
        _, notices = CommentService(db).add_purchase_comment(
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
        notices=notices,
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

