"""PR-15 — SEC-03: WS-токен из query-string.

`authenticate_ws_manager` поддерживает 4 источника токена с приоритетом
cookie → ?token= (DEPRECATED + warning) → первое WS-сообщение (secure-путь
для cookieless-клиентов). Проверяем каждый путь + role-gate + accept/close.
"""
import asyncio

import pytest
from fastapi import WebSocketDisconnect

from uk_management_bot.api.ws import router as ws


class FakeWS:
    def __init__(self, cookies=None, messages=None, hang=False):
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
    """verify_access_token("good") → manager payload; иначе None."""
    def _verify(tok):
        if tok == "good":
            return {"sub": "1", "roles": ["manager"]}
        if tok == "applicant":
            return {"sub": "2", "roles": ["applicant"]}
        return None
    monkeypatch.setattr(ws, "verify_access_token", _verify)


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
        payload = await ws.authenticate_ws_manager(wsk, None)
        assert payload and "manager" in payload["roles"]
        assert wsk.accepted is True
        assert wsk.closed_code == "NOT_CLOSED"
        # cookie-путь не пишет deprecation
        assert "DEPRECATED" not in caplog.text

    @pytest.mark.asyncio
    async def test_legacy_access_token_cookie_ok(self, manager_token):
        wsk = FakeWS(cookies={"access_token": "good"})
        payload = await ws.authenticate_ws_manager(wsk, None)
        assert payload is not None
        assert wsk.accepted is True

    @pytest.mark.asyncio
    async def test_non_manager_cookie_rejected_pre_accept(self, manager_token):
        wsk = FakeWS(cookies={"uk_access": "applicant"})
        payload = await ws.authenticate_ws_manager(wsk, None)
        assert payload is None
        assert wsk.accepted is False  # отклоняем ДО accept
        assert wsk.closed_code == 1008


# ---------------------------------------------------------------------------
# query path (DEPRECATED)
# ---------------------------------------------------------------------------

class TestQueryPath:
    @pytest.mark.asyncio
    async def test_query_token_works_but_warns(self, manager_token, caplog):
        import logging
        wsk = FakeWS()  # no cookies
        with caplog.at_level(logging.WARNING):
            payload = await ws.authenticate_ws_manager(wsk, "good")
        assert payload is not None
        assert wsk.accepted is True
        assert "SEC-03" in caplog.text and "DEPRECATED" in caplog.text

    @pytest.mark.asyncio
    async def test_invalid_query_token_rejected_pre_accept(self, manager_token):
        wsk = FakeWS()
        payload = await ws.authenticate_ws_manager(wsk, "bad")
        assert payload is None
        assert wsk.accepted is False
        assert wsk.closed_code == 1008


# ---------------------------------------------------------------------------
# first-message path (secure, cookieless)
# ---------------------------------------------------------------------------

class TestFirstMessagePath:
    @pytest.mark.asyncio
    async def test_first_message_token_ok(self, manager_token, caplog):
        wsk = FakeWS(messages=['{"token": "good"}'])
        payload = await ws.authenticate_ws_manager(wsk, None)
        assert payload is not None
        assert wsk.accepted is True  # accept до получения сообщения
        assert wsk.closed_code == "NOT_CLOSED"
        assert "DEPRECATED" not in caplog.text  # не query — без warning

    @pytest.mark.asyncio
    async def test_first_message_non_manager_closed(self, manager_token):
        wsk = FakeWS(messages=['{"token": "applicant"}'])
        payload = await ws.authenticate_ws_manager(wsk, None)
        assert payload is None
        assert wsk.accepted is True
        assert wsk.closed_code == 1008

    @pytest.mark.asyncio
    async def test_first_message_disconnect_returns_none(self, manager_token):
        wsk = FakeWS(messages=[])  # receive_text → WebSocketDisconnect
        payload = await ws.authenticate_ws_manager(wsk, None)
        assert payload is None
        assert wsk.accepted is True
        assert wsk.closed_code == 1008

    @pytest.mark.asyncio
    async def test_first_message_timeout_returns_none(self, manager_token, monkeypatch):
        monkeypatch.setattr(ws, "_WS_AUTH_MESSAGE_TIMEOUT", 0.05)
        wsk = FakeWS(hang=True)
        payload = await ws.authenticate_ws_manager(wsk, None)
        assert payload is None
        assert wsk.accepted is True
        assert wsk.closed_code == 1008
