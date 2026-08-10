"""
Regression tests for AUD3-15 — хрупкий разбор callback_data через split("_").

Verify-этап показал: из ~79 сайтов split("_") реально хрупких 6 — те, где
payload сам содержит "_", а парсер брал один сегмент:

1. handlers/user_verification.py  select_info_type
   request_info_{uid}_{info_type}: parts[3] обрезал property_deed → "property".
2. handlers/user_management/actions.py  check/uncheck_document, req_docs
   document_type/docs_str с "_" (property_deed, rental_agreement, utility_bill)
   обрезались на первом "_": галочки не снимались, запрос уходил с мусором.
3. handlers/user_management/roles_specs.py  role_add_/role_remove_
   split('_')[-1] превращал resource_meter_entry → "entry".

Фикс: разбор по фиксированному префиксу ("_".join(parts[N:]) / removeprefix),
формат callback_data НЕ менялся — «летящие» клавиатуры у пользователей
продолжают работать без переходного кода (это проверяют old-format тесты).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_callback(data: str, telegram_id: int = 555):
    cb = MagicMock()
    cb.from_user.id = telegram_id
    cb.data = data
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _make_state(data: dict | None = None) -> AsyncMock:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=data or {})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


# ---------------------------------------------------------------------------
# user_verification.select_info_type — request_info_{uid}_{info_type}
# ---------------------------------------------------------------------------

class TestSelectInfoType:
    @pytest.mark.asyncio
    async def test_info_type_with_underscore_not_truncated(self):
        from uk_management_bot.handlers.user_verification import select_info_type

        cb = _make_callback("request_info_123_property_deed")
        state = _make_state()

        await select_info_type(cb, state, roles=["manager"])

        state.update_data.assert_awaited_once_with(
            target_user_id=123, info_type="property_deed"
        )

    @pytest.mark.asyncio
    async def test_old_format_single_segment_still_works(self):
        """Payload без "_" (address/passport/other) — разбор не изменился."""
        from uk_management_bot.handlers.user_verification import select_info_type

        cb = _make_callback("request_info_7_address")
        state = _make_state()

        await select_info_type(cb, state, roles=["manager"])

        state.update_data.assert_awaited_once_with(
            target_user_id=7, info_type="address"
        )


# ---------------------------------------------------------------------------
# user_management/actions — чек-лист документов
# ---------------------------------------------------------------------------

class TestDocumentChecklist:
    @pytest.mark.asyncio
    async def test_check_document_underscore_type(self):
        from uk_management_bot.handlers.user_management.actions import (
            handle_check_document,
        )

        cb = _make_callback("check_document_5_rental_agreement")
        state = _make_state({"selected_documents": []})

        await handle_check_document(
            cb, state, db=MagicMock(), roles=["manager"], user=MagicMock()
        )

        state.update_data.assert_awaited_once_with(
            {"target_user_id": 5, "selected_documents": ["rental_agreement"]}
        )

    @pytest.mark.asyncio
    async def test_uncheck_document_underscore_type_actually_removes(self):
        """До фикса parts[3] давал "utility" — галочка никогда не снималась."""
        from uk_management_bot.handlers.user_management.actions import (
            handle_uncheck_document,
        )

        cb = _make_callback("uncheck_document_5_utility_bill")
        state = _make_state({"selected_documents": ["utility_bill", "passport"]})

        await handle_uncheck_document(
            cb, state, db=MagicMock(), roles=["manager"], user=MagicMock()
        )

        state.update_data.assert_awaited_once_with(
            {"target_user_id": 5, "selected_documents": ["passport"]}
        )

    @pytest.mark.asyncio
    async def test_req_docs_underscore_types_parsed_fully(self):
        """До фикса req_docs_5_property_deed,passport давал docs=["property"]."""
        from uk_management_bot.handlers.user_management.actions import (
            handle_request_selected_documents,
        )

        cb = _make_callback("req_docs_5_property_deed,passport")
        state = _make_state()
        manager = MagicMock()
        manager.id = 99
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = manager

        await handle_request_selected_documents(
            cb, state, db=db, roles=["manager"], user=MagicMock()
        )

        state.update_data.assert_awaited_once_with(
            {
                "action": "request_multiple_documents",
                "target_user_id": 5,
                "manager_id": 99,
                "selected_documents": ["property_deed", "passport"],
            }
        )


# ---------------------------------------------------------------------------
# user_management/roles_specs — role_add_/role_remove_
# ---------------------------------------------------------------------------

class TestRoleAddRemove:
    @pytest.mark.asyncio
    async def test_add_role_resource_meter_entry_not_truncated(self):
        """До фикса split('_')[-1] добавлял мусорную роль "entry"."""
        from uk_management_bot.handlers.user_management.roles_specs import (
            add_role_to_user,
        )

        cb = _make_callback("role_add_resource_meter_entry")
        state = _make_state({"current_roles": ["applicant"]})

        await add_role_to_user(cb, state)

        state.update_data.assert_awaited_once_with(
            current_roles=["applicant", "resource_meter_entry"]
        )

    @pytest.mark.asyncio
    async def test_remove_role_resource_meter_entry(self):
        from uk_management_bot.handlers.user_management.roles_specs import (
            remove_role_from_user,
        )

        cb = _make_callback("role_remove_resource_meter_entry")
        state = _make_state(
            {"current_roles": ["applicant", "resource_meter_entry"]}
        )

        await remove_role_from_user(cb, state)

        state.update_data.assert_awaited_once_with(current_roles=["applicant"])

    @pytest.mark.asyncio
    async def test_old_format_simple_role_still_works(self):
        """Роли без "_" (manager и т.п.) — «летящие» клавиатуры не ломаются."""
        from uk_management_bot.handlers.user_management.roles_specs import (
            add_role_to_user,
        )

        cb = _make_callback("role_add_manager")
        state = _make_state({"current_roles": ["applicant"]})

        await add_role_to_user(cb, state)

        state.update_data.assert_awaited_once_with(
            current_roles=["applicant", "manager"]
        )
