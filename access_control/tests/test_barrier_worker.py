"""barrier_commands queue_metrics + критерий §15.11 (не webhook_outbox). PostgreSQL-only.

Тесты worker-функций pull-модели (reclaim/dead-letter/tick) удалены вместе
с самими функциями (AUD6): прод-runner так и не появился.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import text

from access_control.services.barrier_worker import queue_metrics
from access_control.services.ingestion import AnprIngestInput, ingest_anpr
from access_control.tests.conftest import (
    PilotFixture,
    seed_barrier_command,
    seed_permanent_vehicle,
    utcnow,
)


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
