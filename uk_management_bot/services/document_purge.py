"""Удаление документов жителя при закрытии проверки.

Инвариант: документы живут, только пока проверка открыта
(`verification_status` ∈ {pending, requested} и `deleted_at IS NULL`). Любой
путь, закрывающий проверку (verified/rejected) или удаляющий пользователя,
вызывает `purge_documents[_sync]` ДО своего commit — строки и ключи шифрования
исчезают атомарно с решением. Вызывать ДО изменения `verification_status`/
`deleted_at`: их flush запускает триггер 026, который удалит строки раньше, и
media_id для гигиены уже не собрать (на sqlite триггера нет — тесты этого не видят). Страховка для забытых путей — триггер в БД
(миграция 026); он не отдаёт media_id, поэтому приложение удаляет само.

После commit — `cleanup_purged_documents`: гигиена медиа-сервиса по точным
media_id. Приватность от неё не зависит (без ключа blob нечитаем), поэтому
сбой только логируется. Префиксная зачистка `USER_<tg>` — лишь для легаси-строк:
новые документы `request_number` не имеют, и следующий цикл она не заденет.
"""
import logging
from dataclasses import dataclass
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_verification import UserDocument
from uk_management_bot.integrations import get_media_client
from uk_management_bot.utils.media_helpers import delete_user_documents_from_media_service

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PurgeResult:
    telegram_id: Optional[int]
    media_ids: tuple[int, ...] = ()
    has_legacy: bool = False
    count: int = 0  # удалено строк (легаси + зашифрованные)

    @property
    def empty(self) -> bool:
        return not self.media_ids and not self.has_legacy


def _result(user: User, documents: Iterable[UserDocument]) -> PurgeResult:
    documents = list(documents)
    return PurgeResult(
        telegram_id=user.telegram_id,
        media_ids=tuple(d.media_id for d in documents if d.media_id is not None),
        has_legacy=any(d.media_id is None for d in documents),
        count=len(documents),
    )


def purge_documents_sync(db: Session, user: User) -> PurgeResult:
    """Удаляет документы пользователя в текущей транзакции (commit — у вызывающего).

    FOR UPDATE строки пользователя — сериализация с загрузкой документа на ЛЮБОМ
    пути (загрузка вставляет под тем же локом): иначе документ, закоммиченный
    между чтением и сменой статуса, удалил бы триггер, а его media_id не попал бы
    в гигиену. flush сразу — DELETE уходит до UPDATE статуса (иначе триггер
    удалит строки первым, и ORM получит «0 rows matched»).
    """
    db.query(User.id).filter(User.id == user.id).with_for_update().first()
    documents = db.query(UserDocument).filter(UserDocument.user_id == user.id).all()
    for document in documents:
        db.delete(document)
    db.flush()
    return _result(user, documents)


async def purge_documents(db: AsyncSession, user: User) -> PurgeResult:
    """Async-двойник `purge_documents_sync` (commit — у вызывающего)."""
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    documents = (await db.execute(
        select(UserDocument).where(UserDocument.user_id == user.id)
    )).scalars().all()
    for document in documents:
        await db.delete(document)
    await db.flush()
    return _result(user, documents)


async def cleanup_purged_documents(result: PurgeResult) -> None:
    """Гигиена медиа-сервиса после commit. Никогда не поднимает исключение."""
    if result.empty:
        return
    failed = list(result.media_ids)
    client = get_media_client()
    if client is None:
        logger.warning("Медиа-сервис выключен — blob'ы документов %s остались (ключи удалены)", failed)
    else:
        failed = []
        for media_id in result.media_ids:
            try:
                if not await client.delete_media(media_id):
                    failed.append(media_id)
            except Exception as e:  # noqa: BLE001 — гигиена не роняет решение
                logger.warning("Удаление blob'а документа %s: %s", media_id, e)
                failed.append(media_id)
        if failed:
            logger.warning("Не удалены blob'ы документов %s (ключи удалены, blob'ы нечитаемы)", failed)
    if result.has_legacy and result.telegram_id:
        try:
            await delete_user_documents_from_media_service(result.telegram_id)
        except Exception as e:  # noqa: BLE001 — гигиена не роняет решение
            logger.warning(
                "Зачистка легаси-копий документов в Media Service не состоялась (%s) — "
                "повторить по telegram_id %s", e, result.telegram_id,
            )
