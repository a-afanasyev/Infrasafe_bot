"""
Detailed shift interface ("📋 Мои смены") — schedule, stats, time tracking.

Uses: Shift.planned_start_time, Shift.planned_end_time (planned times)
Related: shifts.py handles the operational menu ("🔄 Смена")

AUD3-37 (вариант (б), волна B1): DB-фаза каждого хендлера — цельный sync
unit-of-work (`_load_*`/`_start_*`/`_end_*` ниже), исполняемый в worker-потоке
через ``run_db``. Сессия живёт только внутри юнита; наружу выходят DTO
(``_ShiftRow``/``_TransferRow``) — рендеринг и клавиатуры работают по ним
duck-typed. Хендлеры НЕ объявляют параметр ``db``: иначе aiogram DI снова
инъецировал бы middleware-сессию, и запрос исполнялся бы на event loop
(гейт: tests/services/test_aud337_async_handlers_gate.py). Тестовый seam —
keyword-only ``_db`` (aiogram это имя не инъецирует: ключа "_db" в data нет),
с ним юнит исполняется синхронно на переданной сессии.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import run_db
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_transfer import ShiftTransfer
from uk_management_bot.database.models.user import User
from uk_management_bot.keyboards.my_shifts import (
    get_my_shifts_menu,
    get_shift_list_keyboard,
    get_shift_actions_keyboard
)
from uk_management_bot.keyboards.shift_transfer import (
    shift_selection_keyboard,
    transfers_list_keyboard
)
from uk_management_bot.states.my_shifts import MyShiftsStates
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.datetime_utils import utc_now
# ARCH-116: показ и дневные бакеты — в бизнес-зоне (БД остаётся UTC).
from uk_management_bot.utils.business_time import (
    business_date_of,
    business_days_window,
    business_today,
    fmt_date,
    fmt_day_month,
    fmt_time,
)
from sqlalchemy import and_, or_
# Single Source of Truth for button texts - TASK 17
from uk_management_bot.utils.button_texts import get_my_shifts_texts
import logging

logger = logging.getLogger(__name__)
router = Router()

# Константа для фильтрации сообщений "Мои смены"
MY_SHIFTS_TEXTS = get_my_shifts_texts()


# ==========================================================================
# DTO: всё, что рендеру и клавиатурам нужно от Shift/ShiftTransfer.
# Имена полей совпадают с ORM-атрибутами — клавиатуры (get_shift_list_keyboard,
# get_shift_actions_keyboard, shift_selection_keyboard, transfers_list_keyboard)
# работают по ним duck-typed, их код не менялся.
# ==========================================================================

@dataclass(frozen=True)
class _ShiftRow:
    id: int
    status: str
    planned_start_time: Optional[datetime]
    planned_end_time: Optional[datetime]
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    specialization_focus: Optional[list]
    geographic_zone: Optional[str]
    coverage_areas: Optional[list]
    max_requests: Optional[int]
    current_request_count: Optional[int]
    completed_requests: Optional[int]
    average_completion_time: Optional[float]
    efficiency_score: Optional[float]
    notes: Optional[str]


def _shift_row(shift: Shift) -> _ShiftRow:
    return _ShiftRow(
        id=shift.id,
        status=shift.status,
        planned_start_time=shift.planned_start_time,
        planned_end_time=shift.planned_end_time,
        start_time=shift.start_time,
        end_time=shift.end_time,
        specialization_focus=shift.specialization_focus,
        geographic_zone=shift.geographic_zone,
        coverage_areas=shift.coverage_areas,
        max_requests=shift.max_requests,
        current_request_count=shift.current_request_count,
        completed_requests=shift.completed_requests,
        average_completion_time=shift.average_completion_time,
        efficiency_score=shift.efficiency_score,
        notes=shift.notes,
    )


@dataclass(frozen=True)
class _TransferRow:
    id: int
    status: str
    created_at: Optional[datetime]
    from_executor_id: Optional[int]
    to_executor_id: Optional[int]


def _transfer_row(transfer: ShiftTransfer) -> _TransferRow:
    return _TransferRow(
        id=transfer.id,
        status=transfer.status,
        created_at=transfer.created_at,
        from_executor_id=transfer.from_executor_id,
        to_executor_id=transfer.to_executor_id,
    )


# ==========================================================================
# Sync unit-of-work: вся работа с сессией — только здесь (исполняется в
# worker-потоке через run_db). BUG-BOT-005/007: Shift.user_id — FK на users.id
# (внутренний DB id), а не telegram_id, поэтому юниты резолвят user сами;
# ``user_db_id`` — от DI-инъецированного user, чтобы не повторять запрос.
# ==========================================================================

def _resolve_user_id(db, telegram_id: int, user_db_id: Optional[int]) -> Optional[int]:
    if user_db_id is not None:
        return user_db_id
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    return user.id if user else None


def _load_current_shifts(db, telegram_id: int, user_db_id: Optional[int]):
    """-> (user_found, today, [_ShiftRow]) — смены на сегодня/завтра.

    ``today`` возвращается наружу: рендер обязан метить «сегодня/завтра» ТЕМ ЖЕ
    днём, которым построено окно запроса — повторный business_today() в хендлере
    на роллковере бизнес-суток дал бы метки, рассинхронные с выборкой.
    """
    today = business_today()
    user_id = _resolve_user_id(db, telegram_id, user_db_id)
    if user_id is None:
        return False, today, []
    tomorrow = today + timedelta(days=1)

    # FS-06: ad-hoc смены живут на start_time (planned_start_time=NULL) —
    # фильтр/сортировка по «эффективному времени», иначе «🔥 Текущие смены»
    # их не видят (расхождение с «ℹ️ Моя смена»).
    from uk_management_bot.utils.shifts import effective_shift_time
    _eff = effective_shift_time()
    # ARCH-116: окно диапазоном вместо func.date(_eff) — бакет дня считается
    # в бизнес-зоне, а не в зоне сессии БД, и индекс по колонке остаётся живым.
    window_start, window_end = business_days_window(today, tomorrow)
    shifts = db.query(Shift).filter(
        and_(
            Shift.user_id == user_id,
            _eff >= window_start,
            _eff < window_end,
            Shift.status.in_(['planned', 'active'])
        )
    ).order_by(_eff).all()
    return True, today, [_shift_row(s) for s in shifts]


def _load_week_shifts(db, telegram_id: int, user_db_id: Optional[int], is_privileged: bool):
    """-> (user_found, today, [_ShiftRow]) — смены текущей недели.

    ``today`` наружу по той же причине, что в _load_current_shifts: заголовок
    периода и маркер «🔥 сегодня» обязаны совпадать с окном запроса.
    """
    today = business_today()
    user_id = _resolve_user_id(db, telegram_id, user_db_id)
    if user_id is None:
        return False, today, []
    start_of_week = today - timedelta(days=today.weekday())  # Понедельник
    end_of_week = start_of_week + timedelta(days=6)  # Воскресенье

    week_start_utc, week_end_utc = business_days_window(start_of_week, end_of_week)
    filters = [
        Shift.planned_start_time >= week_start_utc,
        Shift.planned_start_time < week_end_utc,
        Shift.status.in_(['planned', 'active', 'completed']),
    ]
    # Executor видит только свои смены; manager/admin — все (BUG-BOT-005).
    if not is_privileged:
        filters.append(Shift.user_id == user_id)

    shifts = db.query(Shift).filter(and_(*filters)).order_by(Shift.planned_start_time).all()
    return True, today, [_shift_row(s) for s in shifts]


def _load_shift_details(db, telegram_id: int, user_db_id: Optional[int], shift_id: int):
    """-> (user_found, _ShiftRow | None) — смена принадлежит исполнителю."""
    user_id = _resolve_user_id(db, telegram_id, user_db_id)
    if user_id is None:
        return False, None

    shift = db.query(Shift).filter(
        and_(Shift.id == shift_id, Shift.user_id == user_id)
    ).first()
    return True, (_shift_row(shift) if shift else None)


def _start_shift(db, telegram_id: int, user_db_id: Optional[int], shift_id: int):
    """planned → active. -> (user_found, _ShiftRow | None). Коммит внутри."""
    user_id = _resolve_user_id(db, telegram_id, user_db_id)
    if user_id is None:
        return False, None

    # with_for_update: в потоках двойной тап по кнопке даёт ДВА конкурентных
    # юнита (на event loop секция SELECT→commit была атомарна «случайно», без
    # await внутри). Лок строки заставляет второй юнит дождаться commit первого
    # и увидеть status != planned → честный «уже начата». На sqlite — no-op.
    shift = db.query(Shift).filter(
        and_(
            Shift.id == shift_id,
            Shift.user_id == user_id,
            Shift.status == 'planned'
        )
    ).with_for_update().first()
    if not shift:
        return True, None

    shift.status = 'active'
    shift.start_time = utc_now()
    db.commit()
    return True, _shift_row(shift)


def _end_shift(db, telegram_id: int, user_db_id: Optional[int], shift_id: int):
    """active → completed. -> (user_found, dict | None). Коммит внутри."""
    user_id = _resolve_user_id(db, telegram_id, user_db_id)
    if user_id is None:
        return False, None

    # with_for_update: та же защита от двойного тапа, что в _start_shift.
    shift = db.query(Shift).filter(
        and_(
            Shift.id == shift_id,
            Shift.user_id == user_id,
            Shift.status == 'active'
        )
    ).with_for_update().first()
    if not shift:
        return True, None

    end_time = utc_now()
    shift.status = 'completed'
    shift.end_time = end_time

    # Рассчитываем фактическую длительность. Shift.start_time — timestamptz,
    # end_time тоже aware UTC — вычитание напрямую (AUD5-CODE-3).
    if shift.start_time:
        actual_duration = (end_time - shift.start_time).total_seconds() / 3600
    else:
        actual_duration = 0

    db.commit()
    return True, {
        "end_time": end_time,
        "actual_duration": actual_duration,
        "request_count": shift.current_request_count or 0,
    }


def _load_shift_history(db, telegram_id: int, user_db_id: Optional[int], is_privileged: bool):
    """-> (user_found, [_ShiftRow]) — завершённые/отменённые за 30 дней."""
    user_id = _resolve_user_id(db, telegram_id, user_db_id)
    if user_id is None:
        return False, []

    end_date = business_today()
    start_date = end_date - timedelta(days=30)

    # FS-07: история через «эффективное время» (ad-hoc на start_time,
    # planned_start_time=NULL) — иначе завершённые ad-hoc смены теряются и
    # «История» расходится с «🔄 Смена → 📜 История» (та на start_time).
    from uk_management_bot.utils.shifts import effective_shift_time
    _eff = effective_shift_time()
    history_start_utc, history_end_utc = business_days_window(start_date, end_date)
    filters = [
        _eff >= history_start_utc,
        _eff < history_end_utc,
        Shift.status.in_(['completed', 'cancelled']),
    ]
    if not is_privileged:
        filters.append(Shift.user_id == user_id)

    shifts = db.query(Shift).filter(and_(*filters)).order_by(_eff.desc()).limit(20).all()
    return True, [_shift_row(s) for s in shifts]


def _load_transfer_menu_counts(db, telegram_id: int):
    """-> (active_count, transfers_count) | None (пользователь не найден)."""
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if user is None:
        return None
    user_id = user.id

    # FS-02: Shift.user_id / from_/to_executor_id — FK на users.id (НЕ telegram_id).
    # Окно по start_time убрано: текущая (уже идущая) active-смена тоже
    # должна быть доступна к передаче, а не только будущие planned.
    active_count = len(db.query(Shift).filter(
        Shift.user_id == user_id,
        Shift.status.in_(['planned', 'active'])
    ).order_by(Shift.start_time).limit(10).all())

    transfers_count = len(db.query(ShiftTransfer).filter(
        or_(
            ShiftTransfer.from_executor_id == user_id,
            ShiftTransfer.to_executor_id == user_id
        )
    ).order_by(ShiftTransfer.created_at.desc()).limit(5).all())

    return active_count, transfers_count


def _load_transferable_shifts(db, telegram_id: int):
    """-> [_ShiftRow] | None (пользователь не найден). FS-02: фильтр по users.id."""
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if user is None:
        return None
    user_id = user.id

    shifts = db.query(Shift).filter(
        Shift.user_id == user_id,
        Shift.status.in_(['planned', 'active'])
    ).order_by(Shift.start_time).limit(10).all()
    return [_shift_row(s) for s in shifts]


def _load_my_transfers(db, telegram_id: int):
    """-> [_TransferRow] | None (пользователь не найден)."""
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if user is None:
        return None
    user_id = user.id

    transfers = db.query(ShiftTransfer).filter(
        or_(
            ShiftTransfer.from_executor_id == user_id,
            ShiftTransfer.to_executor_id == user_id
        )
    ).order_by(ShiftTransfer.created_at.desc()).limit(10).all()
    return [_transfer_row(t) for t in transfers]


# ==========================================================================
# Handlers: только Telegram-IO и рендеринг по DTO.
# ==========================================================================

@router.message(Command("my_shifts"))
async def cmd_my_shifts(message: Message, state: FSMContext, language: str = "ru"):
    """Главное меню моих смен (БД не нужна — раньше сессия открывалась зря)."""
    try:
        lang = language

        await message.answer(
            get_text("my_shifts.handlers.main_menu", language=lang),
            reply_markup=get_my_shifts_menu(lang),
            parse_mode="HTML"
        )

        await state.set_state(MyShiftsStates.main_menu)

    except Exception as e:
        logger.error(f"Ошибка команды /my_shifts: {e}")
        await message.answer(get_text("my_shifts.handlers.error_loading", language=language))


@router.message(F.text.in_(MY_SHIFTS_TEXTS))
async def handle_my_shifts_button(message: Message, state: FSMContext, language: str = "ru"):
    """Обработчик кнопки 'Мои смены'"""
    await cmd_my_shifts(message, state, language=language)


@router.callback_query(F.data == "view_current_shifts")
@require_role(['executor'])
async def handle_current_shifts(callback: CallbackQuery, state: FSMContext, language: str = "ru",
                                user: User = None, roles: list = None, *, _db=None):
    """Просмотр текущих смен."""
    try:
        lang = language
        user_db_id = user.id if user is not None else None

        user_found, today, current_shifts = await run_db(
            lambda s: _load_current_shifts(s, callback.from_user.id, user_db_id), db=_db,
        )
        if not user_found:
            await callback.answer(get_text("my_shifts.handlers.error_occurred", language=lang), show_alert=True)
            return

        if not current_shifts:
            await callback.message.edit_text(
                get_text("my_shifts.handlers.no_current_shifts", language=lang),
                reply_markup=get_my_shifts_menu(lang),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        # Формируем список смен (today — из юнита, тот же день, что окно запроса)
        shifts_text = f"📅 <b>{get_text('my_shifts.handlers.your_current_shifts', language=lang)}</b>\n\n"

        for shift in current_shifts:
            # FS-06: ad-hoc смена не имеет planned_*; берём эффективное время.
            eff_start = shift.planned_start_time or shift.start_time
            eff_end = shift.planned_end_time or shift.end_time
            shift_date = business_date_of(eff_start)
            is_today = shift_date == today
            date_prefix = f"🔥 {get_text('my_shifts.handlers.today', language=lang)}" if is_today else f"📅 {get_text('my_shifts.handlers.tomorrow', language=lang)}"

            start_time = fmt_time(eff_start)
            end_time = fmt_time(eff_end) if eff_end else "?"

            status_emoji = {
                'planned': '⏱️',
                'active': '🔴',
                'completed': '✅'
            }.get(shift.status, '⚪')

            specializations = ""
            if shift.specialization_focus:
                specializations = f"🔧 {', '.join(shift.specialization_focus[:2])}"
                if len(shift.specialization_focus) > 2:
                    specializations += f" (+{len(shift.specialization_focus)-2})"

            geographic_zone = ""
            if shift.geographic_zone:
                geographic_zone = f"🗺️ {shift.geographic_zone}"

            shifts_text += (
                f"{status_emoji} <b>{date_prefix}</b>\n"
                f"⏰ {start_time} - {end_time}\n"
            )

            if specializations:
                shifts_text += f"{specializations}\n"
            if geographic_zone:
                shifts_text += f"{geographic_zone}\n"

            # Информация о заявках
            if shift.max_requests:
                current_requests = shift.current_request_count or 0
                shifts_text += f"📋 {get_text('my_shifts.handlers.requests_label', language=lang)}: {current_requests}/{shift.max_requests}\n"

            shifts_text += "\n"

        await callback.message.edit_text(
            shifts_text,
            reply_markup=get_shift_list_keyboard(current_shifts, lang),
            parse_mode="HTML"
        )

        await state.set_state(MyShiftsStates.viewing_shifts)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка просмотра текущих смен: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_occurred", language=language), show_alert=True)


@router.callback_query(F.data == "view_week_schedule")
@require_role(['admin', 'manager', 'executor'])
async def handle_week_schedule(callback: CallbackQuery, state: FSMContext, language: str = "ru",
                               roles: list = None, user: User = None, *, _db=None):
    """Просмотр расписания на неделю.

    BUG-BOT-005: разрешён доступ executor + manager + admin. Для executor query
    фильтруется по его собственному `Shift.user_id`. Manager/admin — видит все смены.
    """
    try:
        lang = language
        user_db_id = user.id if user is not None else None
        is_privileged = bool(roles) and any(r in ('admin', 'manager') for r in roles)

        user_found, today, week_shifts = await run_db(
            lambda s: _load_week_shifts(s, callback.from_user.id, user_db_id, is_privileged), db=_db,
        )
        if not user_found:
            await callback.answer(get_text("my_shifts.handlers.error_occurred", language=lang), show_alert=True)
            return

        # today — из юнита: заголовок периода совпадает с окном запроса.
        start_of_week = today - timedelta(days=today.weekday())  # Понедельник
        end_of_week = start_of_week + timedelta(days=6)  # Воскресенье

        # Группируем по дням недели
        days_of_week = [
            get_text("my_shifts.handlers.monday", language=lang),
            get_text("my_shifts.handlers.tuesday", language=lang),
            get_text("my_shifts.handlers.wednesday", language=lang),
            get_text("my_shifts.handlers.thursday", language=lang),
            get_text("my_shifts.handlers.friday", language=lang),
            get_text("my_shifts.handlers.saturday", language=lang),
            get_text("my_shifts.handlers.sunday", language=lang),
        ]
        week_schedule = {day: [] for day in days_of_week}

        for shift in week_shifts:
            # ARCH-116: день недели — по бизнес-дате, иначе смена после местной
            # полуночи попадала в предыдущий день.
            day_name = days_of_week[business_date_of(shift.planned_start_time).weekday()]
            week_schedule[day_name].append(shift)

        # Формируем текст расписания
        schedule_text = (
            f"📆 <b>{get_text('my_shifts.handlers.week_schedule', language=lang)}</b>\n"
            f"<b>{get_text('my_shifts.handlers.period', language=lang)}:</b> {fmt_day_month(start_of_week)} - {fmt_date(end_of_week)}\n\n"
        )

        total_shifts = len(week_shifts)
        total_hours = 0

        for day_name, day_shifts in week_schedule.items():
            day_date = start_of_week + timedelta(days=days_of_week.index(day_name))
            is_today = day_date == today
            day_prefix = "🔥" if is_today else "📅"

            if day_shifts:
                schedule_text += f"{day_prefix} <b>{day_name}</b> ({fmt_day_month(day_date)})\n"

                for shift in day_shifts:
                    start_time = fmt_time(shift.planned_start_time)
                    end_time = fmt_time(shift.planned_end_time) if shift.planned_end_time else "?"

                    status_emoji = {
                        'planned': '⏱️',
                        'active': '🔴',
                        'completed': '✅'
                    }.get(shift.status, '⚪')

                    duration = ""
                    if shift.planned_start_time and shift.planned_end_time:
                        hours = (shift.planned_end_time - shift.planned_start_time).total_seconds() / 3600
                        total_hours += hours
                        duration = f" ({hours:.0f}ч)"

                    schedule_text += f"  {status_emoji} {start_time}-{end_time}{duration}\n"

                schedule_text += "\n"
            else:
                schedule_text += f"📅 <b>{day_name}</b> ({fmt_day_month(day_date)}): {get_text('my_shifts.handlers.day_off', language=lang)}\n\n"

        # Итоговая статистика
        schedule_text += (
            f"📊 <b>{get_text('my_shifts.handlers.total', language=lang)}:</b>\n"
            f"• {get_text('my_shifts.handlers.shifts_count', language=lang)}: {total_shifts}\n"
            f"• {get_text('my_shifts.handlers.hours_count', language=lang)}: {total_hours:.1f}\n"
        )

        await callback.message.edit_text(
            schedule_text,
            reply_markup=get_my_shifts_menu(lang),
            parse_mode="HTML"
        )

        await state.set_state(MyShiftsStates.main_menu)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка просмотра недельного расписания: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_occurred", language=language), show_alert=True)


@router.callback_query(F.data.startswith("shift_details:"))
@require_role(['executor'])
async def handle_shift_details(callback: CallbackQuery, state: FSMContext, language: str = "ru",
                               user: User = None, roles: list = None, *, _db=None):
    """Подробная информация о смене.

    BUG-BOT-007: Shift.user_id — FK на users.id (внутренний DB id), а не
    telegram_id. Без user/roles в сигнатуре aiogram DI не передавал roles, и
    require_role отклонял исполнителя на ЕГО ЖЕ смене («нет прав доступа»).
    """
    try:
        shift_id = int(callback.data.split(':')[1])
        lang = language
        user_db_id = user.id if user is not None else None

        user_found, shift = await run_db(
            lambda s: _load_shift_details(s, callback.from_user.id, user_db_id, shift_id), db=_db,
        )
        if not user_found:
            await callback.answer(get_text("my_shifts.handlers.error_occurred", language=lang), show_alert=True)
            return
        if not shift:
            await callback.answer(get_text("my_shifts.handlers.shift_not_found", language=language), show_alert=True)
            return

        # Формируем подробную информацию
        # FS-06: ad-hoc смена без planned_* (достижима из «Текущие смены» →
        # shift_details) → эффективное время, иначе planned_start_time.date() крах.
        eff_start = shift.planned_start_time or shift.start_time
        eff_end = shift.planned_end_time or shift.end_time
        shift_date = business_date_of(eff_start)
        today = business_today()
        is_today = shift_date == today
        is_tomorrow = shift_date == today + timedelta(days=1)

        date_text = f"🔥 {get_text('my_shifts.handlers.today', language=lang)}" if is_today else f"📅 {get_text('my_shifts.handlers.tomorrow', language=lang)}" if is_tomorrow else fmt_date(shift_date)

        start_time = fmt_time(eff_start)
        end_time = fmt_time(eff_end) if eff_end else "?"

        status_text = {
            'planned': f"⏱️ {get_text('my_shifts.handlers.status_planned', language=lang)}",
            'active': f"🔴 {get_text('my_shifts.handlers.status_active', language=lang)}",
            'completed': f"✅ {get_text('my_shifts.handlers.status_completed', language=lang)}",
            'cancelled': f"❌ {get_text('my_shifts.handlers.status_cancelled', language=lang)}"
        }.get(shift.status, f"⚪ {get_text('my_shifts.handlers.status_unknown', language=lang)}")

        details_text = (
            f"📋 <b>{get_text('my_shifts.handlers.shift_details', language=lang)}</b>\n\n"
            f"<b>{get_text('my_shifts.handlers.date_label', language=lang)}:</b> {date_text}\n"
            f"<b>{get_text('my_shifts.handlers.time_label', language=lang)}:</b> {start_time} - {end_time}\n"
            f"<b>{get_text('my_shifts.handlers.status_label', language=lang)}:</b> {status_text}\n\n"
        )

        # Длительность
        if shift.planned_start_time and shift.planned_end_time:
            duration = (shift.planned_end_time - shift.planned_start_time).total_seconds() / 3600
            details_text += f"<b>{get_text('my_shifts.handlers.duration_label', language=lang)}:</b> {duration:.1f} {get_text('my_shifts.handlers.hours_word', language=lang)}\n"

        # Специализации
        if shift.specialization_focus:
            specializations = ', '.join(shift.specialization_focus)
            details_text += f"<b>{get_text('my_shifts.handlers.specializations_label', language=lang)}:</b> {specializations}\n"

        # Географическая зона
        if shift.geographic_zone:
            details_text += f"<b>{get_text('my_shifts.handlers.zone_label', language=lang)}:</b> {shift.geographic_zone}\n"

        # Области покрытия
        if shift.coverage_areas:
            coverage = ', '.join(shift.coverage_areas)
            details_text += f"<b>{get_text('my_shifts.handlers.areas_label', language=lang)}:</b> {coverage}\n"

        details_text += "\n"

        # Заявки
        current_requests = shift.current_request_count or 0
        max_requests = shift.max_requests or 0

        if max_requests > 0:
            details_text += f"<b>📋 {get_text('my_shifts.handlers.requests_label', language=lang)}:</b> {current_requests}/{max_requests}\n"

            if current_requests > 0:
                progress = (current_requests / max_requests) * 100
                progress_bar = "🟩" * int(progress // 20) + "⬜" * (5 - int(progress // 20))
                details_text += f"{get_text('my_shifts.handlers.workload', language=lang)}: {progress_bar} {progress:.0f}%\n"

        # Статистика (если есть)
        if shift.completed_requests:
            details_text += f"<b>{get_text('my_shifts.handlers.completed_requests', language=lang)}:</b> {shift.completed_requests}\n"

        if shift.average_completion_time:
            avg_time = shift.average_completion_time
            details_text += f"<b>{get_text('my_shifts.handlers.average_time', language=lang)}:</b> {avg_time:.1f} {get_text('my_shifts.handlers.minutes_word', language=lang)}\n"

        if shift.efficiency_score:
            score = shift.efficiency_score
            details_text += f"<b>{get_text('my_shifts.handlers.efficiency', language=lang)}:</b> {score:.1f}%\n"

        # Заметки
        if shift.notes:
            details_text += f"\n<b>{get_text('my_shifts.handlers.notes_label', language=lang)}:</b>\n{shift.notes}"

        await callback.message.edit_text(
            details_text,
            reply_markup=get_shift_actions_keyboard(shift, lang),
            parse_mode="HTML"
        )

        await state.update_data(current_shift_id=shift_id)
        await state.set_state(MyShiftsStates.viewing_shift_details)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка просмотра деталей смены: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_occurred", language=language), show_alert=True)


@router.callback_query(F.data == "start_shift")
@require_role(['executor'])
async def handle_start_shift(callback: CallbackQuery, state: FSMContext, language: str = "ru",
                             user: User = None, roles: list = None, *, _db=None):
    """Начать смену"""
    try:
        lang = language
        data = await state.get_data()
        shift_id = data.get('current_shift_id')

        if not shift_id:
            await callback.answer(get_text("my_shifts.handlers.shift_not_selected", language=lang), show_alert=True)
            return

        user_db_id = user.id if user is not None else None
        user_found, shift = await run_db(
            lambda s: _start_shift(s, callback.from_user.id, user_db_id, shift_id), db=_db,
        )
        if not user_found:
            await callback.answer(get_text("my_shifts.handlers.error_occurred", language=lang), show_alert=True)
            return
        if not shift:
            await callback.answer(get_text("my_shifts.handlers.shift_not_found_or_started", language=lang), show_alert=True)
            return

        await callback.message.edit_text(
            get_text("my_shifts.handlers.shift_started", language=lang).format(
                start_time=fmt_time(shift.start_time)
            ),
            reply_markup=get_shift_actions_keyboard(shift, lang),
            parse_mode="HTML"
        )

        await callback.answer(get_text("my_shifts.handlers.shift_started_toast", language=lang))

    except Exception as e:
        logger.error(f"Ошибка начала смены: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_occurred", language=language), show_alert=True)


@router.callback_query(F.data == "end_shift")
@require_role(['executor'])
async def handle_end_shift(callback: CallbackQuery, state: FSMContext, language: str = "ru",
                           user: User = None, roles: list = None, *, _db=None):
    """Завершить смену"""
    try:
        lang = language
        data = await state.get_data()
        shift_id = data.get('current_shift_id')

        if not shift_id:
            await callback.answer(get_text("my_shifts.handlers.shift_not_selected", language=lang), show_alert=True)
            return

        user_db_id = user.id if user is not None else None
        user_found, summary = await run_db(
            lambda s: _end_shift(s, callback.from_user.id, user_db_id, shift_id), db=_db,
        )
        if not user_found:
            await callback.answer(get_text("my_shifts.handlers.error_occurred", language=lang), show_alert=True)
            return
        if summary is None:
            await callback.answer(get_text("my_shifts.handlers.shift_not_found_or_inactive", language=lang), show_alert=True)
            return

        # Формируем итоги смены
        summary_text = get_text("my_shifts.handlers.shift_ended_summary", language=lang).format(
            end_time=fmt_time(summary["end_time"]),
            actual_duration=f"{summary['actual_duration']:.1f}",
            request_count=summary["request_count"]
        )

        await callback.message.edit_text(
            summary_text,
            reply_markup=get_my_shifts_menu(lang),
            parse_mode="HTML"
        )

        await state.set_state(MyShiftsStates.main_menu)
        await callback.answer(get_text("my_shifts.handlers.shift_ended_toast", language=lang))

    except Exception as e:
        logger.error(f"Ошибка завершения смены: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_occurred", language=language), show_alert=True)


@router.callback_query(F.data == "shift_history")
@require_role(['admin', 'manager', 'executor'])
async def handle_shift_history(callback: CallbackQuery, state: FSMContext, language: str = "ru",
                               roles: list = None, user: User = None, *, _db=None):
    """История смен.

    BUG-BOT-005: разрешён доступ executor + manager + admin. Для executor query
    фильтруется по `Shift.user_id == user.id` (внутренний DB id, не telegram_id).
    Manager/admin — видит все смены.
    """
    try:
        lang = language
        user_db_id = user.id if user is not None else None
        is_privileged = bool(roles) and any(r in ('admin', 'manager') for r in roles)

        user_found, history_shifts = await run_db(
            lambda s: _load_shift_history(s, callback.from_user.id, user_db_id, is_privileged), db=_db,
        )
        if not user_found:
            await callback.answer(get_text("my_shifts.handlers.error_occurred", language=lang), show_alert=True)
            return

        if not history_shifts:
            await callback.message.edit_text(
                get_text("my_shifts.handlers.no_shift_history", language=lang),
                reply_markup=get_my_shifts_menu(lang),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        # Статистика
        completed_shifts = [s for s in history_shifts if s.status == 'completed']
        cancelled_shifts = [s for s in history_shifts if s.status == 'cancelled']

        total_hours = 0
        total_requests = 0

        for shift in completed_shifts:
            if shift.start_time and shift.end_time:
                hours = (shift.end_time - shift.start_time).total_seconds() / 3600
                total_hours += hours

            if shift.completed_requests:
                total_requests += shift.completed_requests

        # Формируем текст истории
        history_text = get_text("my_shifts.handlers.shift_history_header", language=lang).format(
            completed_count=len(completed_shifts),
            cancelled_count=len(cancelled_shifts),
            total_hours=f"{total_hours:.1f}",
            total_requests=total_requests
        ) + "\n"

        for shift in history_shifts[:10]:  # Показываем последние 10
            # FS-07: ad-hoc смена без planned_* → эффективное время.
            eff_start = shift.planned_start_time or shift.start_time
            shift_date = fmt_day_month(eff_start)
            start_time = fmt_time(eff_start)

            status_emoji = {
                'completed': '✅',
                'cancelled': '❌'
            }.get(shift.status, '⚪')

            duration = ""
            if shift.start_time and shift.end_time:
                hours = (shift.end_time - shift.start_time).total_seconds() / 3600
                duration = f" ({hours:.1f}ч)"

            requests = ""
            if shift.completed_requests:
                requests = f" • {shift.completed_requests} {get_text('my_shifts.handlers.requests_word', language=lang)}"

            history_text += f"{status_emoji} {shift_date} {start_time}{duration}{requests}\n"

        if len(history_shifts) > 10:
            history_text += f"\n... {get_text('my_shifts.handlers.and_more_shifts', language=lang).format(count=len(history_shifts) - 10)}"

        await callback.message.edit_text(
            history_text,
            reply_markup=get_my_shifts_menu(lang),
            parse_mode="HTML"
        )

        await state.set_state(MyShiftsStates.main_menu)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка просмотра истории смен: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_occurred", language=language), show_alert=True)


@router.callback_query(F.data == "back_to_my_shifts")
async def handle_back_to_my_shifts(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Возврат к главному меню моих смен"""
    try:
        lang = language

        await callback.message.edit_text(
            get_text("my_shifts.handlers.main_menu", language=lang),
            reply_markup=get_my_shifts_menu(lang),
            parse_mode="HTML"
        )

        await state.set_state(MyShiftsStates.main_menu)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка возврата к моим сменам: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_occurred", language=language), show_alert=True)


# ========== ИНТЕГРАЦИЯ С ПЕРЕДАЧЕЙ СМЕН ==========

@router.callback_query(F.data == "shift_transfer_menu")
async def handle_shift_transfer_menu(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработка меню передачи смен (BUG-BOT-006)."""
    try:
        user_lang = language

        counts = await run_db(
            lambda s: _load_transfer_menu_counts(s, callback.from_user.id), db=_db,
        )
        if counts is None:
            await callback.answer(get_text("my_shifts.handlers.user_not_found", language=user_lang), show_alert=True)
            return

        active_shifts_count, transfers_count = counts

        menu_text = get_text("my_shifts.handlers.transfer_menu", language=user_lang).format(
            active_shifts_count=active_shifts_count,
            transfers_count=transfers_count
        )

        # Создаем клавиатуру меню передач
        keyboard = []

        if active_shifts_count:
            keyboard.append([InlineKeyboardButton(
                text=get_text("my_shifts.handlers.btn_transfer_shift", language=user_lang),
                callback_data="initiate_transfer"
            )])

        if transfers_count:
            keyboard.append([InlineKeyboardButton(
                text=get_text("my_shifts.handlers.btn_my_transfers", language=user_lang),
                callback_data="view_my_transfers"
            )])

        # Кнопка назад (убрана по запросу пользователя)

        await callback.message.edit_text(
            menu_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Ошибка меню передачи смен: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_loading_menu", language=user_lang), show_alert=True)


@router.callback_query(F.data == "initiate_transfer")
async def handle_initiate_transfer(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Инициация передачи смены через меню 'Мои смены'"""
    try:
        user_lang = language

        active_shifts = await run_db(
            lambda s: _load_transferable_shifts(s, callback.from_user.id), db=_db,
        )
        if active_shifts is None:
            # Пользователь не найден — раньше это давало AttributeError и ту же
            # ветку с error_initiating_transfer; сообщение сохранено.
            await callback.answer(get_text("my_shifts.handlers.error_initiating_transfer", language=user_lang), show_alert=True)
            return

        if not active_shifts:
            await callback.answer(get_text("my_shifts.handlers.no_shifts_to_transfer", language=user_lang), show_alert=True)
            return

        # Показываем список смен для выбора
        select_text = get_text("my_shifts.handlers.select_shift_to_transfer", language=user_lang)

        await callback.message.edit_text(
            select_text,
            reply_markup=shift_selection_keyboard(active_shifts, user_lang)
        )

    except Exception as e:
        logger.error(f"Ошибка инициации передачи: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_initiating_transfer", language=user_lang), show_alert=True)


@router.callback_query(F.data == "view_my_transfers")
async def handle_view_my_transfers(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Просмотр передач пользователя"""
    try:
        user_lang = language

        my_transfers = await run_db(
            lambda s: _load_my_transfers(s, callback.from_user.id), db=_db,
        )
        if my_transfers is None:
            # Пользователь не найден — раньше AttributeError уводил в ту же
            # ветку с error_loading_transfers; сообщение сохранено.
            await callback.answer(get_text("my_shifts.handlers.error_loading_transfers", language=user_lang), show_alert=True)
            return

        if not my_transfers:
            await callback.answer(get_text("my_shifts.handlers.no_transfers", language=user_lang), show_alert=True)
            return

        view_text = get_text("my_shifts.handlers.your_transfers", language=user_lang)

        await callback.message.edit_text(
            view_text,
            reply_markup=transfers_list_keyboard(my_transfers, user_lang)
        )

    except Exception as e:
        logger.error(f"Ошибка просмотра передач: {e}")
        await callback.answer(get_text("my_shifts.handlers.error_loading_transfers", language=user_lang), show_alert=True)
