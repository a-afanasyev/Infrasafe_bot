"""Карточка смены исполнителя: каждая кнопка обязана иметь хендлер.

Ревью 2026-08-31 (docs/guides/SHIFTS.md, находка №1): клавиатура
`get_shift_actions_keyboard` со скаффолда 2025-09-26 показывала девять кнопок
без единого хендлера — «Связаться с менеджером», «Отклонить смену», «Перерыв»,
«Мои заявки», «Отметить локацию», «Заметка», «SOS», и весь completed-блок.
Нажатие молча не делало ничего.

Решение: мёртвые кнопки убраны, «Мои заявки» реализована редиректом на
существующий раздел заявок. Тест перечисляет ожидаемые callback'и ЯВНО —
новая кнопка без осознанного обновления списка (и, значит, без вопроса «а
хендлер есть?») роняет тест.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uk_management_bot.keyboards.my_shifts import get_shift_actions_keyboard


def _callbacks(markup) -> set:
    return {
        btn.callback_data
        for row in markup.inline_keyboard
        for btn in row
    }


def _shift(status: str, shift_id: int = 5):
    return SimpleNamespace(id=shift_id, status=status)


class TestEveryButtonHasHandler:
    def test_planned_shift_buttons(self):
        cbs = _callbacks(get_shift_actions_keyboard(_shift("planned")))
        assert cbs == {"start_shift", "transfer_shift:5", "view_current_shifts"}

    def test_active_shift_buttons(self):
        cbs = _callbacks(get_shift_actions_keyboard(_shift("active")))
        assert cbs == {
            "end_shift", "shift_requests:5", "transfer_shift:5",
            "view_current_shifts",
        }

    def test_completed_shift_has_only_back(self):
        cbs = _callbacks(get_shift_actions_keyboard(_shift("completed")))
        assert cbs == {"view_current_shifts"}


class TestShiftRequestsButton:
    @pytest.mark.asyncio
    async def test_opens_my_requests_with_active_filter(self):
        """Кнопка «Мои заявки» открывает существующий раздел заявок
        с фильтром «активные» и от имени НАЖАВШЕГО (не бота)."""
        from uk_management_bot.handlers.my_shifts import viewing

        callback = MagicMock()
        callback.data = "shift_requests:5"
        callback.from_user = SimpleNamespace(id=777)
        callback.message = MagicMock()
        callback.answer = AsyncMock()

        state = MagicMock()
        state.update_data = AsyncMock()

        with patch(
            "uk_management_bot.handlers.requests.show_my_requests",
            new=AsyncMock(),
        ) as shown:
            await viewing.open_shift_requests(
                callback, state, roles=["executor"]
            )

        state.update_data.assert_awaited_once_with(
            my_requests_status="active", my_requests_page=1
        )
        shown.assert_awaited_once()
        fake_message = shown.await_args.args[0]
        assert fake_message.from_user.id == 777  # from_user подменён на нажавшего
        callback.answer.assert_awaited()
