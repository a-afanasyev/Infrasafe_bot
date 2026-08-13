"""DTO и sync unit-of-work «Мои смены» (AUD3-37, вариант (б), волна B1).

AUD5-ARCH-3 (волна 7): файл — часть пакета ``my_shifts`` (разбит плоский
Router-файл); здесь живут константа ``MY_SHIFTS_TEXTS``, DTO и sync-юниты,
хендлеры — в соседних под-модулях. Код перенесён 1:1 из handlers/my_shifts.py.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_transfer import ShiftTransfer
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.datetime_utils import utc_now
# ARCH-116: показ и дневные бакеты — в бизнес-зоне (БД остаётся UTC).
from uk_management_bot.utils.business_time import (
    business_days_window,
    business_today,
)
from sqlalchemy import and_, or_
# Single Source of Truth for button texts - TASK 17
from uk_management_bot.utils.button_texts import get_my_shifts_texts

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
    # BUG-142: честный count() вместо len(limit(N).all()) — иначе при >10
    # смен / >5 передач цифры в тексте меню занижались.
    active_count = db.query(Shift).filter(
        Shift.user_id == user_id,
        Shift.status.in_(['planned', 'active'])
    ).count()

    transfers_count = db.query(ShiftTransfer).filter(
        or_(
            ShiftTransfer.from_executor_id == user_id,
            ShiftTransfer.to_executor_id == user_id
        )
    ).count()

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
