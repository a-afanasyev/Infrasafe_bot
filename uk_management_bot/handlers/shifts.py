import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from uk_management_bot.services.shift_service import ShiftService
from uk_management_bot.services.notification_service import async_notify_shift_started, async_notify_shift_ended
from uk_management_bot.keyboards.shifts import (
    get_shifts_main_keyboard,
    get_end_shift_confirm_inline,
    get_shifts_filters_inline,
    get_pagination_inline,
    get_manager_active_shifts_row,
)
from uk_management_bot.keyboards.base import get_executor_suggestion_inline
from uk_management_bot.database.session import get_db
from uk_management_bot.utils.helpers import get_text, get_user_language
from uk_management_bot.utils.button_texts import (
    get_accept_shift_texts,
    get_end_shift_texts,
    get_my_shift_texts,
    get_shift_history_texts,
)


router = Router()
logger = logging.getLogger(__name__)

# Single Source of Truth for button texts - TASK 17
ACCEPT_SHIFT_TEXTS = get_accept_shift_texts()
END_SHIFT_TEXTS = get_end_shift_texts()
MY_SHIFT_TEXTS = get_my_shift_texts()
SHIFT_HISTORY_TEXTS = get_shift_history_texts()


@router.message(F.text.in_(ACCEPT_SHIFT_TEXTS))
async def start_shift(message: Message, db=None, roles: list[str] = None, active_role: str = None, user_status: str | None = None):
    """Начать смену"""
    if not db:
        db = next(get_db())
        need_close = True
    else:
        need_close = False
    
    try:
        lang = get_user_language(message.from_user.id, db)
        
        # Ранняя проверка статуса pending
        if user_status == "pending":
            try:
                await message.answer(get_text("auth.pending", language=lang), reply_markup=get_shifts_main_keyboard(language=lang))
            except Exception:
                await message.answer("⏳ Ожидайте одобрения администратора.", reply_markup=get_shifts_main_keyboard(language=lang))
            return
        
        service = ShiftService(db)
        result = service.start_shift(message.from_user.id)
        if not result.get("success"):
            await message.answer(result.get("message", get_text("shifts.error", language=lang)), reply_markup=get_shifts_main_keyboard(language=lang))
            return
        
        await message.answer(get_text("shifts.started", language=lang), reply_markup=get_shifts_main_keyboard(language=lang))
        
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
                title = get_text("role.suggest_executor_title", language=lang)
                yes_label = get_text("role.suggest_executor_yes", language=lang)
                no_label = get_text("role.suggest_executor_no", language=lang)
                await message.answer(title, reply_markup=get_executor_suggestion_inline(yes_label, no_label))
        except Exception:
            # Предложение — вспомогательная функция; не должна ломать основной поток
            pass
    finally:
        if need_close and db:
            db.close()


@router.message(F.text.in_(END_SHIFT_TEXTS))
async def end_shift_confirm(message: Message, db=None):
    """Показать список активных смен для выбора"""
    if not db:
        db = next(get_db())
        need_close = True
    else:
        need_close = False
    
    try:
        lang = get_user_language(message.from_user.id, db)
        service = ShiftService(db)

        # Получаем пользователя
        from uk_management_bot.database.models.user import User
        from uk_management_bot.database.models.shift import Shift
        from sqlalchemy import and_

        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer(get_text("shifts.user_не_найден", language=lang))
            return

        # Получаем ВСЕ активные смены пользователя
        active_shifts = db.query(Shift).filter(
            and_(
                Shift.user_id == user.id,
                Shift.status == "active"
            )
        ).order_by(Shift.start_time).all()

        if not active_shifts:
            await message.answer(get_text("shifts.no_active", language=lang))
            return

        # Если смена одна - показываем детали сразу
        if len(active_shifts) == 1:
            await show_shift_end_details(message, active_shifts[0].id, db, lang)
            return

        # Если смен несколько - показываем список для выбора
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from datetime import datetime

        text = get_text("shifts.bвыберите_смену_для", language=lang) + "\n\n"

        keyboard_rows = []
        for idx, shift in enumerate(active_shifts, 1):
            # Рассчитываем длительность
            duration = datetime.now() - shift.start_time
            hours = int(duration.total_seconds() // 3600)
            minutes = int((duration.total_seconds() % 3600) // 60)

            # Получаем специализации смены
            specializations = shift.specialization_focus or []
            if isinstance(specializations, str):
                import json
                try:
                    specializations = json.loads(specializations)
                except:
                    specializations = [specializations] if specializations else []

            spec_text = ", ".join(specializations) if specializations else get_text("shifts.universal", language=lang, fallback="Универсальная")

            text += f"{idx}. 🔵 <b>{get_text('shifts.shift', language=lang)} #{shift.id}</b>\n"
            text += f"   📅 {get_text('shifts.start_time', language=lang)}: {shift.start_time.strftime('%d.%m.%Y %H:%M')}\n"
            text += f"   ⏱️ {get_text('shifts.duration', language=lang).replace('{duration}', '')}: {hours}{get_text('shifts.hours', language=lang, fallback='ч')} {minutes}{get_text('shifts.minutes', language=lang, fallback='м')}\n"
            text += f"   🔧 {get_text('shifts.specialization', language=lang, fallback='Специализация')}: {spec_text}\n\n"

            keyboard_rows.append([
                InlineKeyboardButton(
                    text=f"🔚 {get_text('shifts.complete_смену_2', language=lang)} {shift.id}",
                    callback_data=f"end_shift_select:{shift.id}"
                )
            ])

        keyboard_rows.append([
            InlineKeyboardButton(text=get_text("buttons.cancel", language=lang), callback_data="end_shift_cancel")
        ])

        await message.answer(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Ошибка показа списка смен: {e}")
        lang = get_user_language(message.from_user.id, db) if db else "ru"
        await message.answer(get_text("shifts.error_показа_списка", language=lang))
    finally:
        if need_close and db:
            db.close()


async def show_shift_end_details(message: Message, shift_id: int, db, lang: str = "ru"):
    """Показать детали смены перед завершением с проверкой активных заявок"""
    try:
        from uk_management_bot.database.models.shift import Shift
        from uk_management_bot.database.models.request import Request
        from uk_management_bot.database.models.request_assignment import RequestAssignment
        from sqlalchemy import and_, or_
        from datetime import datetime
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        shift = db.query(Shift).filter(Shift.id == shift_id).first()
        if not shift:
            await message.answer(get_text("shifts.shift_не_найдена", language=lang))
            return

        # Рассчитываем длительность
        duration = datetime.now() - shift.start_time
        hours = int(duration.total_seconds() // 3600)
        minutes = int((duration.total_seconds() % 3600) // 60)

        # Получаем специализации смены
        specializations = shift.specialization_focus or []
        if isinstance(specializations, str):
            import json
            try:
                specializations = json.loads(specializations)
            except:
                specializations = [specializations] if specializations else []

        spec_text = ", ".join(specializations) if specializations else "Универсальная"

        # Формируем текст
        text = f"⚠️ <b>Подтверждение завершения смены</b>\n\n"
        text += f"📅 <b>Смена:</b> {shift.start_time.strftime('%d.%m.%Y %H:%M')} - текущее время\n"
        text += f"⏱️ <b>Длительность:</b> {hours}ч {minutes}м\n"
        text += f"🔧 <b>Специализация:</b> {spec_text}\n\n"

        # Получаем активные заявки
        # 1. Групповые заявки (назначенные через specialization)
        group_requests = []
        if specializations:
            group_requests = db.query(Request).join(RequestAssignment).filter(
                and_(
                    RequestAssignment.assignment_type == "group",
                    RequestAssignment.group_specialization.in_(specializations),
                    RequestAssignment.status == "active",
                    Request.status.in_(["В работе", "Закуп", "Уточнение"])
                )
            ).all()

        # 2. Индивидуальные заявки (назначенные конкретно исполнителю)
        from uk_management_bot.database.models.user import User
        user = db.query(User).filter(User.id == shift.user_id).first()

        individual_requests = []
        if user:
            individual_requests = db.query(Request).join(RequestAssignment).filter(
                and_(
                    RequestAssignment.assignment_type == "individual",
                    RequestAssignment.executor_id == user.id,
                    RequestAssignment.status == "active",
                    Request.status.in_(["В работе", "Закуп", "Уточнение"])
                )
            ).all()

        # Показываем информацию о заявках
        if group_requests or individual_requests:
            text += "📋 <b>Активные заявки:</b>\n\n"

            if group_requests:
                text += f"🔵 <b>Дежурные заявки</b> (будут переданы следующей смене): {len(group_requests)}\n"
                for req in group_requests[:3]:  # Показываем первые 3
                    text += f"   • #{req.request_number} - {req.category}\n"
                if len(group_requests) > 3:
                    text += f"   • и ещё {len(group_requests) - 3}...\n"
                text += "\n"

            if individual_requests:
                text += f"👤 <b>Персональные заявки</b> (остаются за вами): {len(individual_requests)}\n"
                for req in individual_requests[:3]:  # Показываем первые 3
                    text += f"   • #{req.request_number} - {req.category}\n"
                if len(individual_requests) > 3:
                    text += f"   • и ещё {len(individual_requests) - 3}...\n"
                text += "\n"

            text += "ℹ️ <i>Дежурные заявки автоматически передадутся следующему исполнителю на смене.\n"
            text += "Персональные заявки останутся за вами до завершения.</i>\n\n"
        else:
            text += "✅ <b>Активных заявок нет</b>\n\n"

        text += "Подтвердить завершение смены?"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, завершить", callback_data=f"shift_end_confirm_yes:{shift_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="end_shift_cancel")
            ]
        ])

        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка показа деталей смены: {e}")
        await message.answer("❌ Произошла ошибка")


@router.callback_query(F.data.startswith("end_shift_select:"))
async def handle_shift_selection(callback: CallbackQuery, db=None):
    """Обработка выбора конкретной смены для завершения"""
    if not db:
        db = next(get_db())
        need_close = True
    else:
        need_close = False
    
    try:
        shift_id = int(callback.data.split(":")[1])
        lang = get_user_language(callback.from_user.id, db)
        await show_shift_end_details(callback.message, shift_id, db, lang)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка выбора смены: {e}")
        lang = get_user_language(callback.from_user.id, db) if db else "ru"
        await callback.answer(get_text("shifts.error_выбора_shifts", language=lang), show_alert=True)
    finally:
        if need_close and db:
            db.close()


@router.callback_query(F.data == "end_shift_cancel")
async def handle_end_shift_cancel(callback: CallbackQuery):
    """Отмена завершения смены"""
    try:
        await callback.message.edit_text("❌ Завершение смены отменено")
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка отмены: {e}")
        await callback.answer()


@router.callback_query(F.data.startswith("shift_end_confirm_yes:"))
async def end_shift_yes_with_id(callback: CallbackQuery, user_status: str | None = None):
    """Подтверждение завершения конкретной смены"""
    if user_status == "pending":
        try:
            await callback.answer(get_text("auth.pending", language=callback.from_user.language_code or "ru"), show_alert=True)
        except Exception:
            await callback.answer("⏳ Ожидайте одобрения администратора.", show_alert=True)
        return

    try:
        shift_id = int(callback.data.split(":")[1])
        db = next(get_db())
        service = ShiftService(db)

        # Завершаем конкретную смену
        from uk_management_bot.database.models.shift import Shift
        from uk_management_bot.database.models.user import User
        from datetime import datetime

        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return

        shift = db.query(Shift).filter(
            Shift.id == shift_id,
            Shift.user_id == user.id,
            Shift.status == "active"
        ).first()

        if not shift:
            await callback.answer("❌ Смена не найдена или уже завершена", show_alert=True)
            return

        # Завершаем смену
        shift.end_time = datetime.now()
        shift.status = "completed"

        # Создаем audit log
        from uk_management_bot.database.models.audit import AuditLog
        audit = AuditLog(
            user_id=user.id,
            telegram_user_id=user.telegram_id,
            action="SHIFT_ENDED",
            details={"shift_id": shift.id, "specializations": shift.specialization_focus}
        )
        db.add(audit)
        db.commit()

        await callback.message.edit_text(
            f"✅ <b>Смена #{shift.id} завершена</b>\n\n"
            f"⏱️ Длительность: {((shift.end_time - shift.start_time).total_seconds() // 3600):.0f}ч "
            f"{((shift.end_time - shift.start_time).total_seconds() % 3600 // 60):.0f}м\n"
            f"📅 Время окончания: {shift.end_time.strftime('%d.%m.%Y %H:%M')}",
            parse_mode="HTML"
        )

        # Отправляем уведомления
        try:
            from uk_management_bot.services.shift_service import async_notify_shift_ended
            from aiogram import Bot
            bot: Bot = callback.message.bot
            await async_notify_shift_ended(bot, db, user, shift)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомлений: {e}")

        await callback.answer("✅ Смена завершена")

    except Exception as e:
        logger.error(f"Ошибка завершения смены: {e}")
        await callback.answer("❌ Произошла ошибка при завершении смены", show_alert=True)


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


@router.message(F.text.in_(MY_SHIFT_TEXTS))
async def my_shift(message: Message, db=None):
    """Показать текущую активную смену"""
    if not db:
        db = next(get_db())
        need_close = True
    else:
        need_close = False
    
    try:
        lang = get_user_language(message.from_user.id, db)
        service = ShiftService(db)
        active = service.get_active_shift(message.from_user.id)
        if not active:
            await message.answer(get_text("shifts.no_active", language=lang), reply_markup=get_shifts_main_keyboard(language=lang))
            return
        await message.answer(
            get_text("shifts.активная_shift_с", language=lang).replace("{...}", active.start_time.strftime('%d.%m.%Y %H:%M')),
            reply_markup=get_shifts_main_keyboard(language=lang),
        )
    finally:
        if need_close and db:
            db.close()


@router.message(F.text.in_(SHIFT_HISTORY_TEXTS))
async def shifts_history(message: Message, state: FSMContext, db=None):
    """Показать историю смен"""
    if not db:
        db = next(get_db())
        need_close = True
    else:
        need_close = False
    
    try:
        lang = get_user_language(message.from_user.id, db)
        data = await state.get_data()
        period = data.get("my_shifts_period", "all")
        status = data.get("my_shifts_status", "all")
        page = int(data.get("my_shifts_page", 1))

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
            text = get_text("shifts.bистория_сменb_за", language=lang)
        else:
            lines = [get_text("shifts.shift_history", language=lang) + ":"]
            for s in page_items:
                end_time = s.end_time.strftime('%d.%m.%Y %H:%M') if s.end_time else "—"
                lines.append(f"- {s.start_time.strftime('%d.%m.%Y %H:%M')} → {end_time} [{s.status}]")
            text = "\n".join(lines)

        filters_kb = get_shifts_filters_inline(period=period, status=status)
        pagination_kb = get_pagination_inline(page, total_pages)
        combined = type(pagination_kb)(inline_keyboard=filters_kb.inline_keyboard + pagination_kb.inline_keyboard)

        await state.update_data(my_shifts_page=page)
        await message.answer(text, reply_markup=combined)
    finally:
        if need_close and db:
            db.close()


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


