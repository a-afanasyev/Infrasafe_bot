"""BUG-142 — предсуществующие дефекты пакета handlers/my_shifts/.

  1. три transfers-хендлера не звали callback.answer() на happy path —
     спиннер на кнопке висел до телеграм-таймаута;
  2. _load_transfer_menu_counts считал len(query.limit(N).all()) —
     при >10 смен / >5 передач счётчики меню занижались;
  3. handle_current_shifts метил «завтра» любую не-«сегодня» смену — метка
     была завязана на позицию в окне, а не на фактическую дату смены.
"""
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from uk_management_bot.utils.datetime_utils import utc_now


def _make_callback():
    cb = MagicMock()
    cb.from_user.id = 4242
    cb.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    return cb


def _make_transfers_db(user, shifts_total, transfers_total,
                       shifts_capped, transfers_capped):
    """count() отдаёт полные счётчики; limit(N).all() — усечённые списки."""
    from uk_management_bot.database.models.shift import Shift
    from uk_management_bot.database.models.shift_transfer import ShiftTransfer
    from uk_management_bot.database.models.user import User

    def query_side_effect(model):
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        if model is User:
            q.first.return_value = user
        elif model is Shift:
            q.all.return_value = [MagicMock()] * shifts_capped
            q.count.return_value = shifts_total
        elif model is ShiftTransfer:
            q.all.return_value = [MagicMock()] * transfers_capped
            q.count.return_value = transfers_total
        return q

    db = MagicMock()
    db.query.side_effect = query_side_effect
    return db


def _db_user():
    user = MagicMock()
    user.id = 7
    user.telegram_id = 4242
    return user


def _plain_ack(answer_mock):
    """Был ли хотя бы один callback.answer() без текста (снятие спиннера)."""
    return any(not c.args and not c.kwargs for c in answer_mock.await_args_list)


# ── 1: callback.answer() на happy path ──────────────────────────────────────

async def test_transfer_menu_answers_callback_on_happy_path():
    from uk_management_bot.handlers.my_shifts import transfers

    cb = _make_callback()
    db = _make_transfers_db(_db_user(), 2, 1, 2, 1)

    await transfers.handle_shift_transfer_menu(cb, state=MagicMock(), language="ru", _db=db)

    cb.message.edit_text.assert_awaited_once()
    assert _plain_ack(cb.answer), "спиннер не снят: callback.answer() не вызван"


async def test_initiate_transfer_answers_callback_on_happy_path():
    from uk_management_bot.handlers.my_shifts import transfers

    cb = _make_callback()
    db = _make_transfers_db(_db_user(), 2, 1, 2, 1)

    with patch.object(transfers, "shift_selection_keyboard", return_value=MagicMock()):
        await transfers.handle_initiate_transfer(cb, state=MagicMock(), language="ru", _db=db)

    cb.message.edit_text.assert_awaited_once()
    assert _plain_ack(cb.answer), "спиннер не снят: callback.answer() не вызван"


async def test_view_my_transfers_answers_callback_on_happy_path():
    from uk_management_bot.handlers.my_shifts import transfers

    cb = _make_callback()
    db = _make_transfers_db(_db_user(), 2, 1, 2, 1)

    with patch.object(transfers, "transfers_list_keyboard", return_value=MagicMock()):
        await transfers.handle_view_my_transfers(cb, state=MagicMock(), language="ru", _db=db)

    cb.message.edit_text.assert_awaited_once()
    assert _plain_ack(cb.answer), "спиннер не снят: callback.answer() не вызван"


# ── 2: счётчики меню без limit-занижения ────────────────────────────────────

def test_transfer_menu_counts_not_capped_by_limit():
    from uk_management_bot.handlers.my_shifts._units import _load_transfer_menu_counts

    db = _make_transfers_db(_db_user(), shifts_total=25, transfers_total=8,
                            shifts_capped=10, transfers_capped=5)

    counts = _load_transfer_menu_counts(db, telegram_id=4242)

    assert counts == (25, 8), f"счётчики занижены limit'ом: {counts}"


# ── 3: метка дня — от фактической даты смены ────────────────────────────────

async def test_current_shifts_label_not_tomorrow_for_far_shift():
    from uk_management_bot.handlers.my_shifts import viewing

    start = utc_now() + timedelta(days=3)
    shift = MagicMock()
    shift.id = 1
    shift.user_id = 7
    shift.status = "planned"
    shift.planned_start_time = start
    shift.planned_end_time = start + timedelta(hours=8)
    shift.start_time = None
    shift.end_time = None
    shift.specialization_focus = None
    shift.geographic_zone = None
    shift.coverage_areas = None
    shift.max_requests = None
    shift.current_request_count = 0
    shift.completed_requests = 0
    shift.average_completion_time = None
    shift.efficiency_score = None
    shift.notes = None

    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = [shift]
    db = MagicMock()
    db.query.return_value = query

    user = MagicMock()
    user.id = 7

    cb = _make_callback()
    state = AsyncMock()

    with patch.object(viewing, "get_shift_list_keyboard", return_value=MagicMock()), \
         patch.object(viewing, "get_text",
                      side_effect=lambda key, language="ru", **kw: key):
        await viewing.handle_current_shifts(
            cb, state, language="ru", user=user, roles=["executor"], _db=db,
        )

    cb.message.edit_text.assert_awaited_once()
    text = cb.message.edit_text.await_args.args[0]
    assert "my_shifts.handlers.tomorrow" not in text, (
        "смена через 3 дня помечена «завтра» — метка от позиции, не от даты"
    )
