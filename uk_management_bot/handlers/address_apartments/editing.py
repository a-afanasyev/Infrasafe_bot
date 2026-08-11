import logging
from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from uk_management_bot.database.session import session_scope
from uk_management_bot.services.address_service import AddressService
from uk_management_bot.states.address_management import ApartmentManagementStates
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.address_helpers import apartment_address
from uk_management_bot.keyboards.address_management import (
    get_apartment_edit_keyboard,
    get_confirmation_keyboard
)
from uk_management_bot.keyboards.base import get_cancel_keyboard
from uk_management_bot.keyboards.base import get_main_keyboard_for_role

from ._router import router
from .details import show_apartment_details
from .viewing import show_apartments_list

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# РЕДАКТИРОВАНИЕ КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_apartment_edit:"))
async def show_apartment_edit_menu(callback: CallbackQuery, language: str = "ru"):
    """Показать меню редактирования квартиры"""
    apartment_id = int(callback.data.split(":")[1])
    lang = language

    await callback.message.edit_text(
        get_text("address_apartments.handlers.edit_menu", language=lang),
        reply_markup=get_apartment_edit_keyboard(apartment_id)
    )


@router.callback_query(F.data.startswith("addr_apartment_toggle:"))
async def toggle_apartment_status(callback: CallbackQuery, language: str = "ru"):
    """Переключить активность квартиры"""
    apartment_id = int(callback.data.split(":")[1])
    lang = language

    try:
        with session_scope() as db:
            apartment = AddressService.get_apartment_by_id(db, apartment_id)
            if not apartment:
                await callback.answer(get_text("address_apartments.handlers.apartment_not_found", language=lang), show_alert=True)
                return

            new_status = not apartment.is_active
            apartment, error = await AddressService.update_apartment(
                session=db,
                apartment_id=apartment_id,
                is_active=new_status
            )

            if error:
                await callback.answer(get_text("address_apartments.handlers.error_with_details", language=lang).format(error=error), show_alert=True)
                return

            status_text = get_text("address_apartments.handlers.status_activated", language=lang) if new_status else get_text("address_apartments.handlers.status_deactivated", language=lang)
            await callback.answer(get_text("address_apartments.handlers.apartment_status_changed", language=lang).format(status=status_text))

            # Обновляем отображение
            await show_apartment_details(callback)

    except Exception as e:
        logger.error(f"Ошибка при переключении статуса квартиры: {e}")
        await callback.answer(get_text("address_apartments.handlers.error_status_change", language=lang), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# УДАЛЕНИЕ КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_apartment_delete:"))
async def confirm_apartment_deletion(callback: CallbackQuery, language: str = "ru"):
    """Подтверждение удаления квартиры"""
    apartment_id = int(callback.data.split(":")[1])
    lang = language

    try:
        with session_scope() as db:
            apartment = AddressService.get_apartment_by_id(db, apartment_id, include_building=True)
            if not apartment:
                await callback.answer(get_text("address_apartments.handlers.apartment_not_found", language=lang), show_alert=True)
                return

            residents_count = apartment.residents_count if hasattr(apartment, 'residents_count') else 0

            warning = ""
            if residents_count > 0:
                warning = "\n\n" + get_text("address_apartments.handlers.delete_warning_residents", language=lang).format(count=residents_count)

            full_address = apartment_address(apartment, lang)

            await callback.message.edit_text(
                get_text("address_apartments.handlers.delete_confirm", language=lang).format(
                    address=full_address
                ) + warning,
                reply_markup=get_confirmation_keyboard(
                    confirm_callback=f"addr_apartment_delete_confirm:{apartment_id}",
                    cancel_callback=f"addr_apartment_view:{apartment_id}"
                )
            )

    except Exception as e:
        logger.error(f"Ошибка при подготовке удаления квартиры: {e}")
        await callback.answer(get_text("address_apartments.handlers.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("addr_apartment_delete_confirm:"))
async def delete_apartment(callback: CallbackQuery, language: str = "ru"):
    """Удаление квартиры"""
    apartment_id = int(callback.data.split(":")[1])
    lang = language

    try:
        with session_scope() as db:
            success, error = await AddressService.delete_apartment(db, apartment_id)

            if not success:
                await callback.answer(get_text("address_apartments.handlers.delete_error", language=lang).format(error=error), show_alert=True)
                return

            await callback.message.edit_text(
                get_text("address_apartments.handlers.delete_success", language=lang)
            )

            logger.info(f"Квартира {apartment_id} удалена пользователем {callback.from_user.id}")

            # Показываем список квартир
            await show_apartments_list(callback, None)

    except Exception as e:
        logger.error(f"Ошибка при удалении квартиры: {e}")
        await callback.answer(get_text("address_apartments.handlers.error_deletion", language=lang), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# РЕДАКТИРОВАНИЕ ПОЛЕЙ КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_apartment_edit_area:"))
async def start_edit_apartment_area(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Начать редактирование площади квартиры"""
    apartment_id = int(callback.data.split(":")[1])
    lang = language

    await state.update_data(editing_apartment_id=apartment_id)
    await state.set_state(ApartmentManagementStates.waiting_for_new_area)

    await callback.message.answer(
        get_text("address_apartments.handlers.edit_area_prompt", language=lang),
        reply_markup=get_cancel_keyboard(language=lang)
    )
    await callback.answer()


@router.message(StateFilter(ApartmentManagementStates.waiting_for_new_area))
async def process_new_apartment_area(message: Message, state: FSMContext, language: str = "ru"):
    """Обработка новой площади квартиры"""
    lang = language
    cancel_text = get_text("buttons.cancel", language=lang)
    if message.text == cancel_text:
        data = await state.get_data()
        apartment_id = data.get('editing_apartment_id')
        await state.clear()

        if apartment_id:
            # Возвращаемся к меню редактирования
            keyboard = get_apartment_edit_keyboard(apartment_id)
            await message.answer(
                get_text("address_apartments.handlers.edit_menu", language=lang),
                reply_markup=keyboard
            )
        return

    try:
        area = float(message.text.strip().replace(',', '.'))
        if area <= 0 or area > 1000:
            raise ValueError("Площадь вне допустимого диапазона")
    except ValueError:
        await message.answer(
            get_text("address_apartments.handlers.invalid_area_format", language=lang)
        )
        return

    data = await state.get_data()
    apartment_id = data.get('editing_apartment_id')

    if not apartment_id:
        await message.answer(get_text("address_apartments.handlers.apartment_not_found", language=lang))
        await state.clear()
        return

    try:
        with session_scope() as db:
            apartment, error = await AddressService.update_apartment(
                session=db,
                apartment_id=apartment_id,
                area=area
            )

            if error:
                await message.answer(
                    get_text("address_apartments.handlers.area_update_error", language=lang).format(error=error),
                    reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
                )
                await state.clear()
                return

            await message.answer(
                get_text("address_apartments.handlers.area_update_success", language=lang).format(area=area),
                reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
            )

            logger.info(f"Площадь квартиры {apartment_id} обновлена на {area} кв.м пользователем {message.from_user.id}")

    except Exception:
        logger.exception("update apartment area handler failed")
        await message.answer(
            get_text("address_apartments.handlers.area_update_exception", language=lang),
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
        )
    finally:
        await state.clear()
