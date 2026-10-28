"""Выключение режима ИИ: сколько открытых заявок было на эскалации.

Состояние лестницы живёт в audit_logs — при переходе ai → rule менеджер
получает одно сообщение с числом открытых заявок, у которых есть шаги
ai_sla_step за последние 30 дней, чтобы они не потерялись.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import uk_management_bot.utils.constants as C
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services.ai_manager import switch_off
from uk_management_bot.services.ai_manager.sla import AUDIT_STEP


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine)()
    s.add_all([
        User(id=2, telegram_id=20, roles='["applicant"]', status="approved", language="ru"),
        User(id=3, telegram_id=30, roles='["manager"]', active_role="manager", status="approved", language="ru"),
    ])
    s.commit()
    yield s
    s.close()
    engine.dispose()


def _req(db, number, status):
    db.add(Request(request_number=number, user_id=2, category="plumbing", description="x",
                   urgency="low", status=status, created_at=datetime.now(timezone.utc)))
    db.commit()


def _step(db, number):
    db.add(AuditLog(user_id=None, action=AUDIT_STEP,
                    details={"request_number": number, "track": "executor", "step": "manager"}))
    db.commit()


def test_counts_only_open_requests_with_steps(db):
    _req(db, "261028-001", C.REQUEST_STATUS_IN_PROGRESS)
    _req(db, "261028-002", C.REQUEST_STATUS_APPROVED)   # закрыта
    _req(db, "261028-003", C.REQUEST_STATUS_IN_PROGRESS)  # без шагов
    _step(db, "261028-001")
    _step(db, "261028-001")  # повторный шаг — та же заявка
    _step(db, "261028-002")
    assert switch_off.count_escalating_sync(db) == 1


def test_zero_when_nothing(db):
    assert switch_off.count_escalating_sync(db) == 0


def test_notices_for_managers_only_when_count_positive(db):
    assert switch_off.manager_notices_sync(db, "ai", "rule") == []
    _req(db, "261028-001", C.REQUEST_STATUS_IN_PROGRESS)
    _step(db, "261028-001")
    assert switch_off.manager_notices_sync(db, "rule", "ai") == []   # включение — не повод
    notices = switch_off.manager_notices_sync(db, "ai", "rule")
    assert [tg for tg, _ in notices] == [30]
    assert "1" in notices[0][1] and "261028-001" not in notices[0][1]
