"""SLA-watchdog ИИ-менеджера (services/ai_manager/sla.py) на sqlite.

Состояние лестницы выводится из audit_logs (`ai_sla_step`) с привязкой к фазе
(track, status_version, phase_started_at); тик — один шаг на заявку;
переназначение и авто-принятие идут через run_command_sync системным
актором ai_manager. Telegram — FakeBot, подбор дежурного — заглушка.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import uk_management_bot.utils.constants as C
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.monitored_group import MonitoredGroup
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services.ai_manager import sla
from uk_management_bot.services.ai_manager.sla import AUDIT_STEP, AiSlaWatchdog
from uk_management_bot.services.auto_manager.config import DEFAULT_CONFIG, save_config_sync

NOW = datetime.now(timezone.utc).replace(microsecond=0)
APPLICANT, MANAGER, EXECUTOR, NEW_EXECUTOR = 2, 3, 4, 5
STAFF_CHAT = -100500
SLA = {
    "in_progress_max": {"low": 10, "medium": 10, "high": 10, "critical": 2},
    "clarification_max": 4,
    "executed_unconfirmed_max": 6,
    "completed_unaccepted_days": 3,
    "critical_unassigned_minutes": 30,
    "ladder": {"remind_executor": 0, "staff_group": 2, "manager": 4, "reassign": 8},
}


class FakeBot:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))


@pytest.fixture()
def SF(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = factory()
    s.add_all([
        User(id=1, telegram_id=settings.INFRASAFE_SYSTEM_USER_TELEGRAM_ID, first_name="System",
             roles='["manager"]', active_role="manager", status="approved", language="ru"),
        User(id=APPLICANT, telegram_id=20, first_name="Житель", roles='["applicant"]',
             active_role="applicant", status="approved", language="uz"),
        User(id=MANAGER, telegram_id=30, first_name="Менеджер", roles='["manager"]',
             active_role="manager", status="approved", language="ru"),
        User(id=EXECUTOR, telegram_id=40, first_name="Вася", roles='["executor"]',
             active_role="executor", status="approved", language="ru", specialization="plumber"),
        User(id=NEW_EXECUTOR, telegram_id=50, first_name="Петя", roles='["executor"]',
             active_role="executor", status="approved", language="ru", specialization="plumber"),
        MonitoredGroup(chat_id=STAFF_CHAT, title="staff", kind="staff", is_active=True),
    ])
    s.commit()
    save_config_sync(s, {**DEFAULT_CONFIG, "enabled": True, "mode": "ai", "sla": SLA})
    s.close()
    monkeypatch.setattr(settings, "AI_MANAGER_ENABLED", True)
    monkeypatch.setattr(sla, "pick_duty_executor_id", lambda spec, db=None, exclude_user_ids=frozenset(), **k: NEW_EXECUTOR)
    yield factory
    engine.dispose()


def _seed(SF, number="261028-001", *, status=C.REQUEST_STATUS_IN_PROGRESS, urgency="critical",
          executor_id=EXECUTOR, assigned_at=None, updated_at=None, executed_at=None,
          completed_at=None, created_at=None, manager_confirmed=False):
    s = SF()
    s.add(Request(request_number=number, user_id=APPLICANT, category="plumbing", description="течёт",
                  address="ул. Тестовая 1", urgency=urgency, status=status, executor_id=executor_id,
                  assigned_at=assigned_at, updated_at=updated_at, executed_at=executed_at,
                  completed_at=completed_at, created_at=created_at or NOW - timedelta(days=1),
                  manager_confirmed=manager_confirmed, status_version=1))
    s.commit()
    s.close()


def _req(SF, number="261028-001") -> Request:
    s = SF()
    try:
        return s.execute(select(Request).where(Request.request_number == number)).scalar_one()
    finally:
        s.close()


def _steps(SF, number="261028-001"):
    s = SF()
    try:
        rows = s.execute(select(AuditLog).where(AuditLog.action == AUDIT_STEP).order_by(AuditLog.id)).scalars()
        return [a.details for a in rows if a.details["request_number"] == number]
    finally:
        s.close()


def _tick(SF, bot, at):
    w = AiSlaWatchdog(bot=bot, session_factory=SF)
    asyncio.run(w.run_once(now=at))
    return bot.sent


# ───────────── выключатели ─────────────


def test_rule_mode_or_flag_off_does_nothing(SF, monkeypatch):
    _seed(SF, assigned_at=NOW - timedelta(hours=10))
    bot = FakeBot()
    monkeypatch.setattr(settings, "AI_MANAGER_ENABLED", False)
    assert _tick(SF, bot, NOW) == [] and _steps(SF) == []
    monkeypatch.setattr(settings, "AI_MANAGER_ENABLED", True)
    s = SF()
    save_config_sync(s, {**DEFAULT_CONFIG, "enabled": True, "mode": "rule", "sla": SLA})
    s.close()
    assert _tick(SF, bot, NOW) == [] and _steps(SF) == []


# ───────────── лестница исполнителя ─────────────


def test_executor_ladder_one_step_per_tick_with_phase_binding(SF):
    assigned = NOW - timedelta(hours=3)  # critical: max 2h → просрочка 1h
    _seed(SF, assigned_at=assigned)
    bot = FakeBot()

    # ступень 0: DM исполнителю, один раз
    assert [c for c, _ in _tick(SF, bot, NOW)] == [40]
    assert "261028-001" in bot.sent[0][1]
    assert _tick(SF, FakeBot(), NOW + timedelta(minutes=10)) == []
    steps = _steps(SF)
    assert len(steps) == 1 and steps[0]["step"] == "remind_executor"
    assert steps[0]["track"] == "executor" and steps[0]["status_version"] == 1

    # ступень 1 (offset 2h от просрочки): staff-группа
    sent = _tick(SF, FakeBot(), assigned + timedelta(hours=2 + 2))
    assert [c for c, _ in sent] == [STAFF_CHAT]
    assert "Вася" in sent[0][1]

    # ступень 2 (offset 4h): менеджер
    sent = _tick(SF, FakeBot(), assigned + timedelta(hours=2 + 4))
    assert [c for c, _ in sent] == [30]

    # ступень 3 (offset 8h): переназначение дежурному
    sent = _tick(SF, FakeBot(), assigned + timedelta(hours=2 + 8))
    req = _req(SF)
    assert req.executor_id == NEW_EXECUTOR and req.status == C.REQUEST_STATUS_IN_PROGRESS
    chats = sorted(c for c, _ in sent)
    assert 40 in chats and 50 in chats and 20 in chats  # старый, новый, житель
    assert [s["step"] for s in _steps(SF)] == ["remind_executor", "staff_group", "manager", "reassign"]

    # новая фаза (другой исполнитель, новый assigned_at/status_version): лестница с нуля
    req = _req(SF)
    sent = _tick(SF, FakeBot(), sla._aware(req.assigned_at) + timedelta(hours=3))
    assert [c for c, _ in sent] == [50]
    assert _steps(SF)[-1]["step"] == "remind_executor" and _steps(SF)[-1]["status_version"] == req.status_version


def test_ladder_skips_steps_when_tick_was_down(SF):
    """Долгий простой тика: выполняется ТОЛЬКО следующая ступень, не вся лестница."""
    _seed(SF, assigned_at=NOW - timedelta(hours=30))
    sent = _tick(SF, FakeBot(), NOW)
    assert [c for c, _ in sent] == [40]
    assert [s["step"] for s in _steps(SF)] == ["remind_executor"]


def test_reassign_without_candidate_tells_manager_once(SF, monkeypatch):
    monkeypatch.setattr(sla, "pick_duty_executor_id", lambda *a, **k: None)
    assigned = NOW - timedelta(hours=2 + 8 + 1)
    _seed(SF, assigned_at=assigned)
    for _ in range(3):
        _tick(SF, FakeBot(), NOW)
    sent = _tick(SF, FakeBot(), NOW)
    assert [c for c, _ in sent] == [30]
    assert _req(SF).executor_id == EXECUTOR
    assert _steps(SF)[-1]["step"] == "reassign" and _steps(SF)[-1]["result"] == "no_candidate"
    assert _tick(SF, FakeBot(), NOW) == []


def test_zero_limit_disables_track(SF):
    s = SF()
    save_config_sync(s, {**DEFAULT_CONFIG, "enabled": True, "mode": "ai",
                         "sla": {**SLA, "in_progress_max": {**SLA["in_progress_max"], "critical": 0}}})
    s.close()
    _seed(SF, assigned_at=NOW - timedelta(days=5))
    assert _tick(SF, FakeBot(), NOW) == []


# ───────────── житель: уточнение и авто-принятие ─────────────


def test_clarification_reminds_applicant_in_their_language_then_manager(SF):
    _seed(SF, status=C.REQUEST_STATUS_CLARIFICATION, executor_id=None,
          updated_at=NOW - timedelta(hours=5))
    sent = _tick(SF, FakeBot(), NOW)
    assert [c for c, _ in sent] == [20]
    assert "ariza" in sent[0][1]  # uz
    assert _tick(SF, FakeBot(), NOW) == []
    sent = _tick(SF, FakeBot(), NOW + timedelta(hours=4))
    assert [c for c, _ in sent] == [30]


def test_completed_unaccepted_is_force_accepted(SF):
    _seed(SF, status=C.REQUEST_STATUS_COMPLETED, manager_confirmed=True,
          completed_at=NOW - timedelta(days=4))
    sent = _tick(SF, FakeBot(), NOW)
    assert _req(SF).status == C.REQUEST_STATUS_APPROVED
    assert [c for c, _ in sent] == [20]
    assert _steps(SF)[-1]["track"] == "completed"
    assert _tick(SF, FakeBot(), NOW) == []


def test_completed_days_zero_never_accepts(SF):
    s = SF()
    save_config_sync(s, {**DEFAULT_CONFIG, "enabled": True, "mode": "ai",
                         "sla": {**SLA, "completed_unaccepted_days": 0}})
    s.close()
    _seed(SF, status=C.REQUEST_STATUS_COMPLETED, manager_confirmed=True,
          completed_at=NOW - timedelta(days=40))
    assert _tick(SF, FakeBot(), NOW) == []
    assert _req(SF).status == C.REQUEST_STATUS_COMPLETED


# ───────────── менеджер ─────────────


def test_executed_unconfirmed_pings_manager_once(SF):
    _seed(SF, status=C.REQUEST_STATUS_EXECUTED, executed_at=NOW - timedelta(hours=7))
    assert [c for c, _ in _tick(SF, FakeBot(), NOW)] == [30]
    assert _tick(SF, FakeBot(), NOW) == []


def test_critical_unassigned_pings_manager_once(SF):
    _seed(SF, status=C.REQUEST_STATUS_NEW, executor_id=None, created_at=NOW - timedelta(minutes=45))
    _seed(SF, number="261028-002", status=C.REQUEST_STATUS_NEW, executor_id=None, urgency="high",
          created_at=NOW - timedelta(minutes=45))
    sent = _tick(SF, FakeBot(), NOW)
    assert [c for c, _ in sent] == [30] and "261028-001" in sent[0][1]
    assert _tick(SF, FakeBot(), NOW) == []


def test_bot_failure_does_not_raise_and_step_is_recorded(SF):
    class BrokenBot:
        async def send_message(self, *a, **k):
            raise RuntimeError("telegram down")

    _seed(SF, assigned_at=NOW - timedelta(hours=3))
    AiSlaWatchdog(bot=BrokenBot(), session_factory=SF)
    asyncio.run(AiSlaWatchdog(bot=BrokenBot(), session_factory=SF).run_once(now=NOW))
    assert [s["step"] for s in _steps(SF)] == ["remind_executor"]
