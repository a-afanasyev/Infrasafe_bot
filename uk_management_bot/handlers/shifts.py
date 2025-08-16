import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from services.shift_service import ShiftService
from services.notification_service import async_notify_shift_started, async_notify_shift_ended
from keyboards.shifts import (
    get_shifts_main_keyboard,
    get_end_shift_confirm_inline,
    get_shifts_filters_inline,
    get_pagination_inline,
    get_manager_active_shifts_row,
)
from keyboards.base import get_executor_suggestion_inline
from database.session import get_db
from utils.helpers import get_text


router = Router()
logger = logging.getLogger(__name__)


@router.message(F.text == "🔄 Принять смену")
async def start_shift(message: Message, roles: list[str] = None, active_role: str = None, user_status: str | None = None):
    # Ранняя проверка статуса pending
    if user_status == "pending":
        try:
            lang = message.from_user.language_code or "ru"
            await message.answer(get_text("auth.pending", language=lang), reply_markup=get_shifts_main_keyboard())
        except Exception:
            await message.answer("⏳ Ожидайте одобрения администратора.", reply_markup=get_shifts_main_keyboard())
        return
    db = next(get_db())
    service = ShiftService(db)
    result = service.start_shift(message.from_user.id)
    if not result.get("success"):
        await message.answer(result.get("message", "Ошибка"), reply_markup=get_shifts_main_keyboard())
        return
    await message.answer("✅ Смена начата", reply_markup=get_shifts_main_keyboard())
    # async notifications
    try:
        from aiogram import Bot
        bot: Bot = message.bot
        user = service._get_user_by_tg(message.from_user.id)
        shift = result.get("shift")
        if user and shift:
            await async_notify_shift_started(bot, db, user, shift)
    except Exception:
        pass

    # Автопредложение перейти в режим исполнителя
    try:
        roles = roles or ["applicant"]
        active_role = active_role or roles[0]
        if ("executor" in roles) and (active_role != "executor"):
            lang = message.from_user.language_code or "ru"
            title = get_text("role.suggest_executor_title", language=lang)
            yes_label = get_text("role.suggest_executor_yes", language=lang)
            no_label = get_text("role.suggest_executor_no", language=lang)
            await message.answer(title, reply_markup=get_executor_suggestion_inline(yes_label, no_label))
    except Exception:
        # Предложение — вспомогательная функция; не должна ломать основной поток
        pass


@router.message(F.text == "🔚 Сдать смену")
async def end_shift_confirm(message: Message):
    await message.answer("Подтвердите сдачу смены", reply_markup=get_end_shift_confirm_inline())


@router.callback_query(F.data == "shift_end_confirm_yes")
async def end_shift_yes(callback: CallbackQuery, user_status: str | None = None):
    if user_status == "pending":
        try:
            await callback.answer(get_text("auth.pending", language=callback.from_user.language_code or "ru"), show_alert=True)
        except Exception:
            await callback.answer("⏳ Ожидайте одобрения администратора.", show_alert=True)
        return
    db = next(get_db())
    service = ShiftService(db)
    result = service.end_shift(callback.from_user.id)
    if not result.get("success"):
        await callback.answer(result.get("message", "Ошибка"), show_alert=True)
        return
    await callback.message.edit_text("✅ Смена завершена", reply_markup=None)
    # async notifications
    try:
        from aiogram import Bot
        bot: Bot = callback.message.bot
        user = service._get_user_by_tg(callback.from_user.id)
        shift = result.get("shift")
        if user and shift:
            await async_notify_shift_ended(bot, db, user, shift)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "suggest_executor_skip")
async def suggest_executor_skip(callback: CallbackQuery):
    """Обработчик отказа от автоматического переключения роли после старта смены."""
    try:
        lang = callback.from_user.language_code or "ru"
        text = get_text("role.suggest_executor_skipped", language=lang)
        await callback.answer()
        await callback.message.answer(text)
    except Exception:
        # Безопасное завершение без побочных эффектов
        try:
            await callback.answer()
        except Exception:
            pass


@router.callback_query(F.data == "shift_end_confirm_no")
async def end_shift_no(callback: CallbackQuery):
    await callback.message.edit_text("Отмена сдачи смены", reply_markup=None)
    await callback.answer()


@router.message(F.text == "ℹ️ Моя смена")
async def my_shift(message: Message):
    db = next(get_db())
    service = ShiftService(db)
    active = service.get_active_shift(message.from_user.id)
    if not active:
        await message.answer("У вас нет активной смены", reply_markup=get_shifts_main_keyboard())
        return
    await message.answer(
        f"Активная смена с {active.start_time.strftime('%d.%m.%Y %H:%M')}",
        reply_markup=get_shifts_main_keyboard(),
    )


@router.message(F.text == "📜 История смен")
async def shifts_history(message: Message, state: FSMContext):
    data = await state.get_data()
    period = data.get("my_shifts_period", "all")
    status = data.get("my_shifts_status", "all")
    page = int(data.get("my_shifts_page", 1))

    db = next(get_db())
    service = ShiftService(db)
    shifts = service.list_shifts(telegram_id=message.from_user.id, period=period if period != "all" else None, status=None if status == "all" else status)
    per_page = 5
    total_pages = max(1, (len(shifts) + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages
    start = (page - 1) * per_page
    end = start + per_page
    page_items = shifts[start:end]

    if not page_items:
        text = "История смен пуста"
    else:
        lines = ["📜 История смен:"]
        for s in page_items:
            end_time = s.end_time.strftime('%d.%m.%Y %H:%M') if s.end_time else "—"
            lines.append(f"- {s.start_time.strftime('%d.%m.%Y %H:%M')} → {end_time} [{s.status}]")
        text = "\n".join(lines)

    filters_kb = get_shifts_filters_inline(period=period, status=status)
    pagination_kb = get_pagination_inline(page, total_pages)
    combined = type(pagination_kb)(inline_keyboard=filters_kb.inline_keyboard + pagination_kb.inline_keyboard)

    await state.update_data(my_shifts_page=page)
    await message.answer(text, reply_markup=combined)


@router.callback_query(F.data.startswith("shifts_page_"))
async def shifts_history_page(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    page_str = callback.data.replace("shifts_page_", "")
    if page_str == "current":
        await callback.answer()
        return
    try:
        page = int(page_str)
    except ValueError:
        await callback.answer("Неверная страница", show_alert=True)
        return
    await state.update_data(my_shifts_page=page)
    # Перерисовать через message flow
    fake = callback.message
    fake.from_user = callback.from_user
    await shifts_history(fake, state)
    await callback.answer()


@router.callback_query(F.data.startswith("shifts_period_"))
async def shifts_filter_period(callback: CallbackQuery, state: FSMContext):
    value = callback.data.replace("shifts_period_", "")
    await state.update_data(my_shifts_period=value, my_shifts_page=1)
    fake = callback.message
    fake.from_user = callback.from_user
    await shifts_history(fake, state)
    await callback.answer()


@router.callback_query(F.data.startswith("shifts_status_"))
async def shifts_filter_status(callback: CallbackQuery, state: FSMContext):
    value = callback.data.replace("shifts_status_", "")
    await state.update_data(my_shifts_status=value, my_shifts_page=1)
    fake = callback.message
    fake.from_user = callback.from_user
    await shifts_history(fake, state)
    await callback.answer()


@router.callback_query(F.data == "shifts_filters_reset")
async def shifts_filters_reset(callback: CallbackQuery, state: FSMContext):
    await state.update_data(my_shifts_status="all", my_shifts_period="all", my_shifts_page=1)
    fake = callback.message
    fake.from_user = callback.from_user
    await shifts_history(fake, state)
    await callback.answer("Фильтры сброшены")


@router.message(F.text == "🟢 Активные смены")
async def manager_active_shifts(message: Message, state: FSMContext):
    # Здесь предполагается, что проверка роли происходит отдельно (например, через middleware)
    db = next(get_db())
    service = ShiftService(db)
    shifts = service.list_shifts(status="active")
    if not shifts:
        await message.answer("Нет активных смен")
        return
    lines = ["Активные смены:"]
    for s in shifts[:10]:
        lines.append(f"- user_id={s.user_id} с {s.start_time.strftime('%d.%m.%Y %H:%M')}")
    await message.answer("\n".join(lines))


@router.callback_query(F.data.startswith("force_end_shift_"))
async def force_end_shift(callback: CallbackQuery):
    db = next(get_db())
    service = ShiftService(db)
    try:
        target_tg = int(callback.data.replace("force_end_shift_", ""))
    except ValueError:
        await callback.answer("Неверные данные", show_alert=True)
        return
    result = service.force_end_shift(callback.from_user.id, target_tg)
    if not result.get("success"):
        await callback.answer(result.get("message", "Ошибка"), show_alert=True)
        return
    await callback.answer("Смена завершена менеджером")


