"""
Request Handlers
UK Management Bot - Bot Gateway Service

Handlers for request management operations.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.states.request_states import RequestCreationStates
from app.keyboards.common import get_cancel_keyboard
from app.keyboards.requests import (
    get_request_list_keyboard,
    get_request_actions_keyboard,
    get_request_status_filter_keyboard
)
from app.integrations.request_client import request_client

logger = logging.getLogger(__name__)

# Create router
router = Router(name="requests")


@router.message(F.text.in_(["📋 Мои заявки", "📋 Mening arizalarim"]))
async def button_my_requests(
    message: Message,
    token: str,
    language: str
):
    """
    Handle "My Requests" button.

    Args:
        message: Telegram message
        token: JWT token from auth middleware
        language: User language
    """
    try:
        # Get user's requests
        result = await request_client.get_my_requests(
            token=token,
            limit=10
        )

        requests = result.get("requests", [])
        total = result.get("total", 0)

        if not requests:
            text = (
                "📋 У вас пока нет заявок.\n"
                "Создайте новую заявку через меню."
                if language == "ru"
                else
                "📋 Sizda hali arizalar yo'q.\n"
                "Menyudan yangi ariza yarating."
            )
            await message.answer(text=text)
            return

        text = (
            f"📋 <b>Ваши заявки</b> (всего: {total})\n\n"
            f"Выберите заявку для просмотра:"
            if language == "ru"
            else
            f"📋 <b>Sizning arizalaringiz</b> (jami: {total})\n\n"
            f"Ko'rish uchun arizani tanlang:"
        )

        await message.answer(
            text=text,
            reply_markup=get_request_list_keyboard(requests, language)
        )

    except Exception as e:
        logger.error(f"Failed to get user requests: {e}")
        error_text = (
            "❌ Ошибка при загрузке заявок"
            if language == "ru"
            else "❌ Arizalarni yuklashda xatolik"
        )
        await message.answer(text=error_text)


@router.message(F.text.in_(["➕ Создать заявку", "➕ Ariza yaratish"]))
async def button_create_request(
    message: Message,
    state: FSMContext,
    language: str
):
    """
    Handle "Create Request" button - start request creation flow.

    Args:
        message: Telegram message
        state: FSM context
        language: User language
    """
    text = (
        "🏢 <b>Создание заявки</b>\n\n"
        "Шаг 1/3: Укажите номер дома"
        if language == "ru"
        else
        "🏢 <b>Ariza yaratish</b>\n\n"
        "1/3 qadam: Uy raqamini kiriting"
    )

    await message.answer(
        text=text,
        reply_markup=get_cancel_keyboard(language)
    )

    # Set FSM state
    await state.set_state(RequestCreationStates.waiting_for_building)
    logger.info(f"User {message.from_user.id} started request creation flow")


@router.message(RequestCreationStates.waiting_for_building)
async def process_building_input(
    message: Message,
    state: FSMContext,
    language: str
):
    """
    Process building number input.

    Args:
        message: Telegram message
        state: FSM context
        language: User language
    """
    building = message.text.strip()

    # Save building to FSM data
    await state.update_data(building=building)

    text = (
        "🏠 <b>Создание заявки</b>\n\n"
        f"Дом: {building}\n\n"
        "Шаг 2/3: Укажите номер квартиры"
        if language == "ru"
        else
        "🏠 <b>Ariza yaratish</b>\n\n"
        f"Uy: {building}\n\n"
        "2/3 qadam: Xonadon raqamini kiriting"
    )

    await message.answer(text=text)

    # Move to next state
    await state.set_state(RequestCreationStates.waiting_for_apartment)


@router.message(RequestCreationStates.waiting_for_apartment)
async def process_apartment_input(
    message: Message,
    state: FSMContext,
    language: str
):
    """
    Process apartment number input.

    Args:
        message: Telegram message
        state: FSM context
        language: User language
    """
    apartment = message.text.strip()

    # Save apartment to FSM data
    await state.update_data(apartment=apartment)

    # Get building from FSM data
    data = await state.get_data()
    building = data.get("building")

    text = (
        "📝 <b>Создание заявки</b>\n\n"
        f"Дом: {building}\n"
        f"Квартира: {apartment}\n\n"
        "Шаг 3/3: Опишите проблему"
        if language == "ru"
        else
        "📝 <b>Ariza yaratish</b>\n\n"
        f"Uy: {building}\n"
        f"Xonadon: {apartment}\n\n"
        "3/3 qadam: Muammoni tavsiflang"
    )

    await message.answer(text=text)

    # Move to next state
    await state.set_state(RequestCreationStates.waiting_for_description)


@router.message(RequestCreationStates.waiting_for_description)
async def process_description_input(
    message: Message,
    state: FSMContext,
    token: str,
    language: str
):
    """
    Process description input and create request.

    Args:
        message: Telegram message
        state: FSM context
        token: JWT token
        language: User language
    """
    description = message.text.strip()

    # Get FSM data
    data = await state.get_data()
    building = data.get("building")
    apartment = data.get("apartment")

    try:
        # Create request via Request Service
        request_data = {
            "building": building,
            "apartment": apartment,
            "description": description,
            "language": language
        }

        result = await request_client.create_request(
            data=request_data,
            token=token
        )

        request_number = result.get("request_number")

        text = (
            f"✅ <b>Заявка создана успешно!</b>\n\n"
            f"Номер заявки: <code>{request_number}</code>\n"
            f"Дом: {building}\n"
            f"Квартира: {apartment}\n"
            f"Описание: {description}\n\n"
            f"Вы получите уведомление, когда заявка будет взята в работу."
            if language == "ru"
            else
            f"✅ <b>Ariza muvaffaqiyatli yaratildi!</b>\n\n"
            f"Ariza raqami: <code>{request_number}</code>\n"
            f"Uy: {building}\n"
            f"Xonadon: {apartment}\n"
            f"Tavsif: {description}\n\n"
            f"Ariza ishga olinganda sizga xabar beriladi."
        )

        await message.answer(text=text)

        logger.info(
            f"Request {request_number} created by user {message.from_user.id}"
        )

    except Exception as e:
        logger.error(f"Failed to create request: {e}")
        error_text = (
            "❌ Ошибка при создании заявки. Попробуйте позже."
            if language == "ru"
            else "❌ Ariza yaratishda xatolik. Keyinroq urinib ko'ring."
        )
        await message.answer(text=error_text)

    finally:
        # Clear FSM state
        await state.clear()


@router.message(F.text.in_(["❌ Отмена", "❌ Bekor qilish"]))
async def button_cancel(
    message: Message,
    state: FSMContext,
    user_role: str,
    language: str
):
    """
    Handle cancel button - clear FSM state.

    Args:
        message: Telegram message
        state: FSM context
        user_role: User role
        language: User language
    """
    await state.clear()

    text = (
        "❌ Операция отменена"
        if language == "ru"
        else "❌ Operatsiya bekor qilindi"
    )

    from app.keyboards.common import get_main_menu_keyboard

    await message.answer(
        text=text,
        reply_markup=get_main_menu_keyboard(user_role, language)
    )


@router.callback_query(F.data.startswith("request:view:"))
async def callback_view_request(
    callback: CallbackQuery,
    token: str,
    user_role: str,
    language: str
):
    """
    Handle view request callback.

    Args:
        callback: Callback query
        token: JWT token
        user_role: User role
        language: User language
    """
    # Extract request_number from callback data
    request_number = callback.data.split(":")[2]

    try:
        # Get request details
        request = await request_client.get_request(
            request_number=request_number,
            token=token
        )

        status = request.get("status")
        building = request.get("building")
        apartment = request.get("apartment")
        description = request.get("description")
        created_at = request.get("created_at", "")[:10]  # Date only

        # Status text
        status_texts = {
            "ru": {
                "new": "🆕 Новая",
                "in_progress": "⏳ В работе",
                "completed": "✅ Завершена",
                "cancelled": "❌ Отменена"
            },
            "uz": {
                "new": "🆕 Yangi",
                "in_progress": "⏳ Jarayonda",
                "completed": "✅ Yakunlangan",
                "cancelled": "❌ Bekor qilingan"
            }
        }

        status_text = status_texts.get(language, status_texts["ru"]).get(
            status, status
        )

        text = (
            f"📋 <b>Заявка {request_number}</b>\n\n"
            f"Статус: {status_text}\n"
            f"Дом: {building}\n"
            f"Квартира: {apartment}\n"
            f"Создана: {created_at}\n\n"
            f"Описание:\n{description}"
            if language == "ru"
            else
            f"📋 <b>Ariza {request_number}</b>\n\n"
            f"Holat: {status_text}\n"
            f"Uy: {building}\n"
            f"Xonadon: {apartment}\n"
            f"Yaratilgan: {created_at}\n\n"
            f"Tavsif:\n{description}"
        )

        await callback.message.edit_text(
            text=text,
            reply_markup=get_request_actions_keyboard(
                request_number=request_number,
                status=status,
                user_role=user_role,
                language=language
            )
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Failed to get request {request_number}: {e}")
        await callback.answer("❌ Ошибка загрузки заявки", show_alert=True)
