"""Тесты services/auto_manager/config.py: validate_config, is_window_active,
load_config_sync/save_config_sync (sqlite in-memory round-trip).

Паттерн sqlite-фикстуры — как в test_feedback_service.py (create_engine
"sqlite:///:memory:" + Base.metadata.create_all).
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.session import Base
from uk_management_bot.services.auto_manager.config import (
    DEFAULT_CONFIG,
    is_window_active,
    load_config_sync,
    save_config_sync,
    validate_config,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


# ─────────────────────────── validate_config: time format ───────────────────────────

@pytest.mark.parametrize("bad_time", ["99:99", "1:2", "1:02", "01:2"])
def test_validate_config_rejects_bad_time_formats(bad_time):
    with pytest.raises(ValueError):
        validate_config({"window_start": bad_time})
    with pytest.raises(ValueError):
        validate_config({"window_end": bad_time})


@pytest.mark.parametrize("good_time", ["20:00", "08:00", "00:00", "23:59"])
def test_validate_config_accepts_good_time_formats(good_time):
    cfg = validate_config({"window_start": good_time, "window_end": good_time})
    assert cfg["window_start"] == good_time
    assert cfg["window_end"] == good_time


# ─────────────────────────── validate_config: defaulting/merge ───────────────────────────

def test_validate_config_merges_over_default_for_missing_keys():
    cfg = validate_config({})
    assert cfg == DEFAULT_CONFIG


def test_validate_config_default_config_is_itself_valid():
    # DEFAULT_CONFIG must round-trip through validation cleanly.
    assert validate_config(DEFAULT_CONFIG) == DEFAULT_CONFIG


def test_validate_config_overrides_only_provided_keys():
    cfg = validate_config({"enabled": True, "max_requests_per_run": 25})
    assert cfg["enabled"] is True
    assert cfg["max_requests_per_run"] == 25
    assert cfg["mode"] == DEFAULT_CONFIG["mode"]
    assert cfg["window_start"] == DEFAULT_CONFIG["window_start"]


def test_validate_config_rejects_non_dict():
    with pytest.raises(ValueError):
        validate_config("not-a-dict")  # type: ignore[arg-type]


# ─────────────────────────── validate_config: timezone ───────────────────────────

def test_validate_config_accepts_valid_timezone():
    cfg = validate_config({"timezone": "Europe/Moscow"})
    assert cfg["timezone"] == "Europe/Moscow"


def test_validate_config_rejects_invalid_timezone():
    with pytest.raises(ValueError):
        validate_config({"timezone": "Not/A_Real_Zone"})


@pytest.mark.parametrize("value", [None, 1, ["Asia/Tashkent"]])
def test_validate_config_rejects_non_string_timezone(value):
    with pytest.raises(ValueError):
        validate_config({"timezone": value})


# ─────────────────────────── validate_config: max_requests_per_run ───────────────────────────

@pytest.mark.parametrize("value", [1, 10, 50])
def test_validate_config_accepts_max_requests_bounds(value):
    cfg = validate_config({"max_requests_per_run": value})
    assert cfg["max_requests_per_run"] == value


@pytest.mark.parametrize("value", [0, -1, 51, 100])
def test_validate_config_rejects_max_requests_out_of_bounds(value):
    with pytest.raises(ValueError):
        validate_config({"max_requests_per_run": value})


@pytest.mark.parametrize("value", [True, False, "10", 10.5, None])
def test_validate_config_rejects_max_requests_wrong_type(value):
    with pytest.raises(ValueError):
        validate_config({"max_requests_per_run": value})


# ─────────────────────────── validate_config: mode ───────────────────────────

@pytest.mark.parametrize("mode", ["rule", "ai"])
def test_validate_config_accepts_valid_modes(mode):
    cfg = validate_config({"mode": mode})
    assert cfg["mode"] == mode


@pytest.mark.parametrize("mode", ["", "RULE", "manual", 1, None, ["rule"]])
def test_validate_config_rejects_invalid_modes(mode):
    with pytest.raises(ValueError):
        validate_config({"mode": mode})


# ─────────────────────────── is_window_active ───────────────────────────

def _dt(hour: int, minute: int = 0) -> datetime:
    """UTC datetime on a fixed date at the given hour:minute."""
    return datetime(2026, 7, 23, hour, minute, tzinfo=timezone.utc)


def test_is_window_active_overnight_window_crosses_midnight():
    # 20:00-08:00 Asia/Tashkent (UTC+5, no DST) → active overnight.
    cfg = validate_config({"window_start": "20:00", "window_end": "08:00"})
    # 21:00 UTC == 02:00 Tashkent next day → inside window.
    assert is_window_active(cfg, _dt(21, 0)) is True
    # 10:00 UTC == 15:00 Tashkent → outside window.
    assert is_window_active(cfg, _dt(10, 0)) is False


def test_is_window_active_overnight_boundaries():
    cfg = validate_config({
        "window_start": "20:00", "window_end": "08:00", "timezone": "UTC",
    })
    assert is_window_active(cfg, _dt(20, 0)) is True   # t == start → active
    assert is_window_active(cfg, _dt(8, 0)) is False    # t == end → not active
    assert is_window_active(cfg, _dt(7, 59)) is True
    assert is_window_active(cfg, _dt(19, 59)) is False


def test_is_window_active_same_day_window():
    cfg = validate_config({
        "window_start": "08:00", "window_end": "20:00", "timezone": "UTC",
    })
    assert is_window_active(cfg, _dt(8, 0)) is True     # t == start → active
    assert is_window_active(cfg, _dt(20, 0)) is False    # t == end → not active
    assert is_window_active(cfg, _dt(19, 59)) is True
    assert is_window_active(cfg, _dt(7, 59)) is False
    assert is_window_active(cfg, _dt(0, 0)) is False


def test_is_window_active_start_equals_end_is_always_active():
    cfg = validate_config({
        "window_start": "10:00", "window_end": "10:00", "timezone": "UTC",
    })
    assert is_window_active(cfg, _dt(0, 0)) is True
    assert is_window_active(cfg, _dt(10, 0)) is True
    assert is_window_active(cfg, _dt(23, 59)) is True


# ─────────────────────────── load_config_sync / save_config_sync ───────────────────────────

def test_load_config_sync_missing_row_returns_default(db):
    assert load_config_sync(db) == DEFAULT_CONFIG


def test_save_then_load_config_sync_round_trip(db):
    saved = save_config_sync(db, {"enabled": True, "max_requests_per_run": 5}, updated_by=None)
    assert saved["enabled"] is True
    assert saved["max_requests_per_run"] == 5

    loaded = load_config_sync(db)
    assert loaded == saved


def test_save_config_sync_upserts_existing_row(db):
    save_config_sync(db, {"enabled": True})
    save_config_sync(db, {"enabled": False, "mode": "ai"})

    loaded = load_config_sync(db)
    assert loaded["enabled"] is False
    assert loaded["mode"] == "ai"

    from uk_management_bot.database.models.auto_manager_config import AutoManagerConfig
    rows = db.query(AutoManagerConfig).all()
    assert len(rows) == 1


def test_save_config_sync_rejects_invalid_payload(db):
    with pytest.raises(ValueError):
        save_config_sync(db, {"mode": "invalid"})
