"""
Обработчики для передачи смен между исполнителями
"""

import logging
from datetime import datetime, date
from typing import Optional, List
import json

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from uk_management_bot.database.session import get_db
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_transfer import ShiftTransfer
from uk_management_bot.states.shift_transfer import ShiftTransferStates
from uk_management_bot.keyboards.shift_transfer import (
    shift_selection_keyboard,
    transfer_reason_keyboard,
    urgency_level_keyboard,
    confirm_transfer_keyboard,
    executor_selection_keyboard,
    transfer_response_keyboard,
    transfers_list_keyboard,
    skip_comment_keyboard
)
from uk_management_bot.services.shift_transfer_service import ShiftTransferService
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.utils.helpers import get_user_language
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import joinedload

logger = logging.getLogger(__name__)
router = Router()


# ========== ИНИЦИАЦИЯ ПЕРЕДАЧИ СМЕНЫ ==========

@router.message(Command("transfer_shift"))
@require_role(['executor'])
async def cmd_transfer_shift(message: Message, state: FSMContext):
    """Команда для передачи смены"""
    try:
        user_lang = await get_user_language(message.from_user.id)

        with get_db() as db:
            # Получаем пользователя
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            if not user:
                error_text = "Пользователь не найден" if user_lang == "ru" else "Foydalanuvchi topilmadi"
                await message.answer(error_text)
                return

            # Получаем активные смены пользователя
            active_shifts = db.query(Shift).filter(
                Shift.user_id == user.telegram_id,
                Shift.status.in_(['planned', 'active']),
                Shift.start_time >= datetime.now()
            ).order_by(Shift.start_time).limit(10).all()

            if not active_shifts:
                no_shifts_text = (
                    "У вас нет активных смен для передачи" if user_lang == "ru"
                    else "Sizda o'tkazish uchun faol smenalar yo'q"
                )
                await message.answer(no_shifts_text)
                return

            # Показываем список смен для выбора
            select_text = (
                "Выберите смену для передачи:" if user_lang == "ru"
                else "O'tkazish uchun smenani tanlang:"
            )

            await message.answer(
                select_text,
                reply_markup=shift_selection_keyboard(active_shifts, user_lang)
            )
            await state.set_state(ShiftTransferStates.select_shift)

    except Exception as e:
        logger.error(f"Ошибка команды передачи смены: {e}")
        error_text = "Ошибка при инициации передачи" if user_lang == "ru" else "O'tkazishni boshlashda xatolik"
        await message.answer(error_text)


@router.callback_query(F.data.startswith("transfer_shift:"))
async def handle_shift_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора смены для передачи"""
    try:
        shift_id = int(callback.data.split(":")[1])
        user_lang = await get_user_language(callback.from_user.id)

        with get_db() as db:
            # Проверяем права на смену
            shift = db.query(Shift).filter(
                Shift.id == shift_id,
                Shift.user_id == callback.from_user.id
            ).first()

            if not shift:
                error_text = "Смена не найдена" if user_lang == "ru" else "Smena topilmadi"
                await callback.answer(error_text, show_alert=True)
                return

            # Проверяем, нет ли уже активной передачи для этой смены
            existing_transfer = db.query(ShiftTransfer).filter(
                ShiftTransfer.shift_id == shift_id,
                ShiftTransfer.status.in_(['pending', 'assigned', 'accepted'])
            ).first()

            if existing_transfer:
                exists_text = (
                    "Для этой смены уже есть активная передача" if user_lang == "ru"
                    else "Bu smena uchun allaqachon faol o'tkazish mavjud"
                )
                await callback.answer(exists_text, show_alert=True)
                return

            # Сохраняем выбранную смену в состояние
            await state.update_data(selected_shift_id=shift_id)

            # Переходим к выбору причины
            reason_text = "Выберите причину передачи:" if user_lang == "ru" else "O'tkazish sababini tanlang:"

            await callback.message.edit_text(
                reason_text,
                reply_markup=transfer_reason_keyboard(user_lang)
            )
            await state.set_state(ShiftTransferStates.select_reason)

    except Exception as e:
        logger.error(f"Ошибка выбора смены: {e}")
        error_text = "Ошибка выбора смены" if user_lang == "ru" else "Smena tanlashda xatolik"
        await callback.answer(error_text, show_alert=True)


@router.callback_query(F.data.startswith("transfer_reason:"))
async def handle_reason_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора причины передачи"""
    try:
        reason = callback.data.split(":")[1]
        user_lang = await get_user_language(callback.from_user.id)

        # Сохраняем причину
        await state.update_data(transfer_reason=reason)

        # Переходим к выбору уровня срочности
        urgency_text = "Выберите уровень срочности:" if user_lang == "ru" else "Shoshilinchlik darajasini tanlang:"

        await callback.message.edit_text(
            urgency_text,
            reply_markup=urgency_level_keyboard(user_lang)
        )
        await state.set_state(ShiftTransferStates.select_urgency)

    except Exception as e:
        logger.error(f"Ошибка выбора причины: {e}")
        await callback.answer("Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("transfer_urgency:"))
async def handle_urgency_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора уровня срочности"""
    try:
        urgency = callback.data.split(":")[1]
        user_lang = await get_user_language(callback.from_user.id)

        # Сохраняем уровень срочности
        await state.update_data(transfer_urgency=urgency)

        # Переходим к вводу комментария
        comment_text = (
            "Введите комментарий к передаче (необязательно):" if user_lang == "ru"
            else "O'tkazish uchun izoh kiriting (ixtiyoriy):"
        )

        await callback.message.edit_text(
            comment_text,
            reply_markup=skip_comment_keyboard(user_lang)
        )
        await state.set_state(ShiftTransferStates.enter_comment)

    except Exception as e:
        logger.error(f"Ошибка выбора срочности: {e}")
        await callback.answer("Ошибка", show_alert=True)


@router.message(ShiftTransferStates.enter_comment)
async def handle_comment_input(message: Message, state: FSMContext):
    """Обработка ввода комментария"""
    try:
        user_lang = await get_user_language(message.from_user.id)

        # Сохраняем комментарий
        await state.update_data(transfer_comment=message.text)

        # Переходим к подтверждению
        await show_transfer_confirmation(message, state, user_lang)

    except Exception as e:
        logger.error(f"Ошибка ввода комментария: {e}")
        error_text = "Ошибка обработки комментария" if user_lang == "ru" else "Izohni qayta ishlashda xatolik"
        await message.answer(error_text)


@router.callback_query(F.data == "transfer_comment:skip")
async def handle_skip_comment(callback: CallbackQuery, state: FSMContext):
    """Обработка пропуска комментария"""
    try:
        user_lang = await get_user_language(callback.from_user.id)

        # Устанавливаем пустой комментарий
        await state.update_data(transfer_comment="")

        # Переходим к подтверждению
        await show_transfer_confirmation(callback.message, state, user_lang, edit_message=True)

    except Exception as e:
        logger.error(f"Ошибка пропуска комментария: {e}")
        await callback.answer("Ошибка", show_alert=True)


async def show_transfer_confirmation(message: Message, state: FSMContext, user_lang: str, edit_message: bool = False):
    """Показать подтверждение передачи"""
    try:
        data = await state.get_data()

        with get_db() as db:
            # Получаем информацию о смене
            shift = db.query(Shift).filter(Shift.id == data['selected_shift_id']).first()

            # Формируем текст подтверждения
            reason_map = {
                "ru": {
                    "illness": "Болезнь",
                    "emergency": "Экстренная ситуация",
                    "workload": "Перегрузка",
                    "vacation": "Отпуск",
                    "other": "Другое"
                },
                "uz": {
                    "illness": "Kasallik",
                    "emergency": "Favqulodda holat",
                    "workload": "Ortiqcha ish",
                    "vacation": "Ta'til",
                    "other": "Boshqa"
                }
            }

            urgency_map = {
                "ru": {
                    "low": "Низкий",
                    "normal": "Обычный",
                    "high": "Высокий",
                    "critical": "Критический"
                },
                "uz": {
                    "low": "Past",
                    "normal": "Oddiy",
                    "high": "Yuqori",
                    "critical": "Kritik"
                }
            }

            reason_text = reason_map.get(user_lang, reason_map["ru"]).get(data['transfer_reason'], data['transfer_reason'])
            urgency_text = urgency_map.get(user_lang, urgency_map["ru"]).get(data['transfer_urgency'], data['transfer_urgency'])

            if user_lang == "ru":
                confirmation_text = f"""
🔄 <b>Подтверждение передачи смены</b>

📅 <b>Смена:</b> {shift.start_time.strftime('%d.%m.%Y %H:%M')}
📝 <b>Причина:</b> {reason_text}
⚡ <b>Срочность:</b> {urgency_text}
💬 <b>Комментарий:</b> {data.get('transfer_comment', 'Не указан') or 'Не указан'}

Подтвердить передачу?
"""
            else:
                confirmation_text = f"""
🔄 <b>Smena o'tkazishni tasdiqlash</b>

📅 <b>Smena:</b> {shift.start_time.strftime('%d.%m.%Y %H:%M')}
📝 <b>Sabab:</b> {reason_text}
⚡ <b>Shoshilinchlik:</b> {urgency_text}
💬 <b>Izoh:</b> {data.get('transfer_comment', "Ko'rsatilmagan") or "Ko'rsatilmagan"}

O'tkazishni tasdiqlaysizmi?
"""

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
    try:
        action = callback.data.split(":")[1]
        user_lang = await get_user_language(callback.from_user.id)

        if action == "cancel":
            cancel_text = "Передача отменена" if user_lang == "ru" else "O'tkazish bekor qilindi"
            await callback.message.edit_text(cancel_text)
            await state.clear()
            return

        elif action == "edit":
            # Возвращаемся к выбору причины
            reason_text = "Выберите причину передачи:" if user_lang == "ru" else "O'tkazish sababini tanlang:"
            await callback.message.edit_text(
                reason_text,
                reply_markup=transfer_reason_keyboard(user_lang)
            )
            await state.set_state(ShiftTransferStates.select_reason)
            return

        elif action == "yes":
            # Создаем передачу
            data = await state.get_data()

            with get_db() as db:
                transfer_service = ShiftTransferService(db)

                result = await transfer_service.create_transfer(
                    shift_id=data['selected_shift_id'],
                    from_executor_id=callback.from_user.id,
                    reason=data['transfer_reason'],
                    comment=data.get('transfer_comment', ''),
                    urgency_level=data['transfer_urgency']
                )

                if result['success']:
                    success_text = (
                        "✅ Передача создана успешно!\nМенеджер получил уведомление." if user_lang == "ru"
                        else "✅ O'tkazish muvaffaqiyatli yaratildi!\nMenejer xabardor qilindi."
                    )
                    await callback.message.edit_text(success_text)
                else:
                    error_text = f"Ошибка создания передачи: {result['error']}"
                    await callback.message.edit_text(error_text)

            await state.clear()

    except Exception as e:
        logger.error(f"Ошибка подтверждения передачи: {e}")
        await callback.answer("Ошибка", show_alert=True)


# ========== НАЗНАЧЕНИЕ ИСПОЛНИТЕЛЯ (ДЛЯ МЕНЕДЖЕРОВ) ==========

@router.message(Command("pending_transfers"))
@require_role(['manager'])
async def cmd_pending_transfers(message: Message):
    """Команда для просмотра ожидающих передач (для менеджеров)"""
    try:
        user_lang = await get_user_language(message.from_user.id)

        with get_db() as db:
            # Получаем ожидающие передачи
            pending_transfers = db.query(ShiftTransfer).filter(
                ShiftTransfer.status == 'pending'
            ).options(
                joinedload(ShiftTransfer.shift),
                joinedload(ShiftTransfer.from_executor)
            ).order_by(ShiftTransfer.created_at.desc()).limit(20).all()

            if not pending_transfers:
                no_transfers_text = (
                    "Нет ожидающих передач" if user_lang == "ru"
                    else "Kutayotgan o'tkazishlar yo'q"
                )
                await message.answer(no_transfers_text)
                return

            # Формируем список передач
            transfers_text = "📋 <b>Ожидающие передачи:</b>\n\n" if user_lang == "ru" else "📋 <b>Kutayotgan o'tkazishlar:</b>\n\n"

            for transfer in pending_transfers:
                executor_name = transfer.from_executor.first_name or "Неизвестный"
                shift_date = transfer.shift.start_time.strftime('%d.%m %H:%M')

                reason_map = {
                    "illness": "Болезнь" if user_lang == "ru" else "Kasallik",
                    "emergency": "Экстренная ситуация" if user_lang == "ru" else "Favqulodda holat",
                    "workload": "Перегрузка" if user_lang == "ru" else "Ortiqcha ish",
                    "vacation": "Отпуск" if user_lang == "ru" else "Ta'til",
                    "other": "Другое" if user_lang == "ru" else "Boshqa"
                }

                reason_text = reason_map.get(transfer.reason, transfer.reason)

                transfers_text += f"• {executor_name} - {shift_date}\n  Причина: {reason_text}\n  /assign_{transfer.id}\n\n"

            await message.answer(transfers_text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка получения ожидающих передач: {e}")
        error_text = "Ошибка загрузки передач" if user_lang == "ru" else "O'tkazishlarni yuklashda xatolik"
        await message.answer(error_text)


# ========== ПРОСМОТР ПЕРЕДАЧ ==========

@router.message(Command("my_transfers"))
@require_role(['executor', 'manager'])
async def cmd_my_transfers(message: Message):
    """Команда для просмотра своих передач"""
    try:
        user_lang = await get_user_language(message.from_user.id)

        with get_db() as db:
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()

            # Получаем передачи пользователя (исходящие и входящие)
            my_transfers = db.query(ShiftTransfer).filter(
                or_(
                    ShiftTransfer.from_executor_id == user.telegram_id,
                    ShiftTransfer.to_executor_id == user.telegram_id
                )
            ).options(
                joinedload(ShiftTransfer.shift),
                joinedload(ShiftTransfer.from_executor),
                joinedload(ShiftTransfer.to_executor)
            ).order_by(ShiftTransfer.created_at.desc()).limit(10).all()

            if not my_transfers:
                no_transfers_text = (
                    "У вас нет передач" if user_lang == "ru"
                    else "Sizda o'tkazishlar yo'q"
                )
                await message.answer(no_transfers_text)
                return

            await message.answer(
                "Выберите передачу:" if user_lang == "ru" else "O'tkazishni tanlang:",
                reply_markup=transfers_list_keyboard(my_transfers, user_lang)
            )

    except Exception as e:
        logger.error(f"Ошибка получения передач пользователя: {e}")
        error_text = "Ошибка загрузки передач" if user_lang == "ru" else "O'tkazishlarni yuklashda xatolik"
        await message.answer(error_text)


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