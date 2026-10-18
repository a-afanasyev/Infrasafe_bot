"""Очистка документов жителя при закрытии проверки (services/document_purge).

Строки удаляются в транзакции решения (ключи уничтожаются вместе с ней), наружу —
точные media_id и признак легаси-строк для гигиены медиа-сервиса после commit.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from uk_management_bot.database.models.user_verification import DocumentType, UserDocument


def _encrypted(user_id: int, media_id: int) -> UserDocument:
    return UserDocument(
        user_id=user_id, document_type=DocumentType.PASSPORT, media_id=media_id,
        encryption_key=b"k" * 32, document_uuid=f"00000000-0000-4000-8000-{media_id:012d}",
    )


def _legacy(user_id: int) -> UserDocument:
    return UserDocument(user_id=user_id, document_type=DocumentType.PASSPORT, file_id="AgACAgIAAx")


@pytest.fixture()
def seeded(el_db, el_seed):
    el_db.add_all([el_seed.user(1), el_seed.user(2)])
    el_db.add_all([_encrypted(1, 501), _encrypted(1, 502), _legacy(1), _encrypted(2, 900)])
    el_db.commit()
    return el_db


def test_sync_purge_deletes_rows_and_reports_ids(seeded):
    from uk_management_bot.database.models.user import User
    from uk_management_bot.services.document_purge import purge_documents_sync

    user = seeded.get(User, 1)
    result = purge_documents_sync(seeded, user)
    seeded.commit()

    assert sorted(result.media_ids) == [501, 502]
    assert result.has_legacy is True
    assert result.count == 3
    assert result.telegram_id == user.telegram_id
    assert seeded.query(UserDocument).filter_by(user_id=1).count() == 0
    assert seeded.query(UserDocument).filter_by(user_id=2).count() == 1  # чужие не тронуты


def test_sync_purge_without_documents_is_empty(el_db, el_seed):
    from uk_management_bot.database.models.user import User
    from uk_management_bot.services.document_purge import purge_documents_sync

    el_db.add(el_seed.user(3))
    el_db.commit()
    result = purge_documents_sync(el_db, el_db.get(User, 3))
    assert result.empty


@pytest.mark.asyncio
async def test_async_purge_matches_sync(el_async_factory, el_seed):
    from uk_management_bot.database.models.user import User
    from uk_management_bot.services.document_purge import purge_documents

    async with el_async_factory() as db:
        db.add(el_seed.user(1))
        db.add_all([_encrypted(1, 601), _legacy(1)])
        await db.commit()
        result = await purge_documents(db, await db.get(User, 1))
        await db.commit()
        from sqlalchemy import func, select
        left = (await db.execute(select(func.count()).select_from(UserDocument))).scalar()

    assert result.media_ids == (601,)
    assert result.has_legacy is True
    assert left == 0


@pytest.mark.asyncio
async def test_cleanup_deletes_exact_ids_and_legacy_prefix(monkeypatch):
    from uk_management_bot.services import document_purge
    from uk_management_bot.services.document_purge import PurgeResult

    client = MagicMock()
    client.delete_media = AsyncMock(return_value=True)
    monkeypatch.setattr(document_purge, "get_media_client", lambda: client)
    legacy = AsyncMock()
    monkeypatch.setattr(document_purge, "delete_user_documents_from_media_service", legacy)

    await document_purge.cleanup_purged_documents(PurgeResult(77, (501, 502), True))

    assert [c.args[0] for c in client.delete_media.await_args_list] == [501, 502]
    legacy.assert_awaited_once_with(77)


@pytest.mark.asyncio
async def test_cleanup_without_legacy_never_scans_prefix(monkeypatch):
    """Префиксная зачистка USER_<tg> задела бы документы следующего цикла — только для легаси."""
    from uk_management_bot.services import document_purge
    from uk_management_bot.services.document_purge import PurgeResult

    client = MagicMock()
    client.delete_media = AsyncMock(return_value=True)
    monkeypatch.setattr(document_purge, "get_media_client", lambda: client)
    legacy = AsyncMock()
    monkeypatch.setattr(document_purge, "delete_user_documents_from_media_service", legacy)

    await document_purge.cleanup_purged_documents(PurgeResult(77, (501,), False))
    legacy.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_failures_are_logged_not_raised(monkeypatch, caplog):
    from uk_management_bot.services import document_purge
    from uk_management_bot.services.document_purge import PurgeResult

    client = MagicMock()
    client.delete_media = AsyncMock(side_effect=[False, RuntimeError("boom")])
    monkeypatch.setattr(document_purge, "get_media_client", lambda: client)

    await document_purge.cleanup_purged_documents(PurgeResult(77, (501, 502), False))
    assert "501" in caplog.text and "502" in caplog.text


@pytest.mark.asyncio
async def test_cleanup_legacy_failure_is_logged_not_raised(monkeypatch, caplog):
    from uk_management_bot.services import document_purge
    from uk_management_bot.services.document_purge import PurgeResult

    monkeypatch.setattr(document_purge, "get_media_client", lambda: None)
    monkeypatch.setattr(document_purge, "delete_user_documents_from_media_service",
                        AsyncMock(side_effect=RuntimeError("media down")))
    await document_purge.cleanup_purged_documents(PurgeResult(77, (), True, 1))
    assert "77" in caplog.text


@pytest.mark.asyncio
async def test_cleanup_media_disabled_logs_ids(monkeypatch, caplog):
    from uk_management_bot.services import document_purge
    from uk_management_bot.services.document_purge import PurgeResult

    monkeypatch.setattr(document_purge, "get_media_client", lambda: None)
    await document_purge.cleanup_purged_documents(PurgeResult(77, (501,), False))
    assert "501" in caplog.text


@pytest.mark.asyncio
async def test_cleanup_empty_is_noop(monkeypatch):
    from uk_management_bot.services import document_purge
    from uk_management_bot.services.document_purge import PurgeResult

    monkeypatch.setattr(document_purge, "get_media_client", MagicMock(side_effect=AssertionError))
    await document_purge.cleanup_purged_documents(PurgeResult(77))


@pytest.mark.parametrize("fields", [
    {"file_id": ""},                                                     # пустая легаси
    {"file_id": "AgAC", "media_id": 1, "encryption_key": b"k", "document_uuid": "u"},  # обе формы
    {"media_id": 1, "encryption_key": b"k"},                             # неполная тройка
    {},                                                                  # ни одной
])
def test_storage_xor_constraint(el_db, el_seed, fields):
    el_db.add(el_seed.user(1))
    el_db.commit()
    el_db.add(UserDocument(user_id=1, document_type=DocumentType.OTHER, **fields))
    with pytest.raises(IntegrityError):
        el_db.commit()
