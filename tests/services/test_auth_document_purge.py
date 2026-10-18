"""AuthService: доверенная роль и удаление пользователя тоже закрывают проверку."""
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_verification import DocumentType, UserDocument
from uk_management_bot.services.auth_service import AuthService


def _seed(db, el_seed, *, verification="pending"):
    db.add(el_seed.user(1, telegram_id=7101, status="pending", verification_status=verification))
    db.flush()
    db.add(UserDocument(user_id=1, document_type=DocumentType.PASSPORT, media_id=951,
                        encryption_key=b"k" * 32, document_uuid="00000000-0000-4000-8000-000000000951"))
    db.commit()


def test_trusted_role_purges_documents(el_db, el_seed):
    _seed(el_db, el_seed)
    assert AuthService(el_db).auto_approve_user_sync(7101, role="manager") is True
    el_db.expire_all()
    assert el_db.get(User, 1).verification_status == "verified"
    assert el_db.query(UserDocument).count() == 0


def test_untrusted_role_keeps_open_documents(el_db, el_seed):
    _seed(el_db, el_seed)
    AuthService(el_db).auto_approve_user_sync(7101, role="applicant")
    el_db.expire_all()
    assert el_db.get(User, 1).verification_status == "pending"
    assert el_db.query(UserDocument).count() == 1


def test_delete_user_purging_documents_reports_ids(el_db, el_seed):
    _seed(el_db, el_seed)
    outcome = AuthService(el_db).delete_user_purging_documents(1, deleted_by=1, reason="x")
    assert outcome.ok is True
    assert outcome.purge.media_ids == (951,)
    assert el_db.query(UserDocument).count() == 0


def test_delete_user_keeps_bool_contract(el_db, el_seed):
    _seed(el_db, el_seed)
    assert AuthService(el_db).delete_user(1, deleted_by=1, reason="x") is True
    assert AuthService(el_db).delete_user(999, deleted_by=1, reason="x") is False
