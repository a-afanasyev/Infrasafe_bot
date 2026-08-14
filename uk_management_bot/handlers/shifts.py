"""
Operational shift menu ("🔄 Смена") — quick actions for shift start/stop.

Uses: Shift.start_time, Shift.end_time (actual times)
Related: my_shifts.py handles the detailed shift interface ("📋 Мои смены")
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from uk_management_bot.services.shift_service import ShiftService
from uk_management_bot.services.notification_service import async_notify_shift_ended
from uk_management_bot.services.notification_service.channel import (
    send_to_channel,
    send_to_user,
)
from uk_management_bot.services.notification_service.shifts import (
    build_shift_ended_message,
    build_shift_started_message,
)
from uk_management_bot.keyboards.shifts import (
    get_shifts_main_keyboard,
    get_shifts_filters_inline,
    get_pagination_inline,
)
from uk_management_bot.keyboards.base import get_executor_suggestion_inline
from uk_management_bot.database.session import run_db, session_scope
from uk_management_bot.utils.helpers import get_text, get_user_language
from uk_management_bot.utils.datetime_utils import utc_now
# ARCH-116: время смен показываем в бизнес-зоне (БД остаётся UTC).
from uk_management_bot.utils.business_time import fmt_datetime, fmt_time
from uk_management_bot.utils.button_texts import (
    get_accept_shift_texts,
    get_end_shift_texts,
    get_my_shift_texts,
    get_shift_history_texts,
    get_active_shifts_button_texts,
)


router = Router()
logger = logging.getLogger(__name__)

# Single Source of Truth for button texts - TASK 17
ACCEPT_SHIFT_TEXTS = get_accept_shift_texts()
END_SHIFT_TEXTS = get_end_shift_texts()
MY_SHIFT_TEXTS = get_my_shift_texts()
SHIFT_HISTORY_TEXTS = get_shift_history_texts()
ACTIVE_SHIFTS_BUTTON_TEXTS = get_active_shifts_button_texts()


# ==========================================================================
# DTO для async-слоя: наружу из run_db выходят примитивы, не ORM-строки
# (у ORM-объекта за пределами worker-потока нет живой сессии).
# ==========================================================================

@dataclass(frozen=True)
class _ActiveShiftRow:
    """Строка списка активных смен для выбора завершения."""
    id: int
    start_time: datetime
    specialization_focus: object  # как в БД: list | str | None (парсится при рендере)


@dataclass(frozen=True)
class _ReqRow:
    """Заявка в сводке перед завершением смены."""
    request_number: str
    category: str


@dataclass(frozen=True)
class _ShiftEndView:
    """Данные для экрана подтверждения завершения смены."""
    shift_id: int
    start_time: datetime
    specializations: tuple
    group_requests: tuple      # tuple[_ReqRow, ...]
    individual_requests: tuple  # tuple[_ReqRow, ...]


@dataclass(frozen=True)
class _HistoryRow:
    """Строка истории смен."""
    start_time: datetime
    end_time: Optional[datetime]
    status: str


# ==========================================================================
# Sync unit-of-work (AUD3-07/AUD5-ARCH-1): исполняются в worker-потоке через
# run_db; сессию открывает и закрывает run_db, event loop БД не трогает.
# ShiftService — sync-сервис, коммитит сам: безопасен в thread-сессии.
# ==========================================================================

def _lang_by_tg(db, telegram_id: int) -> str:
    return get_user_language(telegram_id, db)


def _start_shift_unit(db, telegram_id: int) -> dict:
    """-> {lang, success, message?, notify: (user_tg, user_text, channel_text) | None}.

    B3-раскрой нотификаций: текстовые payload'ы собираются здесь (fetch),
    сама отправка — в async-слое после выхода из db-фазы (send).
    """
    lang = get_user_language(telegram_id, db)
    service = ShiftService(db)
    result = service.start_shift(telegram_id)
    if not result.get("success"):
        return {
            "lang": lang,
            "success": False,
            "message": result.get("message", get_text("shifts.error", language=lang)),
        }

    notify = None
    try:
        user = service._get_user_by_tg(telegram_id)
        shift = result.get("shift")
        if user and shift:
            notify = (
                user.telegram_id,
                build_shift_started_message(user, shift, for_channel=False),
                build_shift_started_message(user, shift, for_channel=True),
            )
    except Exception:
        pass

    return {"lang": lang, "success": True, "notify": notify}


def _load_active_shifts_for_end(db, telegram_id: int):
    """-> (lang, "no_user" | "ok", [_ActiveShiftRow])."""
    lang = get_user_language(telegram_id, db)

    # Получаем пользователя
    from uk_management_bot.database.models.user import User
    from uk_management_bot.database.models.shift import Shift
    from sqlalchemy import and_

    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        return lang, "no_user", []

    # Получаем ВСЕ активные смены пользователя
    active_shifts = db.query(Shift).filter(
        and_(
            Shift.user_id == user.id,
            Shift.status == "active"
        )
    ).order_by(Shift.start_time).all()

    rows = [
        _ActiveShiftRow(
            id=s.id,
            start_time=s.start_time,
            specialization_focus=s.specialization_focus,
        )
        for s in active_shifts
    ]
    return lang, "ok", rows


def _load_shift_end_view(db, shift_id: int) -> Optional[_ShiftEndView]:
    """-> _ShiftEndView | None (None — смена не найдена)."""
    from uk_management_bot.database.models.shift import Shift
    from uk_management_bot.database.models.request import Request
    from uk_management_bot.database.models.request_assignment import RequestAssignment
    from sqlalchemy import and_

    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if not shift:
        return None

    # Получаем специализации смены
    specializations = shift.specialization_focus or []
    if isinstance(specializations, str):
        import json
        try:
            specializations = json.loads(specializations)
        except Exception:
            specializations = [specializations] if specializations else []

    # FS-10: ad-hoc смена не несёт specialization_focus → раньше показывалось
    # «Универсальная», хотя у исполнителя есть спец-ция. Падаем на спец-цию
    # самого исполнителя смены, и только при её отсутствии — «Универсальная».
    if not specializations and shift.user_id:
        from uk_management_bot.database.models.user import User
        from uk_management_bot.utils.specializations import parse_specializations
        shift_user = db.query(User).filter(User.id == shift.user_id).first()
        if shift_user:
            specializations = sorted(parse_specializations(shift_user))

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

    return _ShiftEndView(
        shift_id=shift.id,
        start_time=shift.start_time,
        specializations=tuple(specializations),
        group_requests=tuple(
            _ReqRow(request_number=r.request_number, category=r.category)
            for r in group_requests
        ),
        individual_requests=tuple(
            _ReqRow(request_number=r.request_number, category=r.category)
            for r in individual_requests
        ),
    )


def _end_shift_by_id_unit(db, telegram_id: int, shift_id: int):
    """-> (lang, "no_user" | "no_shift" | "ok", payload | None).

    Цельный unit-of-work: завершение смены + audit log + commit. Notify-payload
    (B3-раскрой) собирается здесь, отправка — в async-слое после коммита.
    """
    lang = get_user_language(telegram_id, db)

    # Завершаем конкретную смену
    from uk_management_bot.database.models.shift import Shift
    from uk_management_bot.database.models.user import User

    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        return lang, "no_user", None

    shift = db.query(Shift).filter(
        Shift.id == shift_id,
        Shift.user_id == user.id,
        Shift.status == "active"
    ).first()

    if not shift:
        return lang, "no_shift", None

    # Завершаем смену
    shift.end_time = utc_now()
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

    notify = None
    try:
        notify = (
            user.telegram_id,
            build_shift_ended_message(user, shift, for_channel=False),
            build_shift_ended_message(user, shift, for_channel=True),
        )
    except Exception:
        pass

    payload = {
        "shift_id": shift.id,
        "hours": f"{((shift.end_time - shift.start_time).total_seconds() // 3600):.0f}",
        "minutes": f"{((shift.end_time - shift.start_time).total_seconds() % 3600 // 60):.0f}",
        "end_time": shift.end_time,
        "notify": notify,
    }
    return lang, "ok", payload


def _my_shift_unit(db, telegram_id: int):
    """-> (lang, found, start_time | None)."""
    lang = get_user_language(telegram_id, db)
    service = ShiftService(db)
    active = service.get_active_shift(telegram_id)
    if not active:
        return lang, False, None
    return lang, True, active.start_time


def _shifts_history_unit(db, telegram_id: int, period, status):
    """-> (lang, [_HistoryRow])."""
    lang = get_user_language(telegram_id, db)
    service = ShiftService(db)
    shifts = service.list_shifts(telegram_id=telegram_id, period=period if period != "all" else None, status=None if status == "all" else status)
    rows = [
        _HistoryRow(start_time=s.start_time, end_time=s.end_time, status=s.status)
        for s in shifts
    ]
    return lang, rows


@router.message(F.text.in_(ACCEPT_SHIFT_TEXTS))
async def start_shift(message: Message, roles: list[str] = None, active_role: str = None, user_status: str | None = None, *, _db=None):
    """Начать смену"""
    # Ранняя проверка статуса pending
    if user_status == "pending":
        lang = await run_db(lambda s: _lang_by_tg(s, message.from_user.id), db=_db)
        try:
            await message.answer(get_text("auth.pending", language=lang), reply_markup=get_shifts_main_keyboard(language=lang))
        except Exception:
            from uk_management_bot.utils.safe_localization import safe_get_text
            await message.answer(safe_get_text("shifts.awaiting_admin_approval", language=lang), reply_markup=get_shifts_main_keyboard(language=lang))
        return

    outcome = await run_db(lambda s: _start_shift_unit(s, message.from_user.id), db=_db)
    lang = outcome["lang"]
    if not outcome["success"]:
        await message.answer(outcome["message"], reply_markup=get_shifts_main_keyboard(language=lang))
        return

    await message.answer(get_text("shifts.started", language=lang), reply_markup=get_shifts_main_keyboard(language=lang))

    # async notifications — сеть в async-слое, вне db-фазы (B3-раскрой)
    try:
        from aiogram import Bot
        bot: Bot = message.bot
        if outcome["notify"]:
            user_tg, user_text, channel_text = outcome["notify"]
            await send_to_user(bot, user_tg, user_text)
            await send_to_channel(bot, channel_text)
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


@router.message(F.text.in_(END_SHIFT_TEXTS))
async def end_shift_confirm(message: Message, *, _db=None):
    """Показать список активных смен для выбора"""
    lang = "ru"  # A6-P3-21 (как в PR #334): except не ходит в БД — сессия закрыта/aborted
    try:
        lang, verdict, active_shifts = await run_db(
            lambda s: _load_active_shifts_for_end(s, message.from_user.id), db=_db,
        )
        if verdict == "no_user":
            await message.answer(get_text("shifts.user_not_found", language=lang))
            return

        if not active_shifts:
            await message.answer(get_text("shifts.no_active", language=lang))
            return

        # Если смена одна - показываем детали сразу
        if len(active_shifts) == 1:
            await show_shift_end_details(message, active_shifts[0].id, lang, _db=_db)
            return

        # Если смен несколько - показываем список для выбора
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        text = get_text("shifts.select_shift_to_end", language=lang) + "\n\n"

        keyboard_rows = []
        for idx, shift in enumerate(active_shifts, 1):
            # Рассчитываем длительность (AUD5-CODE-3: start_time timestamptz — aware)
            duration = utc_now() - shift.start_time
            hours = int(duration.total_seconds() // 3600)
            minutes = int((duration.total_seconds() % 3600) // 60)

            # Получаем специализации смены
            specializations = shift.specialization_focus or []
            if isinstance(specializations, str):
                import json
                try:
                    specializations = json.loads(specializations)
                except Exception:
                    specializations = [specializations] if specializations else []

            # ⚠️ Предсуществующий дефект (сохранён 1:1): сырые ключи специализаций
            # без локализации — в show_shift_end_details тот же список идёт через _loc_spec.
            spec_text = ", ".join(specializations) if specializations else (get_text("shifts.universal", language=lang) or "Универсальная")

            text += f"{idx}. 🔵 <b>{get_text('shifts.shift', language=lang)} #{shift.id}</b>\n"
            text += f"   📅 {get_text('shifts.start_time', language=lang)}: {fmt_datetime(shift.start_time)}\n"
            text += f"   ⏱️ {get_text('shifts.duration', language=lang).replace('{duration}', '')}: {hours}{get_text('shifts.hours', language=lang) or 'ч'} {minutes}{get_text('shifts.minutes', language=lang) or 'м'}\n"
            text += f"   🔧 {get_text('shifts.specialization', language=lang) or 'Специализация'}: {spec_text}\n\n"

            keyboard_rows.append([
                InlineKeyboardButton(
                    text=f"🔚 {get_text('shifts.complete_shift', language=lang)} {shift.id}",
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
        await message.answer(get_text("shifts.error_showing_list", language=lang))


async def show_shift_end_details(message: Message, shift_id: int, lang: str = "ru", *, _db=None):
    """Показать детали смены перед завершением с проверкой активных заявок"""
    try:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        view = await run_db(lambda s: _load_shift_end_view(s, shift_id), db=_db)
        if view is None:
            await message.answer(get_text("shifts.shift_not_found", language=lang))
            return

        # Рассчитываем длительность (AUD5-CODE-3: start_time timestamptz — aware)
        duration = utc_now() - view.start_time
        hours = int(duration.total_seconds() // 3600)
        minutes = int((duration.total_seconds() % 3600) // 60)

        specializations = view.specializations

        # FS-10: локализуем ключи спец-ций (plumber→«Сантехник»); неизвестный
        # ключ get_text вернёт как есть → fallback на сырое значение.
        def _loc_spec(s):
            t = get_text(f"specializations.{s}", language=lang)
            return s if t == f"specializations.{s}" else t

        spec_text = ", ".join(_loc_spec(s) for s in specializations) if specializations else get_text("shifts.handlers.universal", language=lang)

        # Формируем текст
        text = f"⚠️ <b>{get_text('shifts.handlers.end_shift_confirmation', language=lang)}</b>\n\n"
        text += f"📅 <b>{get_text('shifts.handlers.shift_label', language=lang)}:</b> {fmt_datetime(view.start_time)} - {get_text('shifts.handlers.current_time', language=lang)}\n"
        text += f"⏱️ <b>{get_text('shifts.handlers.duration_label', language=lang)}:</b> {hours}{get_text('shifts.handlers.hours_short', language=lang)} {minutes}{get_text('shifts.handlers.minutes_short', language=lang)}\n"
        text += f"🔧 <b>{get_text('shifts.handlers.specialization_label', language=lang)}:</b> {spec_text}\n\n"

        group_requests = view.group_requests
        individual_requests = view.individual_requests

        # Показываем информацию о заявках
        if group_requests or individual_requests:
            text += f"📋 <b>{get_text('shifts.handlers.active_requests', language=lang)}:</b>\n\n"

            if group_requests:
                text += f"🔵 <b>{get_text('shifts.handlers.duty_requests', language=lang)}</b> ({get_text('shifts.handlers.will_be_transferred', language=lang)}): {len(group_requests)}\n"
                for req in group_requests[:3]:
                    text += f"   • #{req.request_number} - {req.category}\n"
                if len(group_requests) > 3:
                    text += f"   • {get_text('shifts.handlers.and_more', language=lang).format(count=len(group_requests) - 3)}...\n"
                text += "\n"

            if individual_requests:
                text += f"👤 <b>{get_text('shifts.handlers.personal_requests', language=lang)}</b> ({get_text('shifts.handlers.stay_with_you', language=lang)}): {len(individual_requests)}\n"
                for req in individual_requests[:3]:
                    text += f"   • #{req.request_number} - {req.category}\n"
                if len(individual_requests) > 3:
                    text += f"   • {get_text('shifts.handlers.and_more', language=lang).format(count=len(individual_requests) - 3)}...\n"
                text += "\n"

            text += f"ℹ️ <i>{get_text('shifts.handlers.duty_requests_info', language=lang)}\n"
            text += f"{get_text('shifts.handlers.personal_requests_info', language=lang)}</i>\n\n"
        else:
            text += f"✅ <b>{get_text('shifts.handlers.no_active_requests', language=lang)}</b>\n\n"

        text += get_text("shifts.handlers.confirm_end_shift", language=lang)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=get_text("shifts.handlers.btn_yes_end", language=lang), callback_data=f"shift_end_confirm_yes:{shift_id}"),
                InlineKeyboardButton(text=get_text("shifts.handlers.btn_cancel", language=lang), callback_data="end_shift_cancel")
            ]
        ])

        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка показа деталей смены: {e}")
        from uk_management_bot.utils.safe_localization import safe_get_text
        await message.answer(safe_get_text("errors.unknown_error", language=lang))


@router.callback_query(F.data.startswith("end_shift_select:"))
async def handle_shift_selection(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Обработка выбора конкретной смены для завершения"""
    lang = "ru"  # A6-P3-21 (как в PR #334): except не ходит в БД — сессия закрыта/aborted
    try:
        shift_id = int(callback.data.split(":")[1])
        lang = await run_db(lambda s: _lang_by_tg(s, callback.from_user.id), db=_db)
        await show_shift_end_details(callback.message, shift_id, lang, _db=_db)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка выбора смены: {e}")
        await callback.answer(get_text("shifts.error_selecting_shift", language=lang), show_alert=True)


@router.callback_query(F.data == "end_shift_cancel")
async def handle_end_shift_cancel(callback: CallbackQuery, language: str = "ru"):
    """Отмена завершения смены"""
    try:
        lang = language
        await callback.message.edit_text(get_text("shifts.handlers.shift_end_cancelled", language=lang))
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка отмены: {e}")
        await callback.answer()


@router.callback_query(F.data.startswith("shift_end_confirm_yes:"))
async def end_shift_yes_with_id(callback: CallbackQuery, user_status: str | None = None, language: str = "ru", *, _db=None):
    """Подтверждение завершения конкретной смены"""
    if user_status == "pending":
        try:
            await callback.answer(get_text("auth.pending", language=language), show_alert=True)
        except Exception:
            await callback.answer(get_text("shifts.handlers.awaiting_approval", language=language), show_alert=True)
        return

    try:
        shift_id = int(callback.data.split(":")[1])
        lang, verdict, payload = await run_db(
            lambda s: _end_shift_by_id_unit(s, callback.from_user.id, shift_id), db=_db,
        )

        if verdict == "no_user":
            await callback.answer(get_text("shifts.handlers.user_not_found", language=lang), show_alert=True)
            return

        if verdict == "no_shift":
            await callback.answer(get_text("shifts.handlers.shift_not_found_or_ended", language=lang), show_alert=True)
            return

        await callback.message.edit_text(
            get_text("shifts.handlers.shift_ended_details", language=lang).format(
                shift_id=payload["shift_id"],
                hours=payload["hours"],
                minutes=payload["minutes"],
                end_time=fmt_datetime(payload["end_time"])
            ),
            parse_mode="HTML"
        )

        # Отправляем уведомления — сеть в async-слое, после коммита (B3-раскрой)
        try:
            from aiogram import Bot
            bot: Bot = callback.message.bot
            if payload["notify"]:
                user_tg, user_text, channel_text = payload["notify"]
                await send_to_user(bot, user_tg, user_text)
                await send_to_channel(bot, channel_text)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомлений: {e}")

        await callback.answer(get_text("shifts.handlers.shift_ended_toast", language=lang))

    except Exception as e:
        logger.error(f"Ошибка завершения смены: {e}")
        lang = language
        await callback.answer(get_text("shifts.handlers.error_ending_shift", language=lang), show_alert=True)


@router.callback_query(F.data == "shift_end_confirm_yes")
async def end_shift_yes(callback: CallbackQuery, user_status: str | None = None, language: str = "ru"):
    if user_status == "pending":
        try:
            await callback.answer(get_text("auth.pending", language=language), show_alert=True)
        except Exception:
            await callback.answer("⏳ Ожидайте одобрения администратора.", show_alert=True)
        return
    with session_scope() as db:  # ARCH-013
        service = ShiftService(db)
        result = service.end_shift(callback.from_user.id)
        lang = get_user_language(callback.from_user.id, db)
        if not result.get("success"):
            await callback.answer(result.get("message", get_text("shifts.handlers.error_generic", language=lang)), show_alert=True)
            return
        await callback.message.edit_text(get_text("shifts.handlers.shift_ended_simple", language=lang), reply_markup=None)
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
async def suggest_executor_skip(callback: CallbackQuery, language: str = "ru"):
    """Обработчик отказа от автоматического переключения роли после старта смены."""
    try:
        lang = language
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
async def end_shift_no(callback: CallbackQuery, language: str = "ru"):
    lang = language
    await callback.message.edit_text(get_text("shifts.handlers.shift_end_cancelled", language=lang), reply_markup=None)
    await callback.answer()


@router.message(F.text.in_(MY_SHIFT_TEXTS))
async def my_shift(message: Message, *, _db=None):
    """Показать текущую активную смену"""
    lang, found, start_time = await run_db(lambda s: _my_shift_unit(s, message.from_user.id), db=_db)
    if not found:
        await message.answer(get_text("shifts.no_active", language=lang), reply_markup=get_shifts_main_keyboard(language=lang))
        return
    await message.answer(
        get_text("shifts.active_shift_since", language=lang).format(start_time=fmt_time(start_time)),
        reply_markup=get_shifts_main_keyboard(language=lang),
    )


@router.message(F.text.in_(SHIFT_HISTORY_TEXTS))
async def shifts_history(message: Message, state: FSMContext, from_user_id: int = None, *, _db=None):
    """Показать историю смен.

    FS-01: `from_user_id` позволяет вызвать рендер из callback-хендлеров фильтров
    БЕЗ мутации `callback.message.from_user` (aiogram 3 `Message` — frozen Pydantic,
    присваивание бросает ValidationError → «непредвиденная ошибка»). Callback'и
    передают `callback.from_user.id` сюда явно.
    """
    user_id = from_user_id or message.from_user.id

    data = await state.get_data()
    period = data.get("my_shifts_period", "all")
    status = data.get("my_shifts_status", "all")
    page = int(data.get("my_shifts_page", 1))

    lang, shifts = await run_db(
        lambda s: _shifts_history_unit(s, user_id, period, status), db=_db,
    )
    per_page = 5
    total_pages = max(1, (len(shifts) + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages
    start = (page - 1) * per_page
    end = start + per_page
    page_items = shifts[start:end]

    if not page_items:
        text = get_text("shifts.shift_history_empty", language=lang)
    else:
        lines = [get_text("shifts.shift_history", language=lang) + ":"]
        for s in page_items:
            end_time = fmt_datetime(s.end_time) if s.end_time else "—"
            lines.append(f"- {fmt_datetime(s.start_time)} → {end_time} [{s.status}]")
        text = "\n".join(lines)

    filters_kb = get_shifts_filters_inline(period=period, status=status)
    pagination_kb = get_pagination_inline(page, total_pages)
    combined = type(pagination_kb)(inline_keyboard=filters_kb.inline_keyboard + pagination_kb.inline_keyboard)

    await state.update_data(my_shifts_page=page)
    await message.answer(text, reply_markup=combined)


@router.callback_query(F.data.startswith("shifts_page_"))
async def shifts_history_page(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    page_str = callback.data.replace("shifts_page_", "")
    if page_str == "current":
        await callback.answer()
        return
    try:
        page = int(page_str)
    except ValueError:
        lang = language
        await callback.answer(get_text("shifts.handlers.invalid_page", language=lang), show_alert=True)
        return
    await state.update_data(my_shifts_page=page)
    # FS-01: перерисовать через message flow, передав id явно (Message — frozen).
    await shifts_history(callback.message, state, from_user_id=callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data.startswith("shifts_period_"))
async def shifts_filter_period(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    value = callback.data.replace("shifts_period_", "")
    await state.update_data(my_shifts_period=value, my_shifts_page=1)
    await shifts_history(callback.message, state, from_user_id=callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data.startswith("shifts_status_"))
async def shifts_filter_status(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    value = callback.data.replace("shifts_status_", "")
    await state.update_data(my_shifts_status=value, my_shifts_page=1)
    await shifts_history(callback.message, state, from_user_id=callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data == "shifts_filters_reset")
async def shifts_filters_reset(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    await state.update_data(my_shifts_status="all", my_shifts_period="all", my_shifts_page=1)
    await shifts_history(callback.message, state, from_user_id=callback.from_user.id)
    lang = language
    await callback.answer(get_text("shifts.handlers.filters_reset", language=lang))


@router.message(F.text.in_(ACTIVE_SHIFTS_BUTTON_TEXTS))
async def manager_active_shifts(message: Message, state: FSMContext, language: str = "ru"):
    # Здесь предполагается, что проверка роли происходит отдельно (например, через middleware)
    with session_scope() as db:  # ARCH-013
        service = ShiftService(db)
        shifts = service.list_shifts(status="active")
        if not shifts:
            from uk_management_bot.utils.safe_localization import safe_get_text
            lang = language
            await message.answer(safe_get_text("shifts.no_active_shifts", language=lang))
            return
        from uk_management_bot.utils.safe_localization import safe_get_text
        lang = language
        lines = [safe_get_text("shifts.active_shifts_list", language=lang, default="Активные смены:")]
        for s in shifts[:10]:
            lines.append(f"- user_id={s.user_id} с {fmt_datetime(s.start_time)}")
        await message.answer("\n".join(lines))


@router.callback_query(F.data.startswith("force_end_shift_"))
async def force_end_shift(callback: CallbackQuery, language: str = "ru"):
    with session_scope() as db:  # ARCH-013
        service = ShiftService(db)
        try:
            target_tg = int(callback.data.replace("force_end_shift_", ""))
        except ValueError:
            lang = language
            await callback.answer(get_text("shifts.handlers.invalid_data", language=lang), show_alert=True)
            return
        lang = language
        result = service.force_end_shift(callback.from_user.id, target_tg)
        if not result.get("success"):
            await callback.answer(result.get("message", get_text("shifts.handlers.error_generic", language=lang)), show_alert=True)
            return
        await callback.answer(get_text("shifts.handlers.shift_ended_by_manager", language=lang))


