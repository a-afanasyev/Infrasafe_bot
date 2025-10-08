"""
Common Handlers
UK Management Bot - Bot Gateway Service

Handlers for common commands: /start, /help, /menu, /language
"""

import logging
from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.keyboards.common import (
    get_main_menu_keyboard,
    get_language_keyboard
)

logger = logging.getLogger(__name__)

# Create router
router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    user_role: str = None,
    language: str = "ru"
):
    """
    Handle /start command.

    Args:
        message: Telegram message
        state: FSM context
        user_role: User role from auth middleware (optional)
        language: User language from auth middleware (default: ru)
    """
    # Clear any active FSM state
    await state.clear()

    # Welcome message based on language
    if language == "uz":
        welcome_text = (
            f"🏢 <b>UK Management Bot</b>ga xush kelibsiz!\n\n"
            f"Men sizga yordam beraman:\n"
            f"• 📋 Arizalar bilan ishlash\n"
            f"• 📅 Smenalar bilan ishlash\n"
            f"• 📊 Analitika ko'rish\n\n"
            f"Quyidagi tugmalardan birini tanlang yoki /help buyrug'ini kiriting."
        )
    else:
        welcome_text = (
            f"🏢 Добро пожаловать в <b>UK Management Bot</b>!\n\n"
            f"Я помогу вам:\n"
            f"• 📋 Управлять заявками\n"
            f"• 📅 Работать со сменами\n"
            f"• 📊 Просматривать аналитику\n\n"
            f"Выберите действие из меню или введите /help для справки."
        )

    await message.answer(
        text=welcome_text,
        reply_markup=get_main_menu_keyboard(user_role, language)
    )

    logger.info(f"User {message.from_user.id} started bot (role: {user_role}, lang: {language})")


@router.message(Command("help"))
async def cmd_help(message: Message, language: str = "ru"):
    """
    Handle /help command.

    Args:
        message: Telegram message
        language: User language (default: ru)
    """
    if language == "uz":
        help_text = (
            "📖 <b>Yordam</b>\n\n"
            "<b>Asosiy buyruqlar:</b>\n"
            "/start - Botni boshlash\n"
            "/help - Yordam\n"
            "/menu - Asosiy menyu\n"
            "/language - Tilni o'zgartirish\n\n"
            "<b>Arizalar:</b>\n"
            "• Ariza yaratish - menyudan tanlang\n"
            "• Mening arizalarim - arizalaringizni ko'ring\n\n"
            "<b>Yordam uchun:</b>\n"
            "Savol yoki muammo bo'lsa, administratorga murojaat qiling."
        )
    else:
        help_text = (
            "📖 <b>Справка</b>\n\n"
            "<b>Основные команды:</b>\n"
            "/start - Запустить бота\n"
            "/help - Справка\n"
            "/menu - Главное меню\n"
            "/language - Изменить язык\n\n"
            "<b>Заявки:</b>\n"
            "• Создать заявку - выберите из меню\n"
            "• Мои заявки - просмотр ваших заявок\n\n"
            "<b>Поддержка:</b>\n"
            "При возникновении вопросов обратитесь к администратору."
        )

    await message.answer(text=help_text)


@router.message(Command("menu"))
@router.message(F.text.in_(["📋 Меню", "📋 Menyu"]))
async def cmd_menu(message: Message, user_role: str = None, language: str = "ru"):
    """
    Handle /menu command and menu button.

    Args:
        message: Telegram message
        user_role: User role (optional)
        language: User language (default: ru)
    """
    text = "Главное меню:" if language == "ru" else "Asosiy menyu:"

    await message.answer(
        text=text,
        reply_markup=get_main_menu_keyboard(user_role, language)
    )


@router.message(Command("language"))
@router.message(F.text.in_(["⚙️ Настройки", "⚙️ Sozlamalar"]))
async def cmd_language(message: Message, language: str = "ru"):
    """
    Handle /language command and settings button.

    Args:
        message: Telegram message
        language: Current user language
    """
    text = (
        "🌐 Выберите язык:\n"
        "🌐 Tilni tanlang:"
    )

    await message.answer(
        text=text,
        reply_markup=get_language_keyboard()
    )


@router.callback_query(F.data.startswith("lang:"))
async def callback_language_selected(
    callback: CallbackQuery,
    user_id: str,
    token: str
):
    """
    Handle language selection callback.

    Args:
        callback: Callback query
        user_id: User ID from auth middleware
        token: JWT token from auth middleware
    """
    # Extract language from callback data
    lang_code = callback.data.split(":")[1]

    try:
        # Update user language in User Service
        from app.integrations.user_client import user_client

        await user_client.set_user_language(
            user_id=user_id,
            language=lang_code,
            token=token
        )

        # Success message
        if lang_code == "uz":
            success_text = "✅ Til o'zgartirildi: O'zbek"
        else:
            success_text = "✅ Язык изменён: Русский"

        await callback.message.edit_text(text=success_text)
        await callback.answer()

        logger.info(f"User {user_id} changed language to {lang_code}")

    except Exception as e:
        logger.error(f"Failed to change language for user {user_id}: {e}")

        error_text = (
            "❌ Ошибка при изменении языка\n"
            "❌ Tilni o'zgartirishda xatolik"
        )
        await callback.message.edit_text(text=error_text)
        await callback.answer()


@router.message(F.text.in_(["❓ Помощь", "❓ Yordam"]))
async def button_help(message: Message, language: str):
    """
    Handle help button from menu.

    Args:
        message: Telegram message
        language: User language
    """
    await cmd_help(message, language)
