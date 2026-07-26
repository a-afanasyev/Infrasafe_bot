"""PENT-F04 (остаток) + AUD5-APIFE-2: WS сверяется с БД, а не только с токеном.

До этого роли брались ИЗ JWT (`_extract_roles(payload)`), и БД при handshake не
читалась вовсе. Практический смысл: менеджера заблокировали или сняли роль —
его WebSocket продолжал получать поток заявок до истечения токена. Часть F-04
(закрытие по `exp`) закрыта в sec-127; здесь закрывается вторая часть.

Второй дефект того же файла (AUD5-APIFE-2): хендлер никогда не читал
`receive()`, поэтому уход клиента не замечался — корутина висела на
`pubsub.listen()`, а подписка Redis жила дальше.

Отдельная забота — НЕ держать сессию БД на всё время стрима. Это ровно тот
класс бага, который уже стоил прод-инцидента в media-service (сессия удерживалась
через сетевой I/O → выеденный пул → 504 на всех медиа). Поэтому проверка личности
делает короткую сессию на каждый вызов, и тест это фиксирует.
"""
import asyncio
import time

import pytest
from fastapi import WebSocketDisconnect

from uk_management_bot.api.ws import router as ws


class FakeWS:
    """`gone=True` — клиент отвалился; иначе живой и молчит.

    Различие принципиально именно теперь: раньше `receive()` никто не читал, и
    «молчит» было неотличимо от «ушёл». Фейк, который мгновенно бросает
    WebSocketDisconnect, моделировал бы не живого клиента, а разрыв.
    """

    def __init__(self, cookies=None, gone=False):
        self.cookies = cookies or {}
        self.accepted = False
        self.closed_code = "NOT_CLOSED"
        self.sent: list[str] = []
        self._gone = gone

    async def accept(self):
        self.accepted = True

    async def close(self, code=None):
        self.closed_code = code

    async def send_text(self, data):
        self.sent.append(data)

    async def receive_text(self):
        if self._gone:
            raise WebSocketDisconnect()
        await asyncio.sleep(3600)  # живой клиент просто молчит


class FakePubSub:
    """Отдаёт заданные сообщения; дальше молчит (`endless`) или завершается.

    По умолчанию молчит — так ведёт себя живой `listen()`. Завершение потока
    моделируем явно: это единственный способ дождаться возврата `_relay`, когда
    все остальные условия (клиент, доступ, exp) держатся.
    """

    def __init__(self, messages=(), endless=True):
        self._messages = list(messages)
        self._endless = endless
        self.unsubscribed = False

    async def listen(self):
        for m in self._messages:
            yield {"type": "message", "data": m}
        while self._endless:
            await asyncio.sleep(3600)

    async def unsubscribe(self):
        self.unsubscribed = True


@pytest.fixture
def token_ok(monkeypatch):
    """Токен валиден и говорит «manager». Что скажет БД — решают тесты."""
    monkeypatch.setattr(ws, "verify_access_token",
                        lambda tok: {"sub": "7", "roles": ["manager"],
                                     "exp": time.time() + 3600} if tok else None)


def _identity(monkeypatch, result, calls=None):
    async def _fake(user_id):
        if calls is not None:
            calls.append(user_id)
        return result() if callable(result) else result

    monkeypatch.setattr(ws, "_ws_identity_ok", _fake)


# ── Handshake: решает БД, а не токен ─────────────────────────────────────


@pytest.mark.asyncio
async def test_blocked_user_rejected_despite_valid_token(token_ok, monkeypatch):
    """Главный сценарий пункта: токен ещё живой, но пользователь заблокирован."""
    _identity(monkeypatch, False)
    sock = FakeWS(cookies={"uk_access": "good"})

    assert await ws.authenticate_ws_manager(sock, None) is None
    assert sock.accepted is False


@pytest.mark.asyncio
async def test_roles_come_from_db_not_from_token(monkeypatch):
    """Инверсия источника правды: в токене ролей нет, в БД manager есть → пускаем.

    Это и есть суть фикса. Раньше решение принималось по `roles` из JWT, то есть
    по слепку на момент выдачи токена.
    """
    monkeypatch.setattr(ws, "verify_access_token",
                        lambda tok: {"sub": "7", "roles": [], "exp": time.time() + 3600})
    _identity(monkeypatch, True)
    sock = FakeWS(cookies={"uk_access": "stale-but-signed"})

    assert await ws.authenticate_ws_manager(sock, None) is not None
    assert sock.accepted is True


@pytest.mark.asyncio
async def test_role_revoked_in_db_rejected(token_ok, monkeypatch):
    _identity(monkeypatch, False)
    sock = FakeWS(cookies={"uk_access": "good"})

    assert await ws.authenticate_ws_manager(sock, None) is None


@pytest.mark.asyncio
async def test_token_without_usable_sub_rejected(monkeypatch):
    """Без `sub` личность в БД не найти — пускать нельзя ни при каких ролях."""
    monkeypatch.setattr(ws, "verify_access_token",
                        lambda tok: {"roles": ["manager"], "exp": time.time() + 3600})
    called = []
    _identity(monkeypatch, True, called)
    sock = FakeWS(cookies={"uk_access": "good"})

    assert await ws.authenticate_ws_manager(sock, None) is None
    assert called == [], "до БД дойти не должны — нечего искать"


@pytest.mark.asyncio
async def test_db_unavailable_fails_closed(token_ok, monkeypatch):
    """Сбой проверки — это отказ, а не «пропустим по токену»."""
    async def _boom(user_id):
        raise RuntimeError("db down")

    monkeypatch.setattr(ws, "_ws_identity_ok", _boom)
    sock = FakeWS(cookies={"uk_access": "good"})

    assert await ws.authenticate_ws_manager(sock, None) is None


# ── Сама _ws_identity_ok, без подмены ────────────────────────────────────
#
# Все тесты выше подменяют `_ws_identity_ok` целиком — то есть её собственное
# тело не исполняется ни в одном из них. Именно поэтому в прод уехал битый
# импорт (`api_roles_for`, которого нет в `api.dependencies`): CI был зелёный, а
# на живом хосте первая же попытка менеджера подключиться давала ImportError →
# fail-closed → 403 на все WS. Эти два теста исполняют функцию по-настоящему.


class _FakeSession:
    """Минимальный async-context вокруг `session.get(User, id)`."""

    def __init__(self, user):
        self._user = user

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, model, pk):
        return self._user


def _stub_session(monkeypatch, user):
    import uk_management_bot.database.session as session_mod

    monkeypatch.setattr(session_mod, "AsyncSessionLocal", lambda: _FakeSession(user))


class _FakeUser:
    def __init__(self, roles, status="approved"):
        self.roles = roles
        self.status = status
        self.role = None


@pytest.mark.asyncio
async def test_identity_ok_reads_roles_from_db_row(monkeypatch):
    """Живой путь функции: manager в `user.roles` → доступ есть."""
    _stub_session(monkeypatch, _FakeUser('["manager"]'))

    assert await ws._ws_identity_ok(7) is True


@pytest.mark.asyncio
async def test_identity_ok_rejects_blocked_and_non_manager(monkeypatch):
    """Тот же путь на отказах — блокировка и потеря роли."""
    _stub_session(monkeypatch, _FakeUser('["manager"]', status="blocked"))
    assert await ws._ws_identity_ok(7) is False

    _stub_session(monkeypatch, _FakeUser('["applicant"]'))
    assert await ws._ws_identity_ok(7) is False

    _stub_session(monkeypatch, None)
    assert await ws._ws_identity_ok(7) is False


# ── Стрим: перепроверка и уход клиента ───────────────────────────────────


@pytest.mark.asyncio
async def test_revoked_mid_stream_closes_socket(monkeypatch):
    """Блокировка во время сессии обязана рвать поток, не дожидаясь exp."""
    monkeypatch.setattr(ws, "_WS_IDENTITY_RECHECK_INTERVAL", 0.01)
    states = iter([True, False])
    _identity(monkeypatch, lambda: next(states, False))
    sock = FakeWS()
    pubsub = FakePubSub()

    await asyncio.wait_for(
        ws._relay(sock, {"sub": "7", "exp": time.time() + 3600}, pubsub), timeout=5
    )

    assert sock.closed_code == ws.WS_ACCESS_REVOKED == 4003


@pytest.mark.asyncio
async def test_client_disconnect_ends_relay(monkeypatch):
    """AUD5-APIFE-2: уход клиента замечается сразу, а не висит до exp.

    Без чтения `receive()` эта корутина не завершилась бы вовсе — тест упал бы
    по таймауту, а в проде осталась бы живая подписка Redis.
    """
    monkeypatch.setattr(ws, "_WS_IDENTITY_RECHECK_INTERVAL", 3600)
    _identity(monkeypatch, True)
    sock = FakeWS(gone=True)
    pubsub = FakePubSub()

    await asyncio.wait_for(
        ws._relay(sock, {"sub": "7", "exp": time.time() + 3600}, pubsub), timeout=5
    )


@pytest.mark.asyncio
async def test_messages_still_forwarded(monkeypatch):
    """Контрольный: полезная работа не сломана — сообщения доходят."""
    monkeypatch.setattr(ws, "_WS_IDENTITY_RECHECK_INTERVAL", 3600)
    _identity(monkeypatch, True)
    sock = FakeWS()
    pubsub = FakePubSub(messages=['{"event":"one"}', '{"event":"two"}'], endless=False)

    await asyncio.wait_for(
        ws._relay(sock, {"sub": "7", "exp": time.time() + 3600}, pubsub), timeout=5
    )

    assert sock.sent == ['{"event":"one"}', '{"event":"two"}']
    # Поток иссяк, а не «доступ отозван» — закрывать выделенным кодом нечего.
    assert sock.closed_code == "NOT_CLOSED"


@pytest.mark.asyncio
async def test_expiry_still_wins(monkeypatch):
    """F-04 (часть sec-127) не потеряна: истечение exp по-прежнему рвёт поток 4001."""
    monkeypatch.setattr(ws, "_WS_IDENTITY_RECHECK_INTERVAL", 3600)
    _identity(monkeypatch, True)
    sock = FakeWS()
    pubsub = FakePubSub()

    await asyncio.wait_for(
        ws._relay(sock, {"sub": "7", "exp": time.time() + 0.05}, pubsub), timeout=5
    )

    assert sock.closed_code == ws.WS_TOKEN_EXPIRED


@pytest.mark.asyncio
async def test_identity_checked_repeatedly_not_once(monkeypatch):
    """Перепроверка периодическая — иначе она бы ничего не давала после handshake.

    Заодно это фиксирует, что сессия БД короткая: проверка вызывается заново,
    а не держит одну открытую сессию на весь стрим (грабля media-service).
    """
    monkeypatch.setattr(ws, "_WS_IDENTITY_RECHECK_INTERVAL", 0.01)
    calls = []
    seq = iter([True] * 3 + [False])
    _identity(monkeypatch, lambda: next(seq, False), calls)
    sock = FakeWS()

    await asyncio.wait_for(
        ws._relay(sock, {"sub": "7", "exp": time.time() + 3600}, FakePubSub()), timeout=5
    )

    assert len(calls) >= 3
