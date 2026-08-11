import logging
from aiogram import F
from aiogram.types import CallbackQuery

from uk_management_bot.database.session import session_scope
from uk_management_bot.services.address_service import AddressService
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.keyboards.address_management import get_apartment_details_keyboard

from ._router import router

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР ДЕТАЛЬНОЙ ИНФОРМАЦИИ О КВАРТИРЕ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_apartment_view:"))
async def show_apartment_details(callback: CallbackQuery, language: str = "ru"):
    """Показать детальную информацию о квартире"""
    apartment_id = int(callback.data.split(":")[1])
    lang = language

    try:
        with session_scope() as db:
            apartment = AddressService.get_apartment_by_id(db, apartment_id, include_building=True)

            if not apartment:
                await callback.answer(get_text("address_apartments.handlers.apartment_not_found", language=lang), show_alert=True)
                return

            status_text = get_text("apartment.active_status", language=lang) if apartment.is_active else get_text("apartment.inactive_status", language=lang)
            residents_count = apartment.residents_count if hasattr(apartment, 'residents_count') else 0
            pending_count = apartment.pending_requests_count if hasattr(apartment, 'pending_requests_count') else 0

            # MGR-08: локаль `apartment.details_title` уже содержит 🏠 — не дублируем эмодзи в шаблоне.
            text = f"<b>{get_text('apartment.details_title', language=lang).format(number=apartment.apartment_number)}</b>\n\n"

            if apartment.building:
                text += f"<b>{get_text('apartment.address_label', language=lang)}</b> {apartment.building.address}\n"
                if apartment.building.yard:
                    text += f"<b>{get_text('apartment.yard_label', language=lang)}</b> {apartment.building.yard.name}\n"

            text += f"<b>{get_text('apartment.status_label', language=lang)}</b> {status_text}\n\n"

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
async def show_apartment_residents(callback: CallbackQuery, language: str = "ru"):
    """Показать список жителей квартиры"""
    apartment_id = int(callback.data.split(":")[1])
    lang = language

    try:
        with session_scope() as db:
            apartment = AddressService.get_apartment_by_id(db, apartment_id, include_building=True)
            if not apartment:
                await callback.answer(get_text("address_apartments.handlers.apartment_not_found", language=lang), show_alert=True)
                return

            residents = AddressService.get_apartment_residents(db, apartment_id, only_approved=False)

            text = get_text("address_apartments.handlers.residents_title", language=lang).format(
                number=apartment.apartment_number
            ) + "\n\n"

            if apartment.building:
                text += f"<b>{get_text('address_apartments.handlers.address_label', language=lang)}</b> {apartment.building.address}\n\n"

            if not residents:
                text += get_text("address_apartments.handlers.residents_list_empty", language=lang)
            else:
                approved = [r for r in residents if r.status == 'approved']
                pending = [r for r in residents if r.status == 'pending']
                rejected = [r for r in residents if r.status == 'rejected']

                if approved:
                    text += get_text("address_apartments.handlers.residents_approved", language=lang) + "\n"
                    for r in approved:
                        user_name = f"{r.user.first_name or ''} {r.user.last_name or ''}".strip() or f"ID: {r.user.telegram_id}"
                        owner_mark = " 👑" if r.is_owner else ""
                        primary_mark = " ⭐" if r.is_primary else ""
                        text += f"• {user_name}{owner_mark}{primary_mark}\n"
                    text += "\n"

                if pending:
                    text += get_text("address_apartments.handlers.residents_pending", language=lang).format(count=len(pending)) + "\n"
                    for r in pending:
                        user_name = f"{r.user.first_name or ''} {r.user.last_name or ''}".strip() or f"ID: {r.user.telegram_id}"
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
