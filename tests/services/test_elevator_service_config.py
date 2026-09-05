"""Конфиг модуля «Лифты»: дефолты, терпимое чтение, upsert (sqlite)."""

from __future__ import annotations

import asyncio
import logging

import pytest
from sqlalchemy.exc import OperationalError

from uk_management_bot.database.models.elevators_config import ElevatorsConfig
from uk_management_bot.services.elevator_service import (
    CONFIG_ROW_ID,
    DEFAULT_ELEVATORS_CONFIG,
    ElevatorValidationError,
    load_config_async,
    load_config_sync,
    merge_config,
    save_config_async,
)

pytestmark = pytest.mark.integration

DEFAULTS = merge_config(None, None)


class TestLoadSync:
    def test_empty_table_gives_defaults(self, el_db):
        config = load_config_sync(el_db)
        assert config == DEFAULTS
        assert isinstance(config, dict) and config is not DEFAULT_ELEVATORS_CONFIG

    def test_stored_merges_over_defaults(self, el_db):
        el_db.add(ElevatorsConfig(id=CONFIG_ROW_ID, data={"module_public": True,
                                                            "downtime_threshold_days": {"not_working": 3}}))
        el_db.commit()
        config = load_config_sync(el_db)
        assert config["module_public"] is True
        assert config["downtime_threshold_days"] == {"not_working": 3, "under_repair": None}
        assert config["staff_reminders"] == DEFAULTS["staff_reminders"]

    def test_unknown_keys_logged_and_dropped(self, el_db, caplog):
        el_db.add(ElevatorsConfig(id=CONFIG_ROW_ID, data={"legacy": 1, "staff_reminders": {"old": 2}}))
        el_db.commit()
        with caplog.at_level(logging.WARNING):
            config = load_config_sync(el_db)
        assert config == DEFAULTS
        assert "legacy" in caplog.text and "staff_reminders.old" in caplog.text

    def test_invalid_stored_falls_back(self, el_db, caplog):
        el_db.add(ElevatorsConfig(id=CONFIG_ROW_ID, data={"module_public": "yes"}))
        el_db.commit()
        with caplog.at_level(logging.WARNING):
            assert load_config_sync(el_db) == DEFAULTS
        assert "невалиден" in caplog.text

    def test_db_error_falls_back(self, el_db, monkeypatch, caplog):
        def boom(*_args, **_kwargs):
            raise OperationalError("select", {}, Exception("no table"))

        monkeypatch.setattr(el_db, "get", boom)
        with caplog.at_level(logging.WARNING):
            assert load_config_sync(el_db) == DEFAULTS
        assert "недоступен" in caplog.text


class TestAsync:
    def test_load_defaults_then_save_upserts(self, el_async_factory):
        async def run():
            async with el_async_factory() as s:
                initial = await load_config_async(s)
                saved = await save_config_async(s, {"module_public": True}, actor_user_id=7)
                await s.commit()
            async with el_async_factory() as s:
                row = await s.get(ElevatorsConfig, CONFIG_ROW_ID)
                stored_snapshot = (dict(row.data), row.updated_by)
                loaded = await load_config_async(s)
                again = await save_config_async(
                    s, {"downtime_threshold_days": {"under_repair": 5}}, actor_user_id=8)
                await s.commit()
                row2 = await s.get(ElevatorsConfig, CONFIG_ROW_ID)
                return initial, saved, stored_snapshot, loaded, again, row2.updated_by

        initial, saved, (stored, by), loaded, again, by2 = asyncio.run(run())
        assert initial == DEFAULTS
        assert saved["module_public"] is True and stored == saved and by == 7
        assert loaded == saved
        assert again["downtime_threshold_days"] == {"not_working": 7, "under_repair": 5}
        assert again["module_public"] is True and by2 == 8

    def test_invalid_patch_rejected(self, el_async_factory):
        async def run():
            async with el_async_factory() as s:
                with pytest.raises(ElevatorValidationError):
                    await save_config_async(s, {"unknown": 1}, actor_user_id=7)
                with pytest.raises(ElevatorValidationError):
                    await save_config_async(s, {"module_public": "yes"}, actor_user_id=7)
                return await s.get(ElevatorsConfig, CONFIG_ROW_ID)

        assert asyncio.run(run()) is None
