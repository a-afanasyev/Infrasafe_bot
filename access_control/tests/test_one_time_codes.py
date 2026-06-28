"""Ф?: Одноразовые коды гостевых пропусков (§9.3). PostgreSQL-only.

Покрывает §9.3 целиком:
* генерация: guest без номера → 8-значный код в ответе РОВНО ОДИН раз, в БД
  только хэш (HMAC), TTL ≤ 30 мин, max_entries=1 (одноразовый);
* guest-с-номером / taxi → прежний путь по номеру, БЕЗ кода;
* redeem валидного кода → success, apartment/тип раскрыты ТОЛЬКО при успехе,
  durable-команда + manual_opening + audit (без кода), pass погашен (used);
* повторное погашение / истёкший / неверный → ОБЩАЯ ошибка (no enumeration);
* 5 неверных за 10 мин → 429 блок (даже верный код после блока → 429);
* RBAC: applicant → 403, без auth → 401;
* код НЕ попадает в логи (caplog по access_control.*);
* атомарность: повторный redeem того же кода даёт ровно одно открытие.

Auth — существующая JWT/cookie (get_current_user); override подставляет
оператора нужной роли (как в test_operator_api_rbac).
"""
from __future__ import annotations

import datetime as dt
import logging
import types

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from access_control.app.main import create_app
from access_control.services.code_rate_limit import (
    InMemoryFailureStore,
    reset_failure_store,
)
from access_control.services.one_time_codes import hash_code
from access_control.services.resident import create_resident_pass
from access_control.tests.conftest import PilotFixture, seed_user, utcnow
from access_control.tests.test_resident_api import (
    _link_user_apartment,
    _link_zone_yard,
    _yard_of,
)
from uk_management_bot.api.dependencies import get_current_user


# ------------------------------ auth / client ------------------------------


def _fake_user(uid: int, role: str = "security_operator", status: str = "approved"):
    import json

    return lambda: types.SimpleNamespace(
        id=uid, roles=json.dumps([role]), active_role=role, status=status
    )


def _operator_client(uid: int, role: str = "security_operator") -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, role)
    return TestClient(app)


# ------------------------------ seed helpers ------------------------------


def _seed_resident(pg_db, pilot: PilotFixture) -> int:
    """Создать applicant-жителя с approved-владением квартирой пилота + зоно-связь."""
    uid = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, uid, pilot.apartment_id, "approved")
    _link_zone_yard(pg_db, pilot.zone_id, _yard_of(pg_db, pilot.apartment_id))
    return uid


def _make_guest_code(pg_db, pilot: PilotFixture, *, valid_until=None) -> tuple[int, str]:
    """Создать guest-пропуск без номера через сервис → (pass_id, plaintext_code)."""
    uid = _seed_resident(pg_db, pilot)
    vu = valid_until or (utcnow() + dt.timedelta(hours=2))
    created = create_resident_pass(
        pg_db,
        actor_user_id=uid,
        apartment_id=pilot.apartment_id,
        pass_type="guest",
        valid_until=vu,
        zone_id=pilot.zone_id,
    )
    return created.access_pass.id, created.one_time_code


@pytest.fixture(autouse=True)
def _fresh_failure_store():
    """Изоляция rate-limit счётчиков между тестами (in-memory, §9.3)."""
    reset_failure_store(InMemoryFailureStore())
    yield
    reset_failure_store(InMemoryFailureStore())


# ============================ генерация (§9.3) ============================


def test_guest_without_plate_generates_8digit_code_once(pg_db, pilot: PilotFixture) -> None:
    pass_id, code = _make_guest_code(pg_db, pilot)
    assert code is not None
    assert len(code) == 8
    assert code.isdigit()


def test_guest_code_stored_only_as_hash(pg_db, pilot: PilotFixture) -> None:
    """В БД хранится только HMAC-хэш, plaintext нигде в строке пропуска (§9.3)."""
    pass_id, code = _make_guest_code(pg_db, pilot)
    row = pg_db.execute(
        text(
            "SELECT one_time_code_hash, plate_number_original, plate_number_normalized "
            "FROM access_passes WHERE id = :i"
        ),
        {"i": pass_id},
    ).first()
    assert row[0] == hash_code(code)
    assert code not in (row[0] or "")
    assert row[1] is None and row[2] is None


def test_guest_code_ttl_capped_at_30min(pg_db, pilot: PilotFixture) -> None:
    """Запрошенный TTL 2ч → valid_until ужимается до ≤ now+30мин (§9.3)."""
    before = utcnow()
    pass_id, _ = _make_guest_code(pg_db, pilot, valid_until=before + dt.timedelta(hours=2))
    vu = pg_db.execute(
        text("SELECT valid_until FROM access_passes WHERE id = :i"), {"i": pass_id}
    ).scalar_one()
    assert vu <= before + dt.timedelta(minutes=30, seconds=5)


def test_guest_code_is_one_time(pg_db, pilot: PilotFixture) -> None:
    """Сгенерированный код — одноразовый: max_entries=1 (§9.3)."""
    pass_id, _ = _make_guest_code(pg_db, pilot)
    me = pg_db.execute(
        text("SELECT max_entries FROM access_passes WHERE id = :i"), {"i": pass_id}
    ).scalar_one()
    assert me == 1


def test_guest_with_plate_no_code(pg_db, pilot: PilotFixture) -> None:
    """guest С номером → прежний путь по номеру, кода нет (§9.3)."""
    uid = _seed_resident(pg_db, pilot)
    created = create_resident_pass(
        pg_db,
        actor_user_id=uid,
        apartment_id=pilot.apartment_id,
        pass_type="guest",
        valid_until=utcnow() + dt.timedelta(hours=2),
        plate_number_original="01X777YZ",
        zone_id=pilot.zone_id,
    )
    assert created.one_time_code is None
    assert created.access_pass.one_time_code_hash is None


def test_taxi_no_code(pg_db, pilot: PilotFixture) -> None:
    uid = _seed_resident(pg_db, pilot)
    created = create_resident_pass(
        pg_db,
        actor_user_id=uid,
        apartment_id=pilot.apartment_id,
        pass_type="taxi",
        valid_until=utcnow() + dt.timedelta(hours=2),
        plate_number_original="01T111AA",
        zone_id=pilot.zone_id,
    )
    assert created.one_time_code is None


# ============================ redeem (§9.3) ============================


def test_redeem_valid_code_success_reveals_and_opens(pg_db, pilot: PilotFixture) -> None:
    pass_id, code = _make_guest_code(pg_db, pilot)
    op = seed_user(pg_db, roles="security_operator")
    client = _operator_client(op)
    resp = client.post("/api/v1/access/passes/redeem-code", json={"code": code})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Раскрытие квартиры/типа ТОЛЬКО при успехе (§9.3).
    assert body["apartment_id"] == pilot.apartment_id
    assert body["pass_type"] == "guest"
    assert body["valid_until"] is not None
    assert body["command"]["command_id"] is not None
    assert body["command"]["barrier_id"] == pilot.barrier_id
    # Pass погашен.
    row = pg_db.execute(
        text("SELECT used_entries, status FROM access_passes WHERE id = :i"),
        {"i": pass_id},
    ).first()
    assert row[0] == 1
    assert row[1] == "used"
    # Команда + manual_opening + audit созданы.
    assert pg_db.execute(
        text("SELECT count(*) FROM barrier_commands WHERE barrier_id = :b"),
        {"b": pilot.barrier_id},
    ).scalar() == 1
    assert pg_db.execute(
        text("SELECT count(*) FROM manual_openings WHERE barrier_id = :b"),
        {"b": pilot.barrier_id},
    ).scalar() == 1
    assert pg_db.execute(
        text(
            "SELECT count(*) FROM access_audit_logs "
            "WHERE action = 'access.guest_code_redeemed'"
        )
    ).scalar() == 1


def test_redeem_used_code_rejected_and_atomic(pg_db, pilot: PilotFixture) -> None:
    """Повторное погашение → общий отказ; ровно ОДНО открытие (атомарность §9.3)."""
    pass_id, code = _make_guest_code(pg_db, pilot)
    op = seed_user(pg_db, roles="security_operator")
    client = _operator_client(op)
    r1 = client.post("/api/v1/access/passes/redeem-code", json={"code": code})
    assert r1.status_code == 200
    r2 = client.post("/api/v1/access/passes/redeem-code", json={"code": code})
    assert r2.status_code == 422
    # Не раскрывает квартиру/тип на отказе.
    assert "apartment_id" not in r2.text
    # Ровно одно открытие.
    assert pg_db.execute(
        text("SELECT count(*) FROM barrier_commands WHERE barrier_id = :b"),
        {"b": pilot.barrier_id},
    ).scalar() == 1


def test_redeem_expired_code_rejected(pg_db, pilot: PilotFixture) -> None:
    pass_id, code = _make_guest_code(pg_db, pilot)
    pg_db.execute(
        text("UPDATE access_passes SET valid_until = :t WHERE id = :i"),
        {"t": utcnow() - dt.timedelta(minutes=1), "i": pass_id},
    )
    pg_db.commit()
    op = seed_user(pg_db, roles="security_operator")
    client = _operator_client(op)
    resp = client.post("/api/v1/access/passes/redeem-code", json={"code": code})
    assert resp.status_code == 422
    assert "apartment_id" not in resp.text


def test_redeem_wrong_code_generic_no_enumeration(pg_db, pilot: PilotFixture) -> None:
    _make_guest_code(pg_db, pilot)
    op = seed_user(pg_db, roles="security_operator")
    client = _operator_client(op)
    resp = client.post("/api/v1/access/passes/redeem-code", json={"code": "00000000"})
    assert resp.status_code == 422
    # Общая ошибка — не раскрывает существование кода/квартиру/тип.
    assert "apartment_id" not in resp.text
    assert "pass_type" not in resp.text


def test_redeem_lockout_after_5_failures(pg_db, pilot: PilotFixture) -> None:
    """4 неверных → 422; 5-я → 429 блок; затем ВЕРНЫЙ код → 429 (блок, §9.3)."""
    _, good_code = _make_guest_code(pg_db, pilot)
    op = seed_user(pg_db, roles="security_operator")
    client = _operator_client(op)
    for _ in range(4):
        r = client.post("/api/v1/access/passes/redeem-code", json={"code": "11111111"})
        assert r.status_code == 422
    r5 = client.post("/api/v1/access/passes/redeem-code", json={"code": "11111111"})
    assert r5.status_code == 429
    # Даже верный код заблокирован.
    r_good = client.post("/api/v1/access/passes/redeem-code", json={"code": good_code})
    assert r_good.status_code == 429


# ------------------------------ RBAC (§9.3/§6.3) ------------------------------


def test_redeem_requires_auth_401(pg_db, pilot: PilotFixture) -> None:
    _, code = _make_guest_code(pg_db, pilot)
    client = TestClient(create_app())
    resp = client.post("/api/v1/access/passes/redeem-code", json={"code": code})
    assert resp.status_code == 401


def test_redeem_applicant_forbidden_403(pg_db, pilot: PilotFixture) -> None:
    _, code = _make_guest_code(pg_db, pilot)
    uid = seed_user(pg_db, roles="applicant")
    client = _operator_client(uid, role="applicant")
    resp = client.post("/api/v1/access/passes/redeem-code", json={"code": code})
    assert resp.status_code == 403


def test_redeem_route_registered() -> None:
    paths = {route.path for route in create_app().routes}
    assert "/api/v1/access/passes/redeem-code" in paths


# ------------------------------ no-log (§9.3/§11) ------------------------------


def test_code_not_in_logs(pg_db, pilot: PilotFixture, caplog) -> None:
    """Plaintext-код не выводится в логи access_control.* (§9.3, §11)."""
    with caplog.at_level(logging.DEBUG, logger="access_control"):
        pass_id, code = _make_guest_code(pg_db, pilot)
        op = seed_user(pg_db, roles="security_operator")
        client = _operator_client(op)
        client.post("/api/v1/access/passes/redeem-code", json={"code": code})
        # неверная попытка тоже не должна логировать сам код
        client.post("/api/v1/access/passes/redeem-code", json={"code": "22222222"})
    assert code not in caplog.text
    assert "22222222" not in caplog.text
