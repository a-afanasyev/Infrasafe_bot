"""A9-P3-12: read-репозитории реестра (SQL вынесен из api/registry.py) — на реальном PG.

Покрывают ветки, которые API-тесты реестра не задевают: пустые входы (без
запроса), связь команды с событием только через ручное открытие, фильтр
approved-жителей, неактивные правила зон, фильтры gate/даты, лимит последних
событий по номеру, экранирование LIKE и выбор кадра по ``kind``.
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import text

from access_control.repositories import (
    event_history_repo,
    passes_repo,
    residence_directory_repo,
    resident_requests_repo,
    vehicles_repo,
)
from access_control.tests.conftest import (
    PilotFixture,
    seed_barrier_command,
    seed_permanent_vehicle,
    seed_user,
    utcnow,
)


def _seed_event(
    db,
    pilot: PilotFixture,
    *,
    plate: str,
    captured_at: dt.datetime,
    gate_id: int | None = None,
    plate_photo: str | None = None,
    overview_photo: str | None = None,
) -> int:
    ce_id = db.execute(
        text(
            "INSERT INTO camera_events "
            "(controller_id, event_id, gate_id, zone_id, direction, captured_at, "
            " received_at, plate_number_original, plate_number_normalized, "
            " plate_photo_url, overview_photo_url) "
            "VALUES (:c, :e, :g, :z, 'entry', :cap, now(), :p, :p, :pp, :op) "
            "RETURNING id"
        ),
        {
            "c": pilot.controller_id,
            "e": f"repo-{uuid.uuid4().hex[:8]}",
            "g": gate_id if gate_id is not None else pilot.gate_id,
            "z": pilot.zone_id,
            "cap": captured_at,
            "p": plate,
            "pp": plate_photo,
            "op": overview_photo,
        },
    ).scalar_one()
    db.commit()
    return ce_id


def _yard_of(db, apartment_id: int) -> int:
    return db.execute(
        text(
            "SELECT b.yard_id FROM apartments a JOIN buildings b ON b.id = a.building_id "
            "WHERE a.id = :id"
        ),
        {"id": apartment_id},
    ).scalar_one()


def _seed_zone(db, name: str) -> int:
    zid = db.execute(
        text("INSERT INTO parking_zones (code, name) VALUES (:c, :n) RETURNING id"),
        {"c": f"z-{uuid.uuid4().hex[:6]}", "n": name},
    ).scalar_one()
    db.commit()
    return zid


# ------------------------------ пустые входы ------------------------------


def test_batch_lookups_short_circuit_on_empty_input(pg_db) -> None:
    assert residence_directory_repo.users_by_ids(pg_db, []) == []
    assert residence_directory_repo.addresses_by_apartment_ids(pg_db, []) == []
    assert residence_directory_repo.serving_zones_by_apartment_ids(pg_db, []) == []
    assert residence_directory_repo.approved_residents_by_apartment_ids(pg_db, []) == []
    assert vehicles_repo.apartment_links(pg_db, []) == []


def test_get_by_id_returns_none_when_missing(pg_db) -> None:
    assert event_history_repo.get_camera_event(pg_db, 999_999) is None
    assert event_history_repo.photo_ref(pg_db, 999_999, "plate") is None
    assert vehicles_repo.get_vehicle(pg_db, 999_999) is None
    assert passes_repo.get_pass(pg_db, 999_999) is None
    assert resident_requests_repo.get_request(pg_db, 999_999) is None
    assert residence_directory_repo.get_zone(pg_db, 999_999) is None


# ------------------------------ история событий ------------------------------


def test_photo_ref_selects_frame_by_kind(pg_db, pilot) -> None:
    ce = _seed_event(
        pg_db, pilot, plate="01PR001", captured_at=utcnow(),
        plate_photo="media://p1", overview_photo="media://o1",
    )
    assert event_history_repo.photo_ref(pg_db, ce, "plate") == "media://p1"
    assert event_history_repo.photo_ref(pg_db, ce, "overview") == "media://o1"


def test_page_events_filters_by_gate_and_date_range(pg_db, pilot, pilot_b) -> None:
    base = utcnow() - dt.timedelta(hours=3)
    old = _seed_event(pg_db, pilot, plate="01GD001", captured_at=base)
    mid = _seed_event(pg_db, pilot, plate="01GD002", captured_at=base + dt.timedelta(hours=1))
    other_gate = _seed_event(
        pg_db, pilot, plate="01GD003", captured_at=base + dt.timedelta(hours=1),
        gate_id=pilot_b.gate_id,
    )

    total, rows = event_history_repo.page_events(
        pg_db, gate_id=pilot.gate_id, limit=50, offset=0
    )
    assert total == 2
    assert [r["id"] for r in rows] == [mid, old]  # captured_at desc

    total, rows = event_history_repo.page_events(
        pg_db,
        date_from=base + dt.timedelta(minutes=30),
        date_to=base + dt.timedelta(hours=2),
        limit=50,
        offset=0,
    )
    assert total == 2
    assert {r["id"] for r in rows} == {mid, other_gate}
    assert all(r["decision"] is None and r["has_command"] is False for r in rows)


def test_page_events_plate_filter_escapes_like_metachars(pg_db, pilot) -> None:
    _seed_event(pg_db, pilot, plate="01ESC01", captured_at=utcnow())
    total, rows = event_history_repo.page_events(pg_db, plate="%", limit=50, offset=0)
    assert (total, rows) == (0, [])
    total, _ = event_history_repo.page_events(pg_db, plate="esc0", limit=50, offset=0)
    assert total == 1


def test_recent_events_by_plate_exact_match_desc_and_limited(pg_db, pilot) -> None:
    base = utcnow() - dt.timedelta(hours=1)
    ids = [
        _seed_event(pg_db, pilot, plate="01RC001", captured_at=base + dt.timedelta(minutes=i))
        for i in range(3)
    ]
    _seed_event(pg_db, pilot, plate="01RC0011", captured_at=base)  # не точное совпадение

    rows = event_history_repo.recent_events_by_plate(pg_db, "01RC001", 2)
    assert [r["id"] for r in rows] == [ids[2], ids[1]]


def test_command_linked_only_via_manual_opening_is_returned(pg_db, pilot) -> None:
    ce = _seed_event(pg_db, pilot, plate="01MO001", captured_at=utcnow())
    operator = seed_user(pg_db, roles="security_operator")
    cmd = seed_barrier_command(pg_db, pilot, decision_id=None)
    pg_db.execute(
        text(
            "INSERT INTO manual_openings "
            "(barrier_id, command_id, operator_user_id, reason, captured_event_id) "
            "VALUES (:b, :cmd, :u, 'проверка', :ce)"
        ),
        {"b": pilot.barrier_id, "cmd": cmd, "u": operator, "ce": ce},
    )
    pg_db.commit()

    # Решений нет → пустые IN заменяются заглушкой, запрос валиден.
    assert event_history_repo.decisions_for_event(pg_db, ce) == []
    openings = event_history_repo.manual_openings_for_event(pg_db, ce, [])
    assert [(str(m["command_id"]), m["operator_user_id"]) for m in openings] == [
        (cmd, operator)
    ]
    commands = event_history_repo.commands_for_event(pg_db, [], [cmd])
    assert [str(c["command_id"]) for c in commands] == [cmd]
    assert event_history_repo.commands_for_event(pg_db, [], []) == []
    assert event_history_repo.confirmations_for_decisions(pg_db, []) == []


# ------------------------------ справочники ------------------------------


def test_residents_only_approved_and_users_named(pg_db, pilot) -> None:
    approved = seed_user(pg_db, roles="applicant")
    pending = seed_user(pg_db, roles="applicant")
    pg_db.execute(
        text("UPDATE users SET first_name = 'Ali', last_name = 'Valiev' WHERE id = :u"),
        {"u": approved},
    )
    for uid, st in ((approved, "approved"), (pending, "pending")):
        pg_db.execute(
            text(
                "INSERT INTO user_apartments "
                "(user_id, apartment_id, status, is_owner, is_primary) "
                "VALUES (:u, :a, :s, false, true)"
            ),
            {"u": uid, "a": pilot.apartment_id, "s": st},
        )
    pg_db.commit()

    residents = residence_directory_repo.approved_residents_by_apartment_ids(
        pg_db, [pilot.apartment_id]
    )
    assert [(r["apartment_id"], r["id"]) for r in residents] == [
        (pilot.apartment_id, approved)
    ]
    users = residence_directory_repo.users_by_ids(pg_db, [approved])
    assert [(u["first_name"], u["last_name"]) for u in users] == [("Ali", "Valiev")]


def test_address_and_serving_zones_follow_apartment_yard(pg_db, pilot) -> None:
    yard = _yard_of(pg_db, pilot.apartment_id)
    pg_db.execute(
        text("INSERT INTO parking_zone_yards (zone_id, yard_id) VALUES (:z, :y)"),
        {"z": pilot.zone_id, "y": yard},
    )
    pg_db.commit()

    [addr] = residence_directory_repo.addresses_by_apartment_ids(pg_db, [pilot.apartment_id])
    assert addr["apartment_id"] == pilot.apartment_id
    assert addr["yard_id"] == yard
    assert addr["building_address"].startswith("ac-bld-")

    zones = residence_directory_repo.serving_zones_by_apartment_ids(
        pg_db, [pilot.apartment_id]
    )
    assert [(z["apartment_id"], z["zone_id"]) for z in zones] == [
        (pilot.apartment_id, pilot.zone_id)
    ]
    assert residence_directory_repo.get_zone(pg_db, pilot.zone_id)["id"] == pilot.zone_id


# ------------------------------ авто / пропуска / заявки ------------------------------


def test_rule_zones_exclude_inactive_rules(pg_db, pilot) -> None:
    vid = seed_permanent_vehicle(pg_db, pilot, normalized="01RZ001")
    other_zone = _seed_zone(pg_db, "Неактивная")
    pg_db.execute(
        text(
            "INSERT INTO access_rules (vehicle_id, zone_id, is_active) "
            "VALUES (:v, :z, false)"
        ),
        {"v": vid, "z": other_zone},
    )
    pg_db.commit()

    assert [z["id"] for z in vehicles_repo.rule_zones(pg_db, vid)] == [pilot.zone_id]


def test_page_vehicles_filters_and_links(pg_db, pilot) -> None:
    vid = seed_permanent_vehicle(pg_db, pilot, normalized="01VH001")
    seed_permanent_vehicle(pg_db, pilot, normalized="01VH002", status="blocked")

    total, rows = vehicles_repo.page_vehicles(
        pg_db, status="active", apartment_id=pilot.apartment_id, limit=50, offset=0
    )
    assert total == 1 and [r["id"] for r in rows] == [vid]
    assert rows[0]["make"] is None  # колонка БД — make (brand — забота API)

    total, _ = vehicles_repo.page_vehicles(pg_db, plate="_", limit=50, offset=0)
    assert total == 0

    links = vehicles_repo.apartment_links(pg_db, [vid])
    assert [(link["vehicle_id"], link["apartment_id"]) for link in links] == [
        (vid, pilot.apartment_id)
    ]


def test_page_passes_and_requests_filters(pg_db, pilot) -> None:
    for st in ("active", "used"):
        pg_db.execute(
            text(
                "INSERT INTO access_passes "
                "(apartment_id, pass_type, max_entries, used_entries, status) "
                "VALUES (:a, 'taxi', 1, :u, :s)"
            ),
            {"a": pilot.apartment_id, "u": 1 if st == "used" else 0, "s": st},
        )
    user = seed_user(pg_db, roles="applicant")
    for st in ("pending", "approved"):
        pg_db.execute(
            text(
                "INSERT INTO resident_access_requests "
                "(apartment_id, created_by_user_id, plate_number_original, "
                " plate_number_normalized, relation_type, status) "
                "VALUES (:a, :u, 'X', 'X', 'owner', :s)"
            ),
            {"a": pilot.apartment_id, "u": user, "s": st},
        )
    pg_db.commit()

    total, rows = passes_repo.page_passes(
        pg_db, pass_type="taxi", status="used", apartment_id=pilot.apartment_id,
        limit=50, offset=0,
    )
    assert total == 1 and rows[0]["status"] == "used"
    assert passes_repo.get_pass(pg_db, rows[0]["id"])["used_entries"] == 1

    total, rows = resident_requests_repo.page_requests(
        pg_db, status="pending", apartment_id=pilot.apartment_id, limit=1, offset=0
    )
    assert total == 1 and rows[0]["status"] == "pending"
    assert resident_requests_repo.get_request(pg_db, rows[0]["id"])["created_by_user_id"] == user
    total, rows = resident_requests_repo.page_requests(pg_db, limit=1, offset=1)
    assert total == 2 and len(rows) == 1
