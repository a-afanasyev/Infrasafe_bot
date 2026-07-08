"""Инвайт: само-онбординговый pending-applicant должен проходить /join.

Баг (profk, 2026-07-08): инструкция кандидату «нажмите Начать, затем /join
<token>». Шаг «Начать» = обычный /start, который создаёт pending-applicant, а
последующий /join отвергал его как «уже зарегистрирован (pending)» →
кандидат-менеджер в тупике. Плюс завершение регистрации звало no-op
``sync_legacy_role`` и не добавляло роль/не гасило nonce.

Здесь фиксируем корректное поведение:
  1. pending-applicant (roles ровно ["applicant"]) НЕ отвергается — уходит в FSM.
  2. pending-пользователь, уже поднявший роль по инвайту (roles шире applicant),
     по-прежнему отвергается.
  3. Завершение регистрации применяет роль через ``process_invite_join`` и
     атомарно гасит nonce (``validate_invite(mark_used_by=...)``).
"""
from __future__ import annotations

import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uk_management_bot.handlers import auth as auth_handlers
from uk_management_bot.states.registration import RegistrationStates


def _pending_applicant(roles: str = '["applicant"]'):
    return types.SimpleNamespace(
        id=4, telegram_id=7124503338, status="pending",
        roles=roles, active_role="applicant",
        first_name="Test", last_name="User", phone="+998900000000",
        specialization=None,
    )


def _state(data=None):
    store = dict(data or {})

    async def _get_data():
        return dict(store)

    async def _update_data(**kwargs):
        store.update(kwargs)
        return dict(store)

    st = AsyncMock()
    st.get_data = AsyncMock(side_effect=_get_data)
    st.update_data = AsyncMock(side_effect=_update_data)
    return st


@pytest.mark.asyncio
async def test_pending_applicant_passes_join():
    """pending-applicant не отвергается: /join уводит его в FSM регистрации."""
    msg = MagicMock()
    msg.from_user.id = 7124503338
    msg.text = "/join invite_v1:sometoken"
    msg.answer = AsyncMock()
    st = _state()

    inv = MagicMock()
    inv.validate_invite.return_value = {"role": "manager", "specialization": ""}

    auth_svc = MagicMock()
    auth_svc.get_user_by_telegram_id = AsyncMock(return_value=_pending_applicant())

    with patch.object(auth_handlers, "InviteService", return_value=inv), \
         patch.object(auth_handlers, "AuthService", return_value=auth_svc), \
         patch.object(auth_handlers.InviteRateLimiter, "is_allowed",
                      AsyncMock(return_value=True)):
        await auth_handlers.join_with_invite(msg, st, MagicMock(), language="ru")

    st.set_state.assert_awaited_with(RegistrationStates.waiting_for_full_name)


@pytest.mark.asyncio
async def test_pending_upgraded_user_still_rejected():
    """pending-пользователь с ролью сверх applicant — по-прежнему отвергается."""
    msg = MagicMock()
    msg.from_user.id = 7124503338
    msg.text = "/join invite_v1:sometoken"
    msg.answer = AsyncMock()
    st = _state()

    inv = MagicMock()
    inv.validate_invite.return_value = {"role": "manager", "specialization": ""}

    auth_svc = MagicMock()
    auth_svc.get_user_by_telegram_id = AsyncMock(
        return_value=_pending_applicant(roles='["applicant", "manager"]'))

    with patch.object(auth_handlers, "InviteService", return_value=inv), \
         patch.object(auth_handlers, "AuthService", return_value=auth_svc), \
         patch.object(auth_handlers.InviteRateLimiter, "is_allowed",
                      AsyncMock(return_value=True)):
        await auth_handlers.join_with_invite(msg, st, MagicMock(), language="ru")

    st.set_state.assert_not_awaited()
    msg.answer.assert_awaited()  # получил отказ (registration_pending)


@pytest.mark.asyncio
async def test_completion_applies_role_and_consumes_nonce():
    """confirm_position: роль применяется через process_invite_join, nonce гасится."""
    cb = MagicMock()
    cb.from_user.id = 7124503338
    cb.from_user.username = "cand"
    cb.from_user.first_name = "Cand"
    cb.from_user.last_name = ""
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    cb.bot.send_message = AsyncMock()
    st = _state({
        "full_name": "Иван Петров", "phone": "+998901112233",
        "invite_role": "manager", "invite_specialization": "",
        "invite_token": "invite_v1:sometoken",
    })

    joined_user = _pending_applicant(roles='["applicant", "manager"]')
    joined_user.active_role = "manager"
    joined_user.created_at = None

    inv = MagicMock()
    inv.validate_invite.return_value = {"role": "manager", "specialization": "", "nonce": "n"}

    auth_svc = MagicMock()
    auth_svc.process_invite_join = AsyncMock(return_value=joined_user)
    auth_svc.get_users_by_role = AsyncMock(return_value=[])

    db = MagicMock()

    with patch.object(auth_handlers, "InviteService", return_value=inv), \
         patch.object(auth_handlers, "AuthService", return_value=auth_svc):
        await auth_handlers.handle_position_confirmation(cb, st, db, language="ru")

    # nonce погашен атомарно (mark_used_by = telegram_id кандидата)
    inv.validate_invite.assert_called_once()
    assert inv.validate_invite.call_args.kwargs.get("mark_used_by") == 7124503338
    # роль применена штатной логикой присоединения
    auth_svc.process_invite_join.assert_awaited_once()
