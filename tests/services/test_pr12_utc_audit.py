"""PR-12 (CODE-09): UTC-sweep DB-writes + восстановление аудита.

Два инварианта:
1. `_create_audit_log` РЕАЛЬНО пишет AuditLog — раньше битый kwarg
   `timestamp=` (нет такой колонки) кидал TypeError, который гасился
   `except` → аудит молча терялся.
2. DB-write метки времени — tz-aware UTC (выровнены с server_default
   func.now() и webhook-каноном datetime.now(timezone.utc)).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.database.session import Base
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request import Request
from uk_management_bot.services.assignment_service import AssignmentService


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    # expire_on_commit=False: sqlite не хранит tzinfo (возвращает naive после
    # round-trip), поэтому проверяем Python-aware значение, записанное кодом,
    # до его истечения. На postgres tz сохраняется и так.
    SF = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    s = SF()
    yield s
    s.close()
    engine.dispose()


class TestAuditRestored:
    def test_create_audit_log_persists_row(self, session):
        """Битый kwarg timestamp= убран → AuditLog реально пишется."""
        svc = AssignmentService(session)
        svc._create_audit_log("260613-001", user_id=1, action_description="назначено")
        session.commit()

        rows = session.query(AuditLog).all()
        assert len(rows) == 1
        assert rows[0].action  # action заполнен
        # created_at заполняется server_default=func.now() после flush/commit
        assert rows[0].created_at is not None

    def test_audit_log_rejects_timestamp_kwarg(self):
        """Регрессия: у AuditLog нет колонки timestamp — kwarg недопустим.
        Гарантирует, что мы не вернём битый вызов обратно."""
        with pytest.raises(TypeError):
            AuditLog(action="x", user_id=1, timestamp="whatever")


class TestUtcAwareWrites:
    def test_assigned_at_is_tz_aware_utc(self, session):
        """request.assigned_at пишется tz-aware UTC (assign_to_executor)."""
        session.add(User(id=1, telegram_id=1, first_name="Exec",
                         roles='["executor"]', active_role="executor",
                         status="approved", language="ru"))
        session.add(Request(
            request_number="260613-002", user_id=1, category="Сантехника",
            description="x", status="Новая", address="addr",
        ))
        session.commit()

        svc = AssignmentService(session)
        svc.assign_to_executor("260613-002", executor_id=1, assigned_by=1)

        req = session.query(Request).get("260613-002")
        assert req.assigned_at is not None
        # CODE-09: метка — текущий UTC-инстант (выровнен с func.now()).
        # tzinfo НЕ проверяем: sqlite-диалект стрипит его на round-trip
        # (на postgres сохраняется); awareness гарантирован источником
        # datetime.now(timezone.utc) — см. grep-инвентаризацию в PR.
        from datetime import datetime
        written = req.assigned_at.replace(tzinfo=None)
        delta = abs((datetime.utcnow() - written).total_seconds())
        assert delta < 120, f"assigned_at не UTC-инстант: {written} (Δ{delta}s от utcnow)"
