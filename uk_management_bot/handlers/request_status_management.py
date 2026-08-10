"""
Обработчики для управления статусами заявок
Обеспечивает функциональность изменения статусов заявок с комментариями

AUD3-07 (канон B1/B4): DB-фаза каждого хендлера — цельный sync unit-of-work
(`_load_*`/`_apply_*` ниже) в worker-потоке через ``run_db``; наружу DTO,
рендер — по ним. Хендлеры НЕ объявляют параметр ``db`` (гейт:
tests/services/test_aud337_async_handlers_gate.py); тестовый seam —
keyword-only ``_db``. Сервисы (RequestService/CommentService) sync и коммитят
сами — безопасны в thread-сессии (прецедент B4/AuthService).
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import run_db
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.states.request_status import RequestStatusStates
from uk_management_bot.services.request_service import RequestService
from uk_management_bot.services.comment_service import CommentService
from uk_management_bot.keyboards.request_status import (
    get_status_selection_keyboard,
    get_status_confirmation_keyboard
)
from uk_management_bot.utils.helpers import get_text, get_user_language
from uk_management_bot.utils.status_display import get_status_display, get_status_with_emoji
from uk_management_bot.utils.auth_helpers import check_user_role_sync
from uk_management_bot.utils.constants import (
    ROLE_MANAGER, ROLE_EXECUTOR, ROLE_APPLICANT,
    REQUEST_STATUS_NEW, REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_PURCHASE,
    REQUEST_STATUS_CLARIFICATION, REQUEST_STATUS_EXECUTED,
    REQUEST_STATUS_COMPLETED, REQUEST_STATUS_APPROVED
)

router = Router()
logger = logging.getLogger(__name__)


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


@router.callback_query(F.data.startswith("change_status_"))
async def handle_status_change_start(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Начало процесса изменения статуса заявки"""
    try:
        lang = language
        # Получаем номер заявки
        request_number = callback.data.split("_")[-1]

        user_id = callback.from_user.id
        outcome, current_status, user_roles, available_statuses = await run_db(
            lambda s: _load_status_change_context(s, request_number, user_id), db=_db
        )

        if outcome == "no_request":
            from uk_management_bot.utils.safe_localization import safe_get_text
            await callback.answer(safe_get_text("errors.request_not_found", language=lang), show_alert=True)
            return

        if outcome == "no_user":
            await callback.answer(get_text("request_status_mgmt.handlers.user_not_found", language=lang), show_alert=True)
            return

        if not available_statuses:
            await callback.answer(get_text("request_status_mgmt.handlers.no_available_statuses", language=lang), show_alert=True)
            return

        # Сохраняем данные в состоянии
        await state.update_data(
            request_number=request_number,
            current_status=current_status,
            user_roles=user_roles
        )

        # Показываем выбор нового статуса
        keyboard = get_status_selection_keyboard(available_statuses, lang)

        await callback.message.edit_text(
            get_text("request_status_mgmt.handlers.select_status", language=lang).format(
                current_status=get_status_display(current_status, language=lang)
            ),
            reply_markup=keyboard
        )

        # Переходим в состояние выбора статуса
        await state.set_state(RequestStatusStates.waiting_for_status)

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка начала изменения статуса: {e}")
        await callback.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.callback_query(F.data.startswith("status_"))
async def handle_status_selection(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработка выбора нового статуса"""
    try:
        lang = language
        # Получаем новый статус из callback data
        new_status = callback.data.split("_", 1)[1]

        # Сохраняем новый статус в состоянии
        await state.update_data(new_status=new_status)

        # Получаем данные заявки
        data = await state.get_data()
        request_number = data.get("request_number")

        # Проверяем существование заявки
        exists = await run_db(lambda s: _request_exists(s, request_number), db=_db)
        if not exists:
            await callback.answer(get_text("request_status_mgmt.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Проверяем, нужен ли комментарий для этого статуса
        requires_comment = new_status in [REQUEST_STATUS_PURCHASE, REQUEST_STATUS_CLARIFICATION, REQUEST_STATUS_EXECUTED]

        if requires_comment:
            # Запрашиваем комментарий
            comment_prompt = get_comment_prompt(new_status, lang)

            await callback.message.edit_text(comment_prompt)

            # Переходим в состояние ввода комментария
            await state.set_state(RequestStatusStates.waiting_for_comment)
        else:
            # Показываем подтверждение без комментария
            await show_status_confirmation(callback, state, new_status, _db=_db)

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка выбора статуса: {e}")
        await callback.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.message(RequestStatusStates.waiting_for_comment)
async def handle_comment_input(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработка ввода комментария для изменения статуса"""
    try:
        lang = language
        # Получаем комментарий
        comment = message.text.strip()

        if not comment:
            await message.answer(get_text("request_status_mgmt.handlers.please_enter_comment", language=lang))
            return

        # Сохраняем комментарий в состоянии
        await state.update_data(comment=comment)

        # Получаем данные из состояния
        data = await state.get_data()
        new_status = data.get("new_status")

        # Показываем подтверждение с комментарием
        await show_status_confirmation(message, state, new_status, comment, _db=_db)

    except Exception as e:
        logger.error(f"Ошибка ввода комментария: {e}")
        await message.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)))

@router.callback_query(F.data == "confirm_status_change")
async def handle_status_confirmation(callback: CallbackQuery, state: FSMContext, language: str = "ru", user: User = None, *, _db=None):
    """Подтверждение изменения статуса"""
    try:
        lang = language
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")
        current_status = data.get("current_status")
        new_status = data.get("new_status")
        comment = data.get("comment")

        if not request_number or not new_status:
            await callback.answer(get_text("request_status_mgmt.handlers.data_not_found", language=lang), show_alert=True)
            return

        actor_tg = callback.from_user.id
        commenter_id = user.id if user else None
        result = await run_db(
            lambda s: _apply_status_change(
                s, request_number, new_status, actor_tg, current_status, comment, commenter_id
            ),
            db=_db,
        )
        if not result["success"]:
            await callback.message.edit_text(f"❌ {result['message']}")
            await state.clear()
            return

        # Показываем сообщение об успехе
        success_text = get_text("request_status_mgmt.handlers.success", language=lang).format(
            request_number=request_number,
            old_status=get_status_display(current_status, language=lang),
            new_status=get_status_display(new_status, language=lang)
        )

        await callback.message.edit_text(success_text)

        # Очищаем состояние
        await state.clear()

        await callback.answer(get_text("request_status_mgmt.handlers.status_changed_success", language=lang))

    except Exception as e:
        logger.error(f"Ошибка подтверждения изменения статуса: {e}")
        await callback.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.callback_query(F.data == "cancel_status_change")
async def handle_status_cancellation(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Отмена изменения статуса"""
    try:
        lang = language
        # Очищаем состояние
        await state.clear()

        await callback.message.edit_text(get_text("request_status_mgmt.handlers.status_change_cancelled", language=lang))
        await callback.answer(get_text("request_status_mgmt.handlers.status_change_cancelled", language=lang))

    except Exception as e:
        logger.error(f"Ошибка отмены изменения статуса: {e}")
        await callback.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

# Специальные обработчики для исполнителей

@router.callback_query(F.data.startswith("take_to_work_"))
async def handle_take_to_work(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Исполнитель берет заявку в работу"""
    try:
        lang = language
        request_number = callback.data.split("_")[-1]
        actor_tg = callback.from_user.id

        outcome, fail_message = await run_db(
            lambda s: _take_to_work(s, request_number, actor_tg), db=_db
        )

        if outcome == "no_role":
            await callback.answer(get_text("request_status_mgmt.handlers.no_permission", language=lang), show_alert=True)
            return
        if outcome == "not_assigned":
            await callback.answer(get_text("request_status_mgmt.handlers.request_not_assigned_to_you", language=lang), show_alert=True)
            return
        if outcome == "fail":
            await callback.answer(fail_message, show_alert=True)
            return

        await callback.answer(get_text("request_status_mgmt.handlers.request_taken_to_work", language=lang))

    except Exception as e:
        logger.error(f"Ошибка взятия в работу: {e}")
        await callback.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.callback_query(F.data.startswith("purchase_materials_"))
async def handle_purchase_materials(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Перевод заявки в статус закупки материалов"""
    try:
        lang = language
        # Проверяем права доступа
        actor_tg = callback.from_user.id
        if not await run_db(lambda s: _has_role(s, actor_tg, ROLE_EXECUTOR), db=_db):
            await callback.answer(get_text("request_status_mgmt.handlers.no_permission", language=lang), show_alert=True)
            return

        request_number = callback.data.split("_")[-1]

        # Сохраняем данные в состоянии
        await state.update_data(
            request_number=request_number,
            action="purchase_materials"
        )

        # Запрашиваем список материалов
        await callback.message.edit_text(
            get_text("request_status_mgmt.handlers.enter_materials", language=lang)
        )

        # Переходим в состояние ввода материалов
        await state.set_state(RequestStatusStates.waiting_for_materials)

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка закупки материалов: {e}")
        await callback.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.message(RequestStatusStates.waiting_for_materials)
async def handle_materials_input(message: Message, state: FSMContext, language: str = "ru", user: User = None, *, _db=None):
    """Обработка ввода списка материалов"""
    try:
        lang = language
        # Получаем список материалов
        materials = message.text.strip()

        if not materials:
            await message.answer(get_text("request_status_mgmt.handlers.please_enter_materials", language=lang))
            return

        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")

        actor_tg = message.from_user.id
        commenter_id = user.id if user else None
        res = await run_db(
            lambda s: _apply_purchase(s, request_number, materials, actor_tg, commenter_id),
            db=_db,
        )

        if res.outcome == "no_request":
            await message.answer(get_text("request_status_mgmt.handlers.request_not_found", language=lang))
            return
        if res.outcome == "fail":
            await message.answer(f"❌ {res.fail_message}")
            await state.clear()
            return

        # Показываем подтверждение с текущими данными
        confirmation_text = get_text("request_status_mgmt.handlers.purchase_status_set", language=lang).format(request_number=request_number)

        if res.requested_materials:
            confirmation_text += get_text("request_status_mgmt.handlers.requested_materials", language=lang).format(materials=res.requested_materials)

        if res.manager_comment:
            confirmation_text += get_text("request_status_mgmt.handlers.manager_comment", language=lang).format(comment=res.manager_comment)

        confirmation_text += get_text("request_status_mgmt.handlers.new_input", language=lang).format(materials=materials)

        await message.answer(confirmation_text)

        if res.active_requests:
            # Показываем список активных заявок
            text = get_text("request_status_mgmt.handlers.active_requests_header", language=lang)
            for i, r in enumerate(res.active_requests, 1):
                addr = r.address[:40] + ("…" if len(r.address) > 40 else "")
                text += f"{i}. {get_status_with_emoji(r.status, language=lang)} #{r.request_number} - {r.category}\n"
                text += f"   📍 {addr}\n\n"

            from uk_management_bot.keyboards.admin import get_manager_main_keyboard
            await message.answer(text, reply_markup=get_manager_main_keyboard(language=lang))

        # Очищаем состояние
        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка сохранения материалов: {e}")
        await message.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)))

@router.callback_query(F.data.startswith("complete_work_"))
async def handle_complete_work(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Завершение работы по заявке"""
    try:
        lang = language
        # Проверяем права доступа
        actor_tg = callback.from_user.id
        if not await run_db(lambda s: _has_role(s, actor_tg, ROLE_EXECUTOR), db=_db):
            await callback.answer(get_text("request_status_mgmt.handlers.no_permission", language=lang), show_alert=True)
            return

        request_number = callback.data.split("_")[-1]

        # Сохраняем данные в состоянии
        await state.update_data(
            request_number=request_number,
            action="complete_work"
        )

        # Запрашиваем отчет о выполнении
        await callback.message.edit_text(
            get_text("request_status_mgmt.handlers.enter_completion_report", language=lang)
        )

        # Переходим в состояние ввода отчета
        await state.set_state(RequestStatusStates.waiting_for_completion_report)

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка завершения работы: {e}")
        await callback.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)), show_alert=True)

@router.message(RequestStatusStates.waiting_for_completion_report, F.photo | F.video)
async def handle_completion_report_media(message: Message, state: FSMContext, language: str = "ru", user: User = None):
    """Обработка фото/видео в отчете о выполнении"""
    try:
        lang = language
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")

        if not request_number:
            await message.answer(get_text("request_status_mgmt.handlers.request_not_found_in_state", language=lang))
            return

        # Получаем file_id
        if message.photo:
            file_id = message.photo[-1].file_id
            file_type = "photo"
        else:
            file_id = message.video.file_id
            file_type = "video"

        # Сохраняем file_id в FSM
        report_media = data.get('report_media', [])
        if len(report_media) >= 5:
            await message.answer(get_text("request_status_mgmt.handlers.max_files_reached", language=lang))
            return

        report_media.append(file_id)
        await state.update_data(report_media=report_media)

        # Загружаем файл в Media Service
        from uk_management_bot.utils.media_helpers import upload_report_file_to_media_service
        try:
            await upload_report_file_to_media_service(
                bot=message.bot,
                file_id=file_id,
                request_number=request_number,
                report_type=f"completion_{file_type}",
                description=f"Фото/видео отчета #{len(report_media)}",
                uploaded_by=user.id if user else None
            )
            logger.info(f"Файл отчета загружен в Media Service для заявки {request_number}")
        except Exception as e:
            logger.error(f"Ошибка загрузки файла отчета в Media Service: {e}")

        await message.answer(
            get_text("request_status_mgmt.handlers.file_added", language=lang).format(
                count=len(report_media), max=5
            )
        )

    except Exception as e:
        logger.error(f"Ошибка обработки медиа отчета: {e}")
        await message.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)))


@router.message(RequestStatusStates.waiting_for_completion_report)
async def handle_completion_report_input(message: Message, state: FSMContext, language: str = "ru", user: User = None, *, _db=None):
    """Обработка ввода отчета о выполнении"""
    try:
        lang = language
        # Получаем отчет
        report = message.text.strip() if message.text else ""

        if not report:
            await message.answer(get_text("request_status_mgmt.handlers.please_enter_report", language=lang))
            return

        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")
        report_media = data.get("report_media", [])

        # Отчёт (completion_report — workflow-поле канона, PR2c): собираем текст
        # ЛОКАЛЬНО и передаём в payload канон-команды; прямую ORM-запись убрали.
        full_report = report
        if report_media:
            full_report += "\n" + get_text("request_status_mgmt.handlers.attached_files", language=lang).format(count=len(report_media))

        actor_tg = message.from_user.id
        commenter_id = user.id if user else None
        outcome, fail_message, request_user_id = await run_db(
            lambda s: _apply_completion(s, request_number, full_report, actor_tg, commenter_id),
            db=_db,
        )

        if outcome == "no_request":
            await message.answer(get_text("request_status_mgmt.handlers.request_not_found", language=lang))
            return
        if outcome == "fail":
            await message.answer(get_text("request_status_mgmt.handlers.work_completion_failed", language=lang).format(message=fail_message))
            await state.clear()
            return

        # Отправляем уведомление заявителю (исторически бьётся AttributeError —
        # см. докстринг _notify_request_completed; except ниже ловит как раньше).
        await run_db(
            lambda s: _notify_request_completed(s, request_number, request_user_id), db=_db
        )

        # Показываем подтверждение
        success_text = get_text("request_status_mgmt.handlers.work_completed", language=lang).format(
            request_id=request_number
        )

        await message.answer(success_text)

        # Очищаем состояние
        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка завершения работы: {e}")
        await message.answer(get_text("request_status_mgmt.handlers.error_occurred", language=language).format(error=str(e)))

# Вспомогательные функции

def get_available_statuses(user: User, request: Request) -> list:
    """Получение доступных статусов в зависимости от роли пользователя и текущего статуса"""
    available_statuses = []

    # Проверяем роли пользователя
    user_roles = user.roles if user.roles else []

    current_status = request.status

    # Менеджеры могут изменять статусы
    if ROLE_MANAGER in user_roles:
        if current_status == REQUEST_STATUS_NEW:
            available_statuses.extend([REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_CLARIFICATION])
        elif current_status == REQUEST_STATUS_IN_PROGRESS:
            available_statuses.extend([REQUEST_STATUS_CLARIFICATION, REQUEST_STATUS_EXECUTED])
        elif current_status == REQUEST_STATUS_PURCHASE:
            available_statuses.append(REQUEST_STATUS_IN_PROGRESS)
        elif current_status == REQUEST_STATUS_CLARIFICATION:
            available_statuses.append(REQUEST_STATUS_IN_PROGRESS)
        elif current_status == REQUEST_STATUS_EXECUTED:
            available_statuses.append(REQUEST_STATUS_APPROVED)
        elif current_status == REQUEST_STATUS_COMPLETED:
            available_statuses.append(REQUEST_STATUS_APPROVED)

    # Исполнители могут изменять статусы своих заявок
    elif ROLE_EXECUTOR in user_roles and request.executor_id == user.id:
        if current_status == REQUEST_STATUS_IN_PROGRESS:
            available_statuses.extend([REQUEST_STATUS_PURCHASE, REQUEST_STATUS_CLARIFICATION, REQUEST_STATUS_EXECUTED])
        elif current_status == REQUEST_STATUS_PURCHASE:
            available_statuses.append(REQUEST_STATUS_IN_PROGRESS)

    # Заявители могут принимать выполненные заявки
    elif ROLE_APPLICANT in user_roles and request.user_id == user.id:
        if current_status == REQUEST_STATUS_EXECUTED:
            available_statuses.append(REQUEST_STATUS_APPROVED)
        elif current_status == REQUEST_STATUS_COMPLETED:
            available_statuses.append(REQUEST_STATUS_APPROVED)

    return available_statuses

def get_comment_prompt(status: str, language: str = "ru") -> str:
    """Получение промпта для комментария в зависимости от статуса"""
    prompts = {
        REQUEST_STATUS_PURCHASE: get_text("request_status_mgmt.handlers.prompt_purchase", language=language),
        REQUEST_STATUS_CLARIFICATION: get_text("request_status_mgmt.handlers.prompt_clarification", language=language),
        REQUEST_STATUS_EXECUTED: get_text("request_status_mgmt.handlers.prompt_executed", language=language),
    }

    return prompts.get(status, get_text("request_status_mgmt.handlers.prompt_default", language=language))

async def show_status_confirmation(callback_or_message, state: FSMContext, new_status: str, comment: str = None, language: str = "ru", *, _db=None):
    """Показ подтверждения изменения статуса"""
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")
        current_status = data.get("current_status")

        # Язык: как исторический get_language_from_event — сперва
        # language_code из Telegram, иначе fallback на БД внутри юнита.
        tg_lang = None
        from_user_id = None
        if hasattr(callback_or_message, 'from_user') and callback_or_message.from_user:
            tg_lang = getattr(callback_or_message.from_user, 'language_code', None)
            from_user_id = callback_or_message.from_user.id

        # `not tg_lang` (не `is None`): исторический get_language_from_event
        # уходил в БД-fallback и на пустой строке language_code (LOW ревью).
        found, category, address, db_lang = await run_db(
            lambda s: _load_confirmation_context(
                s, request_number, from_user_id, need_db_lang=(not tg_lang and from_user_id is not None)
            ),
            db=_db,
        )
        if not found:
            lang_fallback = language
            not_found_text = get_text("request_status_mgmt.handlers.request_not_found", language=lang_fallback)
            if hasattr(callback_or_message, 'edit_text'):
                await callback_or_message.answer(not_found_text, show_alert=True)
            else:
                await callback_or_message.answer(not_found_text)
            return

        # Формируем текст подтверждения
        lang = tg_lang or db_lang or "ru"
        confirmation_text = get_text("request_status_mgmt.handlers.confirmation", language=lang).format(
            request_number=request_number,
            current_status=get_status_display(current_status, language=lang),
            new_status=get_status_display(new_status, language=lang),
            category=category,
            address=address
        )

        if comment:
            confirmation_text += get_text("request_status_mgmt.handlers.confirmation_comment", language=lang).format(comment=comment)

        # Показываем клавиатуру подтверждения
        keyboard = get_status_confirmation_keyboard(lang)

        if hasattr(callback_or_message, 'edit_text'):
            await callback_or_message.edit_text(confirmation_text, reply_markup=keyboard)
        else:
            await callback_or_message.answer(confirmation_text, reply_markup=keyboard)

        # Переходим в состояние подтверждения
        await state.set_state(RequestStatusStates.waiting_for_confirmation)

    except Exception as e:
        logger.error(f"Ошибка показа подтверждения: {e}")
        lang_err = language
        err_text = get_text("request_status_mgmt.handlers.error_occurred", language=lang_err).format(error=str(e))
        if hasattr(callback_or_message, 'edit_text'):
            await callback_or_message.answer(err_text, show_alert=True)
        else:
            await callback_or_message.answer(err_text)
