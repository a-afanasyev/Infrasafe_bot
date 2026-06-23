"""
Обработчики передачи смен между исполнителями (REG-02, перестроено).

Флоу:
  executor: /transfer_shift (или меню «Мои смены») → выбор смены → причина →
            срочность → комментарий → подтверждение → create_transfer (pending)
  manager:  /pending_transfers → /assign_<id> → выбор исполнителя
            (transfer_assign_executor:<transfer_id>:<user_id>) → assign_transfer
  executor: transfer_response:<accept|reject|details>:<transfer_id>

ВСЕ @require_role-хендлеры объявляют db/user/roles в сигнатуре (DI для
require_role). from/to_executor_id — ВСЕГДА внутренний users.id.
"""

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from uk_management_bot.database.session import session_scope
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_transfer import ShiftTransfer
from uk_management_bot.states.shift_transfer import ShiftTransferStates
from uk_management_bot.keyboards.shift_transfer import (
    shift_selection_keyboard,
    transfer_reason_keyboard,
    urgency_level_keyboard,
    confirm_transfer_keyboard,
    transfers_list_keyboard,
    skip_comment_keyboard,
    executor_selection_keyboard,
    transfer_response_keyboard,
)
from uk_management_bot.services.shift_transfer_service import ShiftTransferService
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.utils.helpers import get_user_language, get_text
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

logger = logging.getLogger(__name__)
router = Router()


def _err_text(error: str, language: str) -> str:
    """Локализованный текст по error-key сервиса.

    Ключи живут в ``shift_transfer.errors.*``; на неизвестный ключ get_text
    вернёт сам ключ — поэтому общий запасной текст подставляем явно.
    """
    full_key = f"shift_transfer.errors.{error}"
    text = get_text(full_key, language=language)
    if text == full_key:
        return get_text("shift_transfer.handlers.error_generic", language=language)
    return text


# ========== ИНИЦИАЦИЯ ПЕРЕДАЧИ СМЕНЫ ==========

@router.message(Command("transfer_shift"))
@require_role(['executor'])
async def cmd_transfer_shift(message: Message, state: FSMContext,
                            db=None, user: User = None, roles: list = None):
    """Команда для передачи смены"""
    user_lang = "ru"
    try:
        with session_scope() as db_local:
            user_lang = get_user_language(message.from_user.id, db_local)
            current = db_local.query(User).filter(User.telegram_id == message.from_user.id).first()
            if not current:
                await message.answer(get_text("shift_transfer.handlers.user_not_found", language=user_lang))
                return

            # FS-02: Shift.user_id — FK на users.id (НЕ telegram_id). Окно по
            # start_time убрано: текущая active-смена тоже передаваема.
            active_shifts = db_local.query(Shift).filter(
                Shift.user_id == current.id,
                Shift.status.in_(['planned', 'active'])
            ).order_by(Shift.start_time).limit(10).all()

            if not active_shifts:
                await message.answer(get_text("shift_transfer.handlers.no_active_shifts", language=user_lang))
                return

            await message.answer(
                get_text("shift_transfer.handlers.select_shift", language=user_lang),
                reply_markup=shift_selection_keyboard(active_shifts, user_lang)
            )
            await state.set_state(ShiftTransferStates.select_shift)

    except Exception as e:
        logger.error(f"Ошибка команды передачи смены: {e}")
        await message.answer(get_text("shift_transfer.handlers.error_init_transfer", language=user_lang))


@router.callback_query(F.data.startswith("transfer_shift:"))
async def handle_shift_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора смены для передачи"""
    user_lang = "ru"
    try:
        shift_id = int(callback.data.split(":")[1])

        with session_scope() as db:
            user_lang = get_user_language(callback.from_user.id, db)
            # FS-02: резолвим внутренний user.id (callback.from_user.id — telegram_id).
            current = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
            shift = db.query(Shift).filter(
                Shift.id == shift_id,
                Shift.user_id == (current.id if current else None)
            ).first()

            if not shift:
                await callback.answer(get_text("shift_transfer.handlers.shift_not_found", language=user_lang), show_alert=True)
                return

            existing_transfer = db.query(ShiftTransfer).filter(
                ShiftTransfer.shift_id == shift_id,
                ShiftTransfer.status.in_(['pending', 'assigned', 'accepted'])
            ).first()

            if existing_transfer:
                await callback.answer(get_text("shift_transfer.handlers.transfer_already_exists", language=user_lang), show_alert=True)
                return

            await state.update_data(selected_shift_id=shift_id)

            await callback.message.edit_text(
                get_text("shift_transfer.handlers.select_reason", language=user_lang),
                reply_markup=transfer_reason_keyboard(user_lang)
            )
            await state.set_state(ShiftTransferStates.select_reason)

    except Exception as e:
        logger.error(f"Ошибка выбора смены: {e}")
        await callback.answer(get_text("shift_transfer.handlers.error_shift_selection", language=user_lang), show_alert=True)


@router.callback_query(F.data.startswith("transfer_reason:"))
async def handle_reason_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора причины передачи"""
    user_lang = "ru"
    try:
        reason = callback.data.split(":")[1]
        with session_scope() as db:
            user_lang = get_user_language(callback.from_user.id, db)

        await state.update_data(transfer_reason=reason)

        await callback.message.edit_text(
            get_text("shift_transfer.handlers.select_urgency", language=user_lang),
            reply_markup=urgency_level_keyboard(user_lang)
        )
        await state.set_state(ShiftTransferStates.select_urgency)

    except Exception as e:
        logger.error(f"Ошибка выбора причины: {e}")
        await callback.answer(get_text("shift_transfer.handlers.error_generic", language=user_lang), show_alert=True)


@router.callback_query(F.data.startswith("transfer_urgency:"))
async def handle_urgency_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора уровня срочности"""
    user_lang = "ru"
    try:
        urgency = callback.data.split(":")[1]
        with session_scope() as db:
            user_lang = get_user_language(callback.from_user.id, db)

        await state.update_data(transfer_urgency=urgency)

        await callback.message.edit_text(
            get_text("shift_transfer.handlers.enter_comment", language=user_lang),
            reply_markup=skip_comment_keyboard(user_lang)
        )
        await state.set_state(ShiftTransferStates.enter_comment)

    except Exception as e:
        logger.error(f"Ошибка выбора срочности: {e}")
        await callback.answer(get_text("shift_transfer.handlers.error_generic", language=user_lang), show_alert=True)


@router.message(ShiftTransferStates.enter_comment)
async def handle_comment_input(message: Message, state: FSMContext):
    """Обработка ввода комментария"""
    user_lang = "ru"
    try:
        with session_scope() as db:
            user_lang = get_user_language(message.from_user.id, db)

        await state.update_data(transfer_comment=message.text)
        await show_transfer_confirmation(message, state, user_lang)

    except Exception as e:
        logger.error(f"Ошибка ввода комментария: {e}")
        await message.answer(get_text("shift_transfer.handlers.error_comment_processing", language=user_lang))


@router.callback_query(F.data == "transfer_comment:skip")
async def handle_skip_comment(callback: CallbackQuery, state: FSMContext):
    """Обработка пропуска комментария"""
    user_lang = "ru"
    try:
        with session_scope() as db:
            user_lang = get_user_language(callback.from_user.id, db)

        await state.update_data(transfer_comment="")
        await show_transfer_confirmation(callback.message, state, user_lang, edit_message=True)

    except Exception as e:
        logger.error(f"Ошибка пропуска комментария: {e}")
        await callback.answer(get_text("shift_transfer.handlers.error_generic", language=user_lang), show_alert=True)


async def show_transfer_confirmation(message: Message, state: FSMContext, user_lang: str, edit_message: bool = False):
    """Показать подтверждение передачи"""
    try:
        data = await state.get_data()

        with session_scope() as db:
            shift = db.query(Shift).filter(Shift.id == data['selected_shift_id']).first()

            reason_text = get_text(f"shift_transfer.handlers.reason_{data['transfer_reason']}", language=user_lang)
            urgency_text = get_text(f"shift_transfer.handlers.urgency_{data['transfer_urgency']}", language=user_lang)
            comment_val = data.get('transfer_comment', '') or get_text("shift_transfer.handlers.not_specified", language=user_lang)
            if not comment_val:
                comment_val = get_text("shift_transfer.handlers.not_specified", language=user_lang)

            confirmation_text = get_text("shift_transfer.handlers.transfer_confirmation", language=user_lang).format(
                shift_date=shift.start_time.strftime('%d.%m.%Y %H:%M'),
                reason=reason_text,
                urgency=urgency_text,
                comment=comment_val
            )

            if edit_message:
                await message.edit_text(
                    confirmation_text,
                    reply_markup=confirm_transfer_keyboard(user_lang),
                    parse_mode="HTML"
                )
            else:
                await message.answer(
                    confirmation_text,
                    reply_markup=confirm_transfer_keyboard(user_lang),
                    parse_mode="HTML"
                )

            await state.set_state(ShiftTransferStates.confirm_transfer)

    except Exception as e:
        logger.error(f"Ошибка показа подтверждения: {e}")


@router.callback_query(F.data.startswith("transfer_confirm:"))
async def handle_transfer_confirmation(callback: CallbackQuery, state: FSMContext):
    """Обработка подтверждения передачи"""
    user_lang = "ru"
    try:
        action = callback.data.split(":")[1]
        with session_scope() as db:
            user_lang = get_user_language(callback.from_user.id, db)

        if action == "cancel":
            await callback.message.edit_text(get_text("shift_transfer.handlers.transfer_cancelled", language=user_lang))
            await state.clear()
            return

        elif action == "edit":
            await callback.message.edit_text(
                get_text("shift_transfer.handlers.select_reason", language=user_lang),
                reply_markup=transfer_reason_keyboard(user_lang)
            )
            await state.set_state(ShiftTransferStates.select_reason)
            return

        elif action == "yes":
            data = await state.get_data()

            with session_scope() as db:
                # FS-02: from_executor_id — внутренний users.id.
                current = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
                if not current:
                    await callback.message.edit_text(get_text("shift_transfer.handlers.user_not_found", language=user_lang))
                    await state.clear()
                    return

                transfer_service = ShiftTransferService(db)
                result = transfer_service.create_transfer(
                    shift_id=data['selected_shift_id'],
                    from_executor_id=current.id,
                    reason=data['transfer_reason'],
                    comment=data.get('transfer_comment', ''),
                    urgency_level=data['transfer_urgency']
                )

                if result['success']:
                    await callback.message.edit_text(get_text("shift_transfer.handlers.transfer_created_success", language=user_lang))
                else:
                    await callback.message.edit_text(
                        get_text("shift_transfer.handlers.transfer_create_error", language=user_lang).format(
                            error=_err_text(result['error'], user_lang)
                        )
                    )

            await state.clear()

    except Exception as e:
        logger.error(f"Ошибка подтверждения передачи: {e}")
        await callback.answer(get_text("shift_transfer.handlers.error_generic", language=user_lang), show_alert=True)


# ========== НАЗНАЧЕНИЕ ИСПОЛНИТЕЛЯ (ДЛЯ МЕНЕДЖЕРОВ) ==========

@router.message(Command("pending_transfers"))
@require_role(['manager'])
async def cmd_pending_transfers(message: Message, state: FSMContext = None,
                                db=None, user: User = None, roles: list = None):
    """Команда для просмотра ожидающих передач (для менеджеров)"""
    user_lang = "ru"
    try:
        with session_scope() as db_local:
            user_lang = get_user_language(message.from_user.id, db_local)
            pending_transfers = ShiftTransferService(db_local).list_pending_transfers(limit=20)

            if not pending_transfers:
                await message.answer(get_text("shift_transfer.handlers.no_pending_transfers", language=user_lang))
                return

            transfers_text = get_text("shift_transfer.handlers.pending_transfers_title", language=user_lang) + "\n\n"

            for transfer in pending_transfers:
                executor_name = transfer.from_executor.first_name or get_text("shift_transfer.handlers.unknown", language=user_lang)
                shift_date = transfer.shift.start_time.strftime('%d.%m %H:%M') if transfer.shift and transfer.shift.start_time else "—"
                reason_text = get_text(f"shift_transfer.handlers.reason_{transfer.reason}", language=user_lang)
                transfers_text += f"• {executor_name} - {shift_date}\n  " + get_text("shift_transfer.handlers.reason_label", language=user_lang) + f": {reason_text}\n  /assign_{transfer.id}\n\n"

            await message.answer(transfers_text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка получения ожидающих передач: {e}")
        await message.answer(get_text("shift_transfer.handlers.error_loading_transfers", language=user_lang))


@router.message(F.text.regexp(r"^/assign_(\d+)$"))
@require_role(['manager'])
async def cmd_assign_transfer(message: Message, state: FSMContext = None,
                              db=None, user: User = None, roles: list = None):
    """Менеджер выбирает исполнителя для передачи (/assign_<id>)."""
    user_lang = "ru"
    try:
        transfer_id = int(message.text.split("_", 1)[1])
        with session_scope() as db_local:
            user_lang = get_user_language(message.from_user.id, db_local)
            service = ShiftTransferService(db_local)
            transfer = db_local.query(ShiftTransfer).filter(ShiftTransfer.id == transfer_id).first()
            if not transfer or transfer.status != "pending":
                await message.answer(_err_text("transfer_not_found", user_lang))
                return

            # CR-1: spec-префильтр через сервис (не показывать заведомо невалидных).
            eligible = service.list_eligible_executors(
                exclude_user_id=transfer.from_executor_id,
                shift=service.get_shift(transfer.shift_id),
            )

            if not eligible:
                await message.answer(get_text("shift_transfer.handlers.no_eligible_executors", language=user_lang))
                return

            await message.answer(
                get_text("shift_transfer.handlers.select_executor", language=user_lang),
                reply_markup=executor_selection_keyboard(transfer_id, eligible, user_lang, mode="transfer")
            )

    except Exception as e:
        logger.error(f"Ошибка /assign_: {e}")
        await message.answer(get_text("shift_transfer.handlers.error_generic", language=user_lang))


@router.callback_query(F.data.startswith("transfer_assign_executor:"))
@require_role(['manager'])
async def handle_transfer_assign_executor(callback: CallbackQuery, state: FSMContext = None,
                                          db=None, user: User = None, roles: list = None):
    """Назначение получателя передачи + уведомление получателю с клавиатурой ответа."""
    user_lang = "ru"
    try:
        _, transfer_id_s, to_user_id_s = callback.data.split(":")
        transfer_id, to_executor_id = int(transfer_id_s), int(to_user_id_s)

        with session_scope() as db_local:
            user_lang = get_user_language(callback.from_user.id, db_local)
            manager = db_local.query(User).filter(User.telegram_id == callback.from_user.id).first()

            service = ShiftTransferService(db_local)
            result = service.assign_transfer(transfer_id, to_executor_id, manager.id if manager else None)

            if not result['success']:
                await callback.answer(_err_text(result['error'], user_lang), show_alert=True)
                return

            # Уведомить получателя с клавиатурой ответа (отдельным сообщением).
            recipient = db_local.query(User).filter(User.id == to_executor_id).first()
            if recipient:
                rec_lang = recipient.language or "ru"
                try:
                    await callback.bot.send_message(
                        recipient.telegram_id,
                        get_text("shift_transfer.handlers.transfer_assigned_to_you", language=rec_lang),
                        reply_markup=transfer_response_keyboard(transfer_id, rec_lang)
                    )
                except Exception as send_err:
                    logger.warning(f"Не удалось уведомить получателя {to_executor_id}: {send_err}")

            await callback.message.edit_text(get_text("shift_transfer.handlers.transfer_assigned_success", language=user_lang))

    except Exception as e:
        logger.error(f"Ошибка назначения исполнителя передачи: {e}")
        await callback.answer(get_text("shift_transfer.handlers.error_generic", language=user_lang), show_alert=True)


@router.callback_query(F.data.startswith("transfer_response:"))
@require_role(['executor', 'manager'])
async def handle_transfer_response(callback: CallbackQuery, state: FSMContext = None,
                                   db=None, user: User = None, roles: list = None):
    """Ответ получателя на передачу: accept / reject / details."""
    user_lang = "ru"
    try:
        _, action, transfer_id_s = callback.data.split(":")
        transfer_id = int(transfer_id_s)

        with session_scope() as db_local:
            user_lang = get_user_language(callback.from_user.id, db_local)
            current = db_local.query(User).filter(User.telegram_id == callback.from_user.id).first()
            if not current:
                await callback.answer(get_text("shift_transfer.handlers.user_not_found", language=user_lang), show_alert=True)
                return

            service = ShiftTransferService(db_local)

            if action == "details":
                transfer = service.get_transfer(transfer_id)
                if not transfer:
                    await callback.answer(_err_text("transfer_not_found", user_lang), show_alert=True)
                    return
                shift_date = transfer.shift.start_time.strftime('%d.%m %H:%M') if transfer.shift and transfer.shift.start_time else "—"
                reason_text = get_text(f"shift_transfer.handlers.reason_{transfer.reason}", language=user_lang)
                await callback.answer(
                    get_text("shift_transfer.handlers.transfer_details", language=user_lang).format(
                        date=shift_date, reason=reason_text, comment=transfer.comment or "—"
                    ),
                    show_alert=True
                )
                return

            if action == "accept":
                result = service.accept_transfer(transfer_id, current.id)
                ok_key = "transfer_accepted_success"
            elif action == "reject":
                result = service.reject_transfer(transfer_id, current.id)
                ok_key = "transfer_rejected_success"
            else:
                await callback.answer(get_text("shift_transfer.handlers.error_generic", language=user_lang), show_alert=True)
                return

            if result['success']:
                await callback.message.edit_text(get_text(f"shift_transfer.handlers.{ok_key}", language=user_lang))
            else:
                await callback.answer(_err_text(result['error'], user_lang), show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка ответа на передачу: {e}")
        await callback.answer(get_text("shift_transfer.handlers.error_generic", language=user_lang), show_alert=True)


@router.callback_query(F.data.startswith("view_transfer:"))
@require_role(['executor', 'manager'])
async def handle_view_transfer(callback: CallbackQuery, state: FSMContext = None,
                               db=None, user: User = None, roles: list = None):
    """Детали передачи (из списка «Мои передачи»). Только участник или менеджер."""
    user_lang = "ru"
    try:
        transfer_id = int(callback.data.split(":")[1])
        with session_scope() as db_local:
            user_lang = get_user_language(callback.from_user.id, db_local)
            current = db_local.query(User).filter(
                User.telegram_id == callback.from_user.id
            ).first()
            transfer = ShiftTransferService(db_local).get_transfer(transfer_id)
            if not transfer:
                await callback.answer(_err_text("transfer_not_found", user_lang), show_alert=True)
                return
            # IDOR-guard: детали видит только участник передачи или менеджер.
            is_manager = bool(roles and "manager" in roles)
            if not is_manager and (
                not current
                or current.id not in (transfer.from_executor_id, transfer.to_executor_id)
            ):
                await callback.answer(_err_text("not_your_transfer", user_lang), show_alert=True)
                return

            shift_date = transfer.shift.start_time.strftime('%d.%m %H:%M') if transfer.shift and transfer.shift.start_time else "—"
            reason_text = get_text(f"shift_transfer.handlers.reason_{transfer.reason}", language=user_lang)
            status_text = get_text(f"shift_transfer.keyboards.transfer_status_{transfer.status}", language=user_lang)
            await callback.answer(
                get_text("shift_transfer.handlers.transfer_details", language=user_lang).format(
                    date=shift_date, reason=reason_text, comment=transfer.comment or "—"
                ) + f"\n{status_text}",
                show_alert=True
            )

    except Exception as e:
        logger.error(f"Ошибка просмотра передачи: {e}")
        await callback.answer(get_text("shift_transfer.handlers.error_generic", language=user_lang), show_alert=True)


# ========== ПРОСМОТР ПЕРЕДАЧ ==========

@router.message(Command("my_transfers"))
@require_role(['executor', 'manager'])
async def cmd_my_transfers(message: Message, state: FSMContext = None,
                          db=None, user: User = None, roles: list = None):
    """Команда для просмотра своих передач"""
    user_lang = "ru"
    try:
        with session_scope() as db_local:
            user_lang = get_user_language(message.from_user.id, db_local)
            current = db_local.query(User).filter(User.telegram_id == message.from_user.id).first()

            # FS-02: from/to_executor_id — FK на users.id.
            my_transfers = db_local.query(ShiftTransfer).filter(
                or_(
                    ShiftTransfer.from_executor_id == (current.id if current else None),
                    ShiftTransfer.to_executor_id == (current.id if current else None)
                )
            ).options(
                joinedload(ShiftTransfer.shift),
                joinedload(ShiftTransfer.from_executor),
                joinedload(ShiftTransfer.to_executor)
            ).order_by(ShiftTransfer.created_at.desc()).limit(10).all()

            if not my_transfers:
                await message.answer(get_text("shift_transfer.handlers.no_transfers", language=user_lang))
                return

            await message.answer(
                get_text("shift_transfer.handlers.select_transfer", language=user_lang),
                reply_markup=transfers_list_keyboard(
                    my_transfers, user_lang, current_user_id=current.id if current else None
                )
            )

    except Exception as e:
        logger.error(f"Ошибка получения передач пользователя: {e}")
        await message.answer(get_text("shift_transfer.handlers.error_loading_transfers", language=user_lang))


# ========== НАВИГАЦИЯ ==========

@router.callback_query(F.data == "shift_transfer:back")
@router.callback_query(F.data == "transfer_step:back")
@router.callback_query(F.data == "assign_step:back")
@router.callback_query(F.data == "transfers:back")
async def handle_back_navigation(callback: CallbackQuery, state: FSMContext):
    """Обработка навигации назад"""
    try:
        await callback.message.delete()
        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка навигации назад: {e}")
        await callback.answer()
