"""
Bot Gateway Service - Shift Management Handlers
UK Management Bot

Handlers for shift viewing, assignment, release, and availability management.
"""

from datetime import date, datetime, timedelta
from typing import Optional
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from app.integrations.shift_client import ShiftServiceClient
from app.keyboards import shifts as shift_keyboards
from app.keyboards.common import get_cancel_keyboard, get_main_menu_keyboard
from app.states.shift_states import (
    ShiftViewingStates,
    ShiftTakingStates,
    ShiftReleaseStates,
    AvailabilityStates,
)

logger = logging.getLogger(__name__)

# Create router
router = Router(name="shifts")

# Initialize Shift Service client
shift_client = ShiftServiceClient()


# ===========================================
# Main Shift Menu
# ===========================================


@router.message(F.text.in_(["📅 Смены", "📅 Smenalar"]))
@router.message(Command("shifts"))
async def cmd_shifts_menu(
    message: Message,
    user_role: str,
    language: str,
    state: FSMContext,
):
    """
    Show main shift management menu.

    Available for: executor, manager, admin
    """
    await state.clear()

    texts = {
        "ru": (
            "📅 <b>Управление сменами</b>\n\n"
            "Выберите действие:\n\n"
            "• <b>Мои смены</b> - Ваши назначенные смены\n"
            "• <b>Доступные смены</b> - Смены, которые можно взять\n"
            "• <b>Расписание</b> - График на неделю/месяц\n"
            "• <b>Доступность</b> - Управление доступностью\n"
            "• <b>Статистика</b> - Статистика за период"
        ),
        "uz": (
            "📅 <b>Smenalarni boshqarish</b>\n\n"
            "Amalni tanlang:\n\n"
            "• <b>Mening smenalarim</b> - Sizga tayinlangan smenalar\n"
            "• <b>Mavjud smenalar</b> - Olish mumkin bo'lgan smenalar\n"
            "• <b>Jadval</b> - Hafta/oy jadvali\n"
            "• <b>Mavjudlik</b> - Mavjudlikni boshqarish\n"
            "• <b>Statistika</b> - Davr statistikasi"
        ),
    }

    await message.answer(
        text=texts.get(language, texts["ru"]),
        reply_markup=shift_keyboards.get_shift_menu_keyboard(user_role, language),
        parse_mode="HTML",
    )


# ===========================================
# My Shifts
# ===========================================


@router.message(F.text.in_(["📅 Мои смены", "📅 Mening smenalarim"]))
async def button_my_shifts(
    message: Message,
    token: str,
    language: str,
    state: FSMContext,
):
    """
    Show user's assigned shifts.
    """
    await state.clear()

    texts = {
        "ru": {
            "loading": "⏳ Загружаю ваши смены...",
            "header": "📅 <b>Мои смены</b>\n\n",
            "no_shifts": "У вас пока нет назначенных смен.",
            "shift_template": (
                "📅 <b>Смена {date}</b>\n"
                "🕒 Время: {time_from} - {time_to}\n"
                "🔧 Специализация: {specialization}\n"
                "📍 Объекты: {buildings}\n"
                "📊 Статус: {status}\n"
            ),
            "error": "❌ Ошибка при загрузке смен. Попробуйте позже.",
        },
        "uz": {
            "loading": "⏳ Smenalaringiz yuklanmoqda...",
            "header": "📅 <b>Mening smenalarim</b>\n\n",
            "no_shifts": "Sizda hali tayinlangan smenalar yo'q.",
            "shift_template": (
                "📅 <b>Smena {date}</b>\n"
                "🕒 Vaqt: {time_from} - {time_to}\n"
                "🔧 Mutaxassislik: {specialization}\n"
                "📍 Obyektlar: {buildings}\n"
                "📊 Holat: {status}\n"
            ),
            "error": "❌ Smenalarni yuklashda xatolik. Keyinroq urinib ko'ring.",
        },
    }

    lang_texts = texts.get(language, texts["ru"])

    # Show loading message
    loading_msg = await message.answer(lang_texts["loading"])

    try:
        # Get shifts from Shift Service
        result = await shift_client.get_my_shifts(
            token=token, date_from=date.today(), limit=10
        )

        await loading_msg.delete()

        shifts = result.get("items", [])

        if not shifts:
            await message.answer(lang_texts["no_shifts"])
            return

        # Display shifts
        response = lang_texts["header"]

        for shift in shifts[:5]:  # Show first 5
            shift_date = shift.get("date", "N/A")
            time_from = shift.get("time_from", "N/A")
            time_to = shift.get("time_to", "N/A")
            specialization = shift.get("specialization", "N/A")
            buildings = ", ".join(shift.get("building_ids", []))
            status = shift.get("status", "N/A")

            response += lang_texts["shift_template"].format(
                date=shift_date,
                time_from=time_from,
                time_to=time_to,
                specialization=specialization,
                buildings=buildings or "Не указаны",
                status=status,
            )
            response += "\n"

            # Add action buttons for this shift
            shift_id = shift.get("id")
            is_assigned = True  # User requested their shifts
            await message.answer(
                "➡️",
                reply_markup=shift_keyboards.get_shift_actions_keyboard(
                    shift_id=shift_id,
                    shift_status=status,
                    is_assigned_to_me=is_assigned,
                    user_role="executor",
                    language=language,
                ),
            )

        # Show total count
        total = result.get("total", 0)
        if total > 5:
            response += f"\n<i>Показаны первые 5 из {total} смен</i>"

        await message.answer(response, parse_mode="HTML")

        # Offer filter options
        await message.answer(
            "🔍 Фильтры:" if language == "ru" else "🔍 Filtrlar:",
            reply_markup=shift_keyboards.get_shift_filter_keyboard(language),
        )

    except Exception as e:
        logger.error(f"Error loading shifts: {e}")
        await loading_msg.delete()
        await message.answer(lang_texts["error"])


# ===========================================
# Available Shifts
# ===========================================


@router.message(F.text.in_(["🔍 Доступные смены", "🔍 Mavjud smenalar"]))
async def button_available_shifts(
    message: Message,
    token: str,
    language: str,
    state: FSMContext,
):
    """
    Show available shifts that user can take.
    """
    await state.clear()

    texts = {
        "ru": {
            "loading": "⏳ Загружаю доступные смены...",
            "header": "🔍 <b>Доступные смены</b>\n\n",
            "no_shifts": "Нет доступных смен на ближайшее время.",
            "prompt": "Выберите период или специализацию для фильтрации:",
        },
        "uz": {
            "loading": "⏳ Mavjud smenalar yuklanmoqda...",
            "header": "🔍 <b>Mavjud smenalar</b>\n\n",
            "no_shifts": "Yaqin vaqtda mavjud smenalar yo'q.",
            "prompt": "Filtrlash uchun davr yoki mutaxassislikni tanlang:",
        },
    }

    lang_texts = texts.get(language, texts["ru"])

    # Show loading
    loading_msg = await message.answer(lang_texts["loading"])

    try:
        # Get available shifts
        result = await shift_client.get_available_shifts(
            token=token, date_from=date.today(), limit=10
        )

        await loading_msg.delete()

        shifts = result.get("items", [])

        if not shifts:
            await message.answer(lang_texts["no_shifts"])
            return

        response = lang_texts["header"]

        for shift in shifts[:5]:
            shift_date = shift.get("date", "N/A")
            time_from = shift.get("time_from", "N/A")
            time_to = shift.get("time_to", "N/A")
            specialization = shift.get("specialization", "N/A")

            response += (
                f"📅 {shift_date} | 🕒 {time_from}-{time_to} | 🔧 {specialization}\n"
            )

            # Action buttons
            shift_id = shift.get("id")
            await message.answer(
                "➡️",
                reply_markup=shift_keyboards.get_shift_actions_keyboard(
                    shift_id=shift_id,
                    shift_status="available",
                    is_assigned_to_me=False,
                    user_role="executor",
                    language=language,
                ),
            )

        await message.answer(response, parse_mode="HTML")

        # Filter options
        await message.answer(
            lang_texts["prompt"],
            reply_markup=shift_keyboards.get_shift_filter_keyboard(language),
        )

    except Exception as e:
        logger.error(f"Error loading available shifts: {e}")
        await loading_msg.delete()
        await message.answer("❌ Ошибка при загрузке")


# ===========================================
# Schedule View
# ===========================================


@router.message(F.text.in_(["📆 Расписание", "📆 Jadval"]))
async def button_schedule(
    message: Message,
    token: str,
    language: str,
    state: FSMContext,
):
    """
    Show shift schedule.
    """
    await state.clear()

    texts = {
        "ru": {
            "prompt": "📆 <b>Расписание смен</b>\n\nВыберите период для просмотра:",
        },
        "uz": {
            "prompt": "📆 <b>Smenalar jadvali</b>\n\nKo'rish uchun davrni tanlang:",
        },
    }

    lang_texts = texts.get(language, texts["ru"])

    await message.answer(
        lang_texts["prompt"],
        reply_markup=shift_keyboards.get_date_range_keyboard(language),
        parse_mode="HTML",
    )

    await state.set_state(ShiftViewingStates.waiting_for_date_range)


@router.callback_query(F.data.startswith("date:"), ShiftViewingStates.waiting_for_date_range)
async def callback_schedule_date(
    callback: CallbackQuery,
    token: str,
    language: str,
    state: FSMContext,
):
    """
    Handle date selection for schedule.
    """
    await callback.answer()

    data_parts = callback.data.split(":")
    if len(data_parts) < 3:
        await callback.message.answer("❌ Некорректные данные")
        return

    date_from_str = data_parts[1]
    date_to_str = data_parts[2]

    try:
        date_from = date.fromisoformat(date_from_str)
        date_to = date.fromisoformat(date_to_str)

        # Get schedule
        result = await shift_client.get_schedule(
            token=token, date_from=date_from, date_to=date_to
        )

        schedule_data = result.get("schedule", {})

        if not schedule_data:
            await callback.message.answer(
                "📆 На выбранный период смен нет"
                if language == "ru"
                else "📆 Tanlangan davrda smenalar yo'q"
            )
            await state.clear()
            return

        response = f"📆 <b>Расписание {date_from} - {date_to}</b>\n\n"

        for date_key, shifts in schedule_data.items():
            response += f"📅 <b>{date_key}</b>\n"
            for shift in shifts:
                time_from = shift.get("time_from")
                time_to = shift.get("time_to")
                spec = shift.get("specialization")
                response += f"  🕒 {time_from}-{time_to} | 🔧 {spec}\n"
            response += "\n"

        await callback.message.answer(response, parse_mode="HTML")
        await state.clear()

    except Exception as e:
        logger.error(f"Error loading schedule: {e}")
        await callback.message.answer("❌ Ошибка при загрузке расписания")
        await state.clear()


# ===========================================
# Take Shift
# ===========================================


@router.callback_query(F.data.startswith("shift:take:"))
async def callback_take_shift(
    callback: CallbackQuery,
    token: str,
    language: str,
):
    """
    Handle shift take action.
    """
    shift_id = callback.data.split(":")[-1]

    texts = {
        "ru": {
            "confirm": "❓ Вы уверены, что хотите взять эту смену?",
            "success": "✅ Смена успешно назначена на вас!",
            "error": "❌ Не удалось взять смену. Возможно, она уже занята.",
        },
        "uz": {
            "confirm": "❓ Ushbu smenani olmoqchimisiz?",
            "success": "✅ Smena sizga tayinlandi!",
            "error": "❌ Smenani olishda xatolik. Ehtimol u band.",
        },
    }

    lang_texts = texts.get(language, texts["ru"])

    # Show confirmation
    await callback.message.answer(
        lang_texts["confirm"],
        reply_markup=shift_keyboards.get_confirmation_keyboard("take", shift_id, language),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("take:confirm:"))
async def callback_take_confirm(
    callback: CallbackQuery,
    token: str,
    language: str,
):
    """
    Confirm shift take.
    """
    shift_id = callback.data.split(":")[-1]

    texts = {
        "ru": {
            "processing": "⏳ Обработка...",
            "success": "✅ Смена успешно назначена на вас!",
            "error": "❌ Не удалось взять смену.",
        },
        "uz": {
            "processing": "⏳ Qayta ishlanyapti...",
            "success": "✅ Smena sizga tayinlandi!",
            "error": "❌ Smenani olishda xatolik.",
        },
    }

    lang_texts = texts.get(language, texts["ru"])

    await callback.answer(lang_texts["processing"])

    try:
        result = await shift_client.take_shift(shift_id=shift_id, token=token)

        await callback.message.answer(lang_texts["success"])

    except Exception as e:
        logger.error(f"Error taking shift: {e}")
        await callback.message.answer(lang_texts["error"])


# ===========================================
# Release Shift
# ===========================================


@router.callback_query(F.data.startswith("shift:release:"))
async def callback_release_shift(
    callback: CallbackQuery,
    language: str,
    state: FSMContext,
):
    """
    Handle shift release request.
    """
    shift_id = callback.data.split(":")[-1]

    texts = {
        "ru": {
            "prompt": (
                "❓ <b>Отказ от смены</b>\n\n"
                "Укажите причину отказа от смены (необязательно):\n\n"
                "Или нажмите /skip чтобы пропустить."
            ),
        },
        "uz": {
            "prompt": (
                "❓ <b>Smenadan voz kechish</b>\n\n"
                "Smenadan voz kechish sababini kiriting (majburiy emas):\n\n"
                "Yoki o'tkazib yuborish uchun /skip bosing."
            ),
        },
    }

    lang_texts = texts.get(language, texts["ru"])

    await callback.message.answer(lang_texts["prompt"], parse_mode="HTML")

    await state.update_data(shift_id=shift_id)
    await state.set_state(ShiftReleaseStates.waiting_for_reason)

    await callback.answer()


@router.message(ShiftReleaseStates.waiting_for_reason)
@router.message(Command("skip"), ShiftReleaseStates.waiting_for_reason)
async def process_release_reason(
    message: Message,
    token: str,
    language: str,
    state: FSMContext,
):
    """
    Process release reason and confirm.
    """
    data = await state.get_data()
    shift_id = data.get("shift_id")

    reason = None if message.text.startswith("/skip") else message.text.strip()

    texts = {
        "ru": {"confirm": "❓ Подтвердите отказ от смены?"},
        "uz": {"confirm": "❓ Smenadan voz kechishni tasdiqlaysizmi?"},
    }

    lang_texts = texts.get(language, texts["ru"])

    await message.answer(
        lang_texts["confirm"],
        reply_markup=shift_keyboards.get_confirmation_keyboard("release", shift_id, language),
    )

    await state.update_data(reason=reason)
    await state.set_state(ShiftReleaseStates.waiting_for_confirmation)


@router.callback_query(F.data.startswith("release:confirm:"))
async def callback_release_confirm(
    callback: CallbackQuery,
    token: str,
    language: str,
    state: FSMContext,
):
    """
    Confirm shift release.
    """
    shift_id = callback.data.split(":")[-1]
    data = await state.get_data()
    reason = data.get("reason")

    texts = {
        "ru": {
            "processing": "⏳ Обработка...",
            "success": "✅ Вы отказались от смены.",
            "error": "❌ Не удалось отказаться от смены.",
        },
        "uz": {
            "processing": "⏳ Qayta ishlanyapti...",
            "success": "✅ Siz smenadan voz kechtingiz.",
            "error": "❌ Smenadan voz kechishda xatolik.",
        },
    }

    lang_texts = texts.get(language, texts["ru"])

    await callback.answer(lang_texts["processing"])

    try:
        result = await shift_client.release_shift(
            shift_id=shift_id, reason=reason, token=token
        )

        await callback.message.answer(lang_texts["success"])
        await state.clear()

    except Exception as e:
        logger.error(f"Error releasing shift: {e}")
        await callback.message.answer(lang_texts["error"])
        await state.clear()


# ===========================================
# Availability Management
# ===========================================


@router.message(F.text.in_(["⏰ Доступность", "⏰ Mavjudlik"]))
async def button_availability(
    message: Message,
    language: str,
    state: FSMContext,
):
    """
    Show availability management menu.
    """
    await state.clear()

    texts = {
        "ru": (
            "⏰ <b>Управление доступностью</b>\n\n"
            "Настройте когда вы доступны для назначения на смены.\n\n"
            "Выберите действие:"
        ),
        "uz": (
            "⏰ <b>Mavjudlikni boshqarish</b>\n\n"
            "Smenalarga tayinlanish uchun qachon mavjudligingizni sozlang.\n\n"
            "Amalni tanlang:"
        ),
    }

    await message.answer(
        texts.get(language, texts["ru"]),
        reply_markup=shift_keyboards.get_availability_actions_keyboard(language),
        parse_mode="HTML",
    )


# ===========================================
# Statistics
# ===========================================


@router.message(F.text.in_(["📊 Статистика", "📊 Statistika"]))
async def button_statistics(
    message: Message,
    token: str,
    language: str,
):
    """
    Show shift statistics.
    """
    texts = {
        "ru": {"loading": "⏳ Загружаю статистику..."},
        "uz": {"loading": "⏳ Statistika yuklanmoqda..."},
    }

    lang_texts = texts.get(language, texts["ru"])

    loading_msg = await message.answer(lang_texts["loading"])

    try:
        # Get statistics
        result = await shift_client.get_shift_statistics(token=token)

        await loading_msg.delete()

        total = result.get("total_shifts", 0)
        completed = result.get("completed_shifts", 0)
        cancelled = result.get("cancelled_shifts", 0)
        hours = result.get("total_hours", 0.0)

        response = (
            f"📊 <b>Статистика смен</b>\n\n"
            f"📋 Всего смен: {total}\n"
            f"✅ Выполнено: {completed}\n"
            f"❌ Отменено: {cancelled}\n"
            f"⏱ Часов отработано: {hours:.1f}\n"
        )

        specs = result.get("specializations", {})
        if specs:
            response += "\n<b>По специализациям:</b>\n"
            for spec, count in specs.items():
                response += f"  🔧 {spec}: {count}\n"

        await message.answer(response, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error loading statistics: {e}")
        await loading_msg.delete()
        await message.answer("❌ Ошибка при загрузке статистики")


# ===========================================
# View Shift Details
# ===========================================


@router.callback_query(F.data.startswith("shift:view:"))
async def callback_view_shift(
    callback: CallbackQuery,
    token: str,
    language: str,
):
    """
    View detailed shift information.
    """
    shift_id = callback.data.split(":")[-1]

    try:
        shift = await shift_client.get_shift_by_id(shift_id=shift_id, token=token)

        response = (
            f"📅 <b>Смена {shift.get('date')}</b>\n\n"
            f"🕒 Время: {shift.get('time_from')} - {shift.get('time_to')}\n"
            f"🔧 Специализация: {shift.get('specialization')}\n"
            f"📊 Статус: {shift.get('status')}\n"
            f"📍 Объекты: {', '.join(shift.get('building_ids', []))}\n"
        )

        executor_id = shift.get("executor_id")
        if executor_id:
            response += f"👤 Исполнитель: {executor_id}\n"

        notes = shift.get("notes")
        if notes:
            response += f"\n📝 Примечания: {notes}\n"

        await callback.message.answer(response, parse_mode="HTML")
        await callback.answer()

    except Exception as e:
        logger.error(f"Error loading shift details: {e}")
        await callback.message.answer("❌ Ошибка при загрузке деталей смены")
        await callback.answer()
