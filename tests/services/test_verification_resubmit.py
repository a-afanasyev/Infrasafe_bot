"""Переподача заявки на верификацию после отказа.

Одна транзакция под блокировкой: только «чистый» житель и только из rejected;
первая переподача после отказа проходит сразу, каждая следующая — не раньше
чем через 24 ч после предыдущей (по аудиту, переживает рестарт). Успех —
pending, очищенные поля решения, новая UserVerification(PENDING), аудит.
"""
from datetime import datetime, timedelta, timezone

import pytest

from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_verification import UserVerification, VerificationStatus
from uk_management_bot.services.user_verification_service import (
    ResubmitResult,
    UserVerificationService,
)


@pytest.fixture()
def rejected(el_db, el_seed):
    el_db.add(el_seed.user(1, telegram_id=7301, verification_status="rejected",
                           verification_notes="нечитаемо", verified_by=None))
    el_db.add(UserVerification(user_id=1, status=VerificationStatus.REJECTED))
    el_db.commit()
    return el_db


def test_first_resubmit_right_after_reject(rejected):
    assert UserVerificationService(rejected).resubmit_verification(7301).result is ResubmitResult.RESUBMITTED

    rejected.expire_all()
    user = rejected.get(User, 1)
    assert user.verification_status == "pending"
    assert user.verification_notes is None and user.verification_date is None
    statuses = [v.status for v in rejected.query(UserVerification).filter_by(user_id=1)]
    assert sorted(s.value for s in statuses) == ["pending", "rejected"]
    assert rejected.query(AuditLog).filter_by(action="resident_verification_resubmitted").count() == 1


def test_second_resubmit_within_24h_is_cooldown(rejected):
    service = UserVerificationService(rejected)
    assert service.resubmit_verification(7301).result is ResubmitResult.RESUBMITTED
    rejected.get(User, 1).verification_status = "rejected"  # снова отказ
    rejected.commit()
    assert service.resubmit_verification(7301).result is ResubmitResult.COOLDOWN
    assert rejected.get(User, 1).verification_status == "rejected"


def test_resubmit_after_24h_allowed(rejected):
    service = UserVerificationService(rejected)
    service.resubmit_verification(7301)
    audit = rejected.query(AuditLog).filter_by(action="resident_verification_resubmitted").one()
    audit.created_at = datetime.now(timezone.utc) - timedelta(hours=25)
    rejected.get(User, 1).verification_status = "rejected"
    rejected.commit()
    assert service.resubmit_verification(7301).result is ResubmitResult.RESUBMITTED


@pytest.mark.parametrize("status", ["pending", "requested"])
def test_open_check_is_already_pending(rejected, status):
    rejected.get(User, 1).verification_status = status
    rejected.commit()
    assert UserVerificationService(rejected).resubmit_verification(7301).result is ResubmitResult.ALREADY_PENDING
    assert rejected.query(AuditLog).count() == 0


@pytest.mark.parametrize("change", [
    {"roles": '["applicant", "executor"]'},   # стафф — у него своя очередь
    {"verification_status": "verified"},
    {"status": "blocked"},
])
def test_denied(rejected, change):
    user = rejected.get(User, 1)
    for key, value in change.items():
        setattr(user, key, value)
    rejected.commit()
    assert UserVerificationService(rejected).resubmit_verification(7301).result is ResubmitResult.DENIED
    assert rejected.get(User, 1).verification_status == change.get("verification_status", "rejected")


def test_deleted_user_denied(rejected):
    rejected.get(User, 1).deleted_at = datetime.now(timezone.utc)
    rejected.commit()
    assert UserVerificationService(rejected).resubmit_verification(7301).result is ResubmitResult.DENIED


def test_resubmit_drops_documents_left_from_pre_release_reject(rejected):
    """Отказ до релиза документы не удалял — новая заявка не подхватывает старый паспорт."""
    from uk_management_bot.database.models.user_verification import DocumentType, UserDocument

    rejected.add(UserDocument(user_id=1, document_type=DocumentType.PASSPORT, file_id="AgACold"))
    rejected.commit()
    outcome = UserVerificationService(rejected).resubmit_verification(7301)
    assert outcome.result is ResubmitResult.RESUBMITTED
    assert outcome.purge.has_legacy and outcome.purge.count == 1
    assert rejected.query(UserDocument).filter_by(user_id=1).count() == 0


def test_unknown_user(rejected):
    assert UserVerificationService(rejected).resubmit_verification(1).result is ResubmitResult.NOT_FOUND
