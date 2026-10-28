"""Публичный статус в чат дома (services/ai_manager/public_status.py).

Только при mode="ai", только для критических заявок, пришедших из группы
жителей (source_chat_id = активная residents-группа), только шаблоном без
ФИО/квартиры. Хук — в диспетчерах уведомлений workflow_notifications.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import uk_management_bot.utils.constants as C
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.monitored_group import MonitoredGroup
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services.ai_manager import public_status
from uk_management_bot.services.auto_manager.config import DEFAULT_CONFIG, save_config_sync
from uk_management_bot.utils.request_workflow import Action, EventIntent

CHAT = -100777


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine, autoflush=False)()
    s.add_all([
        User(id=2, telegram_id=20, first_name="Иван Петров", roles='["applicant"]',
             active_role="applicant", status="approved", language="ru"),
        MonitoredGroup(chat_id=CHAT, title="дом 1", kind="residents", is_active=True),
    ])
    s.commit()
    save_config_sync(s, {**DEFAULT_CONFIG, "enabled": True, "mode": "ai"})
    monkeypatch.setattr(settings, "AI_MANAGER_ENABLED", True)
    yield s
    s.close()
    engine.dispose()


def _req(db, *, urgency="critical", source_chat_id=CHAT, number="261028-001", message_id=1):
    db.add(Request(request_number=number, user_id=2, category="electricity", description="нет света",
                   address="ул. Тестовая 1, кв. 45", urgency=urgency, status=C.REQUEST_STATUS_IN_PROGRESS,
                   source_chat_id=source_chat_id, source_message_id=message_id if source_chat_id else None,
                   created_at=datetime.now(timezone.utc)))
    db.commit()


def test_assigned_announcement_without_personal_data(db):
    _req(db)
    out = public_status.outgoing_for_sync(db, "261028-001", {Action.SYSTEM_DISPATCH_ASSIGN})
    assert out is not None and out.chat_id == CHAT and out.kind == "residents_group"
    assert "261028-001" in out.text
    assert "Иван" not in out.text and "кв. 45" not in out.text
    assert "Электрика" in out.text and "Elektrik" in out.text  # ru + uz в одном сообщении


def test_executed_wins_over_assigned_in_one_batch(db):
    _req(db)
    out = public_status.outgoing_for_sync(db, "261028-001", {Action.MANAGER_ASSIGN, Action.EXECUTOR_COMPLETE})
    assert out is not None and ("выполнена" in out.text.lower())


@pytest.mark.parametrize("actions", [set(), {Action.CANCEL}, {Action.CLARIFY_REQUEST}])
def test_other_actions_are_silent(db, actions):
    _req(db)
    assert public_status.outgoing_for_sync(db, "261028-001", actions) is None


def test_non_critical_or_no_source_chat_is_silent(db):
    _req(db, urgency="high", number="261028-002")
    _req(db, source_chat_id=None, number="261028-003")
    assert public_status.outgoing_for_sync(db, "261028-002", {Action.MANAGER_ASSIGN}) is None
    assert public_status.outgoing_for_sync(db, "261028-003", {Action.MANAGER_ASSIGN}) is None


def test_rule_mode_or_flag_off_or_inactive_group_is_silent(db, monkeypatch):
    _req(db)
    save_config_sync(db, {**DEFAULT_CONFIG, "enabled": True, "mode": "rule"})
    assert public_status.outgoing_for_sync(db, "261028-001", {Action.MANAGER_ASSIGN}) is None
    save_config_sync(db, {**DEFAULT_CONFIG, "enabled": True, "mode": "ai"})
    monkeypatch.setattr(settings, "AI_MANAGER_ENABLED", False)
    assert public_status.outgoing_for_sync(db, "261028-001", {Action.MANAGER_ASSIGN}) is None
    monkeypatch.setattr(settings, "AI_MANAGER_ENABLED", True)
    group = db.query(MonitoredGroup).filter_by(chat_id=CHAT).one()
    group.is_active = False
    db.commit()
    assert public_status.outgoing_for_sync(db, "261028-001", {Action.MANAGER_ASSIGN}) is None


def test_sync_collector_appends_group_message(db):
    """collect_notify_messages_sync (бот-путь) добавляет сообщение в группу
    к адресным сообщениям — одной send-фазой."""
    from uk_management_bot.services.workflow_notifications import collect_notify_messages_sync

    _req(db)
    intents = [EventIntent("notify", {"action": Action.EXECUTOR_COMPLETE.value, "request_number": "261028-001"})]
    messages = collect_notify_messages_sync(db, "261028-001", intents)
    chats = [c for c, _ in messages]
    assert 20 in chats and CHAT in chats


def test_sync_dispatcher_delivers_group_message(db, monkeypatch):
    from uk_management_bot.services.workflow_notifications import dispatch_notify_intents_sync

    class FakeBot:
        def __init__(self):
            self.sent = []

        async def send_message(self, chat_id, text, **kw):
            self.sent.append((chat_id, text))

    _req(db)
    bot = FakeBot()
    intents = [EventIntent("notify", {"action": Action.SYSTEM_DISPATCH_ASSIGN.value, "request_number": "261028-001"})]
    import asyncio
    asyncio.run(dispatch_notify_intents_sync(db, "261028-001", intents, bot=bot))
    assert CHAT in [c for c, _ in bot.sent]


# ───────────── правила со страницы «Правила ИИ» ─────────────


def _patch_cfg(db, **blocks):
    from uk_management_bot.services.auto_manager.config import load_config_sync

    cfg = load_config_sync(db)
    save_config_sync(db, {**cfg, **{k: {**cfg[k], **v} for k, v in blocks.items()}})


def test_high_urgency_announced_when_min_urgency_high(db):
    _patch_cfg(db, sla={"public_status": {"enabled": True, "min_urgency": "high"}})
    _req(db, urgency="high")
    assert public_status.outgoing_for_sync(db, "261028-001", {Action.SYSTEM_DISPATCH_ASSIGN}) is not None
    _req(db, urgency="medium", number="261028-002", message_id=2)
    assert public_status.outgoing_for_sync(db, "261028-002", {Action.SYSTEM_DISPATCH_ASSIGN}) is None


def test_public_status_disabled(db):
    _patch_cfg(db, sla={"public_status": {"enabled": False, "min_urgency": "critical"}})
    _req(db)
    assert public_status.outgoing_for_sync(db, "261028-001", {Action.SYSTEM_DISPATCH_ASSIGN}) is None


def test_public_template_override(db):
    _patch_cfg(db, ai={"templates": {"public.assigned": {"ru": "Выехали по №{request_number}"}}})
    _req(db)
    out = public_status.outgoing_for_sync(db, "261028-001", {Action.SYSTEM_DISPATCH_ASSIGN})
    assert out is not None and out.text.startswith("Выехали по №261028-001")
