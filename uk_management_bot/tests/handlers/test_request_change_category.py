"""Смена категории из бота менеджером: клавиатуры, права, роутинг, e2e.

Свойства (каждое — RED-первым):
1. Команда — НАСТОЯЩИЙ `change_category_sync` на sqlite (урок PR #477: мок
   outcome не ловит классовую ошибку в связке хендлер ↔ канон).
2. Экран строится из `CategoryChangeResult`, а не из перечитанной заявки.
3. Кнопка «Переназначить» — только если `can_reassign` (канон MANAGER_ASSIGN:
   «Новая»/«В работе»); в «Закуп» — предупреждение без кнопки.
4. `resolve_ctx` пиннит ВЛАДЕНИЕ префиксами, отказ — прямым вызовом.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.request_comment import RequestComment
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.handlers.admin import category as mod
from uk_management_bot.keyboards.requests import SELECTABLE_CATEGORY_KEYS
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_APPROVED,
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_NEW,
    REQUEST_STATUS_PURCHASE,
)
from uk_management_bot.utils.helpers import get_text

NUMBER = "260903-001"
APPLICANT_ID, EXEC_ID, MANAGER_ID = 1, 2, 5


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    SF = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    yield SF
    engine.dispose()


def _seed(SF, *, status=REQUEST_STATUS_NEW, executor_id=None, executor_spec="electrician"):
    s = SF()
    s.add(User(id=APPLICANT_ID, telegram_id=100, first_name="Owner", roles='["applicant"]',
               status="approved", language="ru"))
    s.add(User(id=EXEC_ID, telegram_id=200, first_name="Exec", roles='["executor"]',
               status="approved", language="ru", specialization=executor_spec))
    s.add(User(id=MANAGER_ID, telegram_id=500, first_name="Mgr", roles='["manager"]',
               status="approved", language="ru"))
    s.add(Request(request_number=NUMBER, user_id=APPLICANT_ID, executor_id=executor_id,
                  category="electricity", description="Нет света", address="Дом 1",
                  status=status, urgency="low"))
    if executor_id is not None:
        s.add(RequestAssignment(request_number=NUMBER, assignment_type="individual",
                                executor_id=executor_id, created_by=MANAGER_ID,
                                status="active"))
    s.commit()
    s.close()


def _callback(data):
    cb = MagicMock()
    cb.data = data
    cb.id = "cb1"
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.bot = MagicMock()
    return cb


def _callbacks(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row]


# ══════════════════════════════════════════════════════════════════════════
# Клавиатуры
# ══════════════════════════════════════════════════════════════════════════


class TestKeyboards:
    def test_row_shown_for_manager_on_non_terminal(self):
        from uk_management_bot.keyboards.admin import get_change_category_button_row

        for status in (REQUEST_STATUS_NEW, REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_PURCHASE):
            row = get_change_category_button_row(NUMBER, status=status, roles=["manager"])
            assert row and row[0].callback_data == f"{mod.MENU_PREFIX}{NUMBER}", status

    @pytest.mark.parametrize("kwargs", [
        {"status": REQUEST_STATUS_APPROVED, "roles": ["manager"]},
        {"status": "Отменена", "roles": ["manager"]},
        {"status": REQUEST_STATUS_NEW, "roles": ["admin"]},
        {"status": REQUEST_STATUS_NEW, "roles": ["executor"]},
        {"status": REQUEST_STATUS_NEW, "roles": []},
    ])
    def test_row_hidden(self, kwargs):
        from uk_management_bot.keyboards.admin import get_change_category_button_row

        assert get_change_category_button_row(NUMBER, **kwargs) == []

    def test_picker_lists_selectable_marks_current_and_returns_to_card(self):
        from uk_management_bot.keyboards.admin import get_category_picker_keyboard

        markup = get_category_picker_keyboard(NUMBER, current_key="electricity", language="ru")
        callbacks = _callbacks(markup)
        for key in SELECTABLE_CATEGORY_KEYS:
            assert f"{mod.SET_PREFIX}{NUMBER}_{key}" in callbacks, key
        assert f"{mod.SET_PREFIX}{NUMBER}_engineering" not in callbacks
        assert f"mview_{NUMBER}" in callbacks
        texts = [b.text for row in markup.inline_keyboard for b in row]
        assert any(t.startswith("• ") and "Электрика" in t for t in texts)
        assert not any(t.startswith("• ") and "Сантехника" in t for t in texts)


# ══════════════════════════════════════════════════════════════════════════
# Права и роутинг
# ══════════════════════════════════════════════════════════════════════════


class TestAuthorization:
    @pytest.mark.asyncio
    async def test_applicant_is_refused_before_touching_db(self):
        cb = _callback(f"{mod.MENU_PREFIX}{NUMBER}")
        with patch.object(mod, "run_db", new=AsyncMock()) as run_db:
            await mod.handle_category_menu(cb, roles=["applicant"], user=MagicMock(), language="ru")
        cb.answer.assert_awaited()
        run_db.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_admin_without_manager_role_is_refused(self):
        cb = _callback(f"{mod.SET_PREFIX}{NUMBER}_plumbing")
        with patch.object(mod, "run_db", new=AsyncMock()):
            await mod.handle_category_set(cb, roles=["admin"], user=MagicMock(), language="ru")
        cb.answer.assert_awaited_with(
            get_text("admin.handlers.category_manager_only", language="ru"), show_alert=True)


class TestRouting:
    def _resolve(self, data, ctx):
        from uk_management_bot.tests.handlers.routing_probe import make_callback, resolve_ctx
        from uk_management_bot.tests.handlers.test_dead_handlers_retired import ROUTERS

        return resolve_ctx(ROUTERS, make_callback(data), "callback_query", **ctx)

    MANAGER = {"roles": ["manager"], "user": None}

    def test_menu_and_set_are_owned(self):
        assert self._resolve(f"{mod.MENU_PREFIX}{NUMBER}", self.MANAGER)[1] == "handle_category_menu"
        module, name = self._resolve(f"{mod.SET_PREFIX}{NUMBER}_plumbing", self.MANAGER)
        assert name == "handle_category_set" and module.endswith("admin.category")

    def test_set_entry_rejects_non_canonical_payload(self):
        for bad in (f"{mod.SET_PREFIX}{NUMBER}", "req_category_set_abc_plumbing",
                    f"{mod.SET_PREFIX}{NUMBER}_Plumbing", f"{mod.SET_PREFIX}{NUMBER}_plumb-ing"):
            assert self._resolve(bad, self.MANAGER) != (
                "uk_management_bot.handlers.admin.category", "handle_category_set"), bad


# ══════════════════════════════════════════════════════════════════════════
# E2E: настоящая команда на sqlite
# ══════════════════════════════════════════════════════════════════════════


class TestEndToEnd:
    def _patches(self, SF):
        return [
            patch("uk_management_bot.database.session.SessionLocal", SF),
            patch.object(mod, "run_db", new=AsyncMock(side_effect=lambda fn, db=None: fn(SF()))),
            patch("uk_management_bot.services.workflow_notifications.send_notify_messages",
                  new=AsyncMock()),
            patch("uk_management_bot.services.redis_pubsub.publish_request_event",
                  new=AsyncMock()),
            patch("uk_management_bot.services.dispatch._notify_assigned_sync", lambda *a, **k: None),
        ]

    async def _run_set(self, SF, key="plumbing"):
        cb = _callback(f"{mod.SET_PREFIX}{NUMBER}_{key}")
        patches = self._patches(SF)
        for p in patches:
            p.start()
        try:
            await mod.handle_category_set(cb, roles=["manager"],
                                          user=SimpleNamespace(id=MANAGER_ID), language="ru")
        finally:
            for p in patches:
                p.stop()
        return cb

    @pytest.mark.asyncio
    async def test_new_request_changes_category_and_writes_comment(self, factory):
        _seed(factory, status=REQUEST_STATUS_NEW)
        cb = await self._run_set(factory, "plumbing")

        s = factory()
        req = s.query(Request).filter_by(request_number=NUMBER).one()
        assert req.category == "plumbing"
        comment = s.query(RequestComment).filter_by(request_number=NUMBER).one()
        assert comment.comment_text == "Категория: Электрика → Сантехника"
        s.close()

        text = cb.message.edit_text.await_args.args[0]
        assert "Сантехника" in text and NUMBER in text
        markup = cb.message.edit_text.await_args.kwargs["reply_markup"]
        assert f"mview_{NUMBER}" in _callbacks(markup)
        assert not any(c.startswith("req_reassign_menu_") for c in _callbacks(markup))

    @pytest.mark.asyncio
    async def test_in_progress_mismatch_offers_reassign(self, factory):
        _seed(factory, status=REQUEST_STATUS_IN_PROGRESS, executor_id=EXEC_ID)
        cb = await self._run_set(factory, "plumbing")

        text = cb.message.edit_text.await_args.args[0]
        assert get_text("admin.handlers.category_spec_mismatch", language="ru") in text
        markup = cb.message.edit_text.await_args.kwargs["reply_markup"]
        assert f"req_reassign_menu_{NUMBER}" in _callbacks(markup)
        s = factory()
        assert s.query(Request).filter_by(request_number=NUMBER).one().executor_id == EXEC_ID
        s.close()

    @pytest.mark.asyncio
    async def test_purchase_mismatch_warns_without_reassign_button(self, factory):
        _seed(factory, status=REQUEST_STATUS_PURCHASE, executor_id=EXEC_ID)
        cb = await self._run_set(factory, "plumbing")

        text = cb.message.edit_text.await_args.args[0]
        assert get_text("admin.handlers.category_spec_mismatch", language="ru") in text
        markup = cb.message.edit_text.await_args.kwargs["reply_markup"]
        assert not any(c.startswith("req_reassign_menu_") for c in _callbacks(markup))

    @pytest.mark.asyncio
    async def test_same_category_is_reported_as_unchanged(self, factory):
        _seed(factory, status=REQUEST_STATUS_NEW)
        cb = await self._run_set(factory, "electricity")
        text = cb.message.edit_text.await_args.args[0]
        assert get_text("admin.handlers.category_same", language="ru",
                        request_number=NUMBER) in text

    @pytest.mark.asyncio
    async def test_terminal_request_is_refused_with_alert(self, factory):
        _seed(factory, status=REQUEST_STATUS_APPROVED)
        cb = await self._run_set(factory, "plumbing")
        cb.answer.assert_awaited_with(
            get_text("admin.handlers.category_bad_status", language="ru"), show_alert=True)
        cb.message.edit_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_key_from_client_is_refused(self, factory):
        """callback_data шлёт КЛИЕНТ — ключ проверяется сервером по SELECTABLE."""
        _seed(factory, status=REQUEST_STATUS_NEW)
        cb = await self._run_set(factory, "engineering")
        cb.answer.assert_awaited_with(
            get_text("admin.handlers.category_unknown", language="ru"), show_alert=True)
        s = factory()
        assert s.query(Request).filter_by(request_number=NUMBER).one().category == "electricity"
        s.close()
