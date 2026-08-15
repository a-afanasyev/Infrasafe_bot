import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from aiogram import F
from aiogram.types import CallbackQuery

from uk_management_bot.database.session import run_db
from uk_management_bot.services.address_service import AddressService
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.keyboards.address_management import get_apartment_details_keyboard

from ._router import router

logger = logging.getLogger(__name__)


# ==========================================================================
# DTO для async-слоя: наружу из run_db выходят примитивы, не ORM-строки
# (lazy-связи building/yard/user за пределами worker-потока дали бы
# DetachedInstanceError).
# ==========================================================================

@dataclass(frozen=True)
class _ApartmentCard:
    """Карточка квартиры. ``building_address is None`` ⇔ здания нет
    (эквивалент прежнего ``if apartment.building``)."""
    is_active: bool
    apartment_number: str
    building_address: Optional[str]
    yard_name: Optional[str]
    entrance: Optional[int]
    floor: Optional[int]
    rooms_count: Optional[int]
    area: Optional[float]
    residents_count: int
    pending_count: int
    description: Optional[str]
    created_at: Optional[datetime]


@dataclass(frozen=True)
class _ResidentRow:
    """Житель квартиры для списка (UserApartment + его User)."""
    status: str
    first_name: Optional[str]
    last_name: Optional[str]
    telegram_id: Optional[int]
    is_owner: bool
    is_primary: bool


@dataclass(frozen=True)
class _ResidentsView:
    """Шапка списка жителей + сами жители."""
    apartment_number: str
    building_address: Optional[str]
    residents: list


# ==========================================================================
# Sync unit-of-work (AUD3-07/AUD5-ARCH-1): исполняются в worker-потоке через
# run_db; сессию открывает и закрывает run_db, event loop БД не трогает.
# ==========================================================================

def _load_apartment_card(db, apartment_id: int) -> Optional[_ApartmentCard]:
    """-> _ApartmentCard | None (None — квартира не найдена)."""
    apartment = AddressService.get_apartment_by_id(db, apartment_id, include_building=True)

    if not apartment:
        return None

    building = apartment.building
    return _ApartmentCard(
        is_active=apartment.is_active,
        apartment_number=apartment.apartment_number,
        building_address=building.address if building else None,
        yard_name=(building.yard.name if building.yard else None) if building else None,
        entrance=apartment.entrance,
        floor=apartment.floor,
        rooms_count=apartment.rooms_count,
        area=apartment.area,
        residents_count=apartment.residents_count if hasattr(apartment, 'residents_count') else 0,
        pending_count=apartment.pending_requests_count if hasattr(apartment, 'pending_requests_count') else 0,
        description=apartment.description,
        created_at=apartment.created_at,
    )


def _load_apartment_residents(db, apartment_id: int) -> Optional[_ResidentsView]:
    """-> _ResidentsView | None (None — квартира не найдена)."""
    apartment = AddressService.get_apartment_by_id(db, apartment_id, include_building=True)
    if not apartment:
        return None

    residents = AddressService.get_apartment_residents(db, apartment_id, only_approved=False)

    building = apartment.building
    return _ResidentsView(
        apartment_number=apartment.apartment_number,
        building_address=building.address if building else None,
        residents=[
            _ResidentRow(
                status=r.status,
                first_name=r.user.first_name,
                last_name=r.user.last_name,
                telegram_id=r.user.telegram_id,
                is_owner=r.is_owner,
                is_primary=r.is_primary,
            )
            for r in residents
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР ДЕТАЛЬНОЙ ИНФОРМАЦИИ О КВАРТИРЕ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_apartment_view:"))
async def show_apartment_details(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Показать детальную информацию о квартире"""
    apartment_id = int(callback.data.split(":")[1])
    lang = language

    try:
        apartment = await run_db(lambda s: _load_apartment_card(s, apartment_id), db=_db)

        if not apartment:
            await callback.answer(get_text("address_apartments.handlers.apartment_not_found", language=lang), show_alert=True)
            return

        status_text = get_text("apartment.active_status", language=lang) if apartment.is_active else get_text("apartment.inactive_status", language=lang)
        residents_count = apartment.residents_count
        pending_count = apartment.pending_count

        # MGR-08: локаль `apartment.details_title` уже содержит 🏠 — не дублируем эмодзи в шаблоне.
        text = f"<b>{get_text('apartment.details_title', language=lang).format(number=apartment.apartment_number)}</b>\n\n"

        if apartment.building_address is not None:
            text += f"<b>{get_text('apartment.address_label', language=lang)}</b> {apartment.building_address}\n"
            if apartment.yard_name:
                text += f"<b>{get_text('apartment.yard_label', language=lang)}</b> {apartment.yard_name}\n"

        text += f"<b>{get_text('apartment.status_label', language=lang)}</b> {status_text}\n\n"

        # ⚠️ Предсуществующий дефект (сохранён 1:1): falsy-0 — подъезд/этаж/
        # комнаты/площадь со значением 0 не показываются вовсе (ветка `if`
        # проверяет истинность, а не «поле задано»).
        if apartment.entrance:
            text += f"<b>{get_text('apartment.entrance_label', language=lang)}</b> {apartment.entrance}\n"
        if apartment.floor:
            text += f"<b>{get_text('apartment.floor_label', language=lang)}</b> {apartment.floor}\n"
        if apartment.rooms_count:
            text += f"<b>{get_text('apartment.rooms_label', language=lang)}</b> {apartment.rooms_count}\n"
        if apartment.area:
            text += f"<b>{get_text('apartment.area_label', language=lang)}</b> {apartment.area} {get_text('address_apartments.handlers.sqm', language=lang)}\n"

        text += f"\n<b>{get_text('apartment.residents_label', language=lang)}</b> {residents_count}\n"

        if pending_count > 0:
            text += f"<b>{get_text('apartment.pending_requests_label', language=lang)}</b> {pending_count}\n"

        if apartment.description:
            text += f"\n<b>{get_text('apartment.description_label', language=lang)}</b>\n{apartment.description}\n"

        if apartment.created_at:
            text += f"\n<b>{get_text('apartment.created_label', language=lang)}</b> {apartment.created_at.strftime('%d.%m.%Y %H:%M')}"

        # ⚠️ Предсуществующий дефект (сохранён 1:1): language не пробрасывается
        # в клавиатуру карточки — её подписи всегда на ru.
        await callback.message.edit_text(
            text,
            reply_markup=get_apartment_details_keyboard(apartment_id)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке информации о квартире {apartment_id}: {e}")
        await callback.answer(get_text("address_apartments.handlers.error_loading_data", language=lang), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР ЖИТЕЛЕЙ КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_apartment_residents:"))
async def show_apartment_residents(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Показать список жителей квартиры"""
    apartment_id = int(callback.data.split(":")[1])
    lang = language

    try:
        view = await run_db(lambda s: _load_apartment_residents(s, apartment_id), db=_db)
        if view is None:
            await callback.answer(get_text("address_apartments.handlers.apartment_not_found", language=lang), show_alert=True)
            return

        residents = view.residents

        text = get_text("address_apartments.handlers.residents_title", language=lang).format(
            number=view.apartment_number
        ) + "\n\n"

        if view.building_address is not None:
            text += f"<b>{get_text('address_apartments.handlers.address_label', language=lang)}</b> {view.building_address}\n\n"

        if not residents:
            text += get_text("address_apartments.handlers.residents_list_empty", language=lang)
        else:
            approved = [r for r in residents if r.status == 'approved']
            pending = [r for r in residents if r.status == 'pending']
            rejected = [r for r in residents if r.status == 'rejected']

            if approved:
                text += get_text("address_apartments.handlers.residents_approved", language=lang) + "\n"
                for r in approved:
                    user_name = f"{r.first_name or ''} {r.last_name or ''}".strip() or f"ID: {r.telegram_id}"
                    owner_mark = " 👑" if r.is_owner else ""
                    primary_mark = " ⭐" if r.is_primary else ""
                    text += f"• {user_name}{owner_mark}{primary_mark}\n"
                text += "\n"

            if pending:
                text += get_text("address_apartments.handlers.residents_pending", language=lang).format(count=len(pending)) + "\n"
                for r in pending:
                    user_name = f"{r.first_name or ''} {r.last_name or ''}".strip() or f"ID: {r.telegram_id}"
                    text += f"• {user_name}\n"
                text += "\n"

            if rejected:
                text += get_text("address_apartments.handlers.residents_rejected", language=lang).format(count=len(rejected)) + "\n"

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text=get_text("address_apartments.handlers.back_to_apartment", language=lang),
                callback_data=f"addr_apartment_view:{apartment_id}"
            )
        ]])

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка при загрузке жителей квартиры {apartment_id}: {e}")
        await callback.answer(get_text("address_apartments.handlers.error_loading_data", language=lang), show_alert=True)
