"""Edge-консьюмер durable-канала: критерии §15.5 и §15.6. PostgreSQL-only.

Симулятор стороны edge: pull(/commands/next) → relay.open() → ack(/ack) с
локальным дедупом по command_id. Через реальные endpoints (TestClient + общий
DATABASE_URL), как test_camera_events_api.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from access_control.app.main import create_app
from access_control.edge.command_consumer import EdgeCommandConsumer
from access_control.integrations.relay import MockRelay
from access_control.tests.conftest import (
    PilotFixture,
    SigningClient,
    seed_barrier_command,
)


def _signed(controller_uid: str) -> SigningClient:
    """Подписывающий device-auth клиент edge (§9.1), привязанный к контроллеру."""
    return SigningClient(TestClient(create_app()), controller_uid)


def test_commands_routes_registered() -> None:
    paths = {route.path for route in create_app().routes}
    assert "/api/v1/access/edge/{controller_id}/commands/next" in paths
    assert (
        "/api/v1/access/edge/{controller_id}/commands/{command_id}/ack" in paths
    )


def test_pull_open_ack_single_relay_open(pg_db, pilot: PilotFixture) -> None:
    """Базовый durable-цикл: одна команда → одно открытие → ack."""
    seed_barrier_command(pg_db, pilot, status="pending")
    relay = MockRelay()
    consumer = EdgeCommandConsumer(_signed(pilot.controller_uid), pilot.controller_uid, relay)

    outcome = consumer.pull_once()
    assert outcome is not None
    assert outcome.relay_opened is True
    assert outcome.acked is True
    assert relay.open_count(outcome.command_id) == 1

    # Команда стала acked в БД.
    status = pg_db.execute(
        text("SELECT status FROM barrier_commands WHERE command_id = :c"),
        {"c": outcome.command_id},
    ).scalar()
    assert status == "acked"

    # Повторный pull пуст — команда больше не pending.
    assert consumer.pull_once() is None


def test_fast_path_then_pull_relay_opens_once(pg_db, pilot: PilotFixture) -> None:
    """Крит. §15.5: одна command_id из fast-path И pull → реле открыто ровно раз."""
    cmd_id = seed_barrier_command(pg_db, pilot, status="pending")
    relay = MockRelay()
    consumer = EdgeCommandConsumer(_signed(pilot.controller_uid), pilot.controller_uid, relay)

    # Fast-path: команда доставлена синхронным ответом (без lease_token).
    fp = consumer.on_fast_path(cmd_id, pilot.barrier_id)
    assert fp.relay_opened is True
    assert relay.open_count(cmd_id) == 1

    # Durable pull той же команды: дедуп по command_id → реле НЕ открывается снова.
    pulled = consumer.pull_once()
    assert pulled is not None
    assert str(pulled.command_id) == cmd_id
    assert pulled.relay_deduplicated is True
    assert pulled.acked is True
    # Физическое открытие по-прежнему ровно одно.
    assert relay.open_count(cmd_id) == 1


def test_lost_fast_path_recovered_by_pull_single_open(
    pg_db, pilot: PilotFixture
) -> None:
    """Крит. §15.6: потерянный fast-path восстановлен durable pull, открытие одно."""
    cmd_id = seed_barrier_command(pg_db, pilot, status="pending")
    relay = MockRelay()
    consumer = EdgeCommandConsumer(_signed(pilot.controller_uid), pilot.controller_uid, relay)

    # Fast-path ОТВЕТ ПОТЕРЯН — edge его не получил (on_fast_path не вызывается).
    # Восстановление через durable pull.
    pulled = consumer.pull_once()
    assert pulled is not None
    assert str(pulled.command_id) == cmd_id
    assert pulled.relay_opened is True
    assert pulled.relay_deduplicated is False
    assert pulled.acked is True
    assert relay.open_count(cmd_id) == 1


def test_repeated_ack_is_idempotent_via_http(pg_db, pilot: PilotFixture) -> None:
    """Крит. §15.5: повторный ACK по HTTP возвращает сохранённый результат, 200."""
    seed_barrier_command(pg_db, pilot, status="pending")
    uid = pilot.controller_uid
    client = _signed(uid)

    nxt = client.get(f"/api/v1/access/edge/{uid}/commands/next")
    assert nxt.status_code == 200
    body = nxt.json()
    ack_payload = {"lease_token": body["lease_token"], "result": {"opened": True}}

    first = client.post(
        f"/api/v1/access/edge/{uid}/commands/{body['command_id']}/ack",
        json=ack_payload,
    )
    second = client.post(
        f"/api/v1/access/edge/{uid}/commands/{body['command_id']}/ack",
        json=ack_payload,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["replayed"] is False
    assert second.json()["replayed"] is True
    assert second.json()["result"] == {"opened": True}


def test_next_empty_queue_returns_204(pg_db, pilot: PilotFixture) -> None:
    resp = _signed(pilot.controller_uid).get(
        f"/api/v1/access/edge/{pilot.controller_uid}/commands/next"
    )
    assert resp.status_code == 204


def test_next_unknown_controller_401(pg_db, pilot: PilotFixture) -> None:
    # Подписываем как несуществующий контроллер → device-auth не найдёт его → 401.
    resp = _signed("ctrl-nope").get("/api/v1/access/edge/ctrl-nope/commands/next")
    assert resp.status_code == 401


def test_ack_foreign_controller_409(pg_db, pilot: PilotFixture, pilot_b) -> None:
    """Крит. §9.1: ACK команды чужого контроллера → 409.

    A лизит свою команду; B (со своей валидной device-auth подписью) пытается
    заакать её на СВОЁМ пути — device-auth проходит как B, но CAS по controller_id
    отвергает чужую команду → 409.
    """
    seed_barrier_command(pg_db, pilot, status="pending")
    client_a = _signed(pilot.controller_uid)
    client_b = _signed(pilot_b.controller_uid)
    nxt = client_a.get(f"/api/v1/access/edge/{pilot.controller_uid}/commands/next")
    body = nxt.json()
    # B пытается заакать команду A на пути B.
    resp = client_b.post(
        f"/api/v1/access/edge/{pilot_b.controller_uid}/commands/{body['command_id']}/ack",
        json={"lease_token": body["lease_token"], "result": {"opened": True}},
    )
    assert resp.status_code == 409
