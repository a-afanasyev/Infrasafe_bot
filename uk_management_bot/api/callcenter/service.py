"""Сервис-слой call-центра (AUD5-ARCH-2 волна 2, ARCH-05a-канон).

Module-level async функции `(db, *, plain-параметры) -> ORM|примитивы`.
HTTPException, парсинг и сериализация — в router.py.
"""
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.requests.elevator_fields import PersistedRequest
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request import Request
from uk_management_bot.services.elevator_service import resolve_request_elevator_async
from uk_management_bot.services.request_number_service import RequestNumberService
from uk_management_bot.utils.auth_helpers import legacy_role_filter
from uk_management_bot.utils.constants import ACCEPTANCE_MODE_RESIDENT
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
    building_id: int | None = None,
    address: str,
    address_type: str,
    notes: str | None,
    elevator_id: int | None = None,
    elevator_operational: bool | None = None,
    acceptance_mode: str | None = None,
) -> PersistedRequest:
    """Создание заявки call-центра: атомарный номер, insert, авто-dispatch.

    PR5: атомарный счётчик дня (раньше COUNT(*)+1 без retry — коллизия
    после удаления строки роняла запрос 500-кой).

    Адрес — ровно один FK (CHECK ck_requests_address_type_fk): ``apartment_id``
    (уровень квартиры) ИЛИ ``building_id`` (уровень дома, ремонт лифта из
    карточки) ИЛИ ни одного (legacy) — роутер даёт согласованный ``address_type``.
    Лифт (Р11, Ф4a-1) — единая проверка ``resolve_request_elevator_async``
    ДО выдачи номера; ``ElevatorValidationError`` наверх (роутер → 422).
    Р18 запрет на лифт «В ремонте»/«На ТО» здесь НЕ применяется
    (``allow_under_works=True``): оператор на линии видит статус в карточке и
    решает сам — через этот же путь идёт и «Создать ремонт» из дашборда.
    ``acceptance_mode=None`` → прежний дефолт ('resident').
    """
    # Дом заявки: building_id (уровень дома) или дом квартиры жителя; при
    # свободном legacy-адресе дома нет → лифт привязать нельзя (security-ревью T6).
    binding = await resolve_request_elevator_async(
        db, category=category, elevator_id=elevator_id,
        elevator_operational=elevator_operational, enabled=settings.ELEVATORS_ENABLED,
        building_id=building_id, apartment_id=apartment_id, allow_under_works=True,
    )
    request_number = await RequestNumberService.next_number_async(db)

    req = Request(
        request_number=request_number,
        user_id=owner_id,
        category=category,
        urgency=urgency,
        description=description,
        apartment_id=apartment_id,
        building_id=building_id,
        address=address,
        address_type=address_type,
        status="Новая",
        source="call_center",
        notes=notes,
        media_files=[],
        elevator_id=binding.elevator_id,
        elevator_operational=binding.elevator_operational,
        acceptance_mode=acceptance_mode or ACCEPTANCE_MODE_RESIDENT,
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
    return PersistedRequest(request=req, elevator=binding.elevator)
