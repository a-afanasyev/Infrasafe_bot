"""
Language Helper Utilities - TASK 17 Phase 1
Provides utilities for language detection, user language management, and locale operations.

Features:
    - Dynamic language detection from Message/CallbackQuery
    - User language preference management
    - Plural support for localized strings
    - Language-aware formatting utilities
"""

from typing import Optional, Union, Dict, Any
from aiogram.types import Message, CallbackQuery, User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.user import User
from uk_management_bot.utils.helpers import load_locale, get_text


# Supported languages
SUPPORTED_LANGUAGES = ['ru', 'uz']
DEFAULT_LANGUAGE = 'ru'


async def get_user_language(
    user_id: int,
    session: AsyncSession,
    default: str = DEFAULT_LANGUAGE
) -> str:
    """
    Get user's preferred language from database.

    Args:
        user_id: Telegram user ID
        session: Database session
        default: Default language if user not found

    Returns:
        Language code ('ru' or 'uz')
    """
    from sqlalchemy import select

    try:
        result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()

        if user and user.language in SUPPORTED_LANGUAGES:
            return user.language

        return default

    except Exception as e:
        print(f"Error getting user language: {e}")
        return default


async def set_user_language(
    user_id: int,
    language: str,
    session: AsyncSession
) -> bool:
    """
    Set user's preferred language in database.

    Args:
        user_id: Telegram user ID
        language: Language code ('ru' or 'uz')
        session: Database session

    Returns:
        True if successful, False otherwise
    """
    from sqlalchemy import select, update

    if language not in SUPPORTED_LANGUAGES:
        print(f"Unsupported language: {language}")
        return False

    try:
        result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()

        if user:
            await session.execute(
                update(User)
                .where(User.telegram_id == user_id)
                .values(language=language)
            )
            await session.commit()
            return True

        return False

    except Exception as e:
        print(f"Error setting user language: {e}")
        await session.rollback()
        return False


def get_language_from_message(event: Union[Message, CallbackQuery]) -> str:
    """
    Extract language code from Telegram event (Message or CallbackQuery).

    Priority:
        1. User's language_code from Telegram
        2. Default language (ru)

    Args:
        event: Telegram Message or CallbackQuery

    Returns:
        Language code ('ru' or 'uz')
    """
    try:
        # Get Telegram user object
        telegram_user: Optional[TelegramUser] = None

        if isinstance(event, Message):
            telegram_user = event.from_user
        elif isinstance(event, CallbackQuery):
            telegram_user = event.from_user

        if telegram_user and hasattr(telegram_user, 'language_code'):
            lang = telegram_user.language_code

            # Map Telegram language codes to our supported languages
            if lang and lang.startswith('uz'):
                return 'uz'
            elif lang and lang.startswith('ru'):
                return 'ru'

        # Default
        return DEFAULT_LANGUAGE

    except Exception as e:
        print(f"Error detecting language from event: {e}")
        return DEFAULT_LANGUAGE


async def get_language_for_user(
    user_id: int,
    session: AsyncSession,
    event: Optional[Union[Message, CallbackQuery]] = None
) -> str:
    """
    Get user's language with fallback chain.

    Priority:
        1. User's saved language in database
        2. Language from Telegram event
        3. Default language

    Args:
        user_id: Telegram user ID
        session: Database session
        event: Optional Telegram event

    Returns:
        Language code ('ru' or 'uz')
    """
    # Try database first
    db_language = await get_user_language(user_id, session)
    if db_language != DEFAULT_LANGUAGE:
        return db_language

    # Try event
    if event:
        event_language = get_language_from_message(event)
        if event_language != DEFAULT_LANGUAGE:
            # Save to database for future
            await set_user_language(user_id, event_language, session)
            return event_language

    return DEFAULT_LANGUAGE


def get_text_with_plural(
    key: str,
    count: int,
    language: str = 'ru',
    **kwargs
) -> str:
    """
    Get localized text with plural support.

    Expects locale keys in format:
        "key": "singular form"
        "key_plural": "plural form"
        "key_plural_many": "many form" (for Russian 5, 6, 7... items)

    Russian plural rules:
        - 1, 21, 31... → singular (1 заявка)
        - 2-4, 22-24... → plural (2 заявки)
        - 5-20, 25-30... → many (5 заявок)

    Uzbek plural rules:
        - 1 → singular
        - 2+ → plural

    Args:
        key: Base locale key
        count: Number for plural selection
        language: Language code
        **kwargs: Format parameters

    Returns:
        Localized string with correct plural form

    Example:
        get_text_with_plural("requests.count", 5, language="ru")
        # Returns: "5 заявок" (if keys exist: requests.count, requests.count_plural, requests.count_plural_many)
    """
    try:
        locale = load_locale(language)

        # Determine plural form
        if language == 'ru':
            plural_key = _get_russian_plural_key(key, count)
        elif language == 'uz':
            plural_key = _get_uzbek_plural_key(key, count)
        else:
            plural_key = key

        # Get text for plural key
        text = get_text(plural_key, language, count=count, **kwargs)

        # If plural key not found, fallback to base key
        if text == plural_key:
            text = get_text(key, language, count=count, **kwargs)

        return text

    except Exception as e:
        print(f"Error in get_text_with_plural: {e}")
        return get_text(key, language, count=count, **kwargs)


def _get_russian_plural_key(base_key: str, count: int) -> str:
    """
    Get Russian plural key based on count.

    Russian plural rules:
        1, 21, 31, 41... → base_key
        2, 3, 4, 22, 23, 24... → base_key_plural
        5-20, 25-30, 35-40... → base_key_plural_many
    """
    abs_count = abs(count)
    last_digit = abs_count % 10
    last_two_digits = abs_count % 100

    # 11-14 are exceptions
    if 11 <= last_two_digits <= 14:
        return f"{base_key}_plural_many"

    # 1, 21, 31...
    if last_digit == 1:
        return base_key

    # 2-4, 22-24...
    if 2 <= last_digit <= 4:
        return f"{base_key}_plural"

    # 5-20, 25-30...
    return f"{base_key}_plural_many"


def _get_uzbek_plural_key(base_key: str, count: int) -> str:
    """
    Get Uzbek plural key based on count.

    Uzbek plural rules (simpler than Russian):
        1 → base_key
        2+ → base_key_plural
    """
    if abs(count) == 1:
        return base_key
    else:
        return f"{base_key}_plural"


def format_number_with_locale(
    number: Union[int, float],
    language: str = 'ru',
    decimals: int = 2
) -> str:
    """
    Format number according to locale conventions.

    Args:
        number: Number to format
        language: Language code
        decimals: Decimal places

    Returns:
        Formatted number string

    Example:
        format_number_with_locale(1234.56, "ru") → "1 234,56"
        format_number_with_locale(1234.56, "uz") → "1 234.56"
    """
    try:
        # Format with thousands separator
        if language == 'ru':
            # Russian format: 1 234,56
            formatted = f"{number:,.{decimals}f}"
            formatted = formatted.replace(',', ' ').replace('.', ',')
        elif language == 'uz':
            # Uzbek format: 1 234.56
            formatted = f"{number:,.{decimals}f}"
            formatted = formatted.replace(',', ' ')
        else:
            formatted = f"{number:,.{decimals}f}"

        return formatted

    except Exception as e:
        print(f"Error formatting number: {e}")
        return str(number)


def get_language_emoji(language: str) -> str:
    """
    Get flag emoji for language.

    Args:
        language: Language code

    Returns:
        Flag emoji
    """
    emoji_map = {
        'ru': '🇷🇺',
        'uz': '🇺🇿',
    }
    return emoji_map.get(language, '🌐')


def get_language_name(language: str, in_language: str = 'ru') -> str:
    """
    Get language name in specified language.

    Args:
        language: Language code to get name for
        in_language: Language to return name in

    Returns:
        Language name

    Example:
        get_language_name('uz', 'ru') → "Узбекский"
        get_language_name('ru', 'uz') → "Русча"
    """
    names = {
        'ru': {
            'ru': 'Русский',
            'uz': 'Узбекский'
        },
        'uz': {
            'ru': 'Русча',
            'uz': "O'zbekcha"
        }
    }

    return names.get(in_language, {}).get(language, language)


async def send_localized_message(
    event: Union[Message, CallbackQuery],
    key: str,
    session: AsyncSession,
    reply_markup: Any = None,
    **kwargs
) -> Message:
    """
    Send localized message to user.

    Automatically detects user language and sends message with correct translation.

    Args:
        event: Telegram Message or CallbackQuery
        key: Locale key
        session: Database session
        reply_markup: Optional keyboard markup
        **kwargs: Format parameters

    Returns:
        Sent message

    Example:
        await send_localized_message(
            message,
            "auth.welcome",
            session,
            name=user.full_name
        )
    """
    user_id = event.from_user.id
    language = await get_language_for_user(user_id, session, event)

    text = get_text(key, language, **kwargs)

    if isinstance(event, Message):
        return await event.answer(text, reply_markup=reply_markup)
    elif isinstance(event, CallbackQuery):
        if event.message:
            return await event.message.answer(text, reply_markup=reply_markup)
        else:
            await event.answer(text)
            return None


async def edit_localized_message(
    callback: CallbackQuery,
    key: str,
    session: AsyncSession,
    reply_markup: Any = None,
    **kwargs
) -> bool:
    """
    Edit message with localized text.

    Args:
        callback: CallbackQuery
        key: Locale key
        session: Database session
        reply_markup: Optional keyboard markup
        **kwargs: Format parameters

    Returns:
        True if successful

    Example:
        await edit_localized_message(
            callback,
            "requests.status_updated",
            session,
            status="Выполнена"
        )
    """
    user_id = callback.from_user.id
    language = await get_language_for_user(user_id, session, callback)

    text = get_text(key, language, **kwargs)

    try:
        if callback.message:
            await callback.message.edit_text(text, reply_markup=reply_markup)
            return True
        return False
    except Exception as e:
        print(f"Error editing message: {e}")
        return False


def validate_language_code(language: str) -> bool:
    """
    Validate if language code is supported.

    Args:
        language: Language code

    Returns:
        True if supported
    """
    return language in SUPPORTED_LANGUAGES


def get_available_languages() -> Dict[str, str]:
    """
    Get all available languages with names.

    Returns:
        Dict mapping language codes to names
    """
    return {
        'ru': get_language_name('ru', 'ru'),
        'uz': get_language_name('uz', 'uz')
    }
