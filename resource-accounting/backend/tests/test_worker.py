"""Heartbeat воркера — контракт docker-healthcheck (ContainerHasNoHealthcheck P2).

Compose-healthcheck судит по свежести HEARTBEAT_PATH, поэтому инвариант ровно
один: успешная итерация касается файла, упавшая — нет.
"""

import pytest

from app import worker


def test_successful_iteration_touches_heartbeat(tmp_path, monkeypatch):
    hb = tmp_path / "hb"
    monkeypatch.setattr(worker, "HEARTBEAT_PATH", hb)
    monkeypatch.setattr(worker, "cleanup_expired_tickets", lambda: 0)

    worker.run_iteration()

    assert hb.exists()


def test_failed_iteration_does_not_beat(tmp_path, monkeypatch):
    hb = tmp_path / "hb"
    monkeypatch.setattr(worker, "HEARTBEAT_PATH", hb)

    def boom() -> int:
        raise RuntimeError("db down")

    monkeypatch.setattr(worker, "cleanup_expired_tickets", boom)

    with pytest.raises(RuntimeError):
        worker.run_iteration()

    assert not hb.exists()
