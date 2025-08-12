import os
import sys
import asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Добавляем в sys.path корень пакета `uk_management_bot`, как в существующих тестах
sys.path.append(os.path.join(os.path.dirname(__file__), 'uk_management_bot'))

from database.session import Base
from database.models.user import User
from database.models.audit import AuditLog
from services.auth_service import AuthService


def setup_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return engine, SessionLocal


def teardown_db(engine):
    Base.metadata.drop_all(bind=engine)


def test_rate_limit_and_audit_record():
    engine, SessionLocal = setup_db()
    try:
        db = SessionLocal()

        # Создаём пользователя с двумя ролями и активной applicant
        user = User(
            telegram_id=999001,
            role="applicant",
            roles='["applicant", "executor"]',
            active_role="applicant",
            status="approved",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        service = AuthService(db)

        # 1) Успешное переключение на executor → должно записать аудит
        ok, reason = asyncio.run(service.try_set_active_role_with_rate_limit(user.telegram_id, "executor", window_seconds=10))
        assert ok is True
        assert reason is None

        # Проверяем аудит
        log = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        assert log is not None
        assert log.action == "role_switched"
        assert log.details.get("old_role") == "applicant"
        assert log.details.get("new_role") == "executor"

        # 2) Повторная попытка в окне лимита → отказ с reason=rate_limited
        ok2, reason2 = asyncio.run(service.try_set_active_role_with_rate_limit(user.telegram_id, "applicant", window_seconds=10))
        assert ok2 is False
        assert reason2 == "rate_limited"

    finally:
        teardown_db(engine)


