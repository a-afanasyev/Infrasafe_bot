"""Тесты бот-UI «Автоматический менеджер» (handlers/auto_manager.py).

Паттерн — клон tests/test_fs_batch_p2.py / tests/test_auto_manager_window.py:
реальная sqlite-сессия (Base.metadata.create_all) для round-trip через
load_config_sync/save_config_sync + MagicMock/AsyncMock для Telegram-объектов
(CallbackQuery/Message/FSMContext), как в tests/handlers/test_shift_planning_confirm.py.

Ключевой сценарий — BUG-BOT-паттерн из памяти проекта: `updated_by` должен
быть внутренним DB `user.id`, а не Telegram ID. Тестовые пользователи ниже
всегда создаются с id != telegram_id, чтобы тест ловил регресс, если кто-то
случайно передаст `user.telegram_id` вместо `user.id`.
"""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message, User as TgUser
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.auto_manager_config import AutoManagerConfig
from uk_management_bot.database.models.user import User
from uk_management_bot.services.auto_manager.config import DEFAULT_CONFIG


# ─────────────────────────────── fixtures ───────────────────────────────

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


def _make_tg_user(user_id: int) -> MagicMock:
    u = MagicMock(spec=TgUser)
    u.id = user_id
    u.first_name = "Mgr"
    u.last_name = "Test"
    u.username = "mgr_test"
    u.language_code = "ru"
    return u


def _make_callback(data: str, telegram_id: int) -> MagicMock:
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.from_user = _make_tg_user(telegram_id)
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.bot = MagicMock()
    return cb


def _make_message(text: str, telegram_id: int) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.from_user = _make_tg_user(telegram_id)
    msg.answer = AsyncMock()
    msg.bot = MagicMock()
    return msg


def _make_state() -> AsyncMock:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    return state


def _make_user(db, *, db_id: int, telegram_id: int, roles='["manager"]', active_role="manager") -> User:
    """DB id и telegram_id deliberately разные — ловит BUG-BOT-паттерн
    (updated_by = telegram_id вместо user.id)."""
    assert db_id != telegram_id, "test setup bug: db_id must differ from telegram_id"
    user = User(
        id=db_id, telegram_id=telegram_id, username="mgr", first_name="Mgr",
        last_name="Test", roles=roles, active_role=active_role,
        status="approved", language="ru",
    )
    db.add(user)
    db.commit()
    return user


def _config_row(db) -> AutoManagerConfig:
    row = db.query(AutoManagerConfig).filter(AutoManagerConfig.id == 1).first()
    assert row is not None, "expected auto_manager_config row to have been persisted"
    return row


# ─────────────────────────── @require_role gate ───────────────────────────


class TestRequireRoleGate:
    @pytest.mark.asyncio
    async def test_non_manager_denied_and_no_render(self, db):
        from uk_management_bot.handlers.auto_manager import handle_auto_manager_menu

        cb = _make_callback(data="auto_manager_menu", telegram_id=1001)
        state = _make_state()

        await handle_auto_manager_menu(cb, state, db=db, roles=["applicant"], user=None)

        cb.message.edit_text.assert_not_called()
        cb.answer.assert_awaited_once()
        _args, kwargs = cb.answer.call_args
        assert kwargs.get("show_alert") is True

    @pytest.mark.parametrize("handler_name", [
        "handle_auto_manager_menu",
        "handle_auto_manager_toggle",
        "handle_auto_manager_mode_ai",
        "handle_auto_manager_change_window",
        "handle_auto_manager_window_input",
    ])
    def test_handlers_accept_di_params(self, handler_name):
        """require_role только читает kwargs — но aiogram передаёт db/user/roles
        через DI лишь если они объявлены в сигнатуре хендлера. Пропуск одного из
        них — тот самый баг, когда авторизованному пользователю прилетает
        «нет прав доступа» (см. reference_require_role_di_signature.md)."""
        import uk_management_bot.handlers.auto_manager as am
        sig = inspect.signature(getattr(am, handler_name))
        for p in ("db", "user", "roles"):
            assert p in sig.parameters, f"{handler_name} не принимает DI-параметр {p}"


# ─────────────────────────────── status screen ───────────────────────────────


class TestStatusScreen:
    @pytest.mark.asyncio
    async def test_renders_current_config_values(self, db):
        from uk_management_bot.handlers.auto_manager import handle_auto_manager_menu

        user = _make_user(db, db_id=5, telegram_id=50005)
        cb = _make_callback(data="auto_manager_menu", telegram_id=50005)
        state = _make_state()

        await handle_auto_manager_menu(cb, state, db=db, roles=["manager"], user=user)

        cb.message.edit_text.assert_called_once()
        text = cb.message.edit_text.call_args.args[0]
        assert DEFAULT_CONFIG["window_start"] in text
        assert DEFAULT_CONFIG["window_end"] in text
        assert DEFAULT_CONFIG["timezone"] in text
        assert str(DEFAULT_CONFIG["max_requests_per_run"]) in text
        cb.answer.assert_awaited_once()


# ─────────────────────────────────── toggle ───────────────────────────────────


class TestToggle:
    @pytest.mark.asyncio
    async def test_flip_persists_with_correct_updated_by(self, db):
        from uk_management_bot.handlers.auto_manager import handle_auto_manager_toggle

        # id (7) != telegram_id (70007) — the exact bug this test guards against.
        user = _make_user(db, db_id=7, telegram_id=70007)
        cb = _make_callback(data="auto_manager_toggle", telegram_id=70007)
        state = _make_state()

        await handle_auto_manager_toggle(cb, state, db=db, roles=["manager"], user=user)

        row = _config_row(db)
        assert row.data["enabled"] is True  # flipped from DEFAULT_CONFIG False
        assert row.updated_by == 7
        assert row.updated_by != 70007
        cb.message.edit_text.assert_called_once()
        cb.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_second_flip_disables_again(self, db):
        from uk_management_bot.handlers.auto_manager import handle_auto_manager_toggle

        user = _make_user(db, db_id=8, telegram_id=80008)
        cb = _make_callback(data="auto_manager_toggle", telegram_id=80008)
        state = _make_state()

        await handle_auto_manager_toggle(cb, state, db=db, roles=["manager"], user=user)
        await handle_auto_manager_toggle(cb, state, db=db, roles=["manager"], user=user)

        row = _config_row(db)
        assert row.data["enabled"] is False


# ───────────────────────────── AI mode blocked button ─────────────────────────────


class TestAiModeBlocked:
    @pytest.mark.asyncio
    async def test_tap_shows_hint_and_never_writes_mode(self, db):
        from uk_management_bot.handlers.auto_manager import handle_auto_manager_mode_ai

        user = _make_user(db, db_id=9, telegram_id=90009)
        cb = _make_callback(data="auto_manager_mode_ai", telegram_id=90009)
        state = _make_state()

        await handle_auto_manager_mode_ai(cb, state, db=db, roles=["manager"], user=user)

        cb.answer.assert_awaited_once()
        _args, kwargs = cb.answer.call_args
        assert kwargs.get("show_alert") is False

        # Nothing persisted at all — button must not touch the config table.
        assert db.query(AutoManagerConfig).count() == 0
        cb.message.edit_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_repeated_taps_never_write_ai_mode(self, db):
        """Double-tap / stale-keyboard redelivery must still be a pure no-op."""
        from uk_management_bot.handlers.auto_manager import handle_auto_manager_mode_ai

        user = _make_user(db, db_id=12, telegram_id=120012)
        cb = _make_callback(data="auto_manager_mode_ai", telegram_id=120012)
        state = _make_state()

        for _ in range(3):
            await handle_auto_manager_mode_ai(cb, state, db=db, roles=["manager"], user=user)

        rows = db.query(AutoManagerConfig).all()
        assert rows == [] or all(r.data["mode"] != "ai" for r in rows)


# ───────────────────────────── change-window entry point ─────────────────────────────


class TestChangeWindowEntry:
    @pytest.mark.asyncio
    async def test_enters_fsm_state_and_shows_prompt(self, db):
        """Tapping «Изменить окно» must switch FSM into entering_window and
        redraw the message with the HH:MM-HH:MM prompt text — behavioral
        coverage, not just the DI-shape check in TestRequireRoleGate."""
        from uk_management_bot.handlers.auto_manager import handle_auto_manager_change_window
        from uk_management_bot.states.auto_manager import AutoManagerStates
        from uk_management_bot.utils.helpers import get_text

        user = _make_user(db, db_id=16, telegram_id=160016)
        cb = _make_callback(data="auto_manager_change_window", telegram_id=160016)
        state = _make_state()

        await handle_auto_manager_change_window(cb, state, db=db, roles=["manager"], user=user)

        state.set_state.assert_awaited_once_with(AutoManagerStates.entering_window)

        cb.message.edit_text.assert_called_once()
        text = cb.message.edit_text.call_args.args[0]
        assert text == get_text("auto_manager.window_input.prompt", language="ru")
        cb.answer.assert_awaited_once()


# ───────────────────────────────── back navigation ─────────────────────────────────


class TestBackNavigation:
    def test_back_button_routes_to_shared_handler(self):
        """Item-1 fix: the «Назад» button now points at the pre-existing
        shared ``back_to_shifts`` callback (handlers/shift_management/schedule.py
        ::handle_back_to_shifts) instead of a duplicate auto_manager-local
        handler — verify both keyboards (status screen + window-cancel) wire
        the button to that shared callback_data."""
        from uk_management_bot.handlers.auto_manager import _status_keyboard, _window_cancel_keyboard
        from uk_management_bot.services.auto_manager.config import DEFAULT_CONFIG

        def _all_callbacks(markup):
            return {btn.callback_data for row in markup.inline_keyboard for btn in row}

        status_cbs = _all_callbacks(_status_keyboard(DEFAULT_CONFIG, "ru"))
        window_cbs = _all_callbacks(_window_cancel_keyboard("ru"))

        assert "back_to_shifts" in status_cbs
        assert "back_to_shifts" in window_cbs
        # The old auto_manager-local callback_data must be gone, not just added alongside.
        assert "auto_manager_back" not in status_cbs
        assert "auto_manager_back" not in window_cbs

    def test_handler_no_longer_exists(self):
        """The duplicate handle_auto_manager_back has been removed entirely —
        guards against it silently reappearing."""
        import uk_management_bot.handlers.auto_manager as am

        assert not hasattr(am, "handle_auto_manager_back")

    @pytest.mark.asyncio
    async def test_shared_handler_redraws_main_menu_and_clears_state_from_auto_manager_screen(self, db):
        """Behavioral coverage for the shared handle_back_to_shifts, invoked
        as it would be when the user is on the auto-manager screen (in
        AutoManagerStates.entering_window): it must redraw the main shift
        menu (not the auto-manager status screen) and clear FSM state.
        No prior behavioral test of this handler existed — only keyboard
        callback_data presence was asserted elsewhere
        (tests/keyboards/test_shift_management.py, tests/handlers/test_bug_p2_nav_ux.py)."""
        from uk_management_bot.handlers.shift_management.schedule import handle_back_to_shifts
        from uk_management_bot.states.auto_manager import AutoManagerStates

        user = _make_user(db, db_id=17, telegram_id=170017)
        cb = _make_callback(data="back_to_shifts", telegram_id=170017)
        state = _make_state()
        state.get_state = AsyncMock(return_value=AutoManagerStates.entering_window)

        await handle_back_to_shifts(cb, state, db=db, roles=["manager"], user=user)

        cb.message.edit_text.assert_called_once()
        _text, kwargs = cb.message.edit_text.call_args.args, cb.message.edit_text.call_args.kwargs
        markup = kwargs["reply_markup"]
        callbacks = {btn.callback_data for row in markup.inline_keyboard for btn in row}
        assert "auto_manager_menu" in callbacks  # confirms main shift menu, not auto-manager status screen

        state.clear.assert_awaited_once()
        cb.answer.assert_awaited_once()


# ─────────────────────────────── window input flow ───────────────────────────────


class TestWindowInput:
    @pytest.mark.asyncio
    async def test_valid_input_persists_both_fields_and_updated_by(self, db):
        from uk_management_bot.handlers.auto_manager import handle_auto_manager_window_input

        user = _make_user(db, db_id=11, telegram_id=110011)
        msg = _make_message(text="21:00-07:30", telegram_id=110011)
        state = _make_state()

        await handle_auto_manager_window_input(msg, state, db=db, roles=["manager"], user=user)

        row = _config_row(db)
        assert row.data["window_start"] == "21:00"
        assert row.data["window_end"] == "07:30"
        assert row.updated_by == 11
        assert row.updated_by != 110011

        state.clear.assert_awaited_once()
        assert msg.answer.await_count == 2  # success confirmation + redrawn status screen

    @pytest.mark.asyncio
    async def test_invalid_time_reprompts_without_persisting(self, db):
        """Reuses the '99:99' case from the shared validate_config test suite —
        must not crash, must not write, must stay in entering_window (no state.clear)."""
        from uk_management_bot.handlers.auto_manager import handle_auto_manager_window_input

        user = _make_user(db, db_id=13, telegram_id=130013)
        msg = _make_message(text="99:99-07:00", telegram_id=130013)
        state = _make_state()

        await handle_auto_manager_window_input(msg, state, db=db, roles=["manager"], user=user)

        assert db.query(AutoManagerConfig).count() == 0
        state.clear.assert_not_awaited()
        msg.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_malformed_text_without_dash_reprompts(self, db):
        from uk_management_bot.handlers.auto_manager import handle_auto_manager_window_input

        user = _make_user(db, db_id=14, telegram_id=140014)
        msg = _make_message(text="not a time", telegram_id=140014)
        state = _make_state()

        await handle_auto_manager_window_input(msg, state, db=db, roles=["manager"], user=user)

        assert db.query(AutoManagerConfig).count() == 0
        state.clear.assert_not_awaited()
        msg.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_does_not_clobber_other_config_fields(self, db):
        """Window edit must only touch window_start/window_end — enabled/mode/
        timezone/max_requests_per_run (out of scope for bot UI in Phase 1) survive."""
        from uk_management_bot.handlers.auto_manager import (
            handle_auto_manager_toggle,
            handle_auto_manager_window_input,
        )

        user = _make_user(db, db_id=15, telegram_id=150015)
        state = _make_state()

        # Enable first, then edit the window — enabled=True must survive.
        cb = _make_callback(data="auto_manager_toggle", telegram_id=150015)
        await handle_auto_manager_toggle(cb, state, db=db, roles=["manager"], user=user)

        msg = _make_message(text="22:15-06:45", telegram_id=150015)
        await handle_auto_manager_window_input(msg, state, db=db, roles=["manager"], user=user)

        row = _config_row(db)
        assert row.data["enabled"] is True
        assert row.data["window_start"] == "22:15"
        assert row.data["window_end"] == "06:45"
        assert row.data["timezone"] == DEFAULT_CONFIG["timezone"]
        assert row.data["max_requests_per_run"] == DEFAULT_CONFIG["max_requests_per_run"]
