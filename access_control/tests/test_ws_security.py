"""Ф6-часть2: WebSocket-панель охраны (§9.6) + live-трансляция событий.

Маппинг на критерии приёмки §15:
* Критерий 13 — охрана видит событие в реальном времени: авторизованный
  WS-клиент получает опубликованное брокером PD-safe событие доступа.
* Критерий 19 (WS) — RBAC §6.3/§3.2:
  - без auth → соединение отклоняется;
  - JWT в query string → отклоняется (§9.6 явный запрет);
  - executor/inspector/applicant → отклоняется;
  - security_operator/manager/system_admin → принимается.
* Доп. — JWT в первом WS-сообщении (cookieless) работает; доставленное
  событие НЕ содержит ПД (§11): нет полного номера/фото.

WS-аутентификация переиспользует ``create_access_token``/``verify_access_token``
(тот же секрет, что и web-сессия). Роли берутся из claim ``roles`` (=roles[],
§3.2), не из active_role. Тесты auth/брокера не зависят от БД (token-only);
тест хука ingestion использует postgres-фикстуры.
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from access_control.app.main import create_app
from access_control.services.event_broadcaster import (
    AccessEventMessage,
    get_broker,
    mask_plate,
    reset_broker,
)
from uk_management_bot.api.auth.service import create_access_token

WS_URL = "/ws/v1/access/security"


@pytest.fixture(autouse=True)
def _fresh_broker():
    """Свежий in-process брокер на каждый тест: подписчики не «протекают»."""
    reset_broker()
    yield
    reset_broker()


def _client_with_cookie(token: str | None = None) -> TestClient:
    client = TestClient(create_app())
    if token is not None:
        client.cookies.set("uk_access", token)
    return client


def _token(role: str) -> str:
    """JWT существующей web-сессии с ролью в claim ``roles`` (§3.2)."""
    return create_access_token(user_id=1, roles=[role])


def _expect_rejected(client: TestClient, **connect_kwargs) -> None:
    """Соединение должно быть отклонено (до accept ИЛИ закрыто после auth-msg)."""
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(WS_URL, **connect_kwargs) as ws:
            # Если сервер всё же принял — попытка чтения упрётся в close (1008).
            ws.receive_json()


# ───────────────────────── Критерий 19 (WS): RBAC-негатив ─────────────────────


def test_no_auth_rejected() -> None:
    """§15.19: без cookie и без токена в первом сообщении → отклонено."""
    client = TestClient(create_app())
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(WS_URL) as ws:
            # cookieless-путь: сервер ждёт auth-сообщение; шлём пустое → close.
            ws.send_json({})
            ws.receive_json()


def test_jwt_in_query_string_rejected() -> None:
    """§9.6/§15.19: JWT в query string запрещён → отклонено до accept."""
    token = _token("security_operator")
    client = TestClient(create_app())
    _expect_rejected(client, params={"token": token})


def test_jwt_in_query_string_access_token_param_rejected() -> None:
    """§9.6: ?access_token=... тоже запрещён (любой токен в query)."""
    token = _token("manager")
    client = TestClient(create_app())
    _expect_rejected(client, params={"access_token": token})


@pytest.mark.parametrize("role", ["executor", "inspector", "applicant"])
def test_forbidden_role_cookie_rejected(role: str) -> None:
    """§15.19: executor/inspector/applicant с валидным cookie-JWT → отклонено."""
    client = _client_with_cookie(_token(role))
    _expect_rejected(client)


@pytest.mark.parametrize("role", ["executor", "inspector", "applicant"])
def test_forbidden_role_first_message_rejected(role: str) -> None:
    """§15.19: запрещённая роль в JWT первого сообщения (cookieless) → отклонено."""
    client = TestClient(create_app())
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(WS_URL) as ws:
            ws.send_json({"token": _token(role)})
            ws.receive_json()


def test_invalid_token_cookie_rejected() -> None:
    """Битый/подделанный JWT в cookie → отклонено."""
    client = _client_with_cookie("not.a.valid.jwt")
    _expect_rejected(client)


# ───────────────────── Критерий 19 (WS): допуск нужных ролей ──────────────────


@pytest.mark.parametrize("role", ["security_operator", "manager", "system_admin"])
def test_allowed_role_cookie_accepted(role: str) -> None:
    """§15.19: security_operator/manager/system_admin (cookie) → принято (ready)."""
    client = _client_with_cookie(_token(role))
    with client.websocket_connect(WS_URL) as ws:
        hello = ws.receive_json()
        assert hello["type"] == "ready"


def test_allowed_role_first_message_accepted() -> None:
    """Доп.: cookieless — JWT в первом сообщении принимается (ready)."""
    client = TestClient(create_app())
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json({"token": _token("security_operator")})
        hello = ws.receive_json()
        assert hello["type"] == "ready"


# ───────────────────── Критерий 13: live-событие в реальном времени ───────────


def test_operator_receives_live_event() -> None:
    """§15.13: подключённый авторизованный клиент получает событие через брокер."""
    client = _client_with_cookie(_token("security_operator"))
    with client.websocket_connect(WS_URL) as ws:
        assert ws.receive_json()["type"] == "ready"  # подписка активна
        get_broker().publish(
            AccessEventMessage(
                decision="allow",
                status="allowed",
                reason="permanent_vehicle_allowed",
                zone_id=7,
                gate_id=3,
                direction="entry",
                occurred_at="2026-06-26T10:00:00+00:00",
                plate_masked=mask_plate("01A001AA"),
            )
        )
        msg = ws.receive_json()
    assert msg["type"] == "access_event"
    assert msg["decision"] == "allow"
    assert msg["status"] == "allowed"
    assert msg["reason"] == "permanent_vehicle_allowed"
    assert msg["zone_id"] == 7
    assert msg["gate_id"] == 3
    assert msg["direction"] == "entry"


def test_live_event_first_message_auth() -> None:
    """§15.13 + cookieless: событие доставляется клиенту, авторизованному JWT-msg."""
    client = TestClient(create_app())
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json({"token": _token("manager")})
        assert ws.receive_json()["type"] == "ready"
        get_broker().publish(
            AccessEventMessage(decision="deny", status="denied", reason="vehicle_not_found")
        )
        msg = ws.receive_json()
    assert msg["decision"] == "deny"
    assert msg["reason"] == "vehicle_not_found"


# ───────────────────── Доп.: PD-safe payload (§11) ────────────────────────────


def test_delivered_event_has_no_pd() -> None:
    """§11: доставленное событие НЕ содержит полного номера/фото."""
    client = _client_with_cookie(_token("security_operator"))
    full_plate = "01A001AA"
    with client.websocket_connect(WS_URL) as ws:
        assert ws.receive_json()["type"] == "ready"
        get_broker().publish(
            AccessEventMessage(
                decision="allow",
                status="allowed",
                reason="permanent_vehicle_allowed",
                plate_masked=mask_plate(full_plate),
            )
        )
        msg = ws.receive_json()
    flat = str(msg)
    # Нет полного номера, нет URL фото, нет ключей фото/полного номера.
    assert full_plate not in flat
    assert "http" not in flat
    assert "plate_number" not in msg
    assert "plate_photo_url" not in msg
    assert "overview_photo_url" not in msg
    # Маскированный номер раскрывает не больше 2 последних символов.
    assert msg["plate_masked"] == mask_plate(full_plate)
    assert msg["plate_masked"].count("*") >= 1


def test_mask_plate_keeps_only_tail() -> None:
    """mask_plate раскрывает только хвост, маскирует начало; None→None."""
    assert mask_plate(None) is None
    masked = mask_plate("01A001AA")
    assert masked is not None
    assert masked.endswith("AA")
    assert "01A001" not in masked


# ───────────────────── Ф6: router подключён ───────────────────────────────────


def test_ws_router_registered() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert WS_URL in paths


# ───────────────────── Хук publish в ingestion (postgres) ─────────────────────


def test_ingestion_publishes_pd_safe_event(pg_db, pilot, monkeypatch) -> None:
    """§9.6/§11: ingestion ПОСЛЕ коммита публикует PD-safe событие (без ПД).

    Хук не должен ломать ingestion: решение/команда пишутся как обычно, а в
    брокер уходит событие БЕЗ полного номера/фото.
    """
    from access_control.services.ingestion import AnprIngestInput, ingest_anpr
    from access_control.tests.conftest import seed_permanent_vehicle, utcnow

    captured: list[AccessEventMessage] = []

    class _CaptureBroker:
        def publish(self, message: AccessEventMessage) -> None:
            captured.append(message)

    monkeypatch.setattr(
        "access_control.services.ingestion.get_broker", lambda: _CaptureBroker()
    )

    seed_permanent_vehicle(pg_db, pilot, normalized="01A001AA")
    res = ingest_anpr(
        pg_db,
        AnprIngestInput(
            controller_id=pilot.controller_id,
            event_id="evt-ws-1",
            zone_id=pilot.zone_id,
            gate_id=pilot.gate_id,
            camera_id=pilot.camera_id,
            barrier_id=pilot.barrier_id,
            plate_number_original="01A001AA",
            direction="entry",
            confidence=0.95,
            captured_at=utcnow(),
            plate_photo_url="https://storage/private/plate.jpg",
        ),
    )

    assert res.decision == "allow"  # ingestion не сломан
    assert len(captured) == 1
    msg = captured[0]
    assert msg.decision == "allow"
    assert msg.zone_id == pilot.zone_id
    assert msg.gate_id == pilot.gate_id
    assert msg.direction == "entry"
    # PD-safe: нет полного номера/URL фото нигде в payload.
    flat = str(msg.to_payload())
    assert "01A001AA" not in flat
    assert "http" not in flat


def test_ingestion_replay_does_not_publish(pg_db, pilot, monkeypatch) -> None:
    """Повтор (controller_id,event_id) не публикует повторное событие (replay)."""
    from access_control.services.ingestion import AnprIngestInput, ingest_anpr
    from access_control.tests.conftest import seed_permanent_vehicle, utcnow

    captured: list[AccessEventMessage] = []

    class _CaptureBroker:
        def publish(self, message: AccessEventMessage) -> None:
            captured.append(message)

    monkeypatch.setattr(
        "access_control.services.ingestion.get_broker", lambda: _CaptureBroker()
    )

    seed_permanent_vehicle(pg_db, pilot, normalized="01A001AA")
    payload = AnprIngestInput(
        controller_id=pilot.controller_id,
        event_id="evt-ws-replay",
        zone_id=pilot.zone_id,
        gate_id=pilot.gate_id,
        camera_id=pilot.camera_id,
        barrier_id=pilot.barrier_id,
        plate_number_original="01A001AA",
        direction="entry",
        confidence=0.95,
        captured_at=utcnow(),
    )
    ingest_anpr(pg_db, payload)
    ingest_anpr(pg_db, payload)  # повтор → replay
    assert len(captured) == 1  # только первое (новое) событие опубликовано
