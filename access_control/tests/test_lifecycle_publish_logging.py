"""A9-P3-10: сбой публикации live-события охране виден в логе.

Публикация best-effort (переход уже закоммичен) — исключение наружу не
выходит, но и не глотается молча: охрана теряет live-событие, и без записи в
логе это не диагностировать. В лог уходит только исход (decision/status/
reason) — без номера и фото (§11).
"""
from __future__ import annotations

import datetime as dt
import logging
from unittest.mock import MagicMock, patch

from access_control.services import lifecycle


def test_publish_failure_is_logged_without_raising(caplog) -> None:
    broker = MagicMock()
    broker.publish.side_effect = RuntimeError("redis down")
    now = dt.datetime(2026, 9, 23, 10, 0, tzinfo=dt.timezone.utc)

    with patch.object(lifecycle, "get_broker", return_value=broker), \
            caplog.at_level(logging.WARNING, logger=lifecycle.__name__):
        lifecycle._publish_lifecycle_event(
            decision="allowed_manually", status="final", reason="operator", now=now
        )

    records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert records, "сбой публикации проглочен без лога"
    msg = records[0].getMessage()
    assert "allowed_manually" in msg and "redis down" in msg


def test_publish_success_logs_nothing(caplog) -> None:
    broker = MagicMock()
    now = dt.datetime(2026, 9, 23, 10, 0, tzinfo=dt.timezone.utc)

    with patch.object(lifecycle, "get_broker", return_value=broker), \
            caplog.at_level(logging.WARNING, logger=lifecycle.__name__):
        lifecycle._publish_lifecycle_event(
            decision="denied_manually", status="final", reason=None, now=now
        )

    broker.publish.assert_called_once()
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
