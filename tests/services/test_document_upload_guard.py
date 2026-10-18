"""Центральный guard загрузки документов и вставка зашифрованной строки.

Документы принимаются, только пока проверка открыта (pending/requested), у
живого незаблокированного жителя (или когда менеджер сам запросил документы),
и не больше MAX_DOCUMENTS_PER_REVIEW на проверку. Guard повторяется при вставке
под блокировкой строки пользователя — сериализация с решением менеджера.
"""
import pytest

from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_verification import DocumentType, UserDocument
from uk_management_bot.services.user_verification_service import (
    MAX_DOCUMENTS_PER_REVIEW,
    UploadDenied,
    UserVerificationService,
)

TG = 7201


@pytest.fixture()
def resident(el_db, el_seed):
    el_db.add(el_seed.user(1, telegram_id=TG, status="pending"))
    el_db.commit()
    return el_db


def _add(db, media_id=1):
    return UserVerificationService(db).add_encrypted_document(
        TG, DocumentType.PASSPORT, media_id=media_id, key=b"k" * 32,
        document_uuid=f"00000000-0000-4000-8000-{media_id:012d}", file_name="p.jpg", file_size=10,
    )


def test_open_check_allows_and_returns_user_id(resident):
    user_id, denial = UserVerificationService(resident).check_document_upload(TG)
    assert (user_id, denial) == (1, None)


def test_insert_stores_encrypted_triple_without_file_id(resident):
    assert _add(resident) is None
    doc = resident.query(UserDocument).one()
    assert doc.media_id == 1 and doc.file_id is None and doc.encryption_key == b"k" * 32


@pytest.mark.parametrize("change, reason", [
    ({"verification_status": "verified"}, UploadDenied.NOT_REQUIRED),
    ({"verification_status": "rejected"}, UploadDenied.REJECTED),
    ({"status": "blocked"}, UploadDenied.NOT_REQUIRED),
    ({"roles": '["executor"]'}, UploadDenied.NOT_REQUIRED),
])
def test_closed_or_foreign_is_denied(resident, change, reason):
    user = resident.get(User, 1)
    for key, value in change.items():
        setattr(user, key, value)
    resident.commit()
    assert UserVerificationService(resident).check_document_upload(TG)[1] is reason
    assert _add(resident) is reason
    assert resident.query(UserDocument).count() == 0


def test_deleted_user_is_denied(resident):
    from datetime import datetime, timezone

    resident.get(User, 1).deleted_at = datetime.now(timezone.utc)
    resident.commit()
    assert _add(resident) is UploadDenied.NOT_REQUIRED


def test_requested_staff_can_upload(resident):
    """Менеджер запросил документы у сотрудника — роль applicant не требуется."""
    user = resident.get(User, 1)
    user.roles = '["executor"]'
    user.verification_status = "requested"
    resident.commit()
    assert _add(resident) is None


def test_unknown_telegram_id_is_denied(resident):
    service = UserVerificationService(resident)
    assert service.check_document_upload(999)[1] is UploadDenied.NOT_REQUIRED


def test_limit_per_review(resident):
    for media_id in range(1, MAX_DOCUMENTS_PER_REVIEW + 1):
        assert _add(resident, media_id) is None
    assert _add(resident, 999) is UploadDenied.LIMIT
    assert resident.query(UserDocument).count() == MAX_DOCUMENTS_PER_REVIEW
