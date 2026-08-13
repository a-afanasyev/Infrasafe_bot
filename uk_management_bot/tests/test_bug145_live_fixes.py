"""BUG-145 — живые дефекты пакета request_status_management.

Живой вход пакета один: менеджерский «Закуп» (handlers/admin/actions.py)
ставит RequestStatusStates.waiting_for_materials, ввод ловит
handle_materials_input → _apply_purchase. Тесты фиксируют два дефекта
этого пути:
  4. message.text = None (фото в стейте ввода) ронял хендлер AttributeError
     → пользователь видел generic error_occurred вместо просьбы ввести текст;
  5. post-commit перечитка заявки в _apply_purchase не проверяла None —
     конкурентное удаление после успешного канон-перехода давало
     AttributeError.
"""
from unittest.mock import AsyncMock, MagicMock, patch

from uk_management_bot.handlers.request_status_management._units import (
    _apply_purchase,
)
from uk_management_bot.handlers.request_status_management.executor_actions import (
    handle_materials_input,
)
from uk_management_bot.utils.helpers import get_text


async def test_materials_input_with_photo_prompts_instead_of_error():
    """Не-текст в стейте ввода материалов → просьба ввести список, не ошибка."""
    message = MagicMock()
    message.text = None  # фото/стикер/войс
    message.answer = AsyncMock()
    state = MagicMock()
    state.get_data = AsyncMock(return_value={"request_number": "260101-001"})
    state.clear = AsyncMock()

    await handle_materials_input(message, state, language="ru", user=None, _db=MagicMock())

    message.answer.assert_awaited_once()
    sent = message.answer.call_args[0][0]
    assert sent == get_text(
        "request_status_mgmt.handlers.please_enter_materials", language="ru"
    ), f"вместо просьбы ввести материалы ушло: {sent!r}"
    state.clear.assert_not_awaited()


def test_apply_purchase_concurrent_deletion_returns_no_request():
    """Заявка удалена между канон-переходом и post-commit перечиткой —
    юнит обязан вернуть исход no_request, а не падать AttributeError."""
    db = MagicMock()
    request = MagicMock()
    request.requested_materials = None
    request.purchase_history = None
    # первый first() — заявка есть; после успешного перехода — уже удалена
    db.query.return_value.filter.return_value.first.side_effect = [request, None]

    with patch(
        "uk_management_bot.handlers.request_status_management._units.RequestService"
    ) as rs:
        rs.return_value.update_status_by_actor.return_value = {"success": True}
        out = _apply_purchase(db, "260101-001", "цемент 2 мешка", 999, commenter_id=None)

    assert out.outcome == "no_request", f"получен исход {out.outcome!r}"
