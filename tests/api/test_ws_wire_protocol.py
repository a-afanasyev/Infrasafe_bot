"""П4 — контракт WS на ПРОВОДЕ, а не в фейке (AUD5-APIFE-7 и др.).

Зачем отдельный файл, если WS уже покрыт `test_pr15_ws_auth.py`. Те тесты
проверяют вызовы на объекте-дублёре (`FakeWS.closed_code`), то есть фиксируют
намерение хендлера, а не то, что получит клиент. Разница не косметическая:

* `close()` ДО `accept()` — ASGI-сообщение `websocket.close` в состоянии
  CONNECTING. Close-кадра не существует, потому что WebSocket-соединения ещё
  нет: ASGI-сервер обязан ответить обычным HTTP. uvicorn отвечает **403**, и
  апгрейд не происходит. Браузер в этом случае НЕ видит 1008 — он видит
  `onerror` и `onclose` с кодом 1006, и `onopen` не вызывается вовсе.
* `close(code)` ПОСЛЕ `accept()` — настоящий close-кадр, код доходит как есть
  (1008 / 4001 / 4003).

Проверено эмпирически: `starlette.testclient.TestClient` для первого случая
показывает `WebSocketDisconnect(code=1008)` — он короткозамыкает ASGI и не
делает HTTP-хендшейк, поэтому врёт ровно так же, как `FakeWS`. Правильный
уровень для этого контракта — **ASGI-сервер** (uvicorn) + настоящий
ws-клиент, что здесь и поднимается.

Ниже подменяется только то, что лежит УРОВНЕМ НИЖЕ предмета: проверка подписи
токена (`verify_access_token`, чужой модуль), обращение к БД (`_ws_identity_ok`)
и подписка на Redis (`subscribe_to_requests`). Сам предмет —
`authenticate_ws_manager` / `_serve_ws` / `_relay` — работает настоящий; иначе
тест повторил бы дефект PR #263, где зелёный CI получался за счёт мока ровно
той функции, которая была сломана.
"""
import asyncio
import threading
import time

import pytest
import uvicorn
import websockets
from fastapi import FastAPI

from uk_management_bot.api.ws import router as ws


class _SilentPubSub:
    """Подписка без сообщений: стрим может закрыть только exp / отзыв доступа."""

    async def listen(self):
        while True:
            await asyncio.sleep(3600)
            yield {"type": "message", "data": "{}"}  # недостижимо

    async def unsubscribe(self):
        pass


class _FakeRedis:
    async def aclose(self):
        pass


async def _fake_subscribe():
    return _SilentPubSub(), _FakeRedis()


@pytest.fixture
def ws_server(monkeypatch):
    """Живой uvicorn с НАСТОЯЩИМ ws-роутером на случайном порту.

    Порт 0 — чтобы параллельные прогоны и занятые порты в CI не давали
    ложных падений; фактический порт вычитывается из сокета сервера.
    """
    app = FastAPI()
    app.include_router(ws.router, prefix="/ws/v2")

    monkeypatch.setattr(ws, "subscribe_to_requests", _fake_subscribe)

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="critical")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 10
    while not server.started:
        if time.time() > deadline:  # pragma: no cover — защита от вечного висения
            server.should_exit = True
            raise RuntimeError("uvicorn не поднялся за 10 с")
        time.sleep(0.02)

    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"ws://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture
def manager_auth(monkeypatch):
    """Подпись и БД «согласны»: manager с длинным exp. Возвращает сеттер exp."""
    state = {"exp_in": 3600.0, "identity_ok": True}

    def _verify(tok):
        if tok == "good":
            return {"sub": "1", "roles": ["manager"], "exp": time.time() + state["exp_in"]}
        if tok == "applicant":
            return {"sub": "2", "roles": ["applicant"], "exp": time.time() + 3600}
        return None

    async def _identity_ok(user_id):
        return user_id == 1 and state["identity_ok"]

    monkeypatch.setattr(ws, "verify_access_token", _verify)
    monkeypatch.setattr(ws, "_ws_identity_ok", _identity_ok)
    return state


# ---------------------------------------------------------------------------
# До upgrade: HTTP-статус, а НЕ close-код
# ---------------------------------------------------------------------------

class TestOriginGate:
    """PENT-F05: чужой Origin отсекается ДО апгрейда.

    Проверяется на живом сервере, а не на дубле: решение принимается до
    `accept()`, а это ровно тот путь, на котором `TestClient` врёт (см.
    docstring модуля).
    """

    @pytest.mark.asyncio
    async def test_foreign_origin_is_rejected_before_upgrade(self, ws_server, manager_auth):
        with pytest.raises(Exception) as exc:
            async with websockets.connect(
                f"{ws_server}/ws/v2/kanban",
                additional_headers={
                    "Cookie": "uk_access=good",
                    "Origin": "https://evil.example",
                },
            ):
                pass
        assert "403" in str(exc.value), (
            f"чужой Origin должен получать HTTP 403 до апгрейда, получено: {exc.value}"
        )

    @pytest.mark.asyncio
    async def test_same_origin_connects(self, ws_server, manager_auth):
        """SPA живёт на том же домене — Origin совпадает с Host."""
        host = ws_server.removeprefix("ws://")
        async with websockets.connect(
            f"{ws_server}/ws/v2/kanban",
            additional_headers={
                "Cookie": "uk_access=good",
                "Origin": f"http://{host}",
            },
        ) as socket:
            assert socket.state.name == "OPEN"

    @pytest.mark.asyncio
    async def test_absent_origin_still_connects(self, ws_server, manager_auth):
        """Не-браузерные клиенты Origin не шлют; у них нет и куки жертвы."""
        async with websockets.connect(
            f"{ws_server}/ws/v2/kanban",
            additional_headers={"Cookie": "uk_access=good"},
        ) as socket:
            assert socket.state.name == "OPEN"


class TestPreUpgradeRejection:
    @pytest.mark.asyncio
    async def test_invalid_cookie_token_is_http_403_not_close_code(self, ws_server, manager_auth):
        """Главный тест пакета: невалидный токен в cookie → HTTP 403 без апгрейда.

        Именно это, а не «клиент получил 1008», происходит на проводе. Ветка
        `event.code === 1008` во фронте для cookie-клиента (то есть для SPA)
        недостижима — отсюда требование к клиенту различать отказ по
        «закрылось, ни разу не открывшись», см. `useWebSocket.ts`.
        """
        with pytest.raises(websockets.InvalidStatus) as exc:
            async with websockets.connect(
                f"{ws_server}/ws/v2/kanban",
                additional_headers={"Cookie": "uk_access=rotten"},
            ):
                pass  # pragma: no cover — до тела не доходит
        assert exc.value.response.status_code == 403

    @pytest.mark.asyncio
    async def test_non_manager_cookie_is_http_403(self, ws_server, manager_auth):
        """Валидная подпись, но роль не та — тот же pre-upgrade отказ."""
        with pytest.raises(websockets.InvalidStatus) as exc:
            async with websockets.connect(
                f"{ws_server}/ws/v2/kanban",
                additional_headers={"Cookie": "uk_access=applicant"},
            ):
                pass  # pragma: no cover
        assert exc.value.response.status_code == 403

    @pytest.mark.asyncio
    async def test_query_token_is_http_403(self, ws_server, manager_auth):
        """SEC-03: `?token=` снят после 2026-09-01 — отказ ДО апгрейда, даже
        если сам токен валиден (он уже утёк в access-логи по дороге)."""
        with pytest.raises(websockets.InvalidStatus) as exc:
            async with websockets.connect(f"{ws_server}/ws/v2/kanban?token=good"):
                pass  # pragma: no cover
        assert exc.value.response.status_code == 403

    @pytest.mark.asyncio
    async def test_manager_cookie_upgrades_successfully(self, ws_server, manager_auth):
        """Контроль: без него 403-тесты были бы зелёными и на сломанном роутере."""
        async with websockets.connect(
            f"{ws_server}/ws/v2/kanban",
            additional_headers={"Cookie": "uk_access=good"},
        ) as client:
            assert client.state.name == "OPEN"


# ---------------------------------------------------------------------------
# После upgrade: настоящие close-кадры
# ---------------------------------------------------------------------------

class TestPostUpgradeCloseCodes:
    @pytest.mark.asyncio
    async def test_first_message_auth_failure_delivers_1008(self, ws_server, manager_auth):
        """1008 на проводе существует — но только на first-message пути.

        Токена нет ни в cookie, ни в query, поэтому сервер обязан сначала
        принять соединение, чтобы получить его сообщением. Отказ после accept —
        уже настоящий close-кадр.
        """
        async with websockets.connect(f"{ws_server}/ws/v2/kanban") as client:
            await client.send('{"token": "rotten"}')
            with pytest.raises(websockets.ConnectionClosed) as exc:
                await asyncio.wait_for(client.recv(), timeout=5)
        assert exc.value.rcvd.code == 1008

    @pytest.mark.asyncio
    async def test_token_expiry_delivers_4001(self, ws_server, manager_auth):
        manager_auth["exp_in"] = 0.4
        async with websockets.connect(
            f"{ws_server}/ws/v2/kanban",
            additional_headers={"Cookie": "uk_access=good"},
        ) as client:
            with pytest.raises(websockets.ConnectionClosed) as exc:
                await asyncio.wait_for(client.recv(), timeout=5)
        assert exc.value.rcvd.code == ws.WS_TOKEN_EXPIRED == 4001

    @pytest.mark.asyncio
    async def test_access_revoked_mid_stream_delivers_4003(
        self, ws_server, manager_auth, monkeypatch
    ):
        """Отзыв доступа во время стрима — 4003, и он приходит клиенту кадром."""
        monkeypatch.setattr(ws, "_WS_IDENTITY_RECHECK_INTERVAL", 0.2)
        async with websockets.connect(
            f"{ws_server}/ws/v2/kanban",
            additional_headers={"Cookie": "uk_access=good"},
        ) as client:
            manager_auth["identity_ok"] = False  # блокировка уже после handshake
            with pytest.raises(websockets.ConnectionClosed) as exc:
                await asyncio.wait_for(client.recv(), timeout=5)
        assert exc.value.rcvd.code == ws.WS_ACCESS_REVOKED == 4003
