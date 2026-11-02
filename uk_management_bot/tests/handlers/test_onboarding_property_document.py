"""Документ на квартиру обязателен в онбординге (решение владельца 2026-11-03).

«Завершить» и старая «Пропустить» решаются ОДНИМ итогом `_documents_outcome`:
проверенному — «уже пройдено» (загрузка ему закрыта, слать в неё — тупик),
отклонённому — переподача, без документа на квартиру — требование загрузить.
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message

from uk_management_bot.keyboards.documents_entry import RESUBMIT_CB
from uk_management_bot.states.onboarding import OnboardingStates
from uk_management_bot.tests.handlers.routing_probe import make_message, resolve_ctx
from uk_management_bot.utils.helpers import get_text

ONB = "uk_management_bot.handlers.onboarding"


def _t(key: str) -> str:
    return get_text(key, language="ru")


def _msg(text: str):
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.from_user = MagicMock(id=123)
    msg.answer = AsyncMock()
    return msg


def _state():
    st = MagicMock()
    st.set_state = AsyncMock()
    st.clear = AsyncMock()
    return st


def _summary(*types: str) -> dict:
    return {"total_documents": len(types), "documents_by_type": {t: 1 for t in types}}


class TestDocumentsOutcome:
    @pytest.mark.parametrize("status,types,expected", [
        ("verified", (), "verified"),
        ("rejected", ("property_deed",), "resubmit"),
        ("pending", (), "need_doc"),
        ("requested", ("passport",), "need_doc"),
        ("pending", ("property_deed",), "done"),
        ("requested", ("rental_agreement", "passport"), "done"),
    ])
    def test_table(self, status, types, expected):
        from uk_management_bot.handlers.onboarding import _documents_outcome

        assert _documents_outcome(status, _summary(*types)["documents_by_type"]) == expected


async def _complete(loaded, text="✅ Завершить онбординг"):
    from uk_management_bot.handlers import onboarding

    msg, state = _msg(text), _state()
    with patch(f"{ONB}.run_db", new=AsyncMock(return_value=loaded)):
        await onboarding.complete_onboarding_with_documents(msg, state, language="ru")
    return msg, state


class TestCompleteOnboarding:
    @pytest.mark.asyncio
    async def test_without_property_document_stays_on_documents_step(self):
        msg, state = await _complete(("pending", _summary("passport"), "pending"))

        assert msg.answer.await_args.args[0] == _t("onboarding.documents.property_required")
        state.set_state.assert_awaited_once_with(OnboardingStates.waiting_for_document_type)
        state.clear.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_with_rental_agreement_completes(self):
        msg, state = await _complete(("pending", _summary("rental_agreement"), "pending"))

        text = msg.answer.await_args.args[0]
        assert _t("onboarding.completed") in text
        state.clear.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_verified_is_not_sent_back_to_upload(self):
        """Менеджер подтвердил → документы удалены и загрузка закрыта; старая
        кнопка «Завершить» не должна требовать документ заново."""
        msg, state = await _complete(("approved", _summary(), "verified"))

        assert msg.answer.await_args.args[0] == _t("onboarding.documents.already_verified")
        state.set_state.assert_not_awaited()
        state.clear.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rejected_gets_resubmit(self):
        msg, state = await _complete(("pending", _summary(), "rejected"))

        kwargs = msg.answer.await_args.kwargs
        callbacks = [b.callback_data for row in kwargs["reply_markup"].inline_keyboard for b in row]
        assert callbacks == [RESUBMIT_CB]
        state.set_state.assert_not_awaited()


class TestLegacySkipButton:
    def _routers(self):
        import uk_management_bot.main as main_mod

        order = re.findall(r"dp\.include_router\((\w+)\)", Path(main_mod.__file__).read_text())
        return [getattr(main_mod, name) for name in order]

    @pytest.mark.parametrize("lang", ["ru", "uz"])
    def test_routes_to_compat_handler_outside_fsm(self, lang):
        text = get_text("onboarding.keyboards.skip_documents", language=lang)
        winner = resolve_ctx(self._routers(), make_message(text), "message",
                             roles=["applicant"], user=None)
        assert winner == (ONB, "skip_documents_legacy")

    @pytest.mark.asyncio
    async def test_skip_without_document_requires_it(self):
        from uk_management_bot.handlers import onboarding

        msg, state = _msg(_t("onboarding.keyboards.skip_documents")), _state()
        with patch(f"{ONB}.run_db", new=AsyncMock(return_value=("pending", _summary(), "pending"))):
            await onboarding.skip_documents_legacy(msg, state, language="ru")

        assert msg.answer.await_args.args[0] == _t("onboarding.documents.property_required")

    @pytest.mark.asyncio
    async def test_skip_when_verified_does_not_open_upload(self):
        from uk_management_bot.handlers import onboarding

        msg, state = _msg(_t("onboarding.keyboards.skip_documents")), _state()
        with patch(f"{ONB}.run_db", new=AsyncMock(return_value=("approved", _summary(), "verified"))):
            await onboarding.skip_documents_legacy(msg, state, language="ru")

        assert msg.answer.await_args.args[0] == _t("onboarding.documents.already_verified")
        state.set_state.assert_not_awaited()
