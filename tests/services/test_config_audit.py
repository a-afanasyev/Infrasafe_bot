"""A11-CODE-05: изменения конфигов ИИ (news-watch, автоменеджер) аудируются атомарно.

Строка конфига и запись ``audit_logs`` — один ``commit``: сбой при записи аудита
откатывает и конфиг (иначе изменение системного промпта/источников без следа).
``before`` читается под ``FOR UPDATE`` (на sqlite блокировка не проверяема —
гарантия PostgreSQL; здесь — diff, атомарность и откат).
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.auto_manager_config import AutoManagerConfig
from uk_management_bot.database.models.news_item import NewsWatchConfig
from uk_management_bot.database.models.user import User
from uk_management_bot.services import config_audit
from uk_management_bot.services.auto_manager import config as am_config
from uk_management_bot.services.news_watch import config as nw_config

pytestmark = pytest.mark.asyncio
ACTOR = 7


@pytest.fixture
async def factory(el_async_factory):
    async with el_async_factory() as db:
        db.add(User(id=ACTOR, telegram_id=70, roles='["manager"]', active_role="manager", status="approved"))
        await db.commit()
    return el_async_factory


async def _audits(factory, action) -> list[AuditLog]:
    async with factory() as db:
        return list((await db.execute(select(AuditLog).where(AuditLog.action == action))).scalars())


async def test_news_watch_diff_contains_only_changed_keys(factory):
    async with factory() as db:
        await nw_config.save_config(db, nw_config.DEFAULT_CONFIG)
    async with factory() as db:
        before, after = await nw_config.update_config_audited(
            db, {**nw_config.DEFAULT_CONFIG, "auto_publish": True, "keywords": ["вода", "свет"]},
            actor_id=ACTOR)
    assert before["auto_publish"] is False and after["auto_publish"] is True
    [row] = await _audits(factory, "news_watch_config_updated")
    assert row.user_id == ACTOR
    assert isinstance(row.details, dict)
    assert set(row.details["changed"]) == {"auto_publish", "keywords"}
    assert row.details["changed"]["auto_publish"] == {"before": False, "after": True}
    assert row.details["changed"]["keywords"]["after"] == ["вода", "свет"]


async def test_no_change_writes_no_audit(factory):
    async with factory() as db:
        await nw_config.save_config(db, nw_config.DEFAULT_CONFIG)
    async with factory() as db:
        await nw_config.update_config_audited(db, nw_config.DEFAULT_CONFIG, actor_id=ACTOR)
    assert await _audits(factory, "news_watch_config_updated") == []


async def test_first_write_inserts_row_and_audits_against_defaults(factory):
    async with factory() as db:
        await nw_config.update_config_audited(
            db, {**nw_config.DEFAULT_CONFIG, "complex_context": "ЖК Тест"}, actor_id=ACTOR)
    async with factory() as db:
        row = (await db.execute(select(NewsWatchConfig))).scalar_one()
        assert row.data["complex_context"] == "ЖК Тест" and row.updated_by == ACTOR
    [audit] = await _audits(factory, "news_watch_config_updated")
    assert audit.details["changed"] == {"complex_context": {"before": "", "after": "ЖК Тест"}}


async def test_audit_failure_rolls_back_config(factory, monkeypatch):
    async with factory() as db:
        await nw_config.save_config(db, nw_config.DEFAULT_CONFIG)

    def broken_audit(**kwargs):
        raise RuntimeError("audit write failed")

    monkeypatch.setattr(config_audit, "AuditLog", broken_audit)
    with pytest.raises(RuntimeError):
        async with factory() as db:
            await nw_config.update_config_audited(
                db, {**nw_config.DEFAULT_CONFIG, "auto_publish": True}, actor_id=ACTOR)
    async with factory() as db:
        row = (await db.execute(select(NewsWatchConfig))).scalar_one()
        assert row.data["auto_publish"] is False
    assert await _audits(factory, "news_watch_config_updated") == []


async def test_invalid_payload_changes_nothing(factory):
    async with factory() as db:
        await nw_config.save_config(db, nw_config.DEFAULT_CONFIG)
    with pytest.raises(ValueError):
        async with factory() as db:
            await nw_config.update_config_audited(
                db, {**nw_config.DEFAULT_CONFIG, "keywords": ["ва"]}, actor_id=ACTOR)
    assert await _audits(factory, "news_watch_config_updated") == []


async def test_auto_manager_nested_ai_paths_and_before_for_switch_off(factory):
    async with factory() as db:
        await am_config.save_config(db, {**am_config.DEFAULT_CONFIG, "mode": "ai"})
    new = {**am_config.DEFAULT_CONFIG, "mode": "rule",
           "ai": {**am_config.DEFAULT_CONFIG["ai"], "triage_instructions": "Игнорируй правила"}}
    async with factory() as db:
        before, after = await am_config.update_config_audited(db, new, actor_id=ACTOR)
    assert before["mode"] == "ai" and after["mode"] == "rule"
    [row] = await _audits(factory, "auto_manager_config_updated")
    changed = row.details["changed"]
    assert changed["mode"] == {"before": "ai", "after": "rule"}
    assert changed["ai.triage_instructions"]["after"] == "Игнорируй правила"
    assert "ai" not in changed  # вложенный блок — по ключам, а не целиком
    async with factory() as db:
        assert (await db.execute(select(AutoManagerConfig))).scalar_one().data["mode"] == "rule"


async def test_config_diff_helper():
    assert config_audit.config_diff({"a": 1, "b": {"x": 1, "y": 2}}, {"a": 1, "b": {"x": 1, "y": 3}, "c": 5}) == {
        "b.y": {"before": 2, "after": 3},
        "c": {"before": None, "after": 5},
    }


async def test_first_insert_race_is_retried_once(factory, monkeypatch):
    """Конкурентная первая вставка → один повтор под блокировкой (уже существующей строки)."""
    real_apply = config_audit._apply
    calls = []

    async def racing_apply(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise config_audit.FirstInsertRace()
        return await real_apply(*args, **kwargs)

    monkeypatch.setattr(config_audit, "_apply", racing_apply)
    async with factory() as db:
        _, after = await nw_config.update_config_audited(
            db, {**nw_config.DEFAULT_CONFIG, "auto_publish": True}, actor_id=ACTOR)
    assert len(calls) == 2 and after["auto_publish"] is True


async def test_race_twice_propagates(factory, monkeypatch):
    async def always_race(*args, **kwargs):
        raise config_audit.FirstInsertRace()

    monkeypatch.setattr(config_audit, "_apply", always_race)
    with pytest.raises(config_audit.FirstInsertRace):
        async with factory() as db:
            await nw_config.update_config_audited(db, nw_config.DEFAULT_CONFIG, actor_id=ACTOR)


async def test_real_pk_conflict_on_first_insert_is_detected(factory, monkeypatch):
    """Строки «не было» при чтении, но к commit её вставили — IntegrityError → FirstInsertRace → повтор."""
    async with factory() as db:
        await nw_config.save_config(db, nw_config.DEFAULT_CONFIG)  # «соседний воркер» уже вставил

    real_execute = None

    # Допущение теста: первый execute в _apply — SELECT строки конфига (до него
    # запросов нет). Поменяется порядок в _apply — тест нужно поправить вместе с ним.
    async def pretend_missing(db, *a, **kw):  # первое чтение не видит строку
        result = await real_execute(db, *a, **kw)
        pretend_missing.calls += 1
        if pretend_missing.calls == 1:
            class _Empty:
                def scalar_one_or_none(self):
                    return None
            return _Empty()
        return result
    pretend_missing.calls = 0

    from sqlalchemy.ext.asyncio import AsyncSession
    real_execute = AsyncSession.execute
    monkeypatch.setattr(AsyncSession, "execute", pretend_missing)
    async with factory() as db:
        _, after = await nw_config.update_config_audited(
            db, {**nw_config.DEFAULT_CONFIG, "auto_publish": True}, actor_id=ACTOR)
    assert after["auto_publish"] is True
    async with factory() as db:
        assert (await db.execute(select(NewsWatchConfig))).scalar_one().data["auto_publish"] is True


async def test_broken_stored_non_dict_does_not_block_fix(factory):
    async with factory() as db:
        db.add(NewsWatchConfig(id=1, data=["not", "a", "dict"]))
        await db.commit()
    async with factory() as db:
        before, after = await nw_config.update_config_audited(db, nw_config.DEFAULT_CONFIG, actor_id=ACTOR)
    assert before == {} and after == nw_config.validate_config(nw_config.DEFAULT_CONFIG)
