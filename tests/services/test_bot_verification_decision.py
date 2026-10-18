"""Решение по верификации из бота — один юнит, один commit.

Раньше бот коммитил статус, квартиры и удаление документов тремя commit'ами без
блокировки, подавляя ошибки, и писал в `verified_by` Telegram ID менеджера
(FK на users.id). Теперь: внутренний id менеджера → лок жителя → guard
pending/requested → удаление документов (ключей) → решение → один commit.
"""
import pytest

from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.database.models.user_verification import (
    DocumentType, UserDocument, UserVerification, VerificationStatus,
)
from uk_management_bot.services.user_verification_service import UserVerificationService

MANAGER_TG = 9001


@pytest.fixture()
def world(el_db, el_seed):
    el_db.add_all([
        el_seed.yard(), el_seed.building(), el_seed.apartment(1),
        el_seed.user(1, telegram_id=7001, verification_status="requested"),
        el_seed.user(2, telegram_id=MANAGER_TG, roles='["manager"]'),
    ])
    el_db.flush()
    el_db.add_all([
        UserApartment(user_id=1, apartment_id=1, status="pending"),
        UserVerification(user_id=1, status=VerificationStatus.REQUESTED),
        UserDocument(user_id=1, document_type=DocumentType.PASSPORT, media_id=801,
                     encryption_key=b"k" * 32, document_uuid="00000000-0000-4000-8000-000000000801"),
    ])
    el_db.commit()
    return el_db


def _docs(db):
    return db.query(UserDocument).filter_by(user_id=1).count()


def test_approve_one_commit_with_internal_manager_id(world):
    purge = UserVerificationService(world).approve_verification_db(1, MANAGER_TG)

    assert purge is not None and purge.media_ids == (801,)
    world.expire_all()
    user = world.get(User, 1)
    assert user.verification_status == "verified"
    assert user.verified_by == 2  # users.id, а не Telegram ID
    assert world.query(UserApartment).filter_by(user_id=1).one().status == "approved"
    assert world.query(UserVerification).filter_by(user_id=1).one().status == VerificationStatus.APPROVED
    assert _docs(world) == 0


def test_reject_deletes_documents(world):
    purge = UserVerificationService(world).reject_verification(1, MANAGER_TG, "нечитаемо")

    assert purge.media_ids == (801,)
    world.expire_all()
    user = world.get(User, 1)
    assert user.verification_status == "rejected"
    assert user.verified_by == 2
    assert world.query(UserApartment).filter_by(user_id=1).one().status == "pending"
    assert _docs(world) == 0


@pytest.mark.parametrize("closed", ["verified", "rejected"])
def test_closed_verification_is_not_decided_again(world, closed):
    world.get(User, 1).verification_status = closed
    world.commit()
    service = UserVerificationService(world)
    assert service.approve_verification_db(1, MANAGER_TG) is None
    assert service.reject_verification(1, MANAGER_TG, "x") is None


def test_unknown_manager_is_refused(world):
    assert UserVerificationService(world).approve_verification_db(1, 123456) is None
    world.expire_all()
    assert world.get(User, 1).verification_status == "requested"
    assert _docs(world) == 1


def test_failure_rolls_back_everything(world, monkeypatch):
    """Сбой на шаге квартир не оставляет «решения без удаления документов»."""
    from uk_management_bot.services import user_verification_service as module

    def boom(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr(module, "_auto_approve_apartments", boom)
    with pytest.raises(RuntimeError):
        UserVerificationService(world).approve_verification_db(1, MANAGER_TG)

    world.expire_all()
    assert world.get(User, 1).verification_status == "requested"
    assert _docs(world) == 1
