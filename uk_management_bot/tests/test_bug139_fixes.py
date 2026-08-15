"""BUG-139 — предсуществующие дефекты пакета handlers/address_apartments/.

  1. toggle_apartment_status терял language при перерисовке карточки
     (show_apartment_details(callback) без language → карточка всегда ru);
  2. delete_apartment терял language при возврате к списку
     (show_apartments_list(callback, None));
  3. FSM-цепочка создания/редактирования хардкодила
     get_main_keyboard_for_role("manager", ["manager"]) — реальные роли
     пользователя из middleware-контекста игнорировались;
  4. parse_apartment_range оборачивал ValueError дважды — пользователю уходило
     вложенное «Некорректный диапазон '…': Некорректный диапазон …».
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uk_management_bot.utils.helpers import get_text


def _make_callback(data):
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = 42
    cb.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    return cb


def _passed_values(await_args):
    args, kwargs = await_args
    return list(args[1:]) + list(kwargs.values())


async def test_toggle_apartment_status_passes_language():
    """1: перерисовка карточки после переключения статуса — на языке юзера."""
    from uk_management_bot.handlers.address_apartments import editing

    cb = _make_callback("addr_apartment_toggle:5")
    apartment = MagicMock()
    apartment.is_active = True

    # A2-хвост волна 6: db-фаза ушла в sync-юнит под run_db — сессия приходит
    # тестовым seam'ом _db, а не патчем session_scope.
    with patch.object(editing, "AddressService") as svc, \
         patch.object(editing, "show_apartment_details", new=AsyncMock()) as details:
        svc.get_apartment_by_id.return_value = apartment
        svc.update_apartment = AsyncMock(return_value=(apartment, None))
        await editing.toggle_apartment_status(cb, language="uz", _db=MagicMock())

    assert details.await_count == 1
    assert "uz" in _passed_values(details.await_args), (
        f"language не проброшен: {details.await_args}"
    )


async def test_delete_apartment_passes_language():
    """2: возврат к списку после удаления — на языке юзера."""
    from uk_management_bot.handlers.address_apartments import editing

    cb = _make_callback("addr_apartment_delete_confirm:5")

    with patch.object(editing, "AddressService") as svc, \
         patch.object(editing, "show_apartments_list", new=AsyncMock()) as listing:
        svc.delete_apartment = AsyncMock(return_value=(True, None))
        await editing.delete_apartment(cb, language="uz")

    assert listing.await_count == 1
    assert "uz" in _passed_values(listing.await_args), (
        f"language не проброшен: {listing.await_args}"
    )


async def test_edit_area_keyboard_uses_middleware_roles():
    """3 (editing.py): клавиатура после апдейта площади — от реальных ролей."""
    from uk_management_bot.handlers.address_apartments import editing

    message = MagicMock()
    message.text = "55"
    message.from_user.id = 42
    message.answer = AsyncMock()
    state = AsyncMock()
    state.get_data.return_value = {"editing_apartment_id": 3}

    with patch.object(editing, "AddressService") as svc, \
         patch.object(editing, "get_main_keyboard_for_role") as kb:
        svc.update_apartment = AsyncMock(return_value=(MagicMock(), None))
        await editing.process_new_apartment_area(
            message, state, language="ru",
            roles=["manager", "admin"], active_role="admin",
        )

    kb.assert_called_once()
    assert kb.call_args.args[0] == "admin"
    assert kb.call_args.args[1] == ["manager", "admin"]


async def test_creation_cancel_keyboard_uses_middleware_roles():
    """3 (creation.py): клавиатура при отмене создания — от реальных ролей."""
    from uk_management_bot.handlers.address_apartments import creation

    message = MagicMock()
    message.text = get_text("address.keyboards.cancel", language="ru")
    message.from_user.id = 42
    message.answer = AsyncMock()
    state = AsyncMock()

    with patch.object(creation, "get_main_keyboard_for_role") as kb:
        await creation.process_apartment_entrance(
            message, state, language="ru",
            roles=["manager", "admin"], active_role="admin",
        )

    kb.assert_called_once()
    assert kb.call_args.args[0] == "admin"
    assert kb.call_args.args[1] == ["manager", "admin"]


def test_parse_apartment_range_reversed_raises_single_error():
    """4: «5-1» → одна ошибка, не вложенная «Некорректный диапазон '…': Некорректный…»."""
    from uk_management_bot.handlers.address_apartments.autofill import parse_apartment_range

    with pytest.raises(ValueError) as ei:
        parse_apartment_range("5-1")
    assert str(ei.value).count("Некорректный диапазон") == 1, (
        f"вложенная обёртка: {ei.value}"
    )
