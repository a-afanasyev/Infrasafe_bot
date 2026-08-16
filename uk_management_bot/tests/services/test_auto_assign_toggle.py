"""Выключатель автоназначения обязан гасить и автоперевод «Новая»→«В работе».

Флаг `auto_manager_config.data.enabled` до этой правки читал только оркестратор
авто-менеджера. Автоперевод при создании заявки делает другой код —
`services/dispatch.py` — и флага не видел: менеджер выключал автоназначение, а
заявки продолжали уезжать в «В работе» с групповым назначением.

Fail-safe направление: если конфиг недоступен (нет таблицы/строки), считаем
автоназначение ВЫКЛЮЧЕННЫМ — заявка останется «Новая», и её возьмёт человек.
Обратное поведение молча раздавало бы заявки при сломанной БД.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.auto_manager_config import AutoManagerConfig
from uk_management_bot.database.session import Base

_engine = create_engine("sqlite:///:memory:", echo=False)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=_engine)
    session = _Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


class _AsyncShim:
    """Минимальный async-фасад над sync-сессией sqlite (у ридера только execute)."""

    def __init__(self, sync_db):
        self._db = sync_db

    async def execute(self, stmt):
        return self._db.execute(stmt)


def _set_enabled(db, value: bool) -> None:
    from uk_management_bot.services.auto_manager.config import (
        CONFIG_ROW_ID,
        DEFAULT_CONFIG,
    )

    db.add(AutoManagerConfig(id=CONFIG_ROW_ID, data={**DEFAULT_CONFIG, "enabled": value}))
    db.commit()


class TestConfigReader:
    def test_disabled_when_no_row(self, db):
        """Строки нет — дефолт `enabled=False`, автоназначение молчит."""
        from uk_management_bot.services.auto_manager.config import is_auto_assign_enabled_sync

        assert is_auto_assign_enabled_sync(db) is False

    def test_enabled_when_row_says_so(self, db):
        from uk_management_bot.services.auto_manager.config import is_auto_assign_enabled_sync

        _set_enabled(db, True)

        assert is_auto_assign_enabled_sync(db) is True

    def test_disabled_when_row_says_so(self, db):
        from uk_management_bot.services.auto_manager.config import is_auto_assign_enabled_sync

        _set_enabled(db, False)

        assert is_auto_assign_enabled_sync(db) is False

    @pytest.mark.asyncio
    async def test_async_reader_mirrors_sync(self, db):
        """Async-ридер обязан отвечать так же — иначе бот и API разъедутся."""
        from uk_management_bot.services.auto_manager.config import is_auto_assign_enabled

        _set_enabled(db, True)

        assert await is_auto_assign_enabled(_AsyncShim(db)) is True


class TestFailSafe:
    def test_unreadable_config_means_disabled(self, monkeypatch):
        """Сессию открыть не удалось — считаем выключенным, а не включённым.

        Чтение идёт ПОСЛЕ commit создания заявки, поэтому оно не вправе ни
        уронить запрос, ни «на всякий случай» раздать заявку.
        """
        import uk_management_bot.database.session as session_mod
        from uk_management_bot.services import dispatch

        def _boom(*a, **kw):
            raise RuntimeError("нет коннекта")

        # Патчим объект модуля, а не строку-путь: в полном прогоне подмодуль
        # `session` может быть ещё не привязан атрибутом к пакету `database`,
        # и строковая форма monkeypatch падает с AttributeError.
        monkeypatch.setattr(session_mod, "SessionLocal", _boom, raising=False)

        assert dispatch._auto_assign_enabled_sync() is False

    @pytest.mark.asyncio
    async def test_unreadable_config_means_disabled_async(self, monkeypatch):
        """AsyncSessionLocal=None (sqlite-conftest) не должен ронять dispatch."""
        import uk_management_bot.database.session as session_mod
        from uk_management_bot.services import dispatch

        monkeypatch.setattr(session_mod, "AsyncSessionLocal", None, raising=False)

        assert await dispatch._auto_assign_enabled_async() is False


class TestSyncDispatchGate:
    def test_disabled_does_not_run_command(self, db, monkeypatch):
        """Выключено — run_command_sync не вызывается вовсе."""
        from uk_management_bot.services import dispatch

        calls = []
        monkeypatch.setattr(
            "uk_management_bot.services.workflow_runner.run_command_sync",
            lambda *a, **kw: calls.append(a),
        )
        _set_enabled(db, False)

        dispatch.auto_dispatch_new_request_sync("260816-001", "elevator", _db=db)

        assert calls == [], "при выключенном автоназначении заявка обязана остаться «Новая»"

    def test_enabled_runs_command(self, db, monkeypatch):
        from uk_management_bot.services import dispatch

        calls = []
        monkeypatch.setattr(
            "uk_management_bot.services.workflow_runner.run_command_sync",
            lambda *a, **kw: calls.append(a),
        )
        _set_enabled(db, True)

        dispatch.auto_dispatch_new_request_sync("260816-001", "elevator", _db=db)

        assert len(calls) == 1, "при включённом автоназначении команда обязана уйти"

    def test_unknown_category_short_circuits_before_flag(self, db, monkeypatch):
        """Нет маппинга категории — выходим раньше, конфиг даже не читаем."""
        from uk_management_bot.services import dispatch

        def _boom(*a, **kw):  # pragma: no cover — не должен вызваться
            raise AssertionError("конфиг не должен читаться без маппинга категории")

        monkeypatch.setattr(
            "uk_management_bot.services.auto_manager.config.is_auto_assign_enabled_sync",
            _boom,
        )

        dispatch.auto_dispatch_new_request_sync("260816-001", "нет-такой-категории", _db=db)


class TestAsyncDispatchGate:
    @pytest.mark.asyncio
    async def test_disabled_does_not_run_command(self, db, monkeypatch):
        from uk_management_bot.services import dispatch

        calls = []

        async def _fake_run(*a, **kw):  # pragma: no cover — не должен вызваться
            calls.append(a)

        monkeypatch.setattr(
            "uk_management_bot.services.workflow_runner.run_command_async", _fake_run,
        )
        _set_enabled(db, False)

        await dispatch.auto_dispatch_new_request_async(
            "260816-001", "elevator", _db=_AsyncShim(db),
        )

        assert calls == [], "при выключенном автоназначении заявка обязана остаться «Новая»"

    @pytest.mark.asyncio
    async def test_enabled_runs_command(self, db, monkeypatch):
        from uk_management_bot.services import dispatch

        calls = []

        async def _fake_run(*a, **kw):
            calls.append(a)
            raise RuntimeError("дальше по пути нас не интересует")

        monkeypatch.setattr(
            "uk_management_bot.services.workflow_runner.run_command_async", _fake_run,
        )
        _set_enabled(db, True)

        await dispatch.auto_dispatch_new_request_async(
            "260816-001", "elevator", _db=_AsyncShim(db),
        )

        assert len(calls) == 1, "при включённом автоназначении команда обязана уйти"
