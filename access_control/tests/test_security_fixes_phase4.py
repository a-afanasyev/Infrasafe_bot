"""Security-фиксы Фазы 4 access_control: эксплойт-тесты (RED→GREEN).

Каждый тест демонстрирует конкретную дыру из security-ревью и фиксирует
закрытие. PostgreSQL-only части используют те же фикстуры, что и остальной
домен (pilot/pilot_b через реальный DATABASE_URL).

Покрытие:
* fix 1 — captured_at freshness: caller-управляемый момент решения → обход срока;
* fix 2 — zone/gate/barrier ownership: payload-зона не сверяется с контроллером;
* fix 3 — статус контроллера: decommissioned контроллер должен отвергаться;
* fix 4 — edge expires_at: протухшая команда не должна открывать реле;
* fix 5 — durable дедуп переживает рестарт (persistent ProcessedStore);
* fix 6 — lease margin: команда, истекающая в течение lease, не выдаётся.
"""
from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import text

from access_control.app.main import create_app
from access_control.edge.command_consumer import EdgeCommandConsumer
from access_control.integrations.relay import MockRelay
from access_control.tests.conftest import (
    PilotFixture,
    SigningClient,
    seed_barrier_command,
    seed_permanent_vehicle,
    seed_taxi_pass,
    utcnow,
)


def _client(controller_uid: str) -> SigningClient:
    """Подписывающий device-auth клиент, привязанный к контроллеру (Ф6, §9.1)."""
    return SigningClient(TestClient(create_app()), controller_uid)


def _anpr_body(pilot: PilotFixture, *, controller_uid, event_id, plate, captured_at):
    return {
        "controller_uid": controller_uid,
        "event_id": event_id,
        "zone_id": pilot.zone_id,
        "gate_id": pilot.gate_id,
        "camera_id": pilot.camera_id,
        "barrier_id": pilot.barrier_id,
        "plate_number": plate,
        "direction": "entry",
        "confidence": 0.95,
        "captured_at": captured_at.isoformat(),
    }


# ----------------------------- fix 1: freshness -----------------------------


def test_stale_captured_at_does_not_bypass_pass_expiry(pg_db, pilot: PilotFixture) -> None:
    """Дыра: вчерашний captured_at для вчера-истёкшего taxi-pass → НЕ allow.

    Эксплойт: pass истёк (valid_until=вчера). Атакующий шлёт captured_at=вчера,
    чтобы движок оценил момент решения внутри окна и выдал allow. Свежесть должна
    отвергнуть запрос (422), команда открытия не создаётся.
    """
    yesterday = utcnow() - dt.timedelta(days=1)
    seed_taxi_pass(
        pg_db,
        pilot,
        normalized="01T777TT",
        max_entries=1,
        valid_from=yesterday - dt.timedelta(days=1),
        valid_until=yesterday,  # истёк вчера
    )
    resp = _client(pilot.controller_uid).post(
        "/api/v1/access/camera-events/anpr",
        json=_anpr_body(
            pilot,
            controller_uid=pilot.controller_uid,
            event_id="fresh-1",
            plate="01T777TT",
            captured_at=yesterday,  # устаревший момент
        ),
    )
    # До фикса: 200 allow (обход срока). После фикса: 422 по свежести.
    assert resp.status_code == 422
    assert resp.json()["detail"] != "allow"


def test_fresh_captured_at_still_passes(pg_db, pilot: PilotFixture) -> None:
    """Легитимный поток: свежий captured_at не ломается фиксом свежести."""
    seed_permanent_vehicle(pg_db, pilot, normalized="01A001AA")
    resp = _client(pilot.controller_uid).post(
        "/api/v1/access/camera-events/anpr",
        json=_anpr_body(
            pilot,
            controller_uid=pilot.controller_uid,
            event_id="fresh-ok-1",
            plate="01A001AA",
            captured_at=utcnow(),
        ),
    )
    assert resp.status_code == 200
    assert resp.json()["decision"] == "allow"


# ------------------------- fix 2: scope ownership ---------------------------


def test_controller_cannot_claim_foreign_zone(
    pg_db, pilot: PilotFixture, pilot_b: PilotFixture
) -> None:
    """Дыра: контроллер зоны A объявляет zone_id зоны B и открывает чужой шлагбаум.

    Эксплойт: авто разрешено только в зоне B. Контроллер зоны A шлёт событие с
    zone_id/gate_id/barrier_id зоны B. До фикса движок оценивает по зоне B → allow
    + команда на чужой шлагбаум. После фикса scope выводится из контроллера →
    zone_not_allowed, команда чужой зоны не создаётся.
    """
    # Авто разрешено в зоне B (pilot_b), но не в зоне A.
    seed_permanent_vehicle(pg_db, pilot_b, normalized="01B222BB")
    body = _anpr_body(
        pilot,
        controller_uid=pilot.controller_uid,
        event_id="scope-1",
        plate="01B222BB",
        captured_at=utcnow(),
    )
    body["zone_id"] = pilot_b.zone_id
    body["gate_id"] = pilot_b.gate_id
    body["barrier_id"] = pilot_b.barrier_id
    resp = _client(pilot.controller_uid).post("/api/v1/access/camera-events/anpr", json=body)
    assert resp.status_code == 200
    out = resp.json()
    assert out["decision"] == "deny"
    assert out["reason"] == "zone_not_allowed"
    assert out["command"] is None
    # Команда на чужой шлагбаум (зона B) не создана.
    foreign_cmds = pg_db.execute(
        text(
            "SELECT count(*) FROM barrier_commands WHERE barrier_id = :b"
        ),
        {"b": pilot_b.barrier_id},
    ).scalar()
    assert foreign_cmds == 0


# ----------------------- fix 3: controller status ---------------------------


def test_decommissioned_controller_rejected_on_anpr(
    pg_db, pilot: PilotFixture
) -> None:
    """Дыра: decommissioned контроллер всё ещё принимается на ANPR-endpoint."""
    pg_db.execute(
        text("UPDATE edge_controllers SET status = 'decommissioned' WHERE id = :i"),
        {"i": pilot.controller_id},
    )
    pg_db.commit()
    resp = _client(pilot.controller_uid).post(
        "/api/v1/access/camera-events/anpr",
        json=_anpr_body(
            pilot,
            controller_uid=pilot.controller_uid,
            event_id="decom-1",
            plate="01A001AA",
            captured_at=utcnow(),
        ),
    )
    assert resp.status_code == 401


def test_decommissioned_controller_rejected_on_commands_next(
    pg_db, pilot: PilotFixture
) -> None:
    """Дыра: decommissioned контроллер всё ещё лизит команды."""
    pg_db.execute(
        text("UPDATE edge_controllers SET status = 'decommissioned' WHERE id = :i"),
        {"i": pilot.controller_id},
    )
    pg_db.commit()
    resp = _client(pilot.controller_uid).get(
        f"/api/v1/access/edge/{pilot.controller_uid}/commands/next"
    )
    assert resp.status_code == 401


def test_inactive_controller_rejected(pg_db, pilot: PilotFixture) -> None:
    """is_active=False контроллер тоже отвергается (defense in depth)."""
    pg_db.execute(
        text("UPDATE edge_controllers SET is_active = false WHERE id = :i"),
        {"i": pilot.controller_id},
    )
    pg_db.commit()
    resp = _client(pilot.controller_uid).post(
        "/api/v1/access/camera-events/anpr",
        json=_anpr_body(
            pilot,
            controller_uid=pilot.controller_uid,
            event_id="inact-1",
            plate="01A001AA",
            captured_at=utcnow(),
        ),
    )
    assert resp.status_code == 401


# ------------------- fix 4 & 5: edge consumer guards ------------------------


class _FakeResp:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload or {}

    def raise_for_status(self) -> None:  # pragma: no cover - happy path
        return None


class _FakeClient:
    """Минимальный HTTP-двойник: GET отдаёт заданный body, POST логирует ack."""

    def __init__(self, body: dict) -> None:
        self._body = body
        self.ack_calls: list[dict] = []

    def get(self, url: str) -> _FakeResp:
        return _FakeResp(200, self._body)

    def post(self, url: str, json: dict) -> _FakeResp:
        self.ack_calls.append(json)
        return _FakeResp(200, {"replayed": False, "result": json.get("result")})


def test_expired_command_does_not_open_relay() -> None:
    """fix 4: команда с expires_at в прошлом не открывает реле (ack как expired)."""
    past = utcnow() - dt.timedelta(seconds=5)
    body = {
        "command_id": "cmd-expired",
        "barrier_id": 7,
        "command_type": "open_barrier",
        "lease_token": "tok-1",
        "expires_at": past.isoformat(),
    }
    client = _FakeClient(body)
    relay = MockRelay()
    consumer = EdgeCommandConsumer(client, "ctrl-uid", relay)

    outcome = consumer.pull_once()
    assert outcome is not None
    # Реле НЕ сработало.
    assert relay.open_count("cmd-expired") == 0
    assert outcome.relay_opened is False
    # Команда всё равно подтверждена (снята с очереди) как expired/skip.
    assert outcome.acked is True
    assert client.ack_calls, "ожидался ack протухшей команды"


def test_processed_store_survives_restart(tmp_path) -> None:
    """fix 5: persistent ProcessedStore переживает «рестарт» edge — реле ≤1 раза."""
    from access_control.edge.command_consumer import FileProcessedStore

    store_path = tmp_path / "processed.json"
    relay = MockRelay()  # одно физическое реле — переживает рестарт процесса edge

    # Старый процесс: fast-path открыл реле и записал command_id в persistent store.
    store1 = FileProcessedStore(str(store_path))
    consumer1 = EdgeCommandConsumer(
        _FakeClient({}), "ctrl-uid", relay, processed_store=store1
    )
    consumer1.on_fast_path("cmd-X", 7)
    assert relay.open_count("cmd-X") == 1

    # «Рестарт»: новый consumer + новый store-инстанс на ТОТ ЖЕ файл, то же реле.
    future = utcnow() + dt.timedelta(seconds=120)
    body = {
        "command_id": "cmd-X",
        "barrier_id": 7,
        "command_type": "open_barrier",
        "lease_token": "tok-2",
        "expires_at": future.isoformat(),
    }
    store2 = FileProcessedStore(str(store_path))
    consumer2 = EdgeCommandConsumer(
        _FakeClient(body), "ctrl-uid", relay, processed_store=store2
    )
    pulled = consumer2.pull_once()
    assert pulled is not None
    assert pulled.relay_deduplicated is True
    # Реле по-прежнему открыто РОВНО один раз, несмотря на рестарт.
    assert relay.open_count("cmd-X") == 1


# --------------------------- fix 6: lease margin ----------------------------


def test_lease_skips_command_expiring_within_lease(
    pg_db, pilot: PilotFixture
) -> None:
    """fix 6: команда, истекающая в течение lease_ttl, не выдаётся (margin)."""
    from access_control.api.commands import lease_next_command

    # expires_at через 10с, lease_ttl=30с → команда истечёт в течение аренды.
    seed_barrier_command(
        pg_db,
        pilot,
        status="pending",
        expires_at=utcnow() + dt.timedelta(seconds=10),
    )
    leased = lease_next_command(pg_db, pilot.controller_id, lease_ttl_seconds=30)
    assert leased is None
