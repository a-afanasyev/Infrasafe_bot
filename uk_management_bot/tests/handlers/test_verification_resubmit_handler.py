"""verif:resubmit — переподача заявки после отказа (бот).

RESUBMITTED: кнопка снимается, открывается выбор типа документа (с «Пропустить»).
Любой другой исход (повтор, кулдаун, стафф, верифицированный) — только
всплывающий ответ: ни сообщений в чат (флуд нажатиями не усиливается), ни
снятия кнопки, ни формы загрузки.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uk_management_bot.handlers import onboarding
from uk_management_bot.keyboards.documents_entry import RESUBMIT_CB, get_resubmit_inline
from uk_management_bot.services.user_verification_service import ResubmitResult
from uk_management_bot.states.onboarding import OnboardingStates
from uk_management_bot.utils.helpers import get_text


def _callback():
    cb = MagicMock()
    cb.from_user = MagicMock(id=7301)
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _state():
    st = MagicMock()
    st.set_state = AsyncMock()
    return st


async def _press(result):
    cb, st = _callback(), _state()
    with patch.object(onboarding, "run_db", AsyncMock(return_value=result)):
        await onboarding.resubmit_verification(cb, st, language="ru")
    return cb, st


@pytest.mark.asyncio
async def test_resubmitted_opens_document_step():
    cb, st = await _press(ResubmitResult.RESUBMITTED)
    cb.message.edit_reply_markup.assert_awaited_once()
    st.set_state.assert_awaited_with(OnboardingStates.waiting_for_document_type)
    cb.answer.assert_awaited()


@pytest.mark.parametrize("result", [
    ResubmitResult.ALREADY_PENDING, ResubmitResult.COOLDOWN,
    ResubmitResult.DENIED, ResubmitResult.NOT_FOUND,
])
@pytest.mark.asyncio
async def test_other_outcomes_only_popup(result):
    cb, st = await _press(result)
    cb.message.answer.assert_not_awaited()
    cb.message.edit_reply_markup.assert_not_awaited()
    st.set_state.assert_not_awaited()
    assert cb.answer.await_args.args[0] == get_text(f"verification_resubmit.{result.value}", language="ru")


def test_resubmit_button():
    kb = get_resubmit_inline("uz")
    button = kb.inline_keyboard[0][0]
    assert button.callback_data == RESUBMIT_CB == "verif:resubmit"
    assert button.text == get_text("verification_resubmit.btn", language="uz")


@pytest.mark.parametrize("language", ["ru", "uz"])
@pytest.mark.parametrize("key", ["btn", "offer", "resubmitted", "already_pending", "cooldown",
                                 "denied", "not_found"])
def test_texts_exist(key, language):
    full = f"verification_resubmit.{key}"
    assert get_text(full, language=language) != full


@pytest.mark.asyncio
async def test_rejected_upload_attempt_offers_resubmit():
    """Отказ «проверка отклонена» несёт кнопку переподачи — вход для отклонённых до релиза."""
    from uk_management_bot.services.user_verification_service import UploadDenied

    msg = MagicMock()
    msg.from_user = MagicMock(id=7301)
    msg.answer = AsyncMock()
    with patch.object(onboarding, "_upload_denial", AsyncMock(return_value=UploadDenied.REJECTED)):
        await onboarding.start_document_upload(msg, _state(), language="ru")
    kb = msg.answer.await_args.kwargs["reply_markup"]
    assert kb.inline_keyboard[0][0].callback_data == RESUBMIT_CB


@pytest.mark.asyncio
async def test_start_offers_resubmit_to_rejected_resident():
    msg = MagicMock()
    msg.from_user = MagicMock(id=7301)
    msg.answer = AsyncMock()
    with patch("uk_management_bot.handlers.base.run_db", AsyncMock(return_value=True)):
        from uk_management_bot.handlers.base import offer_resubmit_if_rejected
        await offer_resubmit_if_rejected(msg, "ru")
    assert msg.answer.await_args.args[0] == get_text("verification_resubmit.offer", language="ru")
    assert msg.answer.await_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == RESUBMIT_CB


@pytest.mark.asyncio
async def test_start_silent_for_others():
    msg = MagicMock()
    msg.from_user = MagicMock(id=7301)
    msg.answer = AsyncMock()
    with patch("uk_management_bot.handlers.base.run_db", AsyncMock(return_value=False)):
        from uk_management_bot.handlers.base import offer_resubmit_if_rejected
        await offer_resubmit_if_rejected(msg, "ru")
    msg.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_bot_rejection_message_carries_resubmit_button():
    from uk_management_bot.handlers.user_verification import access_decision
    from uk_management_bot.services.document_purge import PurgeResult

    cb = MagicMock()
    cb.data = "verify_reject_5"
    cb.from_user = MagicMock(id=9001)
    cb.answer = AsyncMock()
    cb.bot.send_message = AsyncMock()
    with patch.object(access_decision, "run_db",
                      AsyncMock(return_value=(PurgeResult(7301), (7301, "отказ"), "uz"))), \
         patch.object(access_decision, "cleanup_purged_documents", AsyncMock()):
        await access_decision.reject_user_verification(cb, roles=["manager"], language="ru")

    kb = cb.bot.send_message.await_args.kwargs["reply_markup"]
    button = kb.inline_keyboard[0][0]
    assert button.callback_data == RESUBMIT_CB
    assert button.text == get_text("verification_resubmit.btn", language="uz")  # язык жителя
