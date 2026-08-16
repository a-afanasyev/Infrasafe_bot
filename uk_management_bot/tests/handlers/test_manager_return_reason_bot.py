"""Бот-кнопка «вернуть в работу» теперь спрашивает причину.

Раньше она сразу исполняла переход с пустым payload — исполнитель получал
уведомление «заявка возвращена» без единого слова о том, что не так. Теперь
кнопка ставит FSM-состояние `awaiting_return_to_work_reason` (оно было
объявлено, но не использовалось), а переход исполняет message-хендлер.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from uk_management_bot.states.request_acceptance import ManagerAcceptanceStates


class _State:
    def __init__(self, data=None):
        self._data = dict(data or {})
        self.state = None

    async def update_data(self, **kwargs):
        self._data.update(kwargs)

    async def get_data(self):
        return dict(self._data)

    async def set_state(self, state):
        self.state = state

    async def clear(self):
        self.state = None
        self._data = {}


def _manager():
    return SimpleNamespace(id=5, telegram_id=555, roles='["manager"]', active_role="manager")


def _applicant():
    """has_admin_access смотрит и на user.roles — житель должен быть жителем
    в обоих источниках, иначе тест проверяет не то."""
    return SimpleNamespace(id=9, telegram_id=999, roles='["applicant"]', active_role="applicant")


def _callback(request_number="260817-001"):
    cb = MagicMock()
    cb.data = f"return_to_work_{request_number}"
    cb.id = "cb-1"
    cb.from_user = SimpleNamespace(id=555)
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    cb.bot = MagicMock()
    return cb


class TestButtonAsksForReason:
    @pytest.mark.asyncio
    async def test_button_does_not_execute_transition(self, monkeypatch):
        """Ключевое: клик по кнопке больше не меняет статус сам по себе."""
        from uk_management_bot.handlers.admin import views

        calls = []
        monkeypatch.setattr(
            "uk_management_bot.services.workflow_runner.run_command_sync",
            lambda *a, **kw: calls.append(a),
        )
        state = _State()
        callback = _callback()

        await views.handle_manager_return_to_work(
            callback, state, db=MagicMock(), roles=["manager"],
            user=_manager(), language="ru",
        )

        assert calls == [], "переход обязан ждать причину"
        assert state.state == ManagerAcceptanceStates.awaiting_return_to_work_reason
        assert (await state.get_data())["return_to_work_number"] == "260817-001"
        callback.message.edit_text.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_access_does_not_set_state(self):
        from uk_management_bot.handlers.admin import views

        state = _State()
        callback = _callback()

        await views.handle_manager_return_to_work(
            callback, state, db=MagicMock(), roles=["applicant"],
            user=_applicant(), language="ru",
        )

        assert state.state is None
        callback.answer.assert_awaited()


class TestReasonHandlerExecutes:
    @pytest.mark.asyncio
    async def test_reason_reaches_the_engine(self, monkeypatch):
        from uk_management_bot.handlers.admin import views

        captured = {}

        def _fake_run(_sf, number, principal, command, *a, **kw):
            captured["number"] = number
            captured["payload"] = dict(command.payload)
            return SimpleNamespace(
                post_commit_intents=[], old_status="Возвращена",
                public_status="В работе",
            )

        monkeypatch.setattr(
            "uk_management_bot.services.workflow_runner.run_command_sync", _fake_run,
        )
        # Патчим в модуле, где имена ИМПОРТИРОВАНЫ (views), а не там, где
        # объявлены — иначе хендлер продолжит звать оригиналы.
        monkeypatch.setattr(views, "dispatch_notify_intents_sync", AsyncMock())
        monkeypatch.setattr(views, "notify_channel_status_changed", AsyncMock())
        monkeypatch.setattr(views, "AdminHandlerService", MagicMock())

        message = MagicMock()
        message.text = "Плитка положена криво, переделать шов"
        message.from_user = SimpleNamespace(id=555)
        message.answer = AsyncMock()
        message.bot = MagicMock()
        state = _State({"return_to_work_number": "260817-001"})

        await views.handle_return_to_work_reason(
            message, state, db=MagicMock(), roles=["manager"],
            user=_manager(), language="ru",
        )

        assert captured["number"] == "260817-001"
        assert captured["payload"]["reason"] == "Плитка положена криво, переделать шов"
        assert state.state is None, "состояние должно быть снято после исполнения"

    @pytest.mark.asyncio
    async def test_blank_reason_asks_again(self, monkeypatch):
        """Пустой ввод не отправляем в движок — переспрашиваем."""
        from uk_management_bot.handlers.admin import views

        calls = []
        monkeypatch.setattr(
            "uk_management_bot.services.workflow_runner.run_command_sync",
            lambda *a, **kw: calls.append(a),
        )

        message = MagicMock()
        message.text = "   "
        message.from_user = SimpleNamespace(id=555)
        message.answer = AsyncMock()
        state = _State({"return_to_work_number": "260817-001"})

        await views.handle_return_to_work_reason(
            message, state, db=MagicMock(), roles=["manager"],
            user=_manager(), language="ru",
        )

        assert calls == []
        assert state.state is None or state.state == ManagerAcceptanceStates.awaiting_return_to_work_reason
        message.answer.assert_awaited()


class TestCancelClearsState:
    """Отмена обязана снимать FSM.

    Иначе состояние «жду причину» переживало бы отмену, и СЛЕДУЮЩЕЕ любое
    сообщение менеджера (заметка, ответ в другом диалоге) было бы съедено как
    причина и молча вернуло бы заявку в работу — с чужим текстом в карточке и
    уведомлением исполнителю о возврате, которого никто не заказывал.
    """

    @pytest.mark.asyncio
    async def test_cancel_clears_fsm(self):
        from uk_management_bot.handlers.admin import views

        state = _State({"return_to_work_number": "260817-001"})
        await state.set_state(ManagerAcceptanceStates.awaiting_return_to_work_reason)
        callback = _callback()
        callback.data = "rtw_cancel_260817-001"

        await views.handle_return_to_work_cancel(callback, state, language="ru")

        assert state.state is None
        assert await state.get_data() == {}

    @pytest.mark.asyncio
    async def test_cancel_button_does_not_reuse_view_callback(self, monkeypatch):
        """Общий `view_` не чистит состояние — кнопка обязана иметь свой."""
        from uk_management_bot.handlers.admin import views

        monkeypatch.setattr(
            "uk_management_bot.services.workflow_runner.run_command_sync",
            lambda *a, **kw: None,
        )
        state = _State()
        callback = _callback()

        await views.handle_manager_return_to_work(
            callback, state, db=MagicMock(), roles=["manager"],
            user=_manager(), language="ru",
        )

        markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
        callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
        assert callbacks == ["rtw_cancel_260817-001"]

