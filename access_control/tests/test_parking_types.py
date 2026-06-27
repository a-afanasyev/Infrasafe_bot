"""Тесты типа парковки (assigned/shared) + гибкий кап + учёт заездов.

Расширяет Decision Engine зоно-типной логикой постоянного авто (§5, §7, §10.3):

* ``assigned`` — место закреплено за квартирой (``parking_spot_assignments``);
  любой активный авто квартиры пользуется её местом. allow ``assigned_spot_allowed``;
  нет закрепления → deny ``spot_not_assigned``; просроченная аренда →
  deny ``spot_rental_expired``.
* ``shared`` — разрешены все авто квартиры, обслуживаемой зоной (apartment→
  building→yard ∈ зоны через ``parking_zone_yards``). allow ``shared_access_allowed``;
  гибкий кап ``max_permanent_vehicles_per_apartment`` (по умолчанию NULL — без
  лимита): превышение → manual_review ``per_apartment_limit_exceeded``.
* Совместимость: существующая ветка ``access_rules`` остаётся allow-веткой
  (``permanent_vehicle_allowed``) — регрессия в test_decision_engine.

Учёт заездов (§10.3): число РАЗРЕШЁННЫХ въездов по зоне; выезд пока off (presence).
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from access_control.services.decision_engine import AnprDecisionInput, decide
from access_control.services.parking_occupancy import zone_occupancy
from access_control.tests.conftest import (
    PilotFixture,
    seed_permanent_vehicle,
    utcnow,
)


def _input(pilot, normalized, *, confidence=0.95, captured_at=None):
    return AnprDecisionInput(
        controller_id=pilot.controller_id,
        zone_id=pilot.zone_id,
        gate_id=pilot.gate_id,
        camera_id=pilot.camera_id,
        plate_number_normalized=normalized,
        recognition_key=normalized,
        direction="entry",
        confidence=confidence,
        captured_at=captured_at or utcnow(),
    )


def _set_parking_type(db: Session, zone_id: int, parking_type: str) -> None:
    db.execute(
        text("UPDATE parking_zones SET parking_type = :t WHERE id = :z"),
        {"t": parking_type, "z": zone_id},
    )
    db.commit()


def _set_zone_cap(db: Session, zone_id: int, cap: int | None) -> None:
    db.execute(
        text(
            "UPDATE parking_zones "
            "SET max_permanent_vehicles_per_apartment = :c WHERE id = :z"
        ),
        {"c": cap, "z": zone_id},
    )
    db.commit()


def _yard_of_apartment(db: Session, apartment_id: int) -> int:
    return db.execute(
        text(
            "SELECT b.yard_id FROM apartments a "
            "JOIN buildings b ON a.building_id = b.id WHERE a.id = :a"
        ),
        {"a": apartment_id},
    ).scalar_one()


def _link_zone_to_apartment_yard(db: Session, zone_id: int, apartment_id: int) -> None:
    """Подвязать зону к фазе (yard) квартиры → apartment обслуживается зоной."""
    yard_id = _yard_of_apartment(db, apartment_id)
    db.execute(
        text(
            "INSERT INTO parking_zone_yards (zone_id, yard_id) VALUES (:z, :y) "
            "ON CONFLICT (zone_id, yard_id) DO NOTHING"
        ),
        {"z": zone_id, "y": yard_id},
    )
    db.commit()


def _create_spot(db: Session, zone_id: int, *, code: str | None = None) -> int:
    code = code or f"spot-{uuid.uuid4().hex[:6]}"
    return db.execute(
        text(
            "INSERT INTO parking_spots (zone_id, code, status) "
            "VALUES (:z, :c, 'active') RETURNING id"
        ),
        {"z": zone_id, "c": code},
    ).scalar_one()


def _assign_spot(
    db: Session,
    *,
    spot_id: int,
    apartment_id: int,
    ownership_type: str = "owned",
    valid_from: dt.datetime | None = None,
    valid_until: dt.datetime | None = None,
    status: str = "active",
) -> int:
    sid = db.execute(
        text(
            "INSERT INTO parking_spot_assignments "
            "(spot_id, apartment_id, ownership_type, valid_from, valid_until, status) "
            "VALUES (:sp, :ap, :ot, :vf, :vu, :st) RETURNING id"
        ),
        {
            "sp": spot_id,
            "ap": apartment_id,
            "ot": ownership_type,
            "vf": valid_from,
            "vu": valid_until,
            "st": status,
        },
    ).scalar_one()
    db.commit()
    return sid


def _insert_allow_entry_event(db: Session, pilot: PilotFixture) -> None:
    """Вставить разрешённый въезд (allow/entry) в журнал проезда зоны."""
    db.execute(
        text(
            "INSERT INTO access_events "
            "(controller_id, event_id, zone_id, gate_id, direction, decision, "
            " reason, occurred_at) "
            "VALUES (:c, :e, :z, :g, 'entry', 'allow', 'shared_access_allowed', now())"
        ),
        {
            "c": pilot.controller_id,
            "e": f"occ-{uuid.uuid4().hex[:10]}",
            "z": pilot.zone_id,
            "g": pilot.gate_id,
        },
    )
    db.commit()


# ----------------------------- assigned зона ------------------------------------


def test_assigned_spot_allowed(pg_db, pilot) -> None:
    _set_parking_type(pg_db, pilot.zone_id, "assigned")
    vid = seed_permanent_vehicle(
        pg_db, pilot, normalized="01A010AA", with_rule=False
    )
    spot = _create_spot(pg_db, pilot.zone_id)
    _assign_spot(pg_db, spot_id=spot, apartment_id=pilot.apartment_id)
    res = decide(pg_db, _input(pilot, "01A010AA"))
    assert res.decision == "allow"
    assert res.reason == "assigned_spot_allowed"
    assert res.matched_vehicle_id == vid


def test_assigned_without_assignment_denied(pg_db, pilot) -> None:
    _set_parking_type(pg_db, pilot.zone_id, "assigned")
    seed_permanent_vehicle(pg_db, pilot, normalized="01A020AA", with_rule=False)
    res = decide(pg_db, _input(pilot, "01A020AA"))
    assert res.decision == "deny"
    assert res.reason == "spot_not_assigned"


def test_assigned_expired_rental_denied(pg_db, pilot) -> None:
    _set_parking_type(pg_db, pilot.zone_id, "assigned")
    seed_permanent_vehicle(pg_db, pilot, normalized="01A030AA", with_rule=False)
    spot = _create_spot(pg_db, pilot.zone_id)
    past = utcnow() - dt.timedelta(days=2)
    _assign_spot(
        pg_db,
        spot_id=spot,
        apartment_id=pilot.apartment_id,
        ownership_type="rented",
        valid_from=past,
        valid_until=past + dt.timedelta(days=1),
    )
    res = decide(pg_db, _input(pilot, "01A030AA"))
    assert res.decision == "deny"
    assert res.reason == "spot_rental_expired"


# ------------------------------ shared зона -------------------------------------


def test_shared_access_allowed_when_served(pg_db, pilot) -> None:
    _set_parking_type(pg_db, pilot.zone_id, "shared")
    _link_zone_to_apartment_yard(pg_db, pilot.zone_id, pilot.apartment_id)
    vid = seed_permanent_vehicle(
        pg_db, pilot, normalized="01S010SS", with_rule=False
    )
    res = decide(pg_db, _input(pilot, "01S010SS"))
    assert res.decision == "allow"
    assert res.reason == "shared_access_allowed"
    assert res.matched_vehicle_id == vid


def test_shared_not_served_not_allowed(pg_db, pilot) -> None:
    _set_parking_type(pg_db, pilot.zone_id, "shared")
    # НЕ подвязываем зону к фазе квартиры и нет access_rule → не allow.
    seed_permanent_vehicle(pg_db, pilot, normalized="01S020SS", with_rule=False)
    res = decide(pg_db, _input(pilot, "01S020SS"))
    assert res.decision != "allow"
    assert res.reason == "zone_not_allowed"


# ------------------------------ гибкий кап --------------------------------------


def test_shared_cap_exceeded_manual_review(pg_db, pilot) -> None:
    _set_parking_type(pg_db, pilot.zone_id, "shared")
    _link_zone_to_apartment_yard(pg_db, pilot.zone_id, pilot.apartment_id)
    _set_zone_cap(pg_db, pilot.zone_id, 1)
    # Два активных авто на одной квартире → превышение капа 1.
    seed_permanent_vehicle(pg_db, pilot, normalized="01C010CC", with_rule=False)
    seed_permanent_vehicle(pg_db, pilot, normalized="01C011CC", with_rule=False)
    res = decide(pg_db, _input(pilot, "01C010CC"))
    assert res.decision == "manual_review"
    assert res.reason == "per_apartment_limit_exceeded"


def test_shared_no_cap_unlimited(pg_db, pilot) -> None:
    _set_parking_type(pg_db, pilot.zone_id, "shared")
    _link_zone_to_apartment_yard(pg_db, pilot.zone_id, pilot.apartment_id)
    _set_zone_cap(pg_db, pilot.zone_id, None)
    seed_permanent_vehicle(pg_db, pilot, normalized="01C020CC", with_rule=False)
    seed_permanent_vehicle(pg_db, pilot, normalized="01C021CC", with_rule=False)
    res = decide(pg_db, _input(pilot, "01C020CC"))
    assert res.decision == "allow"
    assert res.reason == "shared_access_allowed"


# ------------------------------ учёт заездов ------------------------------------


def test_zone_occupancy_counts_allowed_entries(pg_db, pilot) -> None:
    for _ in range(3):
        _insert_allow_entry_event(pg_db, pilot)
    occ = zone_occupancy(pg_db, pilot.zone_id)
    assert occ.entries == 3
    # Выезд пока не детектируется (presence off, §10.3) → exits=0, occupancy=entries.
    assert occ.exits == 0
    assert occ.occupancy == 3
