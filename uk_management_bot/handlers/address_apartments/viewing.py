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
    get_apartments_list_keyboard,
    get_apartments_menu,
    get_cancel_keyboard_inline
)

from ._router import router

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР СПИСКА КВАРТИР
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "addr_apartments_list")
async def show_apartments_list(callback: CallbackQuery, state: FSMContext | None = None, language: str = "ru"):
    """Показать выбор здания для просмотра квартир"""
    # delete_apartment вызывает без FSM-состояния (state=None) — чистить нечего.
    if state is not None:
        await state.clear()
    lang = language

    try:
        with session_scope() as db:
            from uk_management_bot.database.models import Building
            from sqlalchemy import select, func
            from sqlalchemy.orm import joinedload

            # Получаем все здания с количеством квартир
            result = db.execute(
                select(Building)
                .options(joinedload(Building.yard))
                .where(Building.is_active.is_(True))
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
                    .where(Apartment.is_active.is_(True))
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


@router.callback_query(F.data.startswith("addr_apartments_by_building:"))
async def show_apartments_by_building(callback: CallbackQuery, language: str = "ru"):
    """Показать квартиры конкретного здания"""
    building_id = int(callback.data.split(":")[1])
    lang = language

    try:
        with session_scope() as db:
            building = AddressService.get_building_by_id(db, building_id, include_yard=True)
            if not building:
                await callback.answer(get_text("address_apartments.handlers.building_not_found", language=lang), show_alert=True)
                return

            apartments = AddressService.get_apartments_by_building(db, building_id, only_active=False)

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


@router.callback_query(F.data.startswith("addr_apartments_by_building_page:"))
async def paginate_apartments_by_building(callback: CallbackQuery, language: str = "ru"):
    """Пагинация квартир конкретного здания"""
    parts = callback.data.split(":")
    building_id = int(parts[1])
    page = int(parts[2])
    lang = language

    try:
        with session_scope() as db:
            building = AddressService.get_building_by_id(db, building_id, include_yard=True)
            if not building:
                await callback.answer(get_text("address_apartments.handlers.building_not_found", language=lang), show_alert=True)
                return

            apartments = AddressService.get_apartments_by_building(db, building_id, only_active=False)

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

    try:
        with session_scope() as db:
            apartments = AddressService.search_apartments(db, query, only_active=True)

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
