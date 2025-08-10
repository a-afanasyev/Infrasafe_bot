import asyncio
import types
import pytest

from uk_management_bot.handlers import requests as handlers
from uk_management_bot.keyboards import requests as kb
from uk_management_bot.utils.constants import REQUEST_CATEGORIES, REQUEST_URGENCIES


class DummyUser:
    def __init__(self, user_id: int):
        self.id = user_id


class DummyMessage:
    def __init__(self, user_id: int, text: str = ""):
        self.from_user = DummyUser(user_id)
        self.text = text
        self.last_answer = None
        self.last_edit = None

    async def answer(self, text: str, reply_markup=None):
        self.last_answer = {"text": text, "reply_markup": reply_markup}

    async def edit_text(self, text: str, reply_markup=None):
        self.last_edit = {"text": text, "reply_markup": reply_markup}


class DummyCallback:
    def __init__(self, user_id: int, data: str):
        self.from_user = DummyUser(user_id)
        self.data = data
        self.message = DummyMessage(user_id)
        self.last_alert = None

    async def answer(self, text: str, show_alert: bool = False):
        self.last_alert = {"text": text, "show_alert": show_alert}


class DummyState:
    def __init__(self):
        self._data = {}
        self._state = None

    async def update_data(self, **kwargs):
        self._data.update(kwargs)

    async def set_state(self, state):
        self._state = state

    async def get_state(self):
        return self._state

    async def get_data(self):
        return dict(self._data)

    async def clear(self):
        self._data.clear()
        self._state = None


@pytest.mark.asyncio
async def test_categories_inline_keyboard_contents():
    mk = kb.get_categories_inline_keyboard()
    # Проверяем, что все категории присутствуют и callback_data формируется корректно
    flattened = [btn for row in mk.inline_keyboard for btn in row]
    texts = [btn.text for btn in flattened]
    datas = [btn.callback_data for btn in flattened]

    assert texts == REQUEST_CATEGORIES
    assert all(data.startswith("category_") for data in datas)


@pytest.mark.asyncio
async def test_urgency_inline_keyboard_contents():
    mk = kb.get_urgency_inline_keyboard()
    flattened = [btn for row in mk.inline_keyboard for btn in row]
    texts = [btn.text for btn in flattened]
    datas = [btn.callback_data for btn in flattened]

    assert texts == REQUEST_URGENCIES
    assert all(data.startswith("urgency_") for data in datas)


@pytest.mark.asyncio
async def test_handle_category_selection_transitions_and_saves(monkeypatch):
    # Мокаем клавиатуру выбора адреса, чтобы не трогать БД
    async def dummy_get_address_selection_keyboard(user_id: int):
        return kb.get_cancel_keyboard()

    monkeypatch.setattr(handlers, "get_address_selection_keyboard", dummy_get_address_selection_keyboard)

    state = DummyState()
    callback = DummyCallback(user_id=123, data=f"category_{REQUEST_CATEGORIES[0]}")

    await handlers.handle_category_selection(callback, state)

    data = await state.get_data()
    assert data.get("category") == REQUEST_CATEGORIES[0]
    assert await state.get_state() == handlers.RequestStates.address
    assert callback.message.last_edit is not None
    assert "Выбрана категория" in callback.message.last_edit["text"]


@pytest.mark.asyncio
async def test_handle_urgency_selection_transitions_and_saves():
    state = DummyState()
    callback = DummyCallback(user_id=123, data=f"urgency_{REQUEST_URGENCIES[0]}")

    await handlers.handle_urgency_selection(callback, state)
    data = await state.get_data()
    assert data.get("urgency") == REQUEST_URGENCIES[0]
    assert await state.get_state() == handlers.RequestStates.apartment
    assert callback.message.last_edit is not None
    assert "Выбрана срочность" in callback.message.last_edit["text"]


