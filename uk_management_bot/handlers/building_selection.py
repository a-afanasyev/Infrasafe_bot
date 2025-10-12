"""Building Selection Handlers for Request Creation.

Week 2, Task 6.1: Building Selection Handlers
Handles building selection flow when creating requests.
"""

import logging
from typing import Optional
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from uk_management_bot.states.building_selection import RequestWithBuildingStates
from uk_management_bot.keyboards.buildings import (
    get_city_selection_keyboard,
    get_building_search_keyboard,
    get_building_list_inline_keyboard,
    get_building_confirmation_keyboard,
    get_address_details_keyboard,
    get_manual_address_fallback_keyboard,
    format_building_info,
    format_building_list_message
)
from uk_management_bot.services.building_service import get_building_service
from uk_management_bot.keyboards.base import get_cancel_keyboard

logger = logging.getLogger(__name__)
router = Router()

# Initialize building service
building_service = get_building_service()


# ============================================================================
# City Selection
# ============================================================================

@router.message(RequestWithBuildingStates.building_selection_city)
async def process_city_selection(message: Message, state: FSMContext):
    """Process city selection for building search.

    User selects city from available cities in Directory.
    """
    city_text = message.text

    # Handle cancel
    if city_text == "❌ Отмена":
        await state.clear()
        await message.answer(
            "Создание заявки отменено.",
            reply_markup=None
        )
        return

    # Remove emoji prefix if present
    city = city_text.replace("📍 ", "").strip()

    # Validate city exists in directory
    cities = await building_service.get_cities()

    if city not in cities:
        await message.answer(
            f"❌ Город '{city}' не найден в справочнике.\n\n"
            "Пожалуйста, выберите город из списка:",
            reply_markup=get_city_selection_keyboard(cities)
        )
        return

    # Save city and move to search
    await state.update_data(selected_city=city)
    await state.set_state(RequestWithBuildingStates.building_selection_search)

    await message.answer(
        f"📍 Выбран город: <b>{city}</b>\n\n"
        "🔍 Теперь введите <b>улицу и номер дома</b> для поиска здания.\n\n"
        "Примеры:\n"
        "• Amir Temur 42\n"
        "• Мустакиллик 15\n"
        "• Юнусабад 10",
        parse_mode='HTML',
        reply_markup=get_building_search_keyboard()
    )

    logger.info(f"User {message.from_user.id} selected city: {city}")


# ============================================================================
# Building Search
# ============================================================================

@router.message(RequestWithBuildingStates.building_selection_search)
async def process_building_search(message: Message, state: FSMContext):
    """Process building search query.

    User enters street and house number to search buildings.
    """
    search_text = message.text

    # Handle special buttons
    if search_text == "❌ Отмена":
        await state.clear()
        await message.answer("Создание заявки отменено.", reply_markup=None)
        return

    if search_text == "✏️ Ввести адрес вручную":
        await state.set_state(RequestWithBuildingStates.address_details)
        await message.answer(
            "✏️ Введите полный адрес вручную:\n"
            "Например: г. Ташкент, ул. Амир Темур, д. 42, кв. 5",
            reply_markup=get_manual_address_fallback_keyboard()
        )
        return

    # Get selected city from state
    data = await state.get_data()
    selected_city = data.get('selected_city')

    if not selected_city:
        await message.answer("❌ Ошибка: город не выбран. Начните заново.")
        await state.clear()
        return

    # Search buildings
    try:
        buildings = await building_service.search_buildings(
            query=search_text,
            city=selected_city,
            limit=20
        )

        if not buildings:
            # No results - offer alternatives
            await message.answer(
                f"🔍 По запросу <b>\"{search_text}\"</b> в городе <b>{selected_city}</b> "
                "ничего не найдено.\n\n"
                "Попробуйте:\n"
                "• Изменить запрос\n"
                "• Ввести адрес вручную",
                parse_mode='HTML',
                reply_markup=get_building_search_keyboard()
            )
            return

        # Save search results and show list
        await state.update_data(
            search_query=search_text,
            search_results=buildings,
            search_page=1
        )

        # Create keyboard with first page of results
        keyboard = get_building_list_inline_keyboard(
            buildings=buildings[:10],  # First 10 results
            page=1,
            total_pages=(len(buildings) + 9) // 10  # Ceiling division
        )

        message_text = format_building_list_message(
            buildings=buildings,
            total=len(buildings),
            page=1,
            search_query=search_text
        )

        await message.answer(
            message_text,
            parse_mode='HTML',
            reply_markup=keyboard
        )

        await state.set_state(RequestWithBuildingStates.building_selection_choose)

        logger.info(
            f"User {message.from_user.id} searched buildings: '{search_text}', "
            f"found {len(buildings)} results"
        )

    except Exception as e:
        logger.error(f"Building search error: {e}", exc_info=True)
        await message.answer(
            "❌ Ошибка поиска зданий. Попробуйте еще раз или введите адрес вручную.",
            reply_markup=get_building_search_keyboard()
        )


# ============================================================================
# Building Selection from Results
# ============================================================================

@router.callback_query(F.data.startswith("building_select:"))
async def process_building_selection(callback: CallbackQuery, state: FSMContext):
    """Process building selection from search results.

    User clicks on a building from search results.
    """
    try:
        building_id = callback.data.split(":")[1]

        # Fetch building details
        building = await building_service.get_building(building_id)

        if not building:
            await callback.answer("❌ Здание не найдено", show_alert=True)
            return

        # Show building details with confirmation
        building_info = format_building_info(building)
        confirmation_text = (
            f"{building_info}\n\n"
            "✅ Подтвердите выбор здания или выберите другое."
        )

        await callback.message.edit_text(
            confirmation_text,
            parse_mode='HTML',
            reply_markup=get_building_confirmation_keyboard(building_id)
        )

        # Save selected building
        await state.update_data(selected_building_id=building_id)
        await state.set_state(RequestWithBuildingStates.building_selection_confirm)

        await callback.answer()

        logger.info(
            f"User {callback.from_user.id} selected building: {building_id}"
        )

    except Exception as e:
        logger.error(f"Building selection error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка выбора здания", show_alert=True)


@router.callback_query(F.data.startswith("building_confirm:"))
async def confirm_building_selection(callback: CallbackQuery, state: FSMContext):
    """Confirm building selection and move to address details.

    User confirms the selected building.
    """
    try:
        building_id = callback.data.split(":")[1]

        # Validate building exists
        building = await building_service.get_building(building_id)

        if not building:
            await callback.answer("❌ Здание не найдено", show_alert=True)
            return

        # Save building_id and address
        await state.update_data(
            building_id=building_id,
            building_address=building['full_address']
        )

        # Move to address details (apartment/entrance/floor)
        await state.set_state(RequestWithBuildingStates.address_details)

        await callback.message.edit_text(
            f"✅ Выбрано здание:\n{building['full_address']}\n\n"
            "📋 Теперь укажите <b>уточнения адреса</b> (квартира, подъезд, этаж).\n"
            "Или нажмите <b>\"Пропустить\"</b>, если уточнений нет.",
            parse_mode='HTML'
        )

        await callback.message.answer(
            "Введите уточнения:\n"
            "Например: кв. 42, 3 подъезд",
            reply_markup=get_address_details_keyboard()
        )

        await callback.answer()

        logger.info(
            f"User {callback.from_user.id} confirmed building: {building_id}"
        )

    except Exception as e:
        logger.error(f"Building confirmation error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка подтверждения", show_alert=True)


@router.callback_query(F.data == "building_choose_another")
async def choose_another_building(callback: CallbackQuery, state: FSMContext):
    """Return to building selection.

    User wants to choose a different building.
    """
    try:
        # Get previous search results from state
        data = await state.get_data()
        buildings = data.get('search_results', [])
        search_query = data.get('search_query')
        page = data.get('search_page', 1)

        if not buildings:
            await callback.answer(
                "❌ Результаты поиска не найдены. Начните поиск заново.",
                show_alert=True
            )
            await state.set_state(RequestWithBuildingStates.building_selection_search)
            return

        # Show building list again
        keyboard = get_building_list_inline_keyboard(
            buildings=buildings[:10],
            page=page,
            total_pages=(len(buildings) + 9) // 10
        )

        message_text = format_building_list_message(
            buildings=buildings,
            total=len(buildings),
            page=page,
            search_query=search_query
        )

        await callback.message.edit_text(
            message_text,
            parse_mode='HTML',
            reply_markup=keyboard
        )

        await state.set_state(RequestWithBuildingStates.building_selection_choose)
        await callback.answer()

    except Exception as e:
        logger.error(f"Choose another building error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


# ============================================================================
# Address Details (Apartment/Entrance/Floor)
# ============================================================================

@router.message(RequestWithBuildingStates.address_details)
async def process_address_details(message: Message, state: FSMContext):
    """Process address details (apartment, entrance, floor).

    User enters optional address details or skips.
    """
    details_text = message.text

    if details_text == "❌ Отмена":
        await state.clear()
        await message.answer("Создание заявки отменено.", reply_markup=None)
        return

    if details_text == "➡️ Пропустить":
        # Skip details, move to description
        await state.update_data(address_details=None)
    else:
        # Save details
        await state.update_data(address_details=details_text)

    # Move to description state (from original RequestStates)
    # Note: This transitions back to the original request creation flow
    from uk_management_bot.handlers.requests import RequestStates

    await state.set_state(RequestStates.description)

    # Get category for contextual message
    data = await state.get_data()
    category = data.get('category', '')

    await message.answer(
        f"📝 Категория: <b>{category}</b>\n\n"
        "Опишите проблему подробно:",
        parse_mode='HTML',
        reply_markup=get_cancel_keyboard()
    )

    logger.info(
        f"User {message.from_user.id} entered address details: "
        f"'{details_text}' or skipped"
    )


# ============================================================================
# Pagination
# ============================================================================

@router.callback_query(F.data.startswith("building_page:"))
async def handle_building_pagination(callback: CallbackQuery, state: FSMContext):
    """Handle building list pagination.

    User clicks on page navigation buttons.
    """
    try:
        page = int(callback.data.split(":")[1])

        data = await state.get_data()
        buildings = data.get('search_results', [])
        search_query = data.get('search_query')

        if not buildings:
            await callback.answer("❌ Результаты не найдены", show_alert=True)
            return

        # Update page in state
        await state.update_data(search_page=page)

        # Calculate pagination
        page_size = 10
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_buildings = buildings[start_idx:end_idx]
        total_pages = (len(buildings) + page_size - 1) // page_size

        # Create keyboard for this page
        keyboard = get_building_list_inline_keyboard(
            buildings=page_buildings,
            page=page,
            total_pages=total_pages
        )

        message_text = format_building_list_message(
            buildings=buildings,
            total=len(buildings),
            page=page,
            search_query=search_query
        )

        await callback.message.edit_text(
            message_text,
            parse_mode='HTML',
            reply_markup=keyboard
        )

        await callback.answer(f"Страница {page}/{total_pages}")

    except Exception as e:
        logger.error(f"Pagination error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


# ============================================================================
# Utility Callbacks
# ============================================================================

@router.callback_query(F.data == "building_new_search")
async def handle_new_search(callback: CallbackQuery, state: FSMContext):
    """Start new building search.

    User wants to search again with different query.
    """
    await state.set_state(RequestWithBuildingStates.building_selection_search)

    data = await state.get_data()
    city = data.get('selected_city', 'не выбран')

    await callback.message.edit_text(
        f"🔍 <b>Новый поиск</b>\n\n"
        f"Город: {city}\n\n"
        "Введите улицу и номер дома:",
        parse_mode='HTML'
    )

    await callback.message.answer(
        "Пример: Amir Temur 42",
        reply_markup=get_building_search_keyboard()
    )

    await callback.answer()


@router.callback_query(F.data == "building_manual_entry")
async def handle_manual_entry(callback: CallbackQuery, state: FSMContext):
    """Switch to manual address entry.

    User prefers to enter address manually.
    """
    await state.set_state(RequestWithBuildingStates.address_details)

    await callback.message.edit_text(
        "✏️ <b>Ручной ввод адреса</b>\n\n"
        "Введите полный адрес с уточнениями:",
        parse_mode='HTML'
    )

    await callback.message.answer(
        "Например: г. Ташкент, ул. Амир Темур, д. 42, кв. 5",
        reply_markup=get_manual_address_fallback_keyboard()
    )

    await callback.answer()


@router.callback_query(F.data == "building_cancel")
async def handle_building_cancel(callback: CallbackQuery, state: FSMContext):
    """Cancel building selection and request creation.

    User cancels the entire flow.
    """
    await state.clear()

    await callback.message.edit_text("❌ Создание заявки отменено.")

    await callback.answer()
