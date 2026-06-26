"""barrier_commands worker: reclaim, dead-letter, метрики (§9.2). PostgreSQL-only.

Также критерий §15.11: команды обслуживает ОТДЕЛЬНЫЙ barrier_commands worker;
webhook_outbox не используется (ни запись, ни импорт).
"""
from __future__ import annotations

import datetime as dt
import inspect

from sqlalchemy import text

from access_control.services import barrier_worker
from access_control.services.barrier_worker import (
    queue_metrics,
    reclaim_expired_leases,
    tick,
)
from access_control.services.ingestion import AnprIngestInput, ingest_anpr
from access_control.tests.conftest import (
    PilotFixture,
    seed_barrier_command,
    seed_permanent_vehicle,
    utcnow,
)


def _status(db, cmd_id: str) -> str:
    return db.execute(
        text("SELECT status FROM barrier_commands WHERE command_id = :c"),
        {"c": cmd_id},
    ).scalar()


def test_reclaim_returns_expired_lease_to_pending(pg_db, pilot: PilotFixture) -> None:
    cmd_id = seed_barrier_command(
        pg_db,
        pilot,
        status="leased",
        attempts=1,
        max_attempts=5,
        lease_token="11111111-1111-1111-1111-111111111111",
        lease_expires_at=utcnow() - dt.timedelta(seconds=60),
    )
    n = reclaim_expired_leases(pg_db)
    pg_db.commit()
    assert n == 1
    assert _status(pg_db, cmd_id) == "pending"
    # lease_token очищен.
    tok = pg_db.execute(
        text("SELECT lease_token FROM barrier_commands WHERE command_id = :c"),
        {"c": cmd_id},
    ).scalar()
    assert tok is None


def test_reclaim_ignores_live_lease(pg_db, pilot: PilotFixture) -> None:
    cmd_id = seed_barrier_command(
        pg_db,
        pilot,
        status="leased",
        attempts=1,
        lease_token="22222222-2222-2222-2222-222222222222",
        lease_expires_at=utcnow() + dt.timedelta(seconds=60),
    )
    assert reclaim_expired_leases(pg_db) == 0
    pg_db.commit()
    assert _status(pg_db, cmd_id) == "leased"


def test_tick_dead_letters_after_max_attempts(pg_db, pilot: PilotFixture) -> None:
    """Протухший lease с attempts>=max → dead; dead не лизится/не реклеймится."""
    cmd_id = seed_barrier_command(
        pg_db,
        pilot,
        status="leased",
        attempts=5,
        max_attempts=5,
        lease_token="33333333-3333-3333-3333-333333333333",
        lease_expires_at=utcnow() - dt.timedelta(seconds=60),
    )
    result = tick(pg_db)
    assert result.dead == 1
    assert result.reclaimed == 0
    assert _status(pg_db, cmd_id) == "dead"
    # dead не возвращается в pending повторным тиком.
    tick(pg_db)
    assert _status(pg_db, cmd_id) == "dead"


def test_tick_reclaims_below_max(pg_db, pilot: PilotFixture) -> None:
    cmd_id = seed_barrier_command(
        pg_db,
        pilot,
        status="leased",
        attempts=2,
        max_attempts=5,
        lease_token="44444444-4444-4444-4444-444444444444",
        lease_expires_at=utcnow() - dt.timedelta(seconds=60),
    )
    result = tick(pg_db)
    assert result.reclaimed == 1
    assert result.dead == 0
    assert _status(pg_db, cmd_id) == "pending"


def test_queue_metrics(pg_db, pilot: PilotFixture) -> None:
    seed_barrier_command(
        pg_db,
        pilot,
        status="pending",
        created_at=utcnow() - dt.timedelta(seconds=120),
    )
    seed_barrier_command(pg_db, pilot, status="pending")
    seed_barrier_command(
        pg_db,
        pilot,
        status="leased",
        lease_token="55555555-5555-5555-5555-555555555555",
        lease_expires_at=utcnow() + dt.timedelta(seconds=30),
    )
    seed_barrier_command(pg_db, pilot, status="dead")

    m = queue_metrics(pg_db, pilot.controller_id)
    assert m.pending == 2
    assert m.leased == 1
    assert m.dead == 1
    # Возраст самого старого pending ~120 c.
    assert m.max_pending_age_seconds is not None
    assert m.max_pending_age_seconds >= 100


def test_ingest_allow_writes_barrier_commands_not_webhook_outbox(
    pg_db, pilot: PilotFixture
) -> None:
    """Крит. §15.11: allow пишет в barrier_commands, webhook_outbox не трогается."""
    seed_permanent_vehicle(pg_db, pilot, normalized="01A700AA")
    before_outbox = pg_db.execute(
        text("SELECT count(*) FROM webhook_outbox")
    ).scalar()

    result = ingest_anpr(
        pg_db,
        AnprIngestInput(
            controller_id=pilot.controller_id,
            event_id="wk-allow-1",
            zone_id=pilot.zone_id,
            gate_id=pilot.gate_id,
            camera_id=pilot.camera_id,
            barrier_id=pilot.barrier_id,
            plate_number_original="01A700AA",
            direction="entry",
            confidence=0.95,
            captured_at=utcnow(),
        ),
    )
    assert result.decision == "allow"
    assert result.command is not None

    # Команда — в barrier_commands.
    bc = pg_db.execute(
        text("SELECT count(*) FROM barrier_commands WHERE controller_id = :c"),
        {"c": pilot.controller_id},
    ).scalar()
    assert bc == 1
    # webhook_outbox не вырос.
    after_outbox = pg_db.execute(
        text("SELECT count(*) FROM webhook_outbox")
    ).scalar()
    assert after_outbox == before_outbox

    # Worker обрабатывает barrier_commands и не пишет в webhook_outbox.
    tick(pg_db)
    assert (
        pg_db.execute(text("SELECT count(*) FROM webhook_outbox")).scalar()
        == before_outbox
    )


def test_worker_does_not_reference_webhook_outbox(pg_db) -> None:
    """Крит. §15.11: worker не импортирует модель и не делает SQL по webhook_outbox.

    (Прозаическое упоминание «НЕ webhook_outbox» в docstring допустимо — проверяем
    именно отсутствие импорта модели и SQL-обращений к таблице.)
    """
    src = inspect.getsource(barrier_worker)
    assert "WebhookOutbox" not in src  # модель не импортирована
    for sql in ("FROM webhook_outbox", "INTO webhook_outbox", "UPDATE webhook_outbox"):
        assert sql not in src
    # Воркер не импортирует пакет моделей бота (webhook_outbox живёт там).
    assert "uk_management_bot.database.models" not in src
