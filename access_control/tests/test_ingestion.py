"""Тесты идемпотентного ingestion (§7 шаги 1–11, §10.1, §13.2).

Маппинг на критерии приёмки §15:
* Критерий 1 — постоянный авто → allow + строка barrier_commands.
* Критерий 2 — неизвестный/заблокированный → deny, команды нет.
* Критерий 3 — taxi: ровно один въезд (1-й allow + used→max, 2-й deny).
* Критерий 4 — повтор (controller_id,event_id) → прежнее решение, без дублей.
* Критерий 10 — связность идентификаторов (decision↔event↔command↔access_event).

Все тесты требуют postgres (advisory-lock, ON CONFLICT, partial-unique).
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text

import access_control.services.ingestion as ingestion
from access_control.services.ingestion import AnprIngestInput, ingest_anpr
from access_control.tests.conftest import (
    seed_permanent_vehicle,
    seed_taxi_pass,
    utcnow,
)


def _payload(pilot, *, event_id, plate, captured_at=None, confidence=0.95):
    return AnprIngestInput(
        controller_id=pilot.controller_id,
        event_id=event_id,
        zone_id=pilot.zone_id,
        gate_id=pilot.gate_id,
        camera_id=pilot.camera_id,
        barrier_id=pilot.barrier_id,
        plate_number_original=plate,
        direction="entry",
        confidence=confidence,
        captured_at=captured_at or utcnow(),
    )


def _count(db, table, **where):
    clause = " AND ".join(f"{k} = :{k}" for k in where) or "TRUE"
    return db.execute(
        text(f"SELECT COUNT(*) FROM {table} WHERE {clause}"), where
    ).scalar()


# ── Критерий 1 ──────────────────────────────────────────────────────────────
def test_criterion1_permanent_vehicle_allows_and_creates_command(pg_db, pilot) -> None:
    seed_permanent_vehicle(pg_db, pilot, normalized="01A001AA")
    res = ingest_anpr(pg_db, _payload(pilot, event_id="evt-1", plate="01A001AA"))

    assert res.decision == "allow"
    assert res.reason == "permanent_vehicle_allowed"
    assert res.status == "allowed"
    assert res.command is not None
    assert res.command.barrier_id == pilot.barrier_id
    # Команда действительно записана в barrier_commands со ссылкой на решение.
    assert _count(pg_db, "barrier_commands", decision_id=res.decision_id) == 1


# ── Критерий 2 ──────────────────────────────────────────────────────────────
def test_criterion2_unknown_plate_denied_no_command(pg_db, pilot) -> None:
    res = ingest_anpr(pg_db, _payload(pilot, event_id="evt-unknown", plate="99Z999ZZ"))
    assert res.decision == "deny"
    assert res.reason == "vehicle_not_found"
    assert res.command is None
    assert _count(pg_db, "barrier_commands") == 0


def test_criterion2_blocked_plate_denied_no_command(pg_db, pilot) -> None:
    seed_permanent_vehicle(pg_db, pilot, normalized="01B002BB", status="blocked")
    res = ingest_anpr(pg_db, _payload(pilot, event_id="evt-blocked", plate="01B002BB"))
    assert res.decision == "deny"
    assert res.reason == "vehicle_blocked"
    assert res.command is None
    assert _count(pg_db, "barrier_commands") == 0


# ── Критерий 3 ──────────────────────────────────────────────────────────────
def test_criterion3_taxi_allows_exactly_one_entry(pg_db, pilot) -> None:
    pid = seed_taxi_pass(pg_db, pilot, normalized="01T100TT", max_entries=1)
    # Два РАЗНЫХ въезда: разносим captured_at за окно дедупа (10 c), иначе второй
    # справедливо классифицируется как дубль одного приезда (§10.1).
    t1 = utcnow()
    t2 = t1 + dt.timedelta(minutes=5)

    first = ingest_anpr(
        pg_db, _payload(pilot, event_id="taxi-1", plate="01T100TT", captured_at=t1)
    )
    assert first.decision == "allow"
    assert first.reason == "temporary_pass_allowed"
    assert first.command is not None
    used = pg_db.execute(
        text("SELECT used_entries, status FROM access_passes WHERE id = :p"),
        {"p": pid},
    ).one()
    assert used.used_entries == 1
    assert used.status == "used"

    # Второй въезд НОВЫМ event_id вне окна дедупа — отказ, второй команды нет.
    second = ingest_anpr(
        pg_db, _payload(pilot, event_id="taxi-2", plate="01T100TT", captured_at=t2)
    )
    assert second.decision == "deny"
    assert second.reason == "pass_already_used"
    assert second.command is None
    assert _count(pg_db, "barrier_commands") == 1  # только первая команда


# ── Критерий 4 ──────────────────────────────────────────────────────────────
def test_criterion4_replay_same_event_returns_prior_no_duplicates(pg_db, pilot) -> None:
    seed_permanent_vehicle(pg_db, pilot, normalized="01A001AA")
    captured = utcnow()
    p = _payload(pilot, event_id="evt-dup", plate="01A001AA", captured_at=captured)

    first = ingest_anpr(pg_db, p)
    assert first.decision == "allow"
    assert first.replayed is False

    second = ingest_anpr(pg_db, p)
    assert second.replayed is True
    assert second.decision == "allow"
    assert second.decision_id == first.decision_id
    assert second.command.command_id == first.command.command_id

    # Ни одного дубля строк.
    assert _count(pg_db, "camera_events", controller_id=pilot.controller_id) == 1
    assert _count(pg_db, "access_decisions") == 1
    assert _count(pg_db, "barrier_commands") == 1


def test_criterion4_replay_does_not_reconsume_taxi(pg_db, pilot) -> None:
    pid = seed_taxi_pass(pg_db, pilot, normalized="01T100TT", max_entries=1)
    p = _payload(pilot, event_id="taxi-replay", plate="01T100TT")

    ingest_anpr(pg_db, p)
    ingest_anpr(pg_db, p)  # повтор того же event_id

    used = pg_db.execute(
        text("SELECT used_entries FROM access_passes WHERE id = :p"), {"p": pid}
    ).scalar()
    assert used == 1  # не инкрементнут повторно


# ── Критерий 10 ─────────────────────────────────────────────────────────────
def test_criterion10_identifiers_are_linked(pg_db, pilot) -> None:
    vid = seed_permanent_vehicle(pg_db, pilot, normalized="01A001AA")
    res = ingest_anpr(pg_db, _payload(pilot, event_id="evt-link", plate="01A001AA"))

    # access_decisions.camera_event_id → camera_events.id
    dec = pg_db.execute(
        text(
            "SELECT camera_event_id, decision_group_id, matched_vehicle_id "
            "FROM access_decisions WHERE id = :d"
        ),
        {"d": res.decision_id},
    ).one()
    ce_id = pg_db.execute(
        text(
            "SELECT id FROM camera_events "
            "WHERE controller_id = :c AND event_id = :e"
        ),
        {"c": pilot.controller_id, "e": "evt-link"},
    ).scalar()
    assert dec.camera_event_id == ce_id
    assert dec.matched_vehicle_id == vid
    assert str(dec.decision_group_id) == str(res.decision_group_id)

    # barrier_commands.decision_id → access_decisions.id
    cmd = pg_db.execute(
        text(
            "SELECT decision_id, barrier_id, controller_id "
            "FROM barrier_commands WHERE command_id = :cid"
        ),
        {"cid": res.command.command_id},
    ).one()
    assert cmd.decision_id == res.decision_id
    assert cmd.barrier_id == pilot.barrier_id
    assert cmd.controller_id == pilot.controller_id

    # access_events.decision_id / camera_event_id проставлены.
    ev = pg_db.execute(
        text(
            "SELECT decision_id, camera_event_id FROM access_events "
            "WHERE controller_id = :c AND event_id = :e"
        ),
        {"c": pilot.controller_id, "e": "evt-link"},
    ).one()
    assert ev.decision_id == res.decision_id
    assert ev.camera_event_id == ce_id


# ── Окно дедупа §10.1 ────────────────────────────────────────────────────────
def test_dedup_window_distinct_event_id_returns_prior_no_second_command(
    pg_db, pilot
) -> None:
    """Разный event_id, тот же gate+direction+normalized+captured_at в окне 10c →
    прежнее решение; второй команды и расхода нет (§10.1)."""
    pid = seed_taxi_pass(pg_db, pilot, normalized="01T200TT", max_entries=1)
    t = utcnow()

    first = ingest_anpr(
        pg_db, _payload(pilot, event_id="dedup-A", plate="01T200TT", captured_at=t)
    )
    assert first.decision == "allow"
    assert first.replayed is False

    # ДРУГОЙ event_id, тот же приезд в пределах окна (Δ=3c < 10c).
    second = ingest_anpr(
        pg_db,
        _payload(
            pilot,
            event_id="dedup-B",
            plate="01T200TT",
            captured_at=t + dt.timedelta(seconds=3),
        ),
    )
    assert second.replayed is True
    assert second.decision == "allow"
    assert second.decision_id == first.decision_id

    # Расход taxi ровно один; вторая команда не создана.
    used = pg_db.execute(
        text("SELECT used_entries FROM access_passes WHERE id = :p"), {"p": pid}
    ).scalar()
    assert used == 1
    assert _count(pg_db, "camera_events", controller_id=pilot.controller_id) == 1
    assert _count(pg_db, "barrier_commands") == 1


# ── Негативная атомарность §10.1 ─────────────────────────────────────────────
def test_negative_atomicity_rollback_leaves_no_trace(pg_db, pilot, monkeypatch) -> None:
    """Сбой ПОСЛЕ расхода taxi внутри транзакции → откат: нет camera_event/decision/
    command и used_entries не изменился (§10.1, запись одной транзакцией)."""
    pid = seed_taxi_pass(pg_db, pilot, normalized="01T300TT", max_entries=1)

    def _boom(*args, **kwargs):
        raise RuntimeError("injected failure после расхода taxi")

    # Падаем уже после _consume_taxi и _write_decision, но до commit.
    monkeypatch.setattr(ingestion, "_write_access_event", _boom)

    with pytest.raises(RuntimeError):
        ingest_anpr(pg_db, _payload(pilot, event_id="atomic-1", plate="01T300TT"))

    pg_db.rollback()

    assert _count(pg_db, "camera_events", controller_id=pilot.controller_id) == 0
    assert _count(pg_db, "access_decisions") == 0
    assert _count(pg_db, "barrier_commands") == 0
    used = pg_db.execute(
        text("SELECT used_entries FROM access_passes WHERE id = :p"), {"p": pid}
    ).scalar()
    assert used == 0


# ── Адверсариальный омоглиф §12 ──────────────────────────────────────────────
def test_adversarial_homoglyph_letter_o_vs_digit_zero_not_allowed(pg_db, pilot) -> None:
    """Авто с буквой O (лат), ANPR с 0 (ноль) → НЕ allow (recognition_key не
    даёт auto-allow, §12)."""
    seed_permanent_vehicle(pg_db, pilot, normalized="O123BC")
    res = ingest_anpr(pg_db, _payload(pilot, event_id="homo-O0", plate="0123BC"))
    assert res.decision != "allow"
    assert res.reason == "vehicle_not_found"
    assert res.command is None


def test_adversarial_homoglyph_cyrillic_vs_latin_not_allowed(pg_db, pilot) -> None:
    """Авто с кириллицей, ANPR латиницей → НЕ allow (скрипт сохранён в normalized,
    §12)."""
    seed_permanent_vehicle(pg_db, pilot, normalized="АВ777CD")  # кир. А, В
    res = ingest_anpr(pg_db, _payload(pilot, event_id="homo-cyr", plate="AB777CD"))
    assert res.decision != "allow"
    assert res.reason == "vehicle_not_found"
    assert res.command is None
