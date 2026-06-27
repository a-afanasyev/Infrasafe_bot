"""Ф5: ingestion-взаимодействие с ручной командой (§13.2, последний абзац).

Если для barrier уже создана ручная команда ПОСЛЕ captured_at, ingestion при
manual_review фиксирует решение сразу как allowed_manually и НЕ создаёт новый
pending. PostgreSQL-only (advisory lock §13.2).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import text

from access_control.services.ingestion import AnprIngestInput, ingest_anpr
from access_control.services.lifecycle import manual_open_barrier
from access_control.tests.conftest import PilotFixture, seed_user, utcnow


def test_pending_review_skipped_when_recent_manual_open_exists(
    pg_db, pilot: PilotFixture
) -> None:
    op = seed_user(pg_db, roles="security_operator")
    # Ручное открытие шлагбаума уже выполнено (нет pending).
    manual_open_barrier(
        pg_db,
        barrier_id=pilot.barrier_id,
        operator_user_id=op,
        reason="оператор уже открыл",
        source="emergency",
    )

    # Событие низкой уверенности → движок дал бы manual_review.
    captured = utcnow() - dt.timedelta(seconds=1)
    result = ingest_anpr(
        pg_db,
        AnprIngestInput(
            controller_id=pilot.controller_id,
            event_id="mr-after-manual",
            zone_id=pilot.zone_id,
            gate_id=pilot.gate_id,
            camera_id=pilot.camera_id,
            barrier_id=pilot.barrier_id,
            plate_number_original="01A777AA",
            direction="entry",
            confidence=0.50,  # ниже порога 0.70 → low_confidence/manual_review
            captured_at=captured,
        ),
    )

    # Решение зафиксировано сразу как allowed_manually, новый pending не создан.
    assert result.status == "allowed_manually"
    pending_cnt = pg_db.execute(
        text(
            "SELECT count(*) FROM access_decisions "
            "WHERE status = 'pending_review' AND camera_event_id = "
            "(SELECT id FROM camera_events WHERE event_id = 'mr-after-manual')"
        )
    ).scalar()
    assert pending_cnt == 0
    # ingestion НЕ создаёт вторую команду (ручная уже есть).
    assert result.command is None
