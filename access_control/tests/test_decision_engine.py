"""Тесты Decision Engine (§7 шаги 4–8). Логика пилота: постоянный авто + taxi.

Движок не пишет в БД — только читает и возвращает ``EngineDecision``. Покрывает
ветви: permanent allow, blocked, zone_not_allowed, taxi allow, pass_expired,
pass_already_used, vehicle_not_found, low_confidence.
"""
from __future__ import annotations

import datetime as dt

from access_control.services.decision_engine import AnprDecisionInput, decide
from access_control.tests.conftest import (
    seed_permanent_vehicle,
    seed_taxi_pass,
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


def test_permanent_vehicle_allowed(pg_db, pilot) -> None:
    vid = seed_permanent_vehicle(pg_db, pilot, normalized="01A001AA")
    res = decide(pg_db, _input(pilot, "01A001AA"))
    assert res.decision == "allow"
    assert res.reason == "permanent_vehicle_allowed"
    assert res.matched_vehicle_id == vid


def test_blocked_vehicle_denied(pg_db, pilot) -> None:
    seed_permanent_vehicle(pg_db, pilot, normalized="01B002BB", status="blocked")
    res = decide(pg_db, _input(pilot, "01B002BB"))
    assert res.decision == "deny"
    assert res.reason == "vehicle_blocked"


def test_active_vehicle_without_zone_rule_denied(pg_db, pilot) -> None:
    seed_permanent_vehicle(pg_db, pilot, normalized="01C003CC", with_rule=False)
    res = decide(pg_db, _input(pilot, "01C003CC"))
    assert res.decision == "deny"
    assert res.reason == "zone_not_allowed"


def test_unknown_plate_not_found(pg_db, pilot) -> None:
    res = decide(pg_db, _input(pilot, "99Z999ZZ"))
    assert res.decision == "deny"
    assert res.reason == "vehicle_not_found"


def test_active_taxi_pass_allowed(pg_db, pilot) -> None:
    pid = seed_taxi_pass(pg_db, pilot, normalized="01T100TT")
    res = decide(pg_db, _input(pilot, "01T100TT"))
    assert res.decision == "allow"
    assert res.reason == "temporary_pass_allowed"
    assert res.matched_pass_id == pid


def test_expired_taxi_pass_denied(pg_db, pilot) -> None:
    past = utcnow() - dt.timedelta(hours=2)
    seed_taxi_pass(
        pg_db,
        pilot,
        normalized="01T200TT",
        valid_from=past,
        valid_until=past + dt.timedelta(hours=1),
    )
    res = decide(pg_db, _input(pilot, "01T200TT"))
    assert res.decision == "deny"
    assert res.reason == "pass_expired"


def test_exhausted_taxi_pass_denied(pg_db, pilot) -> None:
    seed_taxi_pass(pg_db, pilot, normalized="01T300TT", max_entries=1, used_entries=1)
    res = decide(pg_db, _input(pilot, "01T300TT"))
    assert res.decision == "deny"
    assert res.reason == "pass_already_used"


def test_low_confidence_manual_review(pg_db, pilot) -> None:
    seed_permanent_vehicle(pg_db, pilot, normalized="01L400LL")
    res = decide(pg_db, _input(pilot, "01L400LL", confidence=0.30))
    assert res.decision == "manual_review"
    assert res.reason == "low_confidence"
