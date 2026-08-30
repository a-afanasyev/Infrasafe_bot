"""PR-15 — SEC-03: WS-токен из query-string.

`authenticate_ws_manager` поддерживает 2 источника токена с приоритетом
cookie → первое WS-сообщение (secure-путь для cookieless-клиентов).
Query-путь (`?token=`) снят после срока депрекации 2026-09-01: токен-подобный
query-параметр отклоняется ДО accept, зеркально панели охраны
(`access_control/api/ws_security._has_query_token`). Проверяем каждый путь +
role-gate + accept/close.

F-04 (аудит 2026-07-11): токен обязан нести числовой exp, стрим живёт не дольше
exp и закрывается выделенным кодом 4001 (клиент обновляет сессию и возвращается).

⚠️ Уровень этого файла — НАМЕРЕНИЕ хендлера, не провод. `FakeWS` записывает
аргумент `close(code=...)` даже тогда, когда апгрейда не было и close-кадра на
проводе не существует: до `accept()` uvicorn отвечает HTTP 403, и код 1008
никуда не уходит. Поэтому `closed_code == 1008` здесь читается как «хендлер
отказал», а НЕ как «клиент получил 1008» — ниже это помечено у каждого
pre-accept случая. Контракт провода живёт отдельно и проверяется живым
ASGI-сервером: `tests/api/test_ws_wire_protocol.py`.
"""
import asyncio
import time

import pytest
from fastapi import WebSocketDisconnect

from uk_management_bot.api.ws import router as ws


class FakeWS:
    def __init__(self, cookies=None, messages=None, hang=False, query_params=None):
        # PENT-F05: у настоящего WebSocket заголовки есть ВСЕГДА. Дубль без
        # `headers` ронял Origin-гейт на AttributeError, то есть моделировал
        # объект, которого не бывает. Пустые заголовки = не-браузерный
        # клиент — валидный сценарий, гейт его пропускает. То же про
        # `query_params` — у настоящего WebSocket они есть всегда.
        self.headers: dict = {}
        self.query_params: dict = query_params or {}
        self.cookies = cookies or {}
        self._messages = list(messages or [])
        self._hang = hang
        self.accepted = False
        self.closed_code = "NOT_CLOSED"

    async def accept(self):
        self.accepted = True

    async def close(self, code=None):
        self.closed_code = code

    async def receive_text(self):
        if self._hang:
            await asyncio.sleep(5)  # длиннее таймаута — провоцируем TimeoutError
        if not self._messages:
            raise WebSocketDisconnect()
        return self._messages.pop(0)


@pytest.fixture
def manager_token(monkeypatch):
    """verify_access_token("good") → manager payload; иначе None.

    Плюс заглушка проверки личности в БД: с F-04 (остаток) роль решает БД, а не
    токен. Здесь БД «согласна» с токеном — эти тесты про ИСТОЧНИК токена, и
    расхождение токен↔БД проверяется отдельно, в test_ws_live_authorization.py.
    """
    def _verify(tok):
        # exp обязателен с F-04 — payload без него отклоняется (см. TestExpClaim).
        if tok == "good":
            return {"sub": "1", "roles": ["manager"], "exp": time.time() + 3600}
        if tok == "applicant":
            return {"sub": "2", "roles": ["applicant"], "exp": time.time() + 3600}
        return None
    monkeypatch.setattr(ws, "verify_access_token", _verify)

    async def _identity_ok(user_id):
        return user_id == 1  # 1 — менеджер, 2 — заявитель

    monkeypatch.setattr(ws, "_ws_identity_ok", _identity_ok)


# ---------------------------------------------------------------------------
# _extract_token_from_message
# ---------------------------------------------------------------------------

class TestExtractToken:
    def test_json_token_field(self):
        assert ws._extract_token_from_message('{"token": "abc"}') == "abc"

    def test_json_type_auth(self):
        assert ws._extract_token_from_message('{"type":"auth","token":"xyz"}') == "xyz"

    def test_bare_string(self):
        assert ws._extract_token_from_message("rawtoken") == "rawtoken"

    def test_empty_returns_none(self):
        assert ws._extract_token_from_message("") is None

    def test_json_without_token_returns_none(self):
        assert ws._extract_token_from_message('{"foo": 1}') is None

    def test_whitespace_token_returns_none(self):
        assert ws._extract_token_from_message('{"token": "  "}') is None


# ---------------------------------------------------------------------------
# cookie path (preferred)
# ---------------------------------------------------------------------------

class TestCookiePath:
    @pytest.mark.asyncio
    async def test_uk_access_cookie_manager_ok(self, manager_token, caplog):
        wsk = FakeWS(cookies={"uk_access": "good"})
        payload = await ws.authenticate_ws_manager(wsk)
        assert payload and "manager" in payload["roles"]
        assert wsk.accepted is True
        assert wsk.closed_code == "NOT_CLOSED"
        # cookie-путь не пишет deprecation
        assert "DEPRECATED" not in caplog.text

    @pytest.mark.asyncio
    async def test_legacy_access_token_cookie_ok(self, manager_token):
        wsk = FakeWS(cookies={"access_token": "good"})
        payload = await ws.authenticate_ws_manager(wsk)
        assert payload is not None
        assert wsk.accepted is True

    @pytest.mark.asyncio
    async def test_non_manager_cookie_rejected_pre_accept(self, manager_token):
        wsk = FakeWS(cookies={"uk_access": "applicant"})
        payload = await ws.authenticate_ws_manager(wsk)
        assert payload is None
        assert wsk.accepted is False  # отклоняем ДО accept → на проводе HTTP 403
        assert wsk.closed_code == 1008  # намерение хендлера; клиент увидит 1006


# ---------------------------------------------------------------------------
# query path (REMOVED after 2026-09-01)
# ---------------------------------------------------------------------------

class TestQueryPath:
    """Само ПРИСУТСТВИЕ токен-подобного ключа в query фатально, даже с валидным
    значением или валидной кукой рядом: токен уже утёк в access-логи, и клиенту
    нужен внятный отказ, а не 10-секундное зависание на first-message-таймауте.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("key", ["token", "access_token", "jwt"])
    async def test_query_token_rejected_pre_accept(self, manager_token, key):
        wsk = FakeWS(query_params={key: "good"})  # токен валиден — не важно
        payload = await ws.authenticate_ws_manager(wsk)
        assert payload is None
        assert wsk.accepted is False  # → на проводе HTTP 403, не close-кадр
        assert wsk.closed_code == 1008

    @pytest.mark.asyncio
    async def test_query_token_rejected_even_with_valid_cookie(self, manager_token):
        wsk = FakeWS(cookies={"uk_access": "good"}, query_params={"token": "good"})
        payload = await ws.authenticate_ws_manager(wsk)
        assert payload is None
        assert wsk.accepted is False

    @pytest.mark.asyncio
    async def test_unrelated_query_params_ignored(self, manager_token):
        wsk = FakeWS(cookies={"uk_access": "good"}, query_params={"v": "2"})
        payload = await ws.authenticate_ws_manager(wsk)
        assert payload is not None
        assert wsk.accepted is True


# ---------------------------------------------------------------------------
# first-message path (secure, cookieless)
# ---------------------------------------------------------------------------

class TestFirstMessagePath:
    @pytest.mark.asyncio
    async def test_first_message_token_ok(self, manager_token, caplog):
        wsk = FakeWS(messages=['{"token": "good"}'])
        payload = await ws.authenticate_ws_manager(wsk)
        assert payload is not None
        assert wsk.accepted is True  # accept до получения сообщения
        assert wsk.closed_code == "NOT_CLOSED"
        assert "DEPRECATED" not in caplog.text  # не query — без warning

    @pytest.mark.asyncio
    async def test_first_message_non_manager_closed(self, manager_token):
        wsk = FakeWS(messages=['{"token": "applicant"}'])
        payload = await ws.authenticate_ws_manager(wsk)
        assert payload is None
        assert wsk.accepted is True
        assert wsk.closed_code == 1008

    @pytest.mark.asyncio
    async def test_first_message_disconnect_returns_none(self, manager_token):
        wsk = FakeWS(messages=[])  # receive_text → WebSocketDisconnect
        payload = await ws.authenticate_ws_manager(wsk)
        assert payload is None
        assert wsk.accepted is True
        assert wsk.closed_code == 1008

    @pytest.mark.asyncio
    async def test_first_message_timeout_returns_none(self, manager_token, monkeypatch):
        monkeypatch.setattr(ws, "_WS_AUTH_MESSAGE_TIMEOUT", 0.05)
        wsk = FakeWS(hang=True)
        payload = await ws.authenticate_ws_manager(wsk)
        assert payload is None
        assert wsk.accepted is True
        assert wsk.closed_code == 1008


# ---------------------------------------------------------------------------
# F-04: обязательный числовой exp + закрытие стрима по истечению (код 4001)
# ---------------------------------------------------------------------------

class _SilentPubSub:
    """PubSub без сообщений: стрим ждёт вечно, закрыть его может только exp."""

    async def listen(self):
        while True:
            await asyncio.sleep(5)
            yield {"type": "ping"}  # недостижимо в тесте


class TestExpClaim:
    @pytest.mark.asyncio
    async def test_token_without_exp_rejected(self, monkeypatch):
        """Подписанный JWT без exp — отказ 1008: стрим нечем ограничить."""
        monkeypatch.setattr(
            ws, "verify_access_token", lambda tok: {"sub": "1", "roles": ["manager"]}
        )
        wsk = FakeWS(cookies={"uk_access": "noexp"})
        payload = await ws.authenticate_ws_manager(wsk)
        assert payload is None
        assert wsk.accepted is False  # cookie-путь отклоняет ДО accept → HTTP 403
        assert wsk.closed_code == 1008

    @pytest.mark.asyncio
    async def test_token_with_non_numeric_exp_rejected(self, monkeypatch):
        monkeypatch.setattr(
            ws,
            "verify_access_token",
            lambda tok: {"sub": "1", "roles": ["manager"], "exp": "tomorrow"},
        )
        wsk = FakeWS(cookies={"uk_access": "badexp"})
        payload = await ws.authenticate_ws_manager(wsk)
        assert payload is None
        assert wsk.closed_code == 1008

    @pytest.mark.asyncio
    async def test_valid_exp_payload_returned(self, manager_token):
        wsk = FakeWS(cookies={"uk_access": "good"})
        payload = await ws.authenticate_ws_manager(wsk)
        assert payload is not None and payload["exp"] > time.time()


class TestStreamExpiry:
    @pytest.mark.asyncio
    async def test_relay_closes_4001_on_token_expiry(self, monkeypatch):
        """Истечение exp во время стрима → close выделенным кодом 4001.

        `hang=True` теперь обязателен: с AUD5-APIFE-2 стрим читает `receive()`,
        и фейк, мгновенно бросающий WebSocketDisconnect, означал бы «клиент уже
        ушёл» — тогда закрывать было бы нечего и код не выставлялся бы.
        Перепроверку личности отодвигаем, чтобы гонку выиграл именно exp.
        """
        monkeypatch.setattr(ws, "_WS_IDENTITY_RECHECK_INTERVAL", 3600)
        wsk = FakeWS(hang=True)
        payload = {"sub": "1", "roles": ["manager"], "exp": time.time() + 0.05}
        await ws._relay_until_exp(wsk, payload, _SilentPubSub())
        assert ws.WS_TOKEN_EXPIRED == 4001
        assert wsk.closed_code == ws.WS_TOKEN_EXPIRED
