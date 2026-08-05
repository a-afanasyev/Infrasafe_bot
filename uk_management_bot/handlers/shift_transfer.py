"""
Обработчики передачи смен между исполнителями (REG-02, перестроено).

Флоу:
  executor: /transfer_shift (или меню «Мои смены») → выбор смены → причина →
            срочность → комментарий → подтверждение → create_transfer (pending)
  manager:  /pending_transfers → /assign_<id> → выбор исполнителя
            (transfer_assign_executor:<transfer_id>:<user_id>) → assign_transfer
  executor: transfer_response:<accept|reject|details>:<transfer_id>

@require_role-хендлеры объявляют user/roles (DI для require_role); параметр
``db`` НЕ объявляется — иначе aiogram DI инъецирует middleware-сессию (AUD3-37).
from/to_executor_id — ВСЕГДА внутренний users.id.

AUD3-37 (вариант (б), волна B2): DB-фаза каждого хендлера — sync unit-of-work,
исполняемый в worker-потоке через ``run_db``; сессия живёт только внутри юнита,
наружу выходят DTO/скаляры. Вызовы ShiftTransferService происходят внутри
юнитов — сервис уезжает в поток транзитивно. Telegram-IO (уведомление
получателю в assign) вынесен ИЗ сессии в async-часть. Тестовый seam —
keyword-only ``_db`` (sync-исполнение на переданной сессии).
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from uk_management_bot.database.session import run_db
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
# ARCH-116: показ времени смен — только через канон бизнес-зоны.
from uk_management_bot.utils.business_time import fmt_datetime, fmt_day_month_time

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


# ==========================================================================
# DTO: поля с именами ORM-атрибутов — клавиатуры (shift_selection_keyboard,
# transfers_list_keyboard, executor_selection_keyboard) работают duck-typed.
# ==========================================================================

@dataclass(frozen=True)
class _ShiftPick:
    id: int
    status: str
    start_time: Optional[datetime]


@dataclass(frozen=True)
class _TransferRow:
    id: int
    status: str
    created_at: Optional[datetime]
    to_executor_id: Optional[int]


@dataclass(frozen=True)
class _ExecutorRow:
    id: int
    first_name: Optional[str]
    last_name: Optional[str]
    specialization: Optional[str]  # сырое поле — parse_specializations(user) читает его


@dataclass(frozen=True)
class _TransferDetails:
    start_time: Optional[datetime]
    reason: str
    comment: Optional[str]
    status: str


def _shift_pick(shift: Shift) -> _ShiftPick:
    return _ShiftPick(id=shift.id, status=shift.status, start_time=shift.start_time)


def _transfer_details(transfer: ShiftTransfer) -> _TransferDetails:
    return _TransferDetails(
        start_time=transfer.shift.start_time if transfer.shift else None,
        reason=transfer.reason,
        comment=transfer.comment,
        status=transfer.status,
    )


# ==========================================================================
# Sync unit-of-work (исполняются в worker-потоке через run_db).
# ==========================================================================

def _lang(db, telegram_id: int) -> str:
    return get_user_language(telegram_id, db)


def _load_transferable(db, telegram_id: int):
    """-> (lang, user_found, [_ShiftPick])."""
    lang = _lang(db, telegram_id)
    current = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not current:
        return lang, False, []

    # FS-02: Shift.user_id — FK на users.id (НЕ telegram_id). Окно по
    # start_time убрано: текущая active-смена тоже передаваема.
    shifts = db.query(Shift).filter(
        Shift.user_id == current.id,
        Shift.status.in_(['planned', 'active'])
    ).order_by(Shift.start_time).limit(10).all()
    return lang, True, [_shift_pick(s) for s in shifts]


def _check_shift_selectable(db, telegram_id: int, shift_id: int):
    """-> (lang, "ok" | "not_found" | "exists")."""
    lang = _lang(db, telegram_id)
    # FS-02: резолвим внутренний user.id (callback.from_user.id — telegram_id).
    current = db.query(User).filter(User.telegram_id == telegram_id).first()
    shift = db.query(Shift).filter(
        Shift.id == shift_id,
        Shift.user_id == (current.id if current else None)
    ).first()
    if not shift:
        return lang, "not_found"

    existing = db.query(ShiftTransfer).filter(
        ShiftTransfer.shift_id == shift_id,
        ShiftTransfer.status.in_(['pending', 'assigned', 'accepted'])
    ).first()
    if existing:
        return lang, "exists"
    return lang, "ok"


def _load_confirmation_start_time(db, shift_id: int) -> Optional[datetime]:
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    return shift.start_time if shift else None


def _create_transfer(db, telegram_id: int, data: dict):
    """-> ("no_user", None) | ("ok", None) | ("err", error_key)."""
    # FS-02: from_executor_id — внутренний users.id.
    current = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not current:
        return "no_user", None

    result = ShiftTransferService(db).create_transfer(
        shift_id=data['selected_shift_id'],
        from_executor_id=current.id,
        reason=data['transfer_reason'],
        comment=data.get('transfer_comment', ''),
        urgency_level=data['transfer_urgency']
    )
    if result['success']:
        return "ok", None
    return "err", result['error']


def _load_pending_transfers(db, telegram_id: int):
    """-> (lang, [(executor_first_name, shift_start_time, reason, transfer_id)])."""
    lang = _lang(db, telegram_id)
    pending = ShiftTransferService(db).list_pending_transfers(limit=20)
    rows = [
        (
            t.from_executor.first_name if t.from_executor else None,
            t.shift.start_time if t.shift and t.shift.start_time else None,
            t.reason,
            t.id,
        )
        for t in pending
    ]
    return lang, rows


def _load_assign_context(db, telegram_id: int, transfer_id: int):
    """-> (lang, "not_found" | "no_eligible" | "ok", [_ExecutorRow])."""
    lang = _lang(db, telegram_id)
    service = ShiftTransferService(db)
    transfer = db.query(ShiftTransfer).filter(ShiftTransfer.id == transfer_id).first()
    if not transfer or transfer.status != "pending":
        return lang, "not_found", []

    # CR-1: spec-префильтр через сервис (не показывать заведомо невалидных).
    eligible = service.list_eligible_executors(
        exclude_user_id=transfer.from_executor_id,
        shift=service.get_shift(transfer.shift_id),
    )
    if not eligible:
        return lang, "no_eligible", []
    rows = [
        _ExecutorRow(
            id=u.id, first_name=u.first_name, last_name=u.last_name,
            specialization=getattr(u, "specialization", None),
        )
        for u in eligible
    ]
    return lang, "ok", rows


def _assign_transfer(db, telegram_id: int, transfer_id: int, to_executor_id: int):
    """-> (lang, error_key | None, recipient (tg_id, lang) | None)."""
    lang = _lang(db, telegram_id)
    manager = db.query(User).filter(User.telegram_id == telegram_id).first()

    result = ShiftTransferService(db).assign_transfer(
        transfer_id, to_executor_id, manager.id if manager else None
    )
    if not result['success']:
        return lang, result['error'], None

    recipient = db.query(User).filter(User.id == to_executor_id).first()
    recipient_dto = (recipient.telegram_id, recipient.language or "ru") if recipient else None
    return lang, None, recipient_dto


def _transfer_response(db, telegram_id: int, action: str, transfer_id: int):
    """-> (lang, outcome, payload):
    outcome: "no_user" | "not_found" | "details" | "ok" | "err" | "bad_action";
    payload: _TransferDetails | ok_key | error_key | None."""
    lang = _lang(db, telegram_id)
    current = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not current:
        return lang, "no_user", None

    service = ShiftTransferService(db)

    if action == "details":
        transfer = service.get_transfer(transfer_id)
        if not transfer:
            return lang, "not_found", None
        return lang, "details", _transfer_details(transfer)

    if action == "accept":
        result = service.accept_transfer(transfer_id, current.id)
        ok_key = "transfer_accepted_success"
    elif action == "reject":
        result = service.reject_transfer(transfer_id, current.id)
        ok_key = "transfer_rejected_success"
    else:
        return lang, "bad_action", None

    if result['success']:
        return lang, "ok", ok_key
    return lang, "err", result['error']


def _load_view_transfer(db, telegram_id: int, transfer_id: int, is_manager: bool):
    """-> (lang, "not_found" | "forbidden" | "ok", _TransferDetails | None)."""
    lang = _lang(db, telegram_id)
    current = db.query(User).filter(User.telegram_id == telegram_id).first()
    transfer = ShiftTransferService(db).get_transfer(transfer_id)
    if not transfer:
        return lang, "not_found", None
    # IDOR-guard: детали видит только участник передачи или менеджер.
    if not is_manager and (
        not current
        or current.id not in (transfer.from_executor_id, transfer.to_executor_id)
    ):
        return lang, "forbidden", None
    return lang, "ok", _transfer_details(transfer)


def _load_my_transfers(db, telegram_id: int):
    """-> (lang, [_TransferRow], current_user_id | None)."""
    lang = _lang(db, telegram_id)
    current = db.query(User).filter(User.telegram_id == telegram_id).first()

    # FS-02: from/to_executor_id — FK на users.id.
    transfers = db.query(ShiftTransfer).filter(
        or_(
            ShiftTransfer.from_executor_id == (current.id if current else None),
            ShiftTransfer.to_executor_id == (current.id if current else None)
        )
    ).options(
        joinedload(ShiftTransfer.shift),
        joinedload(ShiftTransfer.from_executor),
        joinedload(ShiftTransfer.to_executor)
    ).order_by(ShiftTransfer.created_at.desc()).limit(10).all()

    rows = [
        _TransferRow(id=t.id, status=t.status, created_at=t.created_at,
                     to_executor_id=t.to_executor_id)
        for t in transfers
    ]
    return lang, rows, current.id if current else None


# ========== ИНИЦИАЦИЯ ПЕРЕДАЧИ СМЕНЫ ==========

@router.message(Command("transfer_shift"))
@require_role(['executor'])
async def cmd_transfer_shift(message: Message, state: FSMContext,
                             user: User = None, roles: list = None, *, _db=None):
    """Команда для передачи смены"""
    user_lang = "ru"
    try:
        user_lang, found, active_shifts = await run_db(
            lambda s: _load_transferable(s, message.from_user.id), db=_db,
        )
        if not found:
            await message.answer(get_text("shift_transfer.handlers.user_not_found", language=user_lang))
            return

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
async def handle_shift_selection(callback: CallbackQuery, state: FSMContext, *, _db=None):
    """Обработка выбора смены для передачи"""
    user_lang = "ru"
    try:
        shift_id = int(callback.data.split(":")[1])

        user_lang, verdict = await run_db(
            lambda s: _check_shift_selectable(s, callback.from_user.id, shift_id), db=_db,
        )
        if verdict == "not_found":
            await callback.answer(get_text("shift_transfer.handlers.shift_not_found", language=user_lang), show_alert=True)
            return
        if verdict == "exists":
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
async def handle_reason_selection(callback: CallbackQuery, state: FSMContext, *, _db=None):
    """Обработка выбора причины передачи"""
    user_lang = "ru"
    try:
        reason = callback.data.split(":")[1]
        user_lang = await run_db(lambda s: _lang(s, callback.from_user.id), db=_db)

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
async def handle_urgency_selection(callback: CallbackQuery, state: FSMContext, *, _db=None):
    """Обработка выбора уровня срочности"""
    user_lang = "ru"
    try:
        urgency = callback.data.split(":")[1]
        user_lang = await run_db(lambda s: _lang(s, callback.from_user.id), db=_db)

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
async def handle_comment_input(message: Message, state: FSMContext, *, _db=None):
    """Обработка ввода комментария"""
    user_lang = "ru"
    try:
        user_lang = await run_db(lambda s: _lang(s, message.from_user.id), db=_db)

        await state.update_data(transfer_comment=message.text)
        await show_transfer_confirmation(message, state, user_lang, _db=_db)

    except Exception as e:
        logger.error(f"Ошибка ввода комментария: {e}")
        await message.answer(get_text("shift_transfer.handlers.error_comment_processing", language=user_lang))


@router.callback_query(F.data == "transfer_comment:skip")
async def handle_skip_comment(callback: CallbackQuery, state: FSMContext, *, _db=None):
    """Обработка пропуска комментария"""
    user_lang = "ru"
    try:
        user_lang = await run_db(lambda s: _lang(s, callback.from_user.id), db=_db)

        await state.update_data(transfer_comment="")
        await show_transfer_confirmation(callback.message, state, user_lang, edit_message=True, _db=_db)

    except Exception as e:
        logger.error(f"Ошибка пропуска комментария: {e}")
        await callback.answer(get_text("shift_transfer.handlers.error_generic", language=user_lang), show_alert=True)


async def show_transfer_confirmation(message: Message, state: FSMContext, user_lang: str,
                                     edit_message: bool = False, *, _db=None):
    """Показать подтверждение передачи"""
    try:
        data = await state.get_data()

        start_time = await run_db(
            lambda s: _load_confirmation_start_time(s, data['selected_shift_id']), db=_db,
        )
        if start_time is None:
            # Смены нет — раньше это давало AttributeError с тем же исходом:
            # лог + ничего не отправлено (у хелпера нет user-facing error-ветки).
            logger.error("Ошибка показа подтверждения: смена %s не найдена", data.get('selected_shift_id'))
            return

        reason_text = get_text(f"shift_transfer.handlers.reason_{data['transfer_reason']}", language=user_lang)
        urgency_text = get_text(f"shift_transfer.handlers.urgency_{data['transfer_urgency']}", language=user_lang)
        comment_val = data.get('transfer_comment', '') or get_text("shift_transfer.handlers.not_specified", language=user_lang)
        if not comment_val:
            comment_val = get_text("shift_transfer.handlers.not_specified", language=user_lang)

        confirmation_text = get_text("shift_transfer.handlers.transfer_confirmation", language=user_lang).format(
            shift_date=fmt_datetime(start_time),
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
async def handle_transfer_confirmation(callback: CallbackQuery, state: FSMContext, *, _db=None):
    """Обработка подтверждения передачи"""
    user_lang = "ru"
    try:
        action = callback.data.split(":")[1]
        user_lang = await run_db(lambda s: _lang(s, callback.from_user.id), db=_db)

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

            outcome, error = await run_db(
                lambda s: _create_transfer(s, callback.from_user.id, data), db=_db,
            )
            if outcome == "no_user":
                await callback.message.edit_text(get_text("shift_transfer.handlers.user_not_found", language=user_lang))
                await state.clear()
                return

            if outcome == "ok":
                await callback.message.edit_text(get_text("shift_transfer.handlers.transfer_created_success", language=user_lang))
            else:
                await callback.message.edit_text(
                    get_text("shift_transfer.handlers.transfer_create_error", language=user_lang).format(
                        error=_err_text(error, user_lang)
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
                                user: User = None, roles: list = None, *, _db=None):
    """Команда для просмотра ожидающих передач (для менеджеров)"""
    user_lang = "ru"
    try:
        user_lang, pending_rows = await run_db(
            lambda s: _load_pending_transfers(s, message.from_user.id), db=_db,
        )
        if not pending_rows:
            await message.answer(get_text("shift_transfer.handlers.no_pending_transfers", language=user_lang))
            return

        transfers_text = get_text("shift_transfer.handlers.pending_transfers_title", language=user_lang) + "\n\n"

        for executor_first_name, shift_start_time, reason, transfer_id in pending_rows:
            executor_name = executor_first_name or get_text("shift_transfer.handlers.unknown", language=user_lang)
            shift_date = fmt_day_month_time(shift_start_time) if shift_start_time else "—"
            reason_text = get_text(f"shift_transfer.handlers.reason_{reason}", language=user_lang)
            transfers_text += f"• {executor_name} - {shift_date}\n  " + get_text("shift_transfer.handlers.reason_label", language=user_lang) + f": {reason_text}\n  /assign_{transfer_id}\n\n"

        await message.answer(transfers_text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка получения ожидающих передач: {e}")
        await message.answer(get_text("shift_transfer.handlers.error_loading_transfers", language=user_lang))


@router.message(F.text.regexp(r"^/assign_(\d+)$"))
@require_role(['manager'])
async def cmd_assign_transfer(message: Message, state: FSMContext = None,
                              user: User = None, roles: list = None, *, _db=None):
    """Менеджер выбирает исполнителя для передачи (/assign_<id>)."""
    user_lang = "ru"
    try:
        transfer_id = int(message.text.split("_", 1)[1])
        user_lang, verdict, eligible = await run_db(
            lambda s: _load_assign_context(s, message.from_user.id, transfer_id), db=_db,
        )
        if verdict == "not_found":
            await message.answer(_err_text("transfer_not_found", user_lang))
            return
        if verdict == "no_eligible":
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
                                          user: User = None, roles: list = None, *, _db=None):
    """Назначение получателя передачи + уведомление получателю с клавиатурой ответа."""
    user_lang = "ru"
    try:
        _, transfer_id_s, to_user_id_s = callback.data.split(":")
        transfer_id, to_executor_id = int(transfer_id_s), int(to_user_id_s)

        user_lang, error, recipient = await run_db(
            lambda s: _assign_transfer(s, callback.from_user.id, transfer_id, to_executor_id), db=_db,
        )
        if error is not None:
            await callback.answer(_err_text(error, user_lang), show_alert=True)
            return

        # Уведомить получателя с клавиатурой ответа (отдельным сообщением).
        # AUD3-37: отправка вынесена из сессии — Telegram-IO сессию не держит.
        if recipient is not None:
            recipient_tg_id, rec_lang = recipient
            try:
                await callback.bot.send_message(
                    recipient_tg_id,
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
                                   user: User = None, roles: list = None, *, _db=None):
    """Ответ получателя на передачу: accept / reject / details."""
    user_lang = "ru"
    try:
        _, action, transfer_id_s = callback.data.split(":")
        transfer_id = int(transfer_id_s)

        user_lang, outcome, payload = await run_db(
            lambda s: _transfer_response(s, callback.from_user.id, action, transfer_id), db=_db,
        )
        if outcome == "no_user":
            await callback.answer(get_text("shift_transfer.handlers.user_not_found", language=user_lang), show_alert=True)
            return
        if outcome == "not_found":
            await callback.answer(_err_text("transfer_not_found", user_lang), show_alert=True)
            return
        if outcome == "details":
            shift_date = fmt_day_month_time(payload.start_time) if payload.start_time else "—"
            reason_text = get_text(f"shift_transfer.handlers.reason_{payload.reason}", language=user_lang)
            await callback.answer(
                get_text("shift_transfer.handlers.transfer_details", language=user_lang).format(
                    date=shift_date, reason=reason_text, comment=payload.comment or "—"
                ),
                show_alert=True
            )
            return
        if outcome == "bad_action":
            await callback.answer(get_text("shift_transfer.handlers.error_generic", language=user_lang), show_alert=True)
            return

        if outcome == "ok":
            await callback.message.edit_text(get_text(f"shift_transfer.handlers.{payload}", language=user_lang))
        else:
            await callback.answer(_err_text(payload, user_lang), show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка ответа на передачу: {e}")
        await callback.answer(get_text("shift_transfer.handlers.error_generic", language=user_lang), show_alert=True)


@router.callback_query(F.data.startswith("view_transfer:"))
@require_role(['executor', 'manager'])
async def handle_view_transfer(callback: CallbackQuery, state: FSMContext = None,
                               user: User = None, roles: list = None, *, _db=None):
    """Детали передачи (из списка «Мои передачи»). Только участник или менеджер."""
    user_lang = "ru"
    try:
        transfer_id = int(callback.data.split(":")[1])
        is_manager = bool(roles and "manager" in roles)

        user_lang, verdict, details = await run_db(
            lambda s: _load_view_transfer(s, callback.from_user.id, transfer_id, is_manager), db=_db,
        )
        if verdict == "not_found":
            await callback.answer(_err_text("transfer_not_found", user_lang), show_alert=True)
            return
        if verdict == "forbidden":
            await callback.answer(_err_text("not_your_transfer", user_lang), show_alert=True)
            return

        shift_date = fmt_day_month_time(details.start_time) if details.start_time else "—"
        reason_text = get_text(f"shift_transfer.handlers.reason_{details.reason}", language=user_lang)
        status_text = get_text(f"shift_transfer.keyboards.transfer_status_{details.status}", language=user_lang)
        await callback.answer(
            get_text("shift_transfer.handlers.transfer_details", language=user_lang).format(
                date=shift_date, reason=reason_text, comment=details.comment or "—"
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
                           user: User = None, roles: list = None, *, _db=None):
    """Команда для просмотра своих передач"""
    user_lang = "ru"
    try:
        user_lang, my_transfers, current_id = await run_db(
            lambda s: _load_my_transfers(s, message.from_user.id), db=_db,
        )
        if not my_transfers:
            await message.answer(get_text("shift_transfer.handlers.no_transfers", language=user_lang))
            return

        await message.answer(
            get_text("shift_transfer.handlers.select_transfer", language=user_lang),
            reply_markup=transfers_list_keyboard(
                my_transfers, user_lang, current_user_id=current_id
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
