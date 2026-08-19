"""Менеджер: назначение исполнителей (дежурный/конкретный)."""
from aiogram import F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.orm import Session

from uk_management_bot.services.admin_handler_service import AdminHandlerService
from uk_management_bot.keyboards.admin import (
    get_assignment_type_keyboard,
    get_executors_by_category_keyboard,
)
from uk_management_bot.constants.categories import get_specialization_for_category
from uk_management_bot.database.session import run_db
from uk_management_bot.services.request_number_service import REQUEST_NUMBER_CORE

import logging
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.keyboards.requests import resolve_category_key, get_category_display
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.auth_helpers import has_admin_access, has_manager_role
from uk_management_bot.utils.specializations import (
    matches_required_specs,
    parse_specializations,
)

from ._router import router

from .shared import (
    ASSIGN_ALREADY_GROUP,
    ASSIGN_ALREADY_INDIVIDUAL,
    ASSIGN_NO_EXECUTORS,
    ASSIGN_NO_SPECIALIZATION,
    ASSIGN_OK,
    auto_assign_request_by_category,
)

logger = logging.getLogger(__name__)


def _duty_outcome_text(outcome: str, lang: str) -> str:
    """Человеческий текст на каждый неуспешный исход группового назначения."""
    if outcome in (ASSIGN_ALREADY_INDIVIDUAL, ASSIGN_ALREADY_GROUP):
        return get_text("admin.handlers.reassign_already_assigned", language=lang)
    if outcome == ASSIGN_NO_SPECIALIZATION:
        return get_text("admin.handlers.duty_assign_no_specialization", language=lang)
    if outcome == ASSIGN_NO_EXECUTORS:
        return get_text("admin.handlers.duty_assign_no_executors", language=lang)
    return get_text("admin.handlers.duty_assign_failed", language=lang)


# ===== ОБРАБОТЧИКИ НАЗНАЧЕНИЯ ИСПОЛНИТЕЛЕЙ =====

@router.callback_query(F.data.startswith("assign_duty_"))
async def handle_assign_duty_executor_admin(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Назначение дежурного специалиста (автоматическое по сменам)"""
    try:
        lang = language

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("assign_duty_", "")
        logger.info(f"Назначение дежурного специалиста для заявки {request_number}")

        # Получаем заявку
        request = AdminHandlerService(db).get_request_by_number(request_number)
        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Используем существующую логику auto_assign. Исход РАЗЛИЧИМ: раньше
        # функция на всех ветках возвращала None, и «✅ назначена» печаталось
        # даже когда она не сделала ничего — заявка уже назначена, у категории
        # нет специализации, исполнителей нет. Менеджер уходил с ложным
        # подтверждением, а заявка оставалась как была.
        outcome = await auto_assign_request_by_category(request, db, user)

        if outcome != ASSIGN_OK:
            await callback.answer(
                _duty_outcome_text(outcome, lang), show_alert=True)
            return

        # Пытаемся отредактировать сообщение
        success_message = get_text("admin.handlers.duty_assigned_success", language=lang).format(request_number=request_number)

        try:
            await callback.message.edit_text(
                success_message,
                parse_mode="HTML"
            )
        except TelegramBadRequest as telegram_error:
            # Если сообщение не изменилось, отправляем callback.answer вместо редактирования
            if "message is not modified" in str(telegram_error):
                await callback.answer(get_text("admin.handlers.assignment_done_success", language=lang), show_alert=False)
                logger.info(f"Сообщение не изменилось, использован callback.answer для заявки {request_number}")
            else:
                # Если другая ошибка Telegram - отправляем новое сообщение
                await callback.message.answer(success_message, parse_mode="HTML")
                await callback.answer()

        await callback.answer()  # Убираем "часики"
        logger.info(f"Заявка {request_number} назначена дежурному специалисту")

    except TelegramBadRequest as e:
        logger.error(f"Ошибка Telegram при назначении дежурного специалиста: {e}", exc_info=True)
        await callback.answer(get_text("admin.handlers.assignment_done_display_error", language=lang), show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка назначения дежурного специалиста: {e}", exc_info=True)
        await callback.answer(get_text("admin.handlers.error_assigning", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("assign_specific_"))
async def handle_assign_specific_executor_admin(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Показать список исполнителей для ручного выбора"""
    try:
        lang = language

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("assign_specific_", "")
        logger.info(f"Выбор конкретного исполнителя для заявки {request_number}")

        svc = AdminHandlerService(db)
        # Получаем заявку
        request = svc.get_request_by_number(request_number)
        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        # Получаем исполнителей с нужной специализацией.
        # BUG-166: дефолт был `"other"` — не канон, он не совпадал ни с чем и
        # компенсировался джокером `or "other" in specializations` ниже. Джокер
        # ушёл вместе с переходом на общий предикат, поэтому дефолт обязан быть
        # тем же, что у диспетчера, — иначе для незнакомой категории менеджер
        # получал бы пустой список кандидатов.
        spec = get_specialization_for_category(request.category)

        logger.info(f"[SPECIFIC_ASSIGN] Категория '{request.category}' → специализация: '{spec}'")

        # Получаем всех исполнителей с данной специализацией
        # ИСПРАВЛЕНО: проверяем наличие роли "executor" в массиве roles
        # Используем JSONB operator @> для проверки вхождения элемента в массив
        executors = svc.list_approved_executors()

        logger.info(f"[SPECIFIC_ASSIGN] Найдено {len(executors)} исполнителей (с ролью executor) со статусом 'approved'")

        # Фильтруем по специализации
        filtered_executors = []
        for ex in executors:
            # BUG-166: общий предикат вместо своего сравнения. Свой джокер
            # `"other"` при этом уходит: он никогда не был каноническим
            # значением, а миграция 010 развернула его в `repair`.
            #
            # Ушёл и локальный `json.loads` в try/except: он падал на CSV- и
            # скалярном хранении (`'plumber,electric'`, `'plumber'`), и такой
            # исполнитель молча выпадал из списка кандидатов с warning'ом
            # «ошибка парсинга». `parse_specializations` читает все три формы.
            executor_specs = parse_specializations(ex)
            logger.debug(f"[SPECIFIC_ASSIGN] Исполнитель {ex.id} ({ex.first_name}): специализации = {sorted(executor_specs)}")

            if matches_required_specs(executor_specs, {spec}):
                filtered_executors.append(ex)
                logger.info(f"[SPECIFIC_ASSIGN] ✅ Исполнитель {ex.id} ({ex.first_name}) подходит (есть '{spec}')")
            else:
                logger.debug(f"[SPECIFIC_ASSIGN] ❌ Исполнитель {ex.id} ({ex.first_name}) НЕ подходит (нет '{spec}')")

        logger.info(f"[SPECIFIC_ASSIGN] Отфильтровано {len(filtered_executors)} исполнителей с специализацией '{spec}'")

        executors_text = get_text("admin.handlers.executors_found", language=lang).format(count=len(filtered_executors)) if filtered_executors else get_text("admin.handlers.no_executors_available", language=lang)

        await callback.message.edit_text(
            get_text("admin.handlers.choose_executor", language=lang).format(
                request_number=request_number,
                category=get_category_display(resolve_category_key(request.category), language=lang),
                spec=spec,
                executors_text=executors_text
            ),
            reply_markup=get_executors_by_category_keyboard(request_number, request.category, filtered_executors),
            parse_mode="HTML"
        )

        logger.info(f"Показан список из {len(filtered_executors)} исполнителей для заявки {request_number}")

    except Exception as e:
        logger.error(f"Ошибка показа списка исполнителей: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)


# Фильтр СТРОГИЙ, а не startswith: открытый префикс перехватывал чужой
# callback модуля смен `assign_executor_to_shift:{shift_id}:{executor_id}`
# (handlers/shift_management/assignment_b.py), потому что admin_router включён
# в main.py РАНЬШЕ роутера смен. Заявка «to_shift:5:12» разбиралась как номер,
# int() падал — менеджер видел «Ошибка назначения», а назначение исполнителя на
# смену не работало вовсе. Переименовать callback смен нельзя: это убило бы
# кнопки в уже отрисованных у пользователей клавиатурах.
@router.callback_query(F.data.regexp(rf"^assign_executor_{REQUEST_NUMBER_CORE}_\d+$"))
async def handle_final_executor_assignment_admin(callback: CallbackQuery, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Финальное назначение конкретного исполнителя — КАНОНОМ.

    Раньше здесь звался `AssignmentService.assign_to_executor`: строка
    назначения появлялась, а статус оставался «Новой», audit писался не в
    формате workflow, outbox/webhook/realtime не выпускались вовсе, и
    уведомление исполнителю уходило вручную на языке МЕНЕДЖЕРА. Дашборд тем
    временем назначал через `MANAGER_ASSIGN`, то есть у одной операции было два
    писателя с разным результатом.

    Теперь вход общий с переназначением (`handlers/admin/reassignment.py`):
    те же три фазы вокруг `run_command_sync`, те же интенты, тот же текст
    исполнителю на ЕГО языке. Осознанное следствие: назначение из бота теперь
    двигает «Новая»→«В работе» и уведомляет жителя — ровно как с дашборда.
    """
    lang = language
    try:
        from .reassignment import _answer_verdict, _commit_reassign, _preflight

        # Проверка прав — ЗДЕСЬ, а не только внутри общего `_guard`: authz-скан
        # раскрывает вызовы транзитивно лишь в пределах модуля, и импортированный
        # guard он не видит. Хендлер, берущий id из callback.data и идущий в БД,
        # обязан нести признак авторизации на себе (ратчет
        # tests/services/test_handler_authz_ratchet.py).
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return
        # Канон разрешает MANAGER_ASSIGN только менеджеру (`_is_manager`), а
        # has_admin_access пропускает и чистого admin — без этой проверки он
        # дошёл бы до команды и получил NotAuthorized как общую ошибку.
        if not has_manager_role(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.reassign_manager_only", language=lang), show_alert=True)
            return

        # Парсим данные: assign_executor_251013-001_123 (регекс уже гарантировал форму)
        payload = callback.data[len("assign_executor_"):]
        request_number, _, raw_id = payload.rpartition("_")
        executor_id = int(raw_id)

        logger.info(f"Финальное назначение исполнителя {executor_id} на заявку {request_number}")

        pre = await run_db(
            lambda s: _preflight(s, request_number, executor_id, lang), db=None)
        if pre.verdict != "ok":
            await _answer_verdict(callback, pre, lang)
            return

        await _commit_reassign(callback, user, lang, pre)

    except Exception as e:
        logger.error(f"Ошибка финального назначения исполнителя: {e}", exc_info=True)
        await callback.answer(get_text("admin.handlers.error_assigning", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("back_to_assignment_type_"))
async def handle_back_to_assignment_type_admin(callback: CallbackQuery, db: Session, roles: list = None, active_role: str = None, user: User = None, language: str = "ru"):
    """Возврат к выбору типа назначения"""
    try:
        lang = language

        # Проверяем права доступа
        if not has_admin_access(roles=roles, user=user):
            await callback.answer(get_text("admin.handlers.no_access_actions", language=lang), show_alert=True)
            return

        request_number = callback.data.replace("back_to_assignment_type_", "")

        request = AdminHandlerService(db).get_request_by_number(request_number)

        if not request:
            await callback.answer(get_text("admin.handlers.request_not_found", language=lang), show_alert=True)
            return

        await callback.message.edit_text(
            get_text("admin.handlers.request_accepted_choose_assignment", language=lang).format(
                request_number=request_number,
                category=get_category_display(resolve_category_key(request.category), language=lang),
                address=request.address
            ),
            reply_markup=get_assignment_type_keyboard(request_number),
            parse_mode="HTML"
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка возврата к выбору типа назначения: {e}")
        await callback.answer(get_text("admin.handlers.error_occurred", language=lang), show_alert=True)

