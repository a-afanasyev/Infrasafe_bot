import pytest

from uk_management_bot.handlers import requests as handlers


class DummyUser:
    def __init__(self, user_id: int):
        self.id = user_id


class DummyMessage:
    def __init__(self, user_id: int):
        self.from_user = DummyUser(user_id)
        self.last_answer = None

    async def answer(self, text, reply_markup=None):
        self.last_answer = {"text": text, "reply_markup": reply_markup}


class DummyCallback:
    def __init__(self, user_id: int, data: str):
        self.from_user = DummyUser(user_id)
        self.data = data
        self.message = DummyMessage(user_id)
        self._answered = False

    async def answer(self, text: str = "", show_alert: bool = False):
        self._answered = True


class DummyState:
    def __init__(self, initial=None):
        self._data = dict(initial or {})

    async def update_data(self, **kwargs):
        self._data.update(kwargs)

    async def get_data(self):
        return dict(self._data)


@pytest.mark.asyncio
async def test_status_filter_saves_state_and_resets_page():
    state = DummyState({"my_requests_page": 3})
    cb = DummyCallback(user_id=111, data="status_В работе")

    await handlers.handle_status_filter(cb, state)
    data = await state.get_data()
    assert data.get("my_requests_status") == "В работе"
    assert data.get("my_requests_page") == 1


@pytest.mark.asyncio
async def test_category_filter_saves_state_and_resets_page():
    state = DummyState({"my_requests_page": 2})
    cb = DummyCallback(user_id=111, data="categoryfilter_Электрика")

    await handlers.handle_category_filter(cb, state)
    data = await state.get_data()
    assert data.get("my_requests_category") == "Электрика"
    assert data.get("my_requests_page") == 1


@pytest.mark.asyncio
async def test_filters_reset_sets_defaults():
    state = DummyState({"my_requests_page": 5, "my_requests_status": "В работе", "my_requests_category": "Электрика"})
    cb = DummyCallback(user_id=111, data="filters_reset")

    await handlers.handle_filters_reset(cb, state)
    data = await state.get_data()
    assert data.get("my_requests_page") == 1
    assert data.get("my_requests_status") == "all"
    assert data.get("my_requests_category") == "all"
    assert data.get("my_requests_period") == "all"
    assert data.get("my_requests_executor") == "all"

