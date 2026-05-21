"""
Обработчики для управления квартирами (Apartment Management)

Функционал:
- Просмотр списка квартир
- Создание новой квартиры
- Просмотр детальной информации о квартире
- Редактирование квартиры
- Удаление (деактивация) квартиры
- Поиск квартир по номеру или адресу
- Просмотр жителей квартиры
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from uk_management_bot.database.session import get_db
from uk_management_bot.services.address_service import AddressService
from uk_management_bot.states.address_management import ApartmentManagementStates
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.keyboards.address_management import (
    get_apartments_list_keyboard,
    get_apartment_details_keyboard,
    get_apartment_edit_keyboard,
    get_apartments_menu,
    get_confirmation_keyboard,
    get_skip_or_cancel_keyboard,
    get_cancel_keyboard_inline,
    get_user_apartment_selection_keyboard,
    get_address_management_menu
)
from uk_management_bot.keyboards.base import get_cancel_keyboard
from uk_management_bot.keyboards.base import get_main_keyboard_for_role

logger = logging.getLogger(__name__)

router = Router()


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР СПИСКА КВАРТИР
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "addr_apartments_list")
async def show_apartments_list(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Показать выбор здания для просмотра квартир"""
    await state.clear()
    lang = language

    db = next(get_db())
    try:
        from uk_management_bot.database.models import Building
        from sqlalchemy import select, func
        from sqlalchemy.orm import joinedload

        # Получаем все здания с количеством квартир
        result = db.execute(
            select(Building)
            .options(joinedload(Building.yard))
            .where(Building.is_active == True)
            .order_by(Building.address)
        )
        buildings = result.unique().scalars().all()

        if not buildings:
            await callback.message.edit_text(
                get_text("address_apartments.handlers.no_buildings", language=lang),
                reply_markup=get_apartments_menu(language=lang)
            )
            return

        # Считаем количество квартир для каждого здания
        from uk_management_bot.database.models import Apartment
        apartments_counts = {}
        for building in buildings:
            apartments_count = db.execute(
                select(func.count(Apartment.id))
                .where(Apartment.building_id == building.id)
                .where(Apartment.is_active == True)
            ).scalar()
            apartments_counts[building.id] = apartments_count

        text = get_text("address_apartments.handlers.select_building", language=lang).format(
            total=len(buildings)
        )

        # Используем клавиатуру со списком зданий
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton

        builder = InlineKeyboardBuilder()

        apt_suffix = get_text("address_apartments.handlers.apt_suffix", language=lang)

        # Добавляем кнопки для каждого здания
        for building in buildings:
            yard_info = f" ({building.yard.name})" if building.yard else ""
            apt_count = apartments_counts.get(building.id, 0)
            apartments_info = f" - {apt_count} {apt_suffix}" if apt_count > 0 else ""

            # Обрезаем длинный адрес
            address_short = building.address[:50] + "..." if len(building.address) > 50 else building.address

            builder.row(
                InlineKeyboardButton(
                    text=f"{address_short}{yard_info}{apartments_info}",
                    callback_data=f"addr_apartments_by_building:{building.id}"
                )
            )

        # Добавляем кнопки управления
        builder.row(
            InlineKeyboardButton(text=get_text("address_apartments.handlers.btn_add_apartment", language=lang), callback_data="addr_apartment_create")
        )
        builder.row(
            InlineKeyboardButton(text=get_text("address_apartments.handlers.btn_search_apartment", language=lang), callback_data="addr_apartment_search")
        )
        builder.row(
            InlineKeyboardButton(text=get_text("address_apartments.handlers.btn_back", language=lang), callback_data="addr_menu")
        )

        await callback.message.edit_text(
            text,
            reply_markup=builder.as_markup()
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке списка зданий для квартир: {e}")
        await callback.answer(get_text("address_apartments.handlers.error_loading_data", language=lang), show_alert=True)
    finally:
        db.close()


@router.callback_query(F.data.startswith("addr_apartments_by_building:"))
async def show_apartments_by_building(callback: CallbackQuery, language: str = "ru"):
    """Показать квартиры конкретного здания"""
    building_id = int(callback.data.split(":")[1])
    lang = language

    db = next(get_db())
    try:
        building = await AddressService.get_building_by_id(db, building_id, include_yard=True)
        if not building:
            await callback.answer(get_text("address_apartments.handlers.building_not_found", language=lang), show_alert=True)
            return

        apartments = await AddressService.get_apartments_by_building(db, building_id, only_active=False)

        text = get_text("address_apartments.handlers.building_apartments", language=lang).format(
            address=building.address,
            total=len(apartments)
        )

        if not apartments:
            text += "\n" + get_text("address_apartments.handlers.apartments_list_empty", language=lang)

        await callback.message.edit_text(
            text,
            reply_markup=get_apartments_list_keyboard(apartments, page=0, building_id=building_id)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке квартир здания {building_id}: {e}")
        await callback.answer(get_text("address_apartments.handlers.error_loading_data", language=lang), show_alert=True)
    finally:
        db.close()


@router.callback_query(F.data.startswith("addr_apartments_by_building_page:"))
async def paginate_apartments_by_building(callback: CallbackQuery, language: str = "ru"):
    """Пагинация квартир конкретного здания"""
    parts = callback.data.split(":")
    building_id = int(parts[1])
    page = int(parts[2])
    lang = language

    db = next(get_db())
    try:
        building = await AddressService.get_building_by_id(db, building_id, include_yard=True)
        if not building:
            await callback.answer(get_text("address_apartments.handlers.building_not_found", language=lang), show_alert=True)
            return

        apartments = await AddressService.get_apartments_by_building(db, building_id, only_active=False)

        text = get_text("address_apartments.handlers.building_apartments", language=lang).format(
            address=building.address,
            total=len(apartments)
        )

        if not apartments:
            text += "\n" + get_text("address_apartments.handlers.apartments_list_empty", language=lang)

        await callback.message.edit_text(
            text,
            reply_markup=get_apartments_list_keyboard(apartments, page=page, building_id=building_id)
        )

    except Exception as e:
        logger.error(f"Ошибка при пагинации квартир здания {building_id}: {e}")
        await callback.answer(get_text("address_apartments.handlers.error_loading_data", language=lang), show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ПОИСК КВАРТИР
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "addr_apartment_search")
async def start_apartment_search(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Начать поиск квартиры"""
    # TASK 17: Localize apartment search prompt
    lang = language

    await state.set_state(ApartmentManagementStates.waiting_for_apartment_search)

    message_text = (
        f"{get_text('requests.apartment_search_title', language=lang)}\n\n"
        f"{get_text('requests.apartment_search_prompt', language=lang)}\n\n"
        f"{get_text('requests.apartment_search_examples', language=lang)}"
    )

    await callback.message.edit_text(
        message_text,
        reply_markup=get_cancel_keyboard_inline()
    )


@router.message(StateFilter(ApartmentManagementStates.waiting_for_apartment_search))
async def process_apartment_search(message: Message, state: FSMContext, language: str = "ru"):
    """Обработка поискового запроса"""
    # TASK 17: Localize search results
    lang = language
    query = message.text.strip()

    if len(query) < 1:
        await message.answer(
            get_text('requests.search_query_too_short', language=lang)
        )
        return

    db = next(get_db())
    try:
        apartments = await AddressService.search_apartments(db, query, only_active=True)

        if not apartments:
            no_results_text = (
                f"{get_text('requests.search_results_title', language=lang)}\n\n"
                f"{get_text('requests.search_no_results', language=lang, query=query)}\n\n"
                f"{get_text('requests.search_no_results_action', language=lang)}"
            )
            await message.answer(
                no_results_text,
                reply_markup=get_apartments_list_keyboard([], page=0)
            )
            await state.clear()
            return

        text = (
            f"{get_text('requests.search_results_title', language=lang)}\n\n"
            f"{get_text('requests.search_query_label', language=lang, query=query)}\n"
            f"{get_text('requests.search_found_count', language=lang, count=len(apartments))}\n\n"
            f"{get_text('requests.search_select_apartment', language=lang)}"
        )

        await message.answer(
            text,
            reply_markup=get_apartments_list_keyboard(apartments, page=0)
        )

        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка при поиске квартир: {e}")
        await message.answer(get_text("errors.search_error", language=lang))
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР ДЕТАЛЬНОЙ ИНФОРМАЦИИ О КВАРТИРЕ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_apartment_view:"))
async def show_apartment_details(callback: CallbackQuery, language: str = "ru"):
    """Показать детальную информацию о квартире"""
    apartment_id = int(callback.data.split(":")[1])
    lang = language

    db = next(get_db())
    try:
        apartment = await AddressService.get_apartment_by_id(db, apartment_id, include_building=True)

        if not apartment:
            await callback.answer(get_text("address_apartments.handlers.apartment_not_found", language=lang), show_alert=True)
            return

        status_text = get_text("apartment.active_status", language=lang) if apartment.is_active else get_text("apartment.inactive_status", language=lang)
        residents_count = apartment.residents_count if hasattr(apartment, 'residents_count') else 0
        pending_count = apartment.pending_requests_count if hasattr(apartment, 'pending_requests_count') else 0

        text = f"🏠 <b>{get_text('apartment.details_title', language=lang).format(number=apartment.apartment_number)}</b>\n\n"

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
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР ЖИТЕЛЕЙ КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_apartment_residents:"))
async def show_apartment_residents(callback: CallbackQuery, language: str = "ru"):
    """Показать список жителей квартиры"""
    apartment_id = int(callback.data.split(":")[1])
    lang = language

    db = next(get_db())
    try:
        apartment = await AddressService.get_apartment_by_id(db, apartment_id, include_building=True)
        if not apartment:
            await callback.answer(get_text("address_apartments.handlers.apartment_not_found", language=lang), show_alert=True)
            return

        residents = await AddressService.get_apartment_residents(db, apartment_id, only_approved=False)

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
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# СОЗДАНИЕ НОВОЙ КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "addr_apartment_create")
async def start_apartment_creation(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Начать создание новой квартиры - выбор здания"""
    await state.clear()
    lang = language

    db = next(get_db())
    try:
        from uk_management_bot.database.models import Building
        from sqlalchemy import select

        result = db.execute(
            select(Building)
            .where(Building.is_active == True)
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
    finally:
        db.close()


@router.callback_query(F.data.startswith("apartment_create_building:"))
async def process_apartment_building_selection(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Обработка выбора здания для новой квартиры"""
    building_id = int(callback.data.split(":")[1])
    lang = language

    await state.update_data(building_id=building_id)
    await state.set_state(ApartmentManagementStates.waiting_for_apartment_number)

    db = next(get_db())
    try:
        building = await AddressService.get_building_by_id(db, building_id)
        building_addr = building.address if building else get_text("address_apartments.handlers.unknown_building", language=lang)

        await callback.message.edit_text(
            get_text("address_apartments.handlers.create_step2_enter_number", language=lang).format(address=building_addr),
            reply_markup=get_cancel_keyboard_inline()
        )
    finally:
        db.close()


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
async def process_apartment_entrance(message: Message, state: FSMContext, language: str = "ru"):
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
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
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
async def process_apartment_floor(message: Message, state: FSMContext, language: str = "ru"):
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
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
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
async def process_apartment_rooms(message: Message, state: FSMContext, language: str = "ru"):
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
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
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
async def process_apartment_area(message: Message, state: FSMContext, language: str = "ru"):
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
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
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
    db = next(get_db())

    try:
        # Получаем user.id из базы данных (не telegram_id!)
        from uk_management_bot.database.models.user import User
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer(
                get_text("address_apartments.handlers.user_not_found", language=lang),
                reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
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
                reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
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

    except Exception as e:
        logger.error(f"Ошибка при создании квартиры: {e}")
        await message.answer(
            get_text("address_apartments.handlers.creation_exception", language=lang).format(error=str(e)),
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
        )
    finally:
        db.close()
        await state.clear()


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

    db = next(get_db())
    try:
        apartment = await AddressService.get_apartment_by_id(db, apartment_id)
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
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# УДАЛЕНИЕ КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_apartment_delete:"))
async def confirm_apartment_deletion(callback: CallbackQuery, language: str = "ru"):
    """Подтверждение удаления квартиры"""
    apartment_id = int(callback.data.split(":")[1])
    lang = language

    db = next(get_db())
    try:
        apartment = await AddressService.get_apartment_by_id(db, apartment_id, include_building=True)
        if not apartment:
            await callback.answer(get_text("address_apartments.handlers.apartment_not_found", language=lang), show_alert=True)
            return

        residents_count = apartment.residents_count if hasattr(apartment, 'residents_count') else 0

        warning = ""
        if residents_count > 0:
            warning = "\n\n" + get_text("address_apartments.handlers.delete_warning_residents", language=lang).format(count=residents_count)

        full_address = apartment.full_address if hasattr(apartment, 'full_address') else get_text("address_apartments.handlers.apartment_label", language=lang).format(number=apartment.apartment_number)

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
    finally:
        db.close()


@router.callback_query(F.data.startswith("addr_apartment_delete_confirm:"))
async def delete_apartment(callback: CallbackQuery, language: str = "ru"):
    """Удаление квартиры"""
    apartment_id = int(callback.data.split(":")[1])
    lang = language

    db = next(get_db())
    try:
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
    finally:
        db.close()


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

    db = next(get_db())
    try:
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

    except Exception as e:
        logger.error(f"Ошибка при обновлении площади квартиры: {e}")
        await message.answer(
            get_text("address_apartments.handlers.area_update_exception", language=lang).format(error=str(e)),
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
        )
    finally:
        db.close()
        await state.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# АВТОЗАПОЛНЕНИЕ КВАРТИР
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_building_autofill:"))
async def start_autofill_apartments(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Начать процесс автозаполнения квартир для здания"""
    building_id = int(callback.data.split(":")[1])
    lang = language

    db = next(get_db())
    try:
        building = await AddressService.get_building_by_id(db, building_id, include_yard=True)
        if not building:
            await callback.answer(get_text("address_apartments.handlers.building_not_found", language=lang), show_alert=True)
            return

        # Сохраняем ID здания в state
        await state.update_data(autofill_building_id=building_id)
        await state.set_state(ApartmentManagementStates.waiting_for_autofill_range)

        yard_line = f"<b>{get_text('address_apartments.handlers.yard_label', language=lang)}</b> {building.yard.name}" if building.yard else ""

        text = get_text("address_apartments.handlers.autofill_prompt", language=lang).format(
            address=building.address,
            yard_line=yard_line
        )

        await callback.message.edit_text(
            text,
            reply_markup=get_cancel_keyboard_inline()
        )

    except Exception as e:
        logger.error(f"Ошибка при начале автозаполнения: {e}")
        await callback.answer(get_text("address_apartments.handlers.error_generic", language=lang), show_alert=True)
    finally:
        db.close()


@router.message(StateFilter(ApartmentManagementStates.waiting_for_autofill_range))
async def process_autofill_range(message: Message, state: FSMContext, language: str = "ru"):
    """Обработать ввод диапазона номеров квартир"""
    lang = language
    range_text = message.text.strip()

    cancel_text = get_text("address.keyboards.cancel", language=lang)
    if range_text in [cancel_text, "/cancel"]:
        await state.clear()
        await message.answer(
            get_text("address_apartments.handlers.autofill_cancelled", language=lang),
            reply_markup=get_address_management_menu()
        )
        return

    # Парсим диапазон и получаем список номеров квартир
    try:
        apartment_numbers = parse_apartment_range(range_text)

        if not apartment_numbers:
            await message.answer(
                get_text("address_apartments.handlers.invalid_range_format", language=lang)
            )
            return

        if len(apartment_numbers) > 500:
            await message.answer(
                get_text("address_apartments.handlers.too_many_apartments", language=lang).format(count=len(apartment_numbers))
            )
            return

    except ValueError as e:
        await message.answer(get_text("address_apartments.handlers.range_parse_error", language=lang).format(error=e))
        return

    # Получаем данные из state
    data = await state.get_data()
    building_id = data.get("autofill_building_id")

    if not building_id:
        await message.answer(get_text("address_apartments.handlers.autofill_building_lost", language=lang))
        await state.clear()
        return

    # Подтверждение
    await state.update_data(apartment_numbers=apartment_numbers)

    text = get_text("address_apartments.handlers.autofill_confirm_prompt", language=lang).format(
        count=len(apartment_numbers),
        numbers=format_numbers_preview(apartment_numbers, language=lang)
    )

    await message.answer(
        text,
        reply_markup=get_confirmation_keyboard(
            confirm_callback="addr_autofill_confirm",
            cancel_callback="addr_autofill_cancel"
        )
    )


@router.callback_query(F.data == "addr_autofill_confirm")
async def confirm_autofill_apartments(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Подтвердить и выполнить автозаполнение"""
    data = await state.get_data()
    building_id = data.get("autofill_building_id")
    apartment_numbers = data.get("apartment_numbers", [])

    lang = language

    if not building_id or not apartment_numbers:
        await callback.answer(get_text("address_apartments.handlers.autofill_data_not_found", language=lang), show_alert=True)
        await state.clear()
        return

    db = next(get_db())
    try:
        # Получаем user.id из базы данных по telegram_id
        from uk_management_bot.database.models import User
        from sqlalchemy import select

        user = db.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        ).scalar_one_or_none()

        if not user:
            await callback.answer(get_text("address_apartments.handlers.autofill_user_not_found", language=lang), show_alert=True)
            await state.clear()
            db.close()
            return

        # Выполняем массовое создание квартир
        created_count, skipped_count, errors = await AddressService.bulk_create_apartments(
            db,
            building_id=building_id,
            apartment_numbers=apartment_numbers,
            created_by=user.id  # Используем user.id вместо telegram_id
        )

        db.commit()

        # Формируем результат
        text = get_text("address_apartments.handlers.autofill_success", language=lang).format(
            created_count=created_count
        )

        if skipped_count > 0:
            text += get_text("address_apartments.handlers.autofill_skipped", language=lang).format(
                skipped_count=skipped_count
            )

        if errors:
            text += get_text("address_apartments.handlers.autofill_errors_header", language=lang)
            for error in errors[:5]:  # Показываем только первые 5 ошибок
                text += f"• {error}\n"
            if len(errors) > 5:
                text += get_text("address_apartments.handlers.autofill_more_errors", language=lang).format(
                    count=len(errors) - 5
                )

        text += get_text("address_apartments.handlers.autofill_select_action", language=lang)

        await callback.message.edit_text(
            text,
            reply_markup=get_address_management_menu()
        )

    except Exception as e:
        logger.error(f"Ошибка при автозаполнении квартир: {e}")
        await callback.answer(get_text("address_apartments.handlers.autofill_creation_error", language=lang), show_alert=True)
        db.rollback()
    finally:
        db.close()
        await state.clear()


@router.callback_query(F.data == "addr_autofill_cancel")
async def cancel_autofill_apartments(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Отменить автозаполнение"""
    lang = language
    await state.clear()
    await callback.message.edit_text(
        get_text("address_apartments.handlers.autofill_cancelled_confirm", language=lang),
        reply_markup=get_address_management_menu()
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ АВТОЗАПОЛНЕНИЯ
# ═══════════════════════════════════════════════════════════════════════════════

def parse_apartment_range(range_text: str) -> list[str]:
    """
    Парсит диапазон номеров квартир

    Примеры:
        "1-50" -> ["1", "2", ..., "50"]
        "1,5,10" -> ["1", "5", "10"]
        "1-5,10,15-20" -> ["1", "2", "3", "4", "5", "10", "15", "16", "17", "18", "19", "20"]

    Args:
        range_text: Текст с диапазоном

    Returns:
        Список строковых номеров квартир
    """
    result = set()

    # Разбиваем по запятой
    parts = range_text.split(",")

    for part in parts:
        part = part.strip()

        if "-" in part:
            # Это диапазон
            try:
                start, end = part.split("-")
                start_num = int(start.strip())
                end_num = int(end.strip())

                if start_num > end_num:
                    raise ValueError(f"Некорректный диапазон: {start_num} > {end_num}")

                for num in range(start_num, end_num + 1):
                    result.add(str(num))
            except ValueError as e:
                raise ValueError(f"Некорректный диапазон '{part}': {e}")
        else:
            # Это одиночное число
            try:
                num = int(part)
                result.add(str(num))
            except ValueError:
                raise ValueError(f"Некорректный номер квартиры: '{part}'")

    # Сортируем по числовому значению
    return sorted(result, key=lambda x: int(x))


def format_numbers_preview(numbers: list[str], max_show: int = 10, language: str = "ru") -> str:
    """
    Форматирует список номеров для предпросмотра

    Args:
        numbers: Список номеров
        max_show: Максимальное количество отображаемых номеров
        language: Код языка

    Returns:
        Строка с номерами
    """
    if len(numbers) <= max_show:
        return ", ".join(numbers)
    else:
        shown = ", ".join(numbers[:max_show])
        more_text = get_text("address_apartments.handlers.and_more", language=language).format(
            count=len(numbers) - max_show
        )
        return f"{shown}... ({more_text})"


# ═══════════════════════════════════════════════════════════════════════════════
# ОТМЕНА ДЕЙСТВИЙ
# ═══════════════════════════════════════════════════════════════════════════════

async def _return_to_profile_apartments(callback: CallbackQuery, state: FSMContext, language: str = "ru") -> bool:
    """BUG-BOT-021: вернуться в "Мои квартиры" из профиля после отмены."""
    lang = language
    try:
        from uk_management_bot.handlers.user_apartments import show_my_apartments
        await show_my_apartments(callback, state, language=lang)
        return True
    except Exception as e:
        logger.error(f"Ошибка возврата в Мои квартиры из профиля: {e}")
        return False


async def _return_to_admin_yards(callback: CallbackQuery, state: FSMContext, language: str = "ru") -> bool:
    """BUG-BOT-021: вернуться в admin-меню справочника адресов после отмены."""
    lang = language
    try:
        await callback.message.answer(
            get_text("address_apartments.handlers.address_directory", language=lang),
            reply_markup=get_address_management_menu()
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка возврата в admin-меню адресов: {e}")
        return False


@router.callback_query(F.data == "cancel_apartment_selection")
async def cancel_apartment_action(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Отмена выбора квартиры или создания.

    BUG-BOT-021: уважаем entry-point из state.data['entry_from']:
      * "profile" → возврат в "Мои квартиры"
      * иначе (admin)  → возврат в справочник адресов.
    Без этого пользователь из профиля попадал в admin-вью.
    """
    lang = language
    data = await state.get_data()
    entry_from = data.get("entry_from")
    await state.clear()
    await callback.message.edit_text(get_text("address_apartments.handlers.action_cancelled", language=lang))

    if entry_from == "profile":
        ok = await _return_to_profile_apartments(callback, state, language=lang)
        if ok:
            return

    await _return_to_admin_yards(callback, state, language=lang)


@router.callback_query(F.data == "cancel_action")
async def cancel_generic_action(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Отмена текущего действия (универсальный обработчик)"""
    lang = language
    await state.clear()
    await callback.message.edit_text(get_text("address_apartments.handlers.action_cancelled", language=lang))

    await callback.message.answer(
        get_text("address_apartments.handlers.address_directory", language=lang),
        reply_markup=get_address_management_menu()
    )
