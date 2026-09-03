"""BUG-188: документы жителя — фото и файлы вне состояния теряются.

План: docs/superpowers/plans/2026-09-03-bug188-document-upload-entry.md.
Входы в загрузку документов: inline-кнопка в уведомлении о запросе,
stateless-ловушка фото/файлов в приватном чате, подсказка на экране выбора типа.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Chat, Document, Message, PhotoSize, User as TgUser

from uk_management_bot.states.onboarding import OnboardingStates
from uk_management_bot.tests.handlers.routing_probe import make_callback, resolve_ctx
from uk_management_bot.utils.helpers import get_text

ONB = "uk_management_bot.handlers.onboarding"


def _t(key: str) -> str:
    return get_text(key, language="ru")


def _main_routers():
    import uk_management_bot.main as main_mod

    order = re.findall(r"dp\.include_router\((\w+)\)", Path(main_mod.__file__).read_text())
    return [getattr(main_mod, name) for name in order]


def _tg_message(*, photo=False, document=False, chat_type="private"):
    user = TgUser(id=1, is_bot=False, first_name="Тест")
    chat = Chat(id=1 if chat_type == "private" else -100, type=chat_type)
    kwargs = {}
    if photo:
        kwargs["photo"] = [PhotoSize(file_id="f", file_unique_id="u", width=10, height=10, file_size=100)]
    if document:
        kwargs["document"] = Document(file_id="d", file_unique_id="du", file_name="x.pdf", file_size=100)
    return Message(message_id=1, date=datetime.now(timezone.utc), chat=chat, from_user=user, **kwargs)


def _mock_msg(*, photo=False, document=False):
    msg = MagicMock(spec=Message)
    msg.text = None
    msg.from_user = MagicMock(id=123)
    msg.photo = [MagicMock(file_id="f", file_size=100)] if photo else None
    msg.document = MagicMock(file_id="d", file_name="x.pdf", file_size=100) if document else None
    msg.answer = AsyncMock()
    msg.bot = MagicMock()
    return msg


def _state(data=None):
    st = MagicMock()
    st.get_data = AsyncMock(return_value=dict(data or {}))
    st.set_state = AsyncMock()
    st.update_data = AsyncMock()
    st.clear = AsyncMock()
    return st


def _inline_callbacks(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def _has_reply_button(markup, text):
    return any(b.text == text for row in markup.keyboard for b in row)


# ─── Task 1: send_to_user с клавиатурой + кнопка в уведомлении ───────────────

class TestNotificationButton:
    @pytest.mark.asyncio
    async def test_send_to_user_passes_reply_markup(self):
        from uk_management_bot.services.notification_service.channel import send_to_user

        bot = MagicMock()
        bot.send_message = AsyncMock()
        kb = MagicMock()
        assert await send_to_user(bot, 5, "t", reply_markup=kb) is True
        assert bot.send_message.await_args.kwargs["reply_markup"] is kb

        bot.send_message.reset_mock()
        await send_to_user(bot, 5, "t")
        assert "reply_markup" not in bot.send_message.await_args.kwargs

    def test_upload_documents_inline_keyboard(self):
        from uk_management_bot.keyboards.documents_entry import get_upload_documents_inline

        kb = get_upload_documents_inline("ru")
        assert _inline_callbacks(kb) == ["docs:upload"]
        assert kb.inline_keyboard[0][0].text == _t("onboarding.documents.btn_upload_inline")

    @pytest.mark.asyncio
    async def test_document_request_notification_carries_button(self):
        from uk_management_bot.handlers.user_management import fsm
        from uk_management_bot.keyboards.documents_entry import get_upload_documents_inline

        msg = _mock_msg()
        msg.text = "документы"
        st = _state({"action": "request_multiple_documents", "target_user_id": 53,
                     "manager_id": 2, "selected_documents": ["passport"]})
        requested = fsm._DocumentRequest(success=True, target_telegram_id=777,
                                         user_text="user", channel_text="chan",
                                         target_language="uz")
        with patch.object(fsm, "run_db", new=AsyncMock(return_value=requested)), \
             patch("uk_management_bot.services.notification_service.send_to_user",
                   new=AsyncMock(return_value=True)) as send, \
             patch("uk_management_bot.services.notification_service.send_to_channel",
                   new=AsyncMock(return_value=True)):
            await fsm.process_document_request(msg, st, roles=["manager"], user=None,
                                               language="ru", _db=MagicMock())

        assert send.await_args.args[:3] == (msg.bot, 777, "user")
        kb = send.await_args.kwargs["reply_markup"]
        assert _inline_callbacks(kb) == ["docs:upload"]
        assert kb.inline_keyboard[0][0].text == get_upload_documents_inline("uz").inline_keyboard[0][0].text


# ─── Task 2: docs:upload → выбор типа ────────────────────────────────────────

class TestUploadCallback:
    @pytest.mark.asyncio
    async def test_callback_opens_document_type_step(self):
        from uk_management_bot.handlers.onboarding import open_document_upload

        cb = MagicMock()
        cb.from_user = MagicMock(id=123)
        cb.message = _mock_msg()
        cb.message.edit_reply_markup = AsyncMock()
        cb.answer = AsyncMock()
        st = _state()
        await open_document_upload(cb, st, language="ru")

        st.set_state.assert_awaited_with(OnboardingStates.waiting_for_document_type)
        kb = cb.message.answer.await_args.kwargs["reply_markup"]
        assert _has_reply_button(kb, _t("onboarding.keyboards.passport"))
        cb.answer.assert_awaited()

    @pytest.mark.parametrize("raw_state", [None, "OnboardingStates:waiting_for_document_type"])
    def test_callback_routes_to_onboarding(self, raw_state):
        winner = resolve_ctx(_main_routers(), make_callback("docs:upload"), "callback_query",
                             raw_state=raw_state, roles=["applicant"], user=None)
        assert winner == (ONB, "open_document_upload"), winner


# ─── Task 3: stateless фото/файл → подсказка с кнопкой ───────────────────────

class TestStrayDocument:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", ["photo", "document"])
    async def test_stray_file_gets_hint_with_button(self, kind):
        from uk_management_bot.handlers.onboarding import catch_stray_document

        msg = _mock_msg(**{kind: True})
        await catch_stray_document(msg, language="ru")

        assert msg.answer.await_args.args[0] == _t("onboarding.documents.send_after_button")
        assert _inline_callbacks(msg.answer.await_args.kwargs["reply_markup"]) == ["docs:upload"]

    @pytest.mark.parametrize("raw_state,expected", [
        (None, (ONB, "catch_stray_document")),
        ("OnboardingStates:waiting_for_document_file", (ONB, "process_document_file")),
        ("FeedbackStates:waiting_for_photo", ("uk_management_bot.handlers.feedback", None)),
        ("RequestStates:media", ("uk_management_bot.handlers.requests.create", None)),
        ("ExecutorRequestStates:waiting_completion_media", ("uk_management_bot.handlers.requests.executor", None)),
    ])
    def test_photo_routing_by_state(self, raw_state, expected):
        winner = resolve_ctx(_main_routers(), _tg_message(photo=True), "message",
                             raw_state=raw_state, roles=["applicant"], user=None, user_status="pending")
        assert winner is not None, raw_state
        assert winner[0] == expected[0], winner
        if expected[1] is not None:
            assert winner[1] == expected[1], winner

    def test_stray_document_file_routes_to_catcher(self):
        winner = resolve_ctx(_main_routers(), _tg_message(document=True), "message",
                             raw_state=None, roles=["applicant"], user=None, user_status="pending")
        assert winner == (ONB, "catch_stray_document"), winner

    def test_group_photo_is_not_caught(self):
        winner = resolve_ctx(_main_routers(), _tg_message(photo=True, chat_type="supergroup"), "message",
                             raw_state=None, roles=["applicant"], user=None, user_status="pending")
        assert winner != (ONB, "catch_stray_document"), winner


# ─── Task 4: фото до выбора типа ─────────────────────────────────────────────

class TestPhotoBeforeType:
    @pytest.mark.asyncio
    async def test_photo_before_type_repeats_keyboard(self):
        from uk_management_bot.handlers.onboarding import document_before_type

        msg, st = _mock_msg(photo=True), _state()
        await document_before_type(msg, st, language="ru")

        assert msg.answer.await_args.args[0] == _t("onboarding.documents.choose_type_first")
        assert _has_reply_button(msg.answer.await_args.kwargs["reply_markup"], _t("onboarding.keyboards.passport"))
        st.set_state.assert_not_awaited()
        st.clear.assert_not_awaited()

    def test_photo_in_type_state_routes(self):
        winner = resolve_ctx(_main_routers(), _tg_message(photo=True), "message",
                             raw_state="OnboardingStates:waiting_for_document_type",
                             roles=["applicant"], user=None, user_status="pending")
        assert winner == (ONB, "document_before_type"), winner
