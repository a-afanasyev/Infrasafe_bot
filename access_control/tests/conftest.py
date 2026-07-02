"""Фикстуры Ф3: синхронная postgres-сессия + сидинг пилотного оборудования.

Тесты ingestion/decision используют реальный PostgreSQL (advisory-lock §13.2,
``INSERT ... ON CONFLICT`` §10.1, partial-unique индексы, append-only триггеры
§9.7) — их нельзя достоверно проверить на sqlite. Поэтому фикстура ``pg_db``
поднимает синхронную сессию из ``settings.DATABASE_URL`` и пропускает тест
(``pytest.skip``), если процесс не на postgres.

Изоляция: перед каждым тестом ``TRUNCATE`` всех таблиц домена access_control
(``RESTART IDENTITY CASCADE``). TRUNCATE не является ``DELETE`` — row-level
append-only триггер (BEFORE UPDATE OR DELETE) его не блокирует. Родительские
``users/yards/buildings/apartments`` НЕ трогаются; нужные строки создаются с
уникальными именами и остаются (безвредно для пилотного стенда).
"""
from __future__ import annotations

import datetime as dt
import json as _json
import os
import uuid
from dataclasses import dataclass
from urllib.parse import urlsplit

import pytest

# Детерминированные ТЕСТОВЫЕ seed-ы device-auth/snapshot-подписи (session-wide).
# Прод-дефолтов в исходнике нет (H2/M1): ровно поэтому suite сам задаёт синтетические
# значения здесь. Устанавливаются на уровне модуля conftest — раньше любого теста и
# до вызова резолва секрета/подписи. ``setdefault`` — чтобы реальный env стенда (если
# задан) не перетирался тестовыми значениями.
os.environ.setdefault(
    "ACCESS_SNAPSHOT_SIGNING_SEED",
    "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff",
)
os.environ.setdefault("ACCESS_DEVICE_HMAC_SEED", "pilot-test-hmac-seed")
os.environ.setdefault("ACCESS_PHOTO_URL_SECRET", "pilot-test-photo-url-secret")
os.environ.setdefault("ACCESS_CODE_SECRET", "pilot-test-code-secret")
# SEC-02: дефолт nonce/lockout backend теперь зависит от DEBUG (в проде → redis).
# Набор гоняется без redis-сервиса для юнит-части, поэтому явно пиним ``memory``,
# чтобы get_nonce_store()/get_failure_store() не уходили в redis по дефолту.
# ``setdefault`` — реальный env стенда (redis) не перетирается.
os.environ.setdefault("ACCESS_NONCE_BACKEND", "memory")
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from access_control.services.code_rate_limit import (
    InMemoryFailureStore,
    reset_failure_store,
)
from access_control.services.device_auth import (
    InMemoryNonceStore,
    hash_api_key,
    reset_nonce_store,
    resolve_device_secret,
    sign_request,
)

# Регистрируем родительские + пилотные таблицы на общем Base.
import uk_management_bot.database.models  # noqa: F401
import access_control.domain  # noqa: F401
from uk_management_bot.config.settings import settings

# Таблицы домена access_control для очистки между тестами (§5.2, 18 шт).
_ACCESS_TABLES = (
    "barrier_commands",
    "manual_openings",
    "access_audit_logs",
    "access_entry_confirmations",
    "access_events",
    "access_decisions",
    "camera_events",
    "controller_sync_events",
    "access_rules",
    "access_passes",
    "resident_access_requests",
    "vehicle_presence_sessions",
    "vehicle_apartments",
    "vehicles",
    "parking_spot_assignments",
    "parking_spots",
    "access_cameras",
    "access_barriers",
    "access_gates",
    "edge_controllers",
    "parking_zone_yards",
    "parking_zones",
)

_IS_POSTGRES = settings.DATABASE_URL.startswith("postgresql")

# Известный device-auth API-ключ пилотных контроллеров (Ф6, §9.1). Хэш кладётся в
# edge_controllers.api_key_hash при сидинге; тесты подписывают запросы этим ключом.
DEVICE_API_KEY = "pilot-test-device-key"


@dataclass(frozen=True)
class PilotFixture:
    """Идентификаторы засеянного пилотного оборудования одной точки въезда."""

    controller_id: int
    controller_uid: str
    zone_id: int
    gate_id: int
    camera_id: int
    barrier_id: int
    apartment_id: int
    api_key: str = DEVICE_API_KEY


# ----------------------- device-auth тест-хелперы (Ф6, §9.1) -----------------------


def device_headers(
    controller_uid: str,
    *,
    method: str,
    path: str,
    body: bytes = b"",
    api_key: str = DEVICE_API_KEY,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    """Сформировать валидные device-auth заголовки (§9.1) для запроса edge→backend.

    Секрет резолвится так же, как backend — детерминированно из ``controller_uid``
    (пилот, синтетический). ``timestamp``/``nonce`` фиксируются для тестов
    freshness/replay.
    """
    secret = resolve_device_secret(controller_uid)
    return sign_request(
        method,
        path,
        body,
        controller_uid=controller_uid,
        api_key=api_key,
        secret=secret,
        timestamp=timestamp,
        nonce=nonce,
    )


class SigningClient:
    """Обёртка TestClient: автоматически подписывает каждый запрос device-auth (§9.1).

    Тело сериализуется детерминированно и отправляется как ``content=`` — подписанные
    байты совпадают с отправленными (HMAC body). Привязана к одному ``controller_uid``;
    для тестов изоляции создают второй экземпляр на другой контроллер.
    """

    def __init__(
        self, client, controller_uid: str, *, api_key: str = DEVICE_API_KEY
    ) -> None:
        self._c = client
        self._uid = controller_uid
        self._key = api_key

    def get(self, url: str, **kw):
        path = urlsplit(url).path
        headers = device_headers(
            self._uid, method="GET", path=path, body=b"", api_key=self._key
        )
        headers.update(kw.pop("headers", None) or {})
        return self._c.get(url, headers=headers, **kw)

    def post(self, url: str, json=None, **kw):
        path = urlsplit(url).path
        body = _json.dumps(json).encode("utf-8") if json is not None else b""
        headers = device_headers(
            self._uid, method="POST", path=path, body=body, api_key=self._key
        )
        headers["content-type"] = "application/json"
        headers.update(kw.pop("headers", None) or {})
        return self._c.post(url, content=body, headers=headers, **kw)


@pytest.fixture(scope="session")
def _pg_sessionmaker():
    if not _IS_POSTGRES:
        pytest.skip("postgres-only тест (advisory-lock/ON CONFLICT/триггеры)")
    engine = create_engine(settings.DATABASE_URL, future=True)
    factory = sessionmaker(bind=engine, future=True)
    yield factory
    engine.dispose()


@pytest.fixture()
def pg_db(_pg_sessionmaker) -> Session:
    """Чистая сессия: TRUNCATE домена access_control перед тестом."""
    session: Session = _pg_sessionmaker()
    tables = ", ".join(_ACCESS_TABLES)
    session.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    session.commit()
    # Изоляция anti-replay nonce-store между тестами (§9.1): свежий in-memory store,
    # иначе nonce из одного теста «протекал» бы в другой.
    reset_nonce_store(InMemoryNonceStore())
    # Изоляция rate-limit счётчиков одноразовых кодов между тестами (§9.3).
    reset_failure_store(InMemoryFailureStore())
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _seed_apartment(db: Session) -> int:
    """Создать yard→building→apartment с уникальными именами, вернуть apartment_id."""
    # NOT NULL колонки родительских таблиц имеют Python-side default (ORM), не
    # server_default — поэтому в сырых INSERT их задаём явно.
    suffix = uuid.uuid4().hex[:8]
    yard_id = db.execute(
        text("INSERT INTO yards (name, is_active) VALUES (:n, true) RETURNING id"),
        {"n": f"ac-yard-{suffix}"},
    ).scalar_one()
    building_id = db.execute(
        text(
            "INSERT INTO buildings "
            "(address, yard_id, entrance_count, floor_count, is_active) "
            "VALUES (:a, :y, 1, 1, true) RETURNING id"
        ),
        {"a": f"ac-bld-{suffix}", "y": yard_id},
    ).scalar_one()
    apartment_id = db.execute(
        text(
            "INSERT INTO apartments (building_id, apartment_number, is_active) "
            "VALUES (:b, :n, true) RETURNING id"
        ),
        {"b": building_id, "n": f"{suffix[:4]}"},
    ).scalar_one()
    return apartment_id


@pytest.fixture()
def pilot(pg_db: Session) -> PilotFixture:
    """Засеять одну зону/точку/камеру/шлагбаум/контроллер + квартиру (§14.2)."""
    from access_control.domain.equipment import (
        AccessBarrier,
        AccessCamera,
        AccessGate,
        EdgeController,
    )
    from access_control.domain.territory import ParkingZone

    zone = ParkingZone(code=f"zone-{uuid.uuid4().hex[:6]}", name="Пилотная зона")
    pg_db.add(zone)
    pg_db.flush()

    controller_uid = f"ctrl-{uuid.uuid4().hex[:6]}"
    controller = EdgeController(
        controller_uid=controller_uid,
        api_key_hash=hash_api_key(DEVICE_API_KEY),
        zone_id=zone.id,
    )
    pg_db.add(controller)
    pg_db.flush()

    gate = AccessGate(
        code=f"gate-{uuid.uuid4().hex[:6]}",
        zone_id=zone.id,
        controller_id=controller.id,
        direction="entry",
    )
    pg_db.add(gate)
    pg_db.flush()

    camera = AccessCamera(
        code=f"cam-{uuid.uuid4().hex[:6]}",
        gate_id=gate.id,
        controller_id=controller.id,
        direction="entry",
    )
    barrier = AccessBarrier(
        code=f"bar-{uuid.uuid4().hex[:6]}",
        gate_id=gate.id,
        controller_id=controller.id,
    )
    pg_db.add_all([camera, barrier])
    pg_db.flush()

    apartment_id = _seed_apartment(pg_db)
    pg_db.commit()

    return PilotFixture(
        controller_id=controller.id,
        controller_uid=controller_uid,
        zone_id=zone.id,
        gate_id=gate.id,
        camera_id=camera.id,
        barrier_id=barrier.id,
        apartment_id=apartment_id,
    )


@pytest.fixture()
def pilot_b(pg_db: Session, pilot: PilotFixture) -> PilotFixture:
    """Второй контроллер/точка/шлагбаум — для тестов изоляции по controller_id (§9.1)."""
    from access_control.domain.equipment import (
        AccessBarrier,
        AccessCamera,
        AccessGate,
        EdgeController,
    )
    from access_control.domain.territory import ParkingZone

    zone = ParkingZone(code=f"zoneB-{uuid.uuid4().hex[:6]}", name="Зона B")
    pg_db.add(zone)
    pg_db.flush()

    controller_uid = f"ctrlB-{uuid.uuid4().hex[:6]}"
    controller = EdgeController(
        controller_uid=controller_uid,
        api_key_hash=hash_api_key(DEVICE_API_KEY),
        zone_id=zone.id,
    )
    pg_db.add(controller)
    pg_db.flush()

    gate = AccessGate(
        code=f"gateB-{uuid.uuid4().hex[:6]}",
        zone_id=zone.id,
        controller_id=controller.id,
        direction="entry",
    )
    pg_db.add(gate)
    pg_db.flush()

    camera = AccessCamera(
        code=f"camB-{uuid.uuid4().hex[:6]}",
        gate_id=gate.id,
        controller_id=controller.id,
        direction="entry",
    )
    barrier = AccessBarrier(
        code=f"barB-{uuid.uuid4().hex[:6]}",
        gate_id=gate.id,
        controller_id=controller.id,
    )
    pg_db.add_all([camera, barrier])
    pg_db.flush()
    pg_db.commit()

    return PilotFixture(
        controller_id=controller.id,
        controller_uid=controller_uid,
        zone_id=zone.id,
        gate_id=gate.id,
        camera_id=camera.id,
        barrier_id=barrier.id,
        apartment_id=pilot.apartment_id,
    )


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def seed_permanent_vehicle(
    db: Session,
    pilot: PilotFixture,
    *,
    normalized: str,
    status: str = "active",
    with_rule: bool = True,
) -> int:
    """Засеять постоянный авто: vehicle + active vehicle_apartments + access_rule.

    ``with_rule=False`` пропускает правило зоны (для проверки zone_not_allowed).
    Возвращает vehicle_id.
    """
    from access_control.domain.passes import AccessRule
    from access_control.domain.vehicles import Vehicle, VehicleApartment

    vehicle = Vehicle(
        plate_number_original=normalized,
        plate_number_normalized=normalized,
        plate_country="UZ",
        status=status,
    )
    db.add(vehicle)
    db.flush()
    db.add(
        VehicleApartment(
            vehicle_id=vehicle.id,
            apartment_id=pilot.apartment_id,
            relation_type="owner",
            status="active",
        )
    )
    if with_rule:
        db.add(
            AccessRule(
                vehicle_id=vehicle.id,
                apartment_id=pilot.apartment_id,
                zone_id=pilot.zone_id,
                allowed_directions=["entry"],
                is_active=True,
            )
        )
    db.commit()
    return vehicle.id


def seed_barrier_command(
    db: Session,
    pilot: PilotFixture,
    *,
    decision_id: int | None = None,
    status: str = "pending",
    attempts: int = 0,
    max_attempts: int = 5,
    lease_token: str | None = None,
    lease_expires_at: dt.datetime | None = None,
    expires_at: dt.datetime | None = None,
    created_at: dt.datetime | None = None,
) -> str:
    """Вставить строку barrier_commands напрямую (Ф4). Возвращает command_id (str).

    Позволяет детерминированно засеять очередь для тестов lease/reclaim/dead-letter
    без прохождения полного ingestion.
    """
    command_id = str(uuid.uuid4())
    db.execute(
        text(
            """
            INSERT INTO barrier_commands
              (command_id, decision_id, controller_id, barrier_id, command_type,
               status, attempts, max_attempts, lease_token, lease_expires_at,
               expires_at, created_at, updated_at)
            VALUES
              (:cmd, :did, :cid, :bid, 'open_barrier', :st, :att, :max, :tok,
               :lexp, :exp, COALESCE(:cat, now()), now())
            """
        ),
        {
            "cmd": command_id,
            "did": decision_id,
            "cid": pilot.controller_id,
            "bid": pilot.barrier_id,
            "st": status,
            "att": attempts,
            "max": max_attempts,
            "tok": lease_token,
            "lexp": lease_expires_at,
            "exp": expires_at,
            "cat": created_at,
        },
    )
    db.commit()
    return command_id


@dataclass(frozen=True)
class PendingReviewFixture:
    """Идентификаторы засеянного pending_review-решения (Ф5, §9.5)."""

    camera_event_id: int
    decision_id: int
    decision_group_id: str


def seed_user(
    db: Session, *, roles: str | list[str] = "security_operator", status: str = "approved"
) -> int:
    """Создать пользователя с ролью(ями) для operator/admin API (Ф5, §6.3).

    Возвращает users.id. Роли пишутся в ``users.roles`` (JSON-массив) — единый
    источник ролей (CLAUDE.md). ``operator_user_id`` в manual_openings — FK RESTRICT,
    поэтому пользователь должен существовать.
    """
    import json

    role_list = [roles] if isinstance(roles, str) else list(roles)
    tid = int(uuid.uuid4().int % 1_000_000_000) + 3_000_000_000
    uid = db.execute(
        text(
            "INSERT INTO users "
            "(telegram_id, roles, active_role, status, language, verification_status) "
            "VALUES (:t, :r, :ar, :st, 'ru', 'verified') RETURNING id"
        ),
        {"t": tid, "r": json.dumps(role_list), "ar": role_list[0], "st": status},
    ).scalar()
    db.commit()
    return uid


def seed_pending_review(
    db: Session,
    pilot: PilotFixture,
    *,
    event_id: str | None = None,
    deadline_at: dt.datetime | None = None,
    captured_at: dt.datetime | None = None,
) -> PendingReviewFixture:
    """Засеять camera_event + access_decision(pending_review) под шлагбаум пилота.

    Позволяет детерминированно проверять резолюцию/expiry (§9.5) без прогона полного
    ingestion. ``deadline_at`` в прошлом моделирует просроченный pending.
    """
    eid = event_id or f"mr-{uuid.uuid4().hex[:8]}"
    cap = captured_at or utcnow()
    ce_id = db.execute(
        text(
            "INSERT INTO camera_events "
            "(controller_id, event_id, gate_id, zone_id, direction, captured_at, received_at) "
            "VALUES (:c, :e, :g, :z, 'entry', :cap, now()) RETURNING id"
        ),
        {"c": pilot.controller_id, "e": eid, "g": pilot.gate_id, "z": pilot.zone_id, "cap": cap},
    ).scalar()
    grp = str(uuid.uuid4())
    deadline = deadline_at if deadline_at is not None else (utcnow() + dt.timedelta(seconds=120))
    did = db.execute(
        text(
            "INSERT INTO access_decisions "
            "(camera_event_id, decision_group_id, decision, status, reason, "
            " review_deadline_at, source) "
            "VALUES (:ce, :g, 'manual_review', 'pending_review', "
            " 'manual_review_required', :dl, 'connected') RETURNING id"
        ),
        {"ce": ce_id, "g": grp, "dl": deadline},
    ).scalar()
    db.commit()
    return PendingReviewFixture(
        camera_event_id=ce_id, decision_id=did, decision_group_id=grp
    )


def seed_taxi_pass(
    db: Session,
    pilot: PilotFixture,
    *,
    normalized: str,
    max_entries: int = 1,
    used_entries: int = 0,
    valid_from: dt.datetime | None = None,
    valid_until: dt.datetime | None = None,
    status: str = "active",
) -> int:
    """Засеять активный taxi-pass с номером ``normalized``. Возвращает pass_id."""
    from access_control.domain.passes import AccessPass

    ap = AccessPass(
        apartment_id=pilot.apartment_id,
        pass_type="taxi",
        zone_id=pilot.zone_id,
        plate_number_original=normalized,
        plate_number_normalized=normalized,
        valid_from=valid_from,
        valid_until=valid_until,
        max_entries=max_entries,
        used_entries=used_entries,
        status=status,
    )
    db.add(ap)
    db.commit()
    return ap.id
