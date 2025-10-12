"""Request Creation with Building Directory Integration.

Week 2, Task 6.2: Integrated Request Creation Flow
Combines request creation with building selection from Directory.
"""

import logging
from typing import Optional
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext

from uk_management_bot.states.building_selection import RequestWithBuildingStates
from uk_management_bot.keyboards.buildings import get_city_selection_keyboard
from uk_management_bot.keyboards.requests import get_categories_inline_keyboard_with_cancel
from uk_management_bot.services.building_service import get_building_service
from uk_management_bot.utils.constants import REQUEST_CATEGORIES

logger = logging.getLogger(__name__)
router = Router()

# Apply auth middleware
from uk_management_bot.middlewares.auth import auth_middleware, role_mode_middleware
router.message.middleware(auth_middleware)
router.message.middleware(role_mode_middleware)
router.callback_query.middleware(auth_middleware)
router.callback_query.middleware(role_mode_middleware)

building_service = get_building_service()


# ============================================================================
# Request Creation Start (with Building Directory)
# ============================================================================

@router.message(F.text == "🏢 Создать заявку (новое)")
async def start_request_with_building(
    message: Message,
    state: FSMContext,
    user_status: Optional[str] = None
):
    """Start request creation with Building Directory integration.

    This is the NEW flow that uses Building Directory.
    Users select: Category → City → Building → Details → Description → etc.
    """
    # Check if user is pending
    if user_status == "pending":
        await message.answer(
            "⏳ Ваша заявка на регистрацию находится на рассмотрении."
        )
        return

    # Check phone requirement
    from uk_management_bot.database.session import get_db
    from uk_management_bot.database.models.user import User

    db = next(get_db())
    try:
        user = db.query(User).filter(
            User.telegram_id == message.from_user.id
        ).first()

        if user and not user.phone:
            await message.answer(
                "📱 Для создания заявок необходимо указать номер телефона.\n"
                "Пожалуйста, добавьте телефон в профиле."
            )
            return
    except Exception as e:
        logger.error(f"Error checking user phone: {e}")
    finally:
        db.close()

    # Start the flow with category selection
    await state.set_state(RequestWithBuildingStates.category)

    await message.answer(
        "Начинаем создание заявки с выбором здания из справочника…",
        reply_markup=ReplyKeyboardRemove()
    )

    await message.answer(
        "📋 Шаг 1/6: Выберите категорию заявки:",
        reply_markup=get_categories_inline_keyboard_with_cancel()
    )

    logger.info(
        f"User {message.from_user.id} started request creation with Building Directory"
    )


# ============================================================================
# Category Selection
# ============================================================================

@router.callback_query(
    RequestWithBuildingStates.category,
    F.data.startswith("category:")
)
async def process_category_selection(callback: CallbackQuery, state: FSMContext):
    """Process category selection.

    After category, move to city selection for building.
    """
    try:
        category = callback.data.split(":")[1]

        if category not in REQUEST_CATEGORIES:
            await callback.answer("❌ Неверная категория", show_alert=True)
            return

        # Save category
        await state.update_data(category=category)

        # Move to city selection for building
        await state.set_state(RequestWithBuildingStates.building_selection_city)

        # Get available cities from Building Directory
        cities = await building_service.get_cities()

        if not cities:
            # Fallback: no cities in directory
            await callback.message.edit_text(
                "⚠️ В справочнике зданий пока нет данных.\n\n"
                "Введите адрес вручную:"
            )
            await state.set_state(RequestWithBuildingStates.address_details)
            await callback.answer(
                "Справочник пуст - используйте ручной ввод",
                show_alert=True
            )
            return

        # Show city selection
        await callback.message.edit_text(
            f"✅ Категория: <b>{category}</b>\n\n"
            f"📍 Шаг 2/6: Выберите город:",
            parse_mode='HTML'
        )

        city_keyboard = get_city_selection_keyboard(cities)

        await callback.message.answer(
            f"🏙️ Доступные города ({len(cities)}):",
            reply_markup=city_keyboard
        )

        await callback.answer()

        logger.info(
            f"User {callback.from_user.id} selected category: {category}"
        )

    except Exception as e:
        logger.error(f"Category selection error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка выбора категории", show_alert=True)


@router.callback_query(
    RequestWithBuildingStates.category,
    F.data == "cancel_create"
)
async def cancel_category_selection(callback: CallbackQuery, state: FSMContext):
    """Cancel request creation from category selection."""
    await state.clear()

    await callback.message.edit_text("❌ Создание заявки отменено.")

    await callback.answer()


# ============================================================================
# Integration with existing request flow
# ============================================================================

async def finalize_request_creation(
    message: Message,
    state: FSMContext,
    request_number: str
):
    """Finalize request creation after all data is collected.

    This function is called after the request is saved to database.
    It handles building_id association.

    Args:
        message: User message
        state: FSM context with request data
        request_number: Generated request number
    """
    try:
        data = await state.get_data()

        # Extract building-related data
        building_id = data.get('building_id')
        building_address = data.get('building_address')
        address_details = data.get('address_details')

        if building_id:
            # Update request with building_id
            # This will be sent to request-service API
            logger.info(
                f"Request {request_number} associated with building: {building_id}"
            )

            # Log for integration with request-service
            logger.info(
                f"[BUILDING_INTEGRATION] Request: {request_number}, "
                f"Building ID: {building_id}, "
                f"Building Address: {building_address}, "
                f"Address Details: {address_details}"
            )

            # TODO: Update request via request-service API
            # await request_service.update_request(
            #     request_number=request_number,
            #     building_id=building_id,
            #     building_address=building_address,
            #     address=address_details  # User's apartment/entrance/floor
            # )

        return True

    except Exception as e:
        logger.error(f"Request finalization error: {e}", exc_info=True)
        return False


# ============================================================================
# Command to switch between old/new flows (for testing)
# ============================================================================

@router.message(F.text == "/use_building_directory")
async def enable_building_directory(message: Message, state: FSMContext):
    """Enable Building Directory for this user.

    Admin command to test the new flow.
    """
    await state.update_data(use_building_directory=True)

    await message.answer(
        "✅ Building Directory включен!\n\n"
        "Теперь используйте команду:\n"
        "🏢 Создать заявку (новое)\n\n"
        "Или кнопку '🏢 Создать заявку (новое)' если она есть."
    )

    logger.info(f"User {message.from_user.id} enabled Building Directory")


@router.message(F.text == "/use_old_flow")
async def disable_building_directory(message: Message, state: FSMContext):
    """Disable Building Directory (use old flow).

    Admin command to revert to original flow.
    """
    await state.update_data(use_building_directory=False)

    await message.answer(
        "✅ Возврат к старому flow создания заявок.\n\n"
        "Используйте обычную кнопку 'Создать заявку'."
    )

    logger.info(f"User {message.from_user.id} disabled Building Directory")


# ============================================================================
# Info/Help
# ============================================================================

@router.message(F.text == "/building_directory_help")
async def show_building_directory_help(message: Message):
    """Show help about Building Directory feature."""
    help_text = (
        "🏢 <b>Справочник зданий</b>\n\n"
        "Новая функция для точного указания адреса заявки:\n\n"
        "<b>Как использовать:</b>\n"
        "1️⃣ Выберите категорию заявки\n"
        "2️⃣ Выберите город\n"
        "3️⃣ Найдите здание (улица + номер)\n"
        "4️⃣ Подтвердите выбор\n"
        "5️⃣ Добавьте уточнения (кв., подъезд)\n"
        "6️⃣ Опишите проблему\n\n"
        "<b>Преимущества:</b>\n"
        "✅ Точный адрес из справочника\n"
        "✅ Автоматические координаты\n"
        "✅ Нет опечаток в адресе\n"
        "✅ Быстрый поиск здания\n\n"
        "<b>Команды:</b>\n"
        "/use_building_directory - включить новый flow\n"
        "/use_old_flow - вернуться к старому\n"
        "🏢 Создать заявку (новое) - создать с Building Directory"
    )

    await message.answer(help_text, parse_mode='HTML')
