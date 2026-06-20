"""Регресс-тесты батча FS-01..FS-03 (P2 bugfix-пачка 2026-06-20).

FS-01 — фильтры истории смен падали: callback'и мутировали `callback.message.from_user`
        (aiogram 3 Message — frozen Pydantic → ValidationError). Фикс: передавать
        `from_user_id` в `shifts_history` явно, без мутации.
FS-02 — меню «Передача смен» приходило с пустой клавиатурой: запросы фильтровали
        `Shift.user_id == user.telegram_id` (а user_id — FK на users.id).
FS-03 — 4 кнопки «Назначение исполнителей» падали:
        workload_analysis (User.is_active нет), schedule_conflicts (Shift.executor_id/
        .executor/.date нет), ai_assignment (sync-метод, список смен, не await),
        redistribute_load (метод redistribute_workload не существует → balance_executor_workload).
"""

import inspect
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.shift import Shift

_engine = create_engine("sqlite:///:memory:", echo=False)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=_engine)
    session = _Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


# ─────────────────────────── FS-01 ───────────────────────────

@pytest.mark.asyncio
async def test_fs01_period_filter_passes_from_user_id_without_mutation():
    """Callback фильтра вызывает shifts_history с from_user_id и НЕ трогает message."""
    from uk_management_bot.handlers import shifts as shifts_mod

    cb = MagicMock()
    cb.data = "shifts_period_7d"
    cb.from_user = MagicMock(id=777)
    cb.message = MagicMock()
    cb.answer = AsyncMock()
    state = MagicMock()
    state.update_data = AsyncMock()

    with patch.object(shifts_mod, "shifts_history", new=AsyncMock()) as hist:
        await shifts_mod.shifts_filter_period(cb, state, language="ru")

    hist.assert_awaited_once()
    # Дискриминатор: id передаётся через kwarg, мутации callback.message нет.
    assert hist.await_args.kwargs.get("from_user_id") == 777


def test_fs01_shifts_history_accepts_from_user_id():
    sig = inspect.signature(__import__(
        "uk_management_bot.handlers.shifts", fromlist=["shifts_history"]
    ).shifts_history)
    assert "from_user_id" in sig.parameters


# ─────────────────────────── FS-02 ───────────────────────────

@pytest.mark.asyncio
async def test_fs02_transfer_menu_shows_button_for_active_shift(db):
    """Активная смена (user_id=user.id) → в меню есть кнопка initiate_transfer."""
    from uk_management_bot.handlers import my_shifts as ms

    # id != telegram_id — именно это расхождение ломало фильтр.
    user = User(id=1, telegram_id=9999, username="u", first_name="A", last_name="B",
                roles='["executor"]', active_role="executor", status="approved", language="ru")
    db.add(user)
    db.add(Shift(user_id=user.id, status="active",
                 start_time=datetime.now() - timedelta(hours=1),
                 end_time=datetime.now() + timedelta(hours=2)))
    db.commit()

    cb = MagicMock()
    cb.from_user = MagicMock(id=9999)
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()

    with patch.object(ms, "get_db", return_value=iter([db])), \
         patch.object(ms, "get_text", side_effect=lambda key, language="ru", **kw: key):
        await ms.handle_shift_transfer_menu(cb, state=MagicMock(), language="ru")

    cb.message.edit_text.assert_awaited_once()
    kb = cb.message.edit_text.await_args.kwargs["reply_markup"]
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "initiate_transfer" in callbacks


@pytest.mark.asyncio
async def test_fs02_transfer_menu_empty_when_no_shifts(db):
    """Без смен — кнопки передачи нет (контроль: пустота не от бага id)."""
    from uk_management_bot.handlers import my_shifts as ms

    user = User(id=2, telegram_id=8888, username="u2", first_name="C", last_name="D",
                roles='["executor"]', active_role="executor", status="approved", language="ru")
    db.add(user)
    db.commit()

    cb = MagicMock()
    cb.from_user = MagicMock(id=8888)
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()

    with patch.object(ms, "get_db", return_value=iter([db])), \
         patch.object(ms, "get_text", side_effect=lambda key, language="ru", **kw: key):
        await ms.handle_shift_transfer_menu(cb, state=MagicMock(), language="ru")

    kb = cb.message.edit_text.await_args.kwargs["reply_markup"]
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "initiate_transfer" not in callbacks


# ─────────────────────────── FS-03 ───────────────────────────

def test_fs03_list_executors_without_shifts_runs(db):
    """workload_analysis: сервис не обращается к несуществующему User.is_active."""
    from uk_management_bot.services.shift_management_service import ShiftManagementService

    db.add(User(id=10, telegram_id=100, username="ex", first_name="E", last_name="X",
                roles='["executor"]', active_role="executor", status="approved", language="ru"))
    db.commit()

    free = ShiftManagementService(db).list_executors_without_shifts([])
    assert [u.id for u in free] == [10]


def test_fs03_user_has_no_is_active_column():
    assert not hasattr(User, "is_active")


def test_fs03_shift_has_no_executor_aliases():
    """schedule_conflicts опирается на user_id/user, не executor_id/executor/date."""
    assert not hasattr(Shift, "executor_id")
    assert not hasattr(Shift, "executor")
    assert not hasattr(Shift, "date")


def test_fs03_auto_assign_is_sync_and_takes_shift_list():
    """ai_assignment: метод синхронный и принимает список смен (не await/target_date)."""
    from uk_management_bot.services.shift_assignment_service import ShiftAssignmentService

    m = ShiftAssignmentService.auto_assign_executors_to_shifts
    assert not inspect.iscoroutinefunction(m)
    assert "shifts" in inspect.signature(m).parameters


def test_fs03_redistribute_uses_balance_method_not_missing_one():
    """redistribute_load: balance_executor_workload есть, redistribute_workload нет."""
    from uk_management_bot.services.shift_assignment_service import ShiftAssignmentService

    assert hasattr(ShiftAssignmentService, "balance_executor_workload")
    assert not hasattr(ShiftAssignmentService, "redistribute_workload")


def test_fs03_conflicts_template_no_dangling_header_at_zero():
    """FS-03 косметика: при 0 конфликтов шаблон не оставляет висячий заголовок."""
    from uk_management_bot.utils.helpers import get_text

    # заголовок секции вынесен в отдельный ключ (не хардкод в шаблоне)
    header = get_text("shift_management.conflicts_found_header", language="ru")
    assert header and header != "shift_management.conflicts_found_header"

    rendered = get_text(
        "shift_management.conflicts_analysis_result",
        language="ru",
        period_start="01.01", period_end="07.01",
        conflicts_count=0,
        no_conflicts=get_text("shift_management.no_conflicts_found", language="ru"),
        conflicts_list="",
    )
    # при 0 конфликтов «Обнаруженные конфликты» НЕ должно появляться
    assert "Обнаруженные конфликты" not in rendered
