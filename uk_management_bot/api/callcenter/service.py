"""Сервис-слой call-центра (AUD5-ARCH-2 волна 2, ARCH-05a-канон).

Module-level async функции `(db, *, plain-параметры) -> ORM|примитивы`.
HTTPException, парсинг и сериализация — в router.py.
"""
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request import Request
from uk_management_bot.services.request_number_service import RequestNumberService
from uk_management_bot.utils.auth_helpers import legacy_role_filter
from uk_management_bot.utils.sql_search import (
    ci_contains_any,
    escape_like as _escape_like,
    is_postgres,
)


async def search_approved_applicants(db: AsyncSession, *, q: str):
    """Поиск approved-жителей по телефону/имени/фамилии (лимит 10)."""
    escaped_q = _escape_like(q)
    pattern = f"%{escaped_q}%"

    # Single query with subquery for request count to avoid N+1
    count_subq = (
        select(func.count(Request.request_number))
        .where(Request.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )

    result = await db.execute(
        select(
            User.id,
            User.telegram_id,
            User.first_name,
            User.last_name,
            User.phone,
            count_subq.label("requests_count"),
        ).where(
            # Только approved-жители: менеджер не должен выбрать того, кому потом
            # нельзя создать заявку (план «Обходчик», R52).
            User.status == "approved",
            or_(
                User.roles.like('%"applicant"%'),
                legacy_role_filter("applicant"),
            ),
            ci_contains_any(
                (User.phone, User.first_name, User.last_name),
                pattern,
                is_postgres=is_postgres(db),
            ),
        ).limit(10)
    )
    return result.all()


async def user_by_id(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, user_id)


async def persist_call_center_request(
    db: AsyncSession,
    *,
    owner_id: int,
    category: str,
    urgency: str,
    description: str,
    apartment_id: int | None,
    address: str,
    address_type: str,
    notes: str | None,
) -> Request:
    """Создание заявки call-центра: атомарный номер, insert, авто-dispatch.

    PR5: атомарный счётчик дня (раньше COUNT(*)+1 без retry — коллизия
    после удаления строки роняла запрос 500-кой).
    """
    request_number = await RequestNumberService.next_number_async(db)

    req = Request(
        request_number=request_number,
        user_id=owner_id,
        category=category,
        urgency=urgency,
        description=description,
        apartment_id=apartment_id,
        address=address,
        address_type=address_type,
        status="Новая",
        source="call_center",
        notes=notes,
        media_files=[],
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)

    # FEAT-группы (followup #1): call-center — ещё один канал создания. Авто-dispatch
    # на группу-специализацию (Новая→В работе + group) через канонический
    # run_command, как в persist_request (twa/inspector) и боте. Best-effort —
    # ошибка не валит уже-созданную заявку. refresh — чтобы карточка отразила статус.
    from uk_management_bot.services.dispatch import auto_dispatch_new_request_async
    await auto_dispatch_new_request_async(req.request_number, category)
    await db.refresh(req)
    return req
