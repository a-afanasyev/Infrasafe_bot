"""Address CRUD core — single async implementation shared by the bot adapter
(services/address_service.py) and the FastAPI router (api/addresses/router.py).

Contract:
  * Functions take an AsyncSession plus primitives — NO Pydantic, NO imports
    from `api/` (services/ must not depend on api/).
  * They validate, mutate, and emit events, then commit. On a violated
    invariant they raise a domain exception from .exceptions.
  * update_* take an explicit `updates: dict` so callers can distinguish
    "field absent" (leave unchanged) from "field present = None" (clear it).

Each write follows the same shape:
  validate -> ORM insert/update + flush -> build raw event data ->
  enqueue_outbox (same tx) -> commit -> refresh -> publish_realtime_after_commit.
"""
import logging

from sqlalchemy import select, func, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models import (
    Yard, Building, Apartment, UserApartment,
)
from uk_management_bot.services.addresses.exceptions import (
    AddressNotFound, AddressConflict, AddressValidationError,
)
from uk_management_bot.services.addresses.events import (
    enqueue_outbox, publish_realtime_after_commit,
)
from uk_management_bot.services.addresses.payloads import (
    build_yard_event_data, build_building_event_data, build_apartment_event_data,
)

logger = logging.getLogger(__name__)

_APARTMENT_NUMBER_MAX_LEN = 20


# ───────────────────────── internal helpers ─────────────────────────

async def _get_yard_or_raise(db: AsyncSession, yard_id: int) -> Yard:
    yard = await db.get(Yard, yard_id)
    if yard is None:
        raise AddressNotFound("Двор не найден", code="yard_not_found")
    return yard


async def _get_building_or_raise(db: AsyncSession, building_id: int) -> Building:
    building = await db.get(Building, building_id)
    if building is None:
        raise AddressNotFound("Здание не найдено", code="building_not_found")
    return building


async def _get_apartment_or_raise(db: AsyncSession, apartment_id: int) -> Apartment:
    apartment = await db.get(Apartment, apartment_id)
    if apartment is None:
        raise AddressNotFound("Квартира не найдена", code="apartment_not_found")
    return apartment


async def _get_user_apartment_or_raise(db: AsyncSession, ua_id: int) -> UserApartment:
    ua = await db.get(UserApartment, ua_id)
    if ua is None:
        raise AddressNotFound("Заявка не найдена", code="request_not_found")
    return ua


async def _count_active_buildings(db: AsyncSession, yard_id: int) -> int:
    return (await db.execute(
        select(func.count(Building.id)).where(
            and_(Building.yard_id == yard_id, Building.is_active.is_(True))
        )
    )).scalar() or 0


async def _count_active_apartments(db: AsyncSession, building_id: int) -> int:
    return (await db.execute(
        select(func.count(Apartment.id)).where(
            and_(Apartment.building_id == building_id, Apartment.is_active.is_(True))
        )
    )).scalar() or 0


async def _count_approved_residents(db: AsyncSession, apartment_id: int) -> int:
    return (await db.execute(
        select(func.count(UserApartment.id)).where(
            and_(UserApartment.apartment_id == apartment_id,
                 UserApartment.status == "approved")
        )
    )).scalar() or 0


# ───────────────────────── Yards ─────────────────────────

async def create_yard(
    db: AsyncSession,
    *,
    name: str,
    created_by: int,
    description: str | None = None,
    gps_latitude: float | None = None,
    gps_longitude: float | None = None,
) -> Yard:
    existing = (await db.execute(
        select(Yard.id).where(Yard.name == name)
    )).scalar_one_or_none()
    if existing is not None:
        raise AddressConflict(f"Двор с названием '{name}' уже существует")

    yard = Yard(
        name=name,
        description=description,
        gps_latitude=gps_latitude,
        gps_longitude=gps_longitude,
        created_by=created_by,
        is_active=True,
    )
    db.add(yard)
    await db.flush()

    data = build_yard_event_data(yard)
    await enqueue_outbox(db, event="yard.created", data=data)
    await db.commit()
    await db.refresh(yard)
    await publish_realtime_after_commit("yard.created", data)
    logger.info("Создан двор: %s (ID: %s)", yard.name, yard.id)
    return yard


async def update_yard(db: AsyncSession, yard_id: int, updates: dict) -> Yard:
    """`updates` keys present are applied (None clears the field); absent keys
    are left unchanged."""
    yard = await _get_yard_or_raise(db, yard_id)

    # Canonical guard: block deactivation while active buildings exist.
    if updates.get("is_active") is False and yard.is_active:
        active = await _count_active_buildings(db, yard_id)
        if active > 0:
            raise AddressConflict(
                f"Невозможно деактивировать двор: есть {active} активных зданий"
            )

    if "name" in updates and updates["name"] != yard.name:
        clash = (await db.execute(
            select(Yard.id).where(and_(Yard.name == updates["name"], Yard.id != yard_id))
        )).scalar_one_or_none()
        if clash is not None:
            raise AddressConflict(f"Двор с названием '{updates['name']}' уже существует")

    for field, value in updates.items():
        setattr(yard, field, value)
    await db.flush()

    data = build_yard_event_data(yard)
    await enqueue_outbox(db, event="yard.updated", data=data)
    await db.commit()
    await db.refresh(yard)
    await publish_realtime_after_commit("yard.updated", data)
    logger.info("Обновлен двор: %s (ID: %s)", yard.name, yard.id)
    return yard


async def delete_yard(db: AsyncSession, yard_id: int) -> None:
    """Soft-delete (deactivate). Blocked while active buildings exist."""
    yard = await _get_yard_or_raise(db, yard_id)
    active = await _count_active_buildings(db, yard_id)
    if active > 0:
        raise AddressConflict(f"Невозможно удалить двор: есть {active} активных зданий")

    yard.is_active = False
    await db.flush()

    data = build_yard_event_data(yard)
    await enqueue_outbox(db, event="yard.deleted", data=data)
    await db.commit()
    await publish_realtime_after_commit("yard.deleted", data)
    logger.info("Деактивирован двор: %s (ID: %s)", yard.name, yard.id)


# ───────────────────────── Buildings ─────────────────────────

async def create_building(
    db: AsyncSession,
    *,
    address: str,
    yard_id: int,
    created_by: int,
    gps_latitude: float | None = None,
    gps_longitude: float | None = None,
    entrance_count: int = 1,
    floor_count: int = 1,
    description: str | None = None,
) -> Building:
    yard = await _get_yard_or_raise(db, yard_id)
    if not yard.is_active:
        raise AddressConflict("Двор неактивен", code="yard_inactive")

    building = Building(
        address=address,
        yard_id=yard_id,
        gps_latitude=gps_latitude,
        gps_longitude=gps_longitude,
        entrance_count=entrance_count,
        floor_count=floor_count,
        description=description,
        created_by=created_by,
        is_active=True,
    )
    db.add(building)
    await db.flush()

    data = build_building_event_data(building, yard_name=yard.name)
    await enqueue_outbox(db, event="building.created", data=data)
    await db.commit()
    await db.refresh(building)
    await publish_realtime_after_commit("building.created", data)
    logger.info("Создано здание: %s (ID: %s)", building.address, building.id)
    return building


async def update_building(db: AsyncSession, building_id: int, updates: dict) -> Building:
    building = await _get_building_or_raise(db, building_id)

    # Canonical guard: block deactivation while active apartments exist.
    if updates.get("is_active") is False and building.is_active:
        active = await _count_active_apartments(db, building_id)
        if active > 0:
            raise AddressConflict(
                f"Невозможно деактивировать здание: есть {active} активных квартир"
            )

    # Moving to another yard — target must exist and be active.
    if "yard_id" in updates and updates["yard_id"] != building.yard_id:
        target_yard = await _get_yard_or_raise(db, updates["yard_id"])
        if not target_yard.is_active:
            raise AddressConflict("Двор неактивен", code="yard_inactive")

    for field, value in updates.items():
        setattr(building, field, value)
    await db.flush()

    yard = await db.get(Yard, building.yard_id)
    data = build_building_event_data(building, yard_name=yard.name if yard else "")
    await enqueue_outbox(db, event="building.updated", data=data)
    await db.commit()
    await db.refresh(building)
    await publish_realtime_after_commit("building.updated", data)
    logger.info("Обновлено здание: %s (ID: %s)", building.address, building.id)
    return building


async def delete_building(db: AsyncSession, building_id: int) -> None:
    """Soft-delete (deactivate). Blocked while active apartments exist."""
    building = await _get_building_or_raise(db, building_id)
    active = await _count_active_apartments(db, building_id)
    if active > 0:
        raise AddressConflict(
            f"Невозможно удалить здание: есть {active} активных квартир"
        )

    building.is_active = False
    await db.flush()

    yard = await db.get(Yard, building.yard_id)
    data = build_building_event_data(building, yard_name=yard.name if yard else "")
    await enqueue_outbox(db, event="building.deleted", data=data)
    await db.commit()
    await publish_realtime_after_commit("building.deleted", data)
    logger.info("Деактивировано здание: %s (ID: %s)", building.address, building.id)


# ───────────────────────── Apartments ─────────────────────────

async def create_apartment(
    db: AsyncSession,
    *,
    building_id: int,
    apartment_number: str,
    created_by: int,
    entrance: int | None = None,
    floor: int | None = None,
    rooms_count: int | None = None,
    area: float | None = None,
    description: str | None = None,
) -> Apartment:
    building = await _get_building_or_raise(db, building_id)
    if not building.is_active:
        raise AddressConflict("Здание неактивно", code="building_inactive")

    clash = (await db.execute(
        select(Apartment.id).where(and_(
            Apartment.building_id == building_id,
            Apartment.apartment_number == apartment_number,
        ))
    )).scalar_one_or_none()
    if clash is not None:
        raise AddressConflict(
            f"Квартира {apartment_number} уже существует в этом здании"
        )

    apartment = Apartment(
        building_id=building_id,
        apartment_number=apartment_number,
        entrance=entrance,
        floor=floor,
        rooms_count=rooms_count,
        area=area,
        description=description,
        created_by=created_by,
        is_active=True,
    )
    db.add(apartment)
    await db.flush()

    data = build_apartment_event_data(apartment)
    await enqueue_outbox(db, event="apartment.created", data=data)
    await db.commit()
    await db.refresh(apartment)
    await publish_realtime_after_commit("apartment.created", data)
    logger.info("Создана квартира: %s в здании ID %s",
                apartment.apartment_number, building_id)
    return apartment


async def bulk_create_apartments(
    db: AsyncSession,
    *,
    building_id: int,
    apartment_numbers: list[str],
    created_by: int,
) -> tuple[int, int, list[str]]:
    """Create many apartments at once. Returns (created, skipped, errors).

    Canonical per-number validation (matches the API endpoint): each number is
    stripped, empties are rejected, numbers longer than 20 chars are rejected,
    already-existing numbers are skipped. No events are emitted (parity with
    both legacy paths).
    """
    building = await _get_building_or_raise(db, building_id)
    if not building.is_active:
        raise AddressConflict("Здание неактивно", code="building_inactive")

    existing = set((await db.execute(
        select(Apartment.apartment_number).where(Apartment.building_id == building_id)
    )).scalars().all())

    created = 0
    skipped = 0
    errors: list[str] = []

    for raw in apartment_numbers:
        number = raw.strip()
        if not number:
            errors.append("Пустой номер квартиры пропущен")
            continue
        if len(number) > _APARTMENT_NUMBER_MAX_LEN:
            errors.append(
                f"Номер квартиры '{number}' слишком длинный "
                f"(максимум {_APARTMENT_NUMBER_MAX_LEN} символов)"
            )
            continue
        if number in existing:
            skipped += 1
            continue
        db.add(Apartment(
            building_id=building_id,
            apartment_number=number,
            created_by=created_by,
            is_active=True,
        ))
        existing.add(number)
        created += 1

    if created > 0:
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            errors.append("Ошибка целостности БД при массовом создании")
            created = 0

    logger.info(
        "Массовое создание квартир в здании %s: создано %s, пропущено %s, ошибок %s",
        building_id, created, skipped, len(errors),
    )
    return created, skipped, errors


async def update_apartment(db: AsyncSession, apartment_id: int, updates: dict) -> Apartment:
    apartment = await _get_apartment_or_raise(db, apartment_id)

    # Canonical guard: block deactivation while approved residents exist.
    if updates.get("is_active") is False and apartment.is_active:
        approved = await _count_approved_residents(db, apartment_id)
        if approved > 0:
            raise AddressConflict(
                f"Невозможно деактивировать квартиру: "
                f"есть {approved} подтвержденных жителей"
            )

    target_building_id = updates.get("building_id", apartment.building_id)
    target_number = updates.get("apartment_number", apartment.apartment_number)

    # Moving to another building — target must exist and be active.
    if "building_id" in updates and updates["building_id"] != apartment.building_id:
        target_building = await _get_building_or_raise(db, updates["building_id"])
        if not target_building.is_active:
            raise AddressConflict("Здание неактивно", code="building_inactive")

    number_changed = "apartment_number" in updates and target_number != apartment.apartment_number
    building_changed = "building_id" in updates and target_building_id != apartment.building_id
    if number_changed or building_changed:
        clash = (await db.execute(
            select(Apartment.id).where(and_(
                Apartment.building_id == target_building_id,
                Apartment.apartment_number == target_number,
                Apartment.id != apartment_id,
            ))
        )).scalar_one_or_none()
        if clash is not None:
            raise AddressConflict(
                f"Квартира {target_number} уже существует в этом здании"
            )

    for field, value in updates.items():
        setattr(apartment, field, value)
    await db.flush()

    data = build_apartment_event_data(apartment)
    await enqueue_outbox(db, event="apartment.updated", data=data)
    await db.commit()
    await db.refresh(apartment)
    await publish_realtime_after_commit("apartment.updated", data)
    logger.info("Обновлена квартира: %s (ID: %s)",
                apartment.apartment_number, apartment.id)
    return apartment


async def delete_apartment(db: AsyncSession, apartment_id: int) -> None:
    """Soft-delete (deactivate). Blocked while approved residents exist."""
    apartment = await _get_apartment_or_raise(db, apartment_id)
    approved = await _count_approved_residents(db, apartment_id)
    if approved > 0:
        raise AddressConflict(
            f"Невозможно удалить квартиру: есть {approved} подтвержденных жителей"
        )

    apartment.is_active = False
    await db.flush()

    data = build_apartment_event_data(apartment)
    await enqueue_outbox(db, event="apartment.deleted", data=data)
    await db.commit()
    await publish_realtime_after_commit("apartment.deleted", data)
    logger.info("Деактивирована квартира: %s (ID: %s)",
                apartment.apartment_number, apartment.id)


# ───────────────────── User ↔ Apartment requests ─────────────────────

async def request_apartment(
    db: AsyncSession,
    *,
    user_id: int,
    apartment_id: int,
    is_owner: bool = False,
    is_primary: bool = True,
) -> UserApartment:
    """A resident requests a binding to an apartment (moderation: pending)."""
    apartment = await _get_apartment_or_raise(db, apartment_id)
    if not apartment.is_active:
        raise AddressConflict("Квартира неактивна", code="apartment_inactive")

    existing = (await db.execute(
        select(UserApartment).where(and_(
            UserApartment.user_id == user_id,
            UserApartment.apartment_id == apartment_id,
        ))
    )).scalar_one_or_none()
    if existing is not None:
        if existing.status == "pending":
            raise AddressConflict("Заявка уже отправлена и ожидает рассмотрения", code="request_already_pending")
        if existing.status == "approved":
            raise AddressConflict("Вы уже подтверждены как житель этой квартиры", code="already_resident")
        if existing.status == "rejected":
            raise AddressConflict(
                "Ваша предыдущая заявка была отклонена. Обратитесь к администратору."
            )

    ua = UserApartment(
        user_id=user_id,
        apartment_id=apartment_id,
        status="pending",
        is_owner=is_owner,
        is_primary=is_primary,
    )
    db.add(ua)
    await db.flush()

    data = build_apartment_event_data(apartment)
    await enqueue_outbox(db, event="apartment_request.created", data=data)
    await db.commit()
    await db.refresh(ua)
    await publish_realtime_after_commit("apartment_request.created", data)
    logger.info("Пользователь %s запросил квартиру %s", user_id, apartment_id)
    return ua


async def approve_apartment_request(
    db: AsyncSession,
    *,
    user_apartment_id: int,
    reviewer_id: int,
    comment: str | None = None,
) -> UserApartment:
    ua = await _get_user_apartment_or_raise(db, user_apartment_id)
    if ua.status != "pending":
        raise AddressConflict(f"Заявка уже обработана (статус: {ua.status})")

    ua.approve(reviewer_id, comment)
    await db.flush()

    apartment = await db.get(Apartment, ua.apartment_id)
    data = build_apartment_event_data(apartment) if apartment else {"id": ua.apartment_id}
    await enqueue_outbox(db, event="apartment_request.approved", data=data)
    await db.commit()
    await db.refresh(ua)
    await publish_realtime_after_commit("apartment_request.approved", data)
    logger.info("Заявка %s подтверждена администратором %s",
                user_apartment_id, reviewer_id)
    return ua


async def reject_apartment_request(
    db: AsyncSession,
    *,
    user_apartment_id: int,
    reviewer_id: int,
    comment: str | None = None,
) -> UserApartment:
    ua = await _get_user_apartment_or_raise(db, user_apartment_id)
    if ua.status != "pending":
        raise AddressConflict(f"Заявка уже обработана (статус: {ua.status})")

    ua.reject(reviewer_id, comment)
    await db.flush()

    apartment = await db.get(Apartment, ua.apartment_id)
    data = build_apartment_event_data(apartment) if apartment else {"id": ua.apartment_id}
    await enqueue_outbox(db, event="apartment_request.rejected", data=data)
    await db.commit()
    await db.refresh(ua)
    await publish_realtime_after_commit("apartment_request.rejected", data)
    logger.info("Заявка %s отклонена администратором %s",
                user_apartment_id, reviewer_id)
    return ua


async def remove_user_from_apartment(db: AsyncSession, *, user_apartment_id: int) -> None:
    """Hard-delete a user↔apartment link. No event emitted (parity with legacy)."""
    ua = await _get_user_apartment_or_raise(db, user_apartment_id)
    user_id, apartment_id = ua.user_id, ua.apartment_id
    await db.delete(ua)
    await db.commit()
    logger.info("Удалена связь: пользователь %s → квартира %s", user_id, apartment_id)
