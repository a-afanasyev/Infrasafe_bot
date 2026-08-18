"""Пять `admin_*`-хендлеров квартир работали без проверки роли (аудит 2026-08-18).

`user_apartments.py` — смешанный роутер: жительские `my_apartments`/`set_primary:`/
`view_apartment:` живут рядом с пятью админскими `admin_*`. Роутер включён в
`main.py:390`, `callback_data` присылает клиент — «кнопку жителю не рисуем»
защитой не является (тот же класс, что BUG-154/172/175).

До guard'а житель callback'ом `admin_toggle_owner_<id>` переключал `is_owner`
ЛЮБОЙ записи, а `admin_approve_apartment_<id>` — одобрял привязку к квартире,
включая свою (привязка участвует в предикате доступа к заявкам → эскалация).

⚠️ Guard берёт роли из middleware (`@require_role` читает kwargs `roles`/`user`),
поэтому `roles`/`user` обязаны быть В СИГНАТУРАХ хендлеров: aiogram фильтрует
kwargs по сигнатуре, без параметров middleware их не передаст вовсе. Три
внутренних вызова `admin_apartment_detail` (после approve/reject/toggle) обязаны
передавать `roles=roles, user=user` — иначе настоящий менеджер получит отказ
сразу ПОСЛЕ успешного действия (см. прецедент test_request_assignment_guard).
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery

from uk_management_bot.handlers import user_apartments as ua
from uk_management_bot.utils.helpers import get_text

APPLICANT_ROLES = ["applicant"]
MANAGER_ROLES = ["manager"]

NO_ACCESS_TEXT = get_text("auth.no_access", language="ru")


class _FakeState:
    def __init__(self):
        self.cleared = False

    async def clear(self):
        self.cleared = True


def _callback(data: str, from_id: int = 777):
    # spec обязателен: require_role шлёт отказ только в isinstance(event, CallbackQuery)
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.from_user = MagicMock()
    cb.from_user.id = from_id
    cb.from_user.language_code = "ru"
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    return cb


def _forbidden_db():
    """Сессия, которая громко падает: guard обязан отказать ДО обращения к БД."""
    db = MagicMock()
    db.query.side_effect = AssertionError("guard пропустил жителя к БД")
    return db


def _apartment_view(apartment_id: int = 5) -> ua._ApartmentView:
    return ua._ApartmentView(
        id=apartment_id,
        status="pending",
        is_primary=False,
        is_owner=False,
        admin_comment=None,
        address="ул. Тестовая, 1, кв. 2",
        user_telegram_id=111,
        entrance=None,
        floor=None,
        rooms_count=None,
        area=None,
        requested_at=datetime(2026, 8, 1, 12, 0),
        reviewed_at=None,
        has_reviewer=False,
        reviewer_first_name=None,
        reviewer_username=None,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Житель (и отсутствие ролей вовсе) не проходит ни в один из пяти admin_*
# ══════════════════════════════════════════════════════════════════════════════

ADMIN_CALLS = [
    ("admin_manage_apartments_111", "admin_manage_user_apartments"),
    ("admin_apartment_detail_5", "admin_apartment_detail"),
    ("admin_approve_apartment_5", "admin_approve_apartment"),
    ("admin_reject_apartment_5", "admin_reject_apartment"),
    ("admin_toggle_owner_5", "admin_toggle_owner_status"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("callback_data,handler_name", ADMIN_CALLS)
async def test_admin_handlers_deny_applicant(callback_data, handler_name):
    handler = getattr(ua, handler_name)
    callback = _callback(callback_data)
    state = _FakeState()

    await handler(
        callback, state, language="ru",
        roles=APPLICANT_ROLES, user=None, _db=_forbidden_db(),
    )

    callback.answer.assert_awaited_once_with(NO_ACCESS_TEXT, show_alert=True)
    callback.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("callback_data,handler_name", ADMIN_CALLS)
@pytest.mark.parametrize("roles", [None, []])
async def test_admin_handlers_fail_closed_without_roles(callback_data, handler_name, roles):
    """roles=None/[] (нет middleware-данных) → отказ, не проход."""
    handler = getattr(ua, handler_name)
    callback = _callback(callback_data)

    kwargs = {"language": "ru", "user": None, "_db": _forbidden_db()}
    if roles is not None:
        kwargs["roles"] = roles

    await handler(callback, _FakeState(), **kwargs)

    callback.answer.assert_awaited_once_with(NO_ACCESS_TEXT, show_alert=True)
    callback.message.edit_text.assert_not_awaited()


# ══════════════════════════════════════════════════════════════════════════════
# Менеджер проходит, включая внутренние вызовы admin_apartment_detail
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_manager_passes_to_detail():
    callback = _callback("admin_apartment_detail_5")
    db = MagicMock()

    with patch.object(ua, "_load_admin_apartment_view", return_value=_apartment_view()):
        await ua.admin_apartment_detail(
            callback, _FakeState(), language="ru",
            roles=MANAGER_ROLES, user=None, _db=db,
        )

    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("callback_data,handler_name,unit_name,unit_result", [
    ("admin_approve_apartment_5", "admin_approve_apartment", "_admin_approve_apartment", "approved"),
    ("admin_reject_apartment_5", "admin_reject_apartment", "_admin_reject_apartment", "rejected"),
    ("admin_toggle_owner_5", "admin_toggle_owner_status", "_admin_toggle_owner", True),
])
async def test_manager_action_then_internal_detail_call_passes(
    callback_data, handler_name, unit_name, unit_result
):
    """После approve/reject/toggle хендлер зовёт admin_apartment_detail НАПРЯМУЮ.

    `require_role` читает kwargs — если внутренний вызов не передаст
    `roles`/`user`, менеджер получит `auth.no_access` сразу после успешного
    действия. Тест пиннит, что карточка отрендерена (edit_text awaited).
    """
    handler = getattr(ua, handler_name)
    callback = _callback(callback_data)
    db = MagicMock()

    with patch.object(ua, unit_name, return_value=unit_result), \
         patch.object(ua, "_load_admin_apartment_view", return_value=_apartment_view()):
        await handler(
            callback, _FakeState(), language="ru",
            roles=MANAGER_ROLES, user=None, _db=db,
        )

    callback.message.edit_text.assert_awaited_once()
    # отказа "auth.no_access" не было ни на одном из двух answer-вызовов
    for call in callback.answer.await_args_list:
        assert NO_ACCESS_TEXT not in (call.args or ("",))[0:1]
