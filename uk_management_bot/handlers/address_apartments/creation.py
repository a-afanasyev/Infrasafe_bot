import logging
from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from uk_management_bot.database.session import session_scope
from uk_management_bot.services.address_service import AddressService
from uk_management_bot.states.address_management import ApartmentManagementStates
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.keyboards.address_management import (
    get_user_apartment_selection_keyboard,
    get_skip_or_cancel_keyboard,
    get_cancel_keyboard_inline,
    get_address_management_menu
)
from uk_management_bot.keyboards.base import get_main_keyboard_for_role

from ._router import router

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# СОЗДАНИЕ НОВОЙ КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "addr_apartment_create")
async def start_apartment_creation(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Начать создание новой квартиры - выбор здания"""
    await state.clear()
    lang = language

    try:
        with session_scope() as db:
            from uk_management_bot.database.models import Building
            from sqlalchemy import select

            result = db.execute(
                select(Building)
                .where(Building.is_active.is_(True))
                .order_by(Building.address)
                .limit(50)
            )
            buildings = result.scalars().all()

            if not buildings:
                await callback.message.edit_text(
                    get_text("address_apartments.handlers.create_no_buildings", language=lang),
                    reply_markup=get_cancel_keyboard_inline()
                )
                return

            await state.set_state(ApartmentManagementStates.waiting_for_building_selection)

            await callback.message.edit_text(
                get_text("address_apartments.handlers.create_step1_select_building", language=lang),
                reply_markup=get_user_apartment_selection_keyboard(buildings, "building", "apartment_create_building")
            )

    except Exception as e:
        logger.error(f"Ошибка при начале создания квартиры: {e}")
        await callback.answer(get_text("address_apartments.handlers.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("apartment_create_building:"))
async def process_apartment_building_selection(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Обработка выбора здания для новой квартиры"""
    building_id = int(callback.data.split(":")[1])
    lang = language

    await state.update_data(building_id=building_id)
    await state.set_state(ApartmentManagementStates.waiting_for_apartment_number)

    with session_scope() as db:
        building = AddressService.get_building_by_id(db, building_id)
        building_addr = building.address if building else get_text("address_apartments.handlers.unknown_building", language=lang)

        await callback.message.edit_text(
            get_text("address_apartments.handlers.create_step2_enter_number", language=lang).format(address=building_addr),
            reply_markup=get_cancel_keyboard_inline()
        )


@router.message(StateFilter(ApartmentManagementStates.waiting_for_apartment_number))
async def process_apartment_number(message: Message, state: FSMContext, language: str = "ru"):
    """Обработка номера квартиры"""
    lang = language
    number = message.text.strip()

    if len(number) < 1 or len(number) > 20:
        await message.answer(
            get_text("address_apartments.handlers.invalid_apartment_number", language=lang)
        )
        return

    await state.update_data(apartment_number=number)
    await state.set_state(ApartmentManagementStates.waiting_for_entrance_number)

    await message.answer(
        get_text("address_apartments.handlers.create_step3_enter_entrance", language=lang).format(number=number),
        reply_markup=get_skip_or_cancel_keyboard()
    )


@router.message(StateFilter(ApartmentManagementStates.waiting_for_entrance_number))
async def process_apartment_entrance(message: Message, state: FSMContext, language: str = "ru",
                                     roles: list = None, active_role: str = None):
    """Обработка номера подъезда"""
    lang = language
    skip_text = get_text("address.keyboards.skip", language=lang)
    cancel_text = get_text("address.keyboards.cancel", language=lang)
    if message.text == skip_text:
        entrance = None
    elif message.text == cancel_text:
        await state.clear()
        await message.answer(
            get_text("address_apartments.handlers.creation_cancelled", language=lang),
            reply_markup=get_main_keyboard_for_role(active_role or "manager", roles or ["manager"], language=lang)
        )
        return
    else:
        try:
            entrance = int(message.text.strip())
            if entrance < 1 or entrance > 50:
                raise ValueError("Entrance number out of range")
        except ValueError:
            await message.answer(
                get_text("address_apartments.handlers.invalid_entrance", language=lang)
            )
            return

    await state.update_data(entrance=entrance)
    await state.set_state(ApartmentManagementStates.waiting_for_floor_number)

    entrance_text = f"<b>{entrance}</b>" if entrance else get_text("address_apartments.handlers.not_specified", language=lang)
    await message.answer(
        get_text("address_apartments.handlers.create_step4_enter_floor", language=lang).format(entrance=entrance_text),
        reply_markup=get_skip_or_cancel_keyboard()
    )


@router.message(StateFilter(ApartmentManagementStates.waiting_for_floor_number))
async def process_apartment_floor(message: Message, state: FSMContext, language: str = "ru",
                                  roles: list = None, active_role: str = None):
    """Обработка номера этажа"""
    lang = language
    skip_text = get_text("address.keyboards.skip", language=lang)
    cancel_text = get_text("address.keyboards.cancel", language=lang)
    if message.text == skip_text:
        floor = None
    elif message.text == cancel_text:
        await state.clear()
        await message.answer(
            get_text("address_apartments.handlers.creation_cancelled", language=lang),
            reply_markup=get_main_keyboard_for_role(active_role or "manager", roles or ["manager"], language=lang)
        )
        return
    else:
        try:
            floor = int(message.text.strip())
            if floor < 1 or floor > 100:
                raise ValueError("Floor number out of range")
        except ValueError:
            await message.answer(
                get_text("address_apartments.handlers.invalid_floor", language=lang)
            )
            return

    await state.update_data(floor=floor)
    await state.set_state(ApartmentManagementStates.waiting_for_rooms_count)

    floor_text = f"<b>{floor}</b>" if floor else get_text("address_apartments.handlers.not_specified", language=lang)
    await message.answer(
        get_text("address_apartments.handlers.create_step5_enter_rooms", language=lang).format(floor=floor_text),
        reply_markup=get_skip_or_cancel_keyboard()
    )


@router.message(StateFilter(ApartmentManagementStates.waiting_for_rooms_count))
async def process_apartment_rooms(message: Message, state: FSMContext, language: str = "ru",
                                  roles: list = None, active_role: str = None):
    """Обработка количества комнат и переход к вводу площади"""
    lang = language
    skip_text = get_text("address.keyboards.skip", language=lang)
    cancel_text = get_text("address.keyboards.cancel", language=lang)
    if message.text == skip_text:
        rooms_count = None
    elif message.text == cancel_text:
        await state.clear()
        await message.answer(
            get_text("address_apartments.handlers.creation_cancelled", language=lang),
            reply_markup=get_main_keyboard_for_role(active_role or "manager", roles or ["manager"], language=lang)
        )
        return
    else:
        try:
            rooms_count = int(message.text.strip())
            if rooms_count < 1 or rooms_count > 20:
                raise ValueError("Rooms count out of range")
        except ValueError:
            await message.answer(
                get_text("address_apartments.handlers.invalid_rooms", language=lang)
            )
            return

    await state.update_data(rooms_count=rooms_count)
    await state.set_state(ApartmentManagementStates.waiting_for_area)

    rooms_text = f"<b>{rooms_count}</b>" if rooms_count else get_text("address_apartments.handlers.not_specified_neuter", language=lang)
    await message.answer(
        get_text("address_apartments.handlers.create_step6_enter_area", language=lang).format(rooms=rooms_text),
        reply_markup=get_skip_or_cancel_keyboard()
    )


@router.message(StateFilter(ApartmentManagementStates.waiting_for_area))
async def process_apartment_area(message: Message, state: FSMContext, language: str = "ru",
                                 roles: list = None, active_role: str = None):
    """Обработка площади квартиры и создание квартиры"""
    lang = language
    skip_text = get_text("address.keyboards.skip", language=lang)
    cancel_text = get_text("address.keyboards.cancel", language=lang)
    if message.text == skip_text:
        area = None
    elif message.text == cancel_text:
        await state.clear()
        await message.answer(
            get_text("address_apartments.handlers.creation_cancelled", language=lang),
            reply_markup=get_main_keyboard_for_role(active_role or "manager", roles or ["manager"], language=lang)
        )
        return
    else:
        try:
            area = float(message.text.strip().replace(',', '.'))
            if area <= 0 or area > 1000:
                raise ValueError("Area out of range")
        except ValueError:
            await message.answer(
                get_text("address_apartments.handlers.invalid_area", language=lang)
            )
            return

    # Сохраняем квартиру в базу
    data = await state.get_data()

    try:
        with session_scope() as db:
            # Получаем user.id из базы данных (не telegram_id!)
            from uk_management_bot.database.models.user import User
            user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
            if not user:
                await message.answer(
                    get_text("address_apartments.handlers.user_not_found", language=lang),
                    reply_markup=get_main_keyboard_for_role(active_role or "manager", roles or ["manager"], language=lang)
                )
                await state.clear()
                return

            apartment, error = await AddressService.create_apartment(
                session=db,
                building_id=data['building_id'],
                apartment_number=data['apartment_number'],
                created_by=user.id,  # ИСПРАВЛЕНО: используем user.id из БД, а не telegram_id
                entrance=data.get('entrance'),
                floor=data.get('floor'),
                rooms_count=data.get('rooms_count'),
                area=area  # ДОБАВЛЕНО: передаём площадь
            )

            if error:
                await message.answer(
                    get_text("address_apartments.handlers.creation_error", language=lang).format(error=error),
                    reply_markup=get_main_keyboard_for_role(active_role or "manager", roles or ["manager"], language=lang)
                )
                await state.clear()
                return

            text = get_text("address_apartments.handlers.creation_success", language=lang).format(
                number=apartment.apartment_number
            )

            if apartment.entrance:
                text += get_text("address_apartments.handlers.detail_entrance", language=lang).format(value=apartment.entrance)
            if apartment.floor:
                text += get_text("address_apartments.handlers.detail_floor", language=lang).format(value=apartment.floor)
            if apartment.rooms_count:
                text += get_text("address_apartments.handlers.detail_rooms", language=lang).format(value=apartment.rooms_count)
            if apartment.area:
                text += get_text("address_apartments.handlers.detail_area", language=lang).format(value=apartment.area)

            text += "\n" + get_text("address_apartments.handlers.select_action", language=lang)

            await message.answer(
                text,
                reply_markup=get_address_management_menu()
            )

            logger.info(f"Создана новая квартира: {apartment.apartment_number} (ID: {apartment.id}) пользователем {message.from_user.id}")

    except Exception:
        logger.exception("create apartment handler failed")
        await message.answer(
            get_text("address_apartments.handlers.creation_exception", language=lang),
            reply_markup=get_main_keyboard_for_role(active_role or "manager", roles or ["manager"], language=lang)
        )
    finally:
        await state.clear()
