import logging
from aiogram import F
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from uk_management_bot.utils.helpers import get_text
from uk_management_bot.keyboards.address_management import get_address_management_menu

from ._router import router

logger = logging.getLogger(__name__)


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


# BUG-155 п.3 (закрыто 2026-08-18): у этого модуля своей группы состояний нет —
# он и есть универсальный запасной вариант. `StateFilter(None)` оставляет за ним
# ровно случай «состояния нет»: без этого он, будучи включённым раньше дворов
# (`main.py:392` против `:394`), перехватывал бы отмену их флоу вместо
# `address_moderation`. Молчаливый клик хуже неверного экрана, поэтому
# stateless-ветка сохранена, а не убрана.
@router.callback_query(StateFilter(None), F.data == "cancel_action")
async def cancel_generic_action(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Отмена текущего действия (универсальный обработчик)"""
    lang = language
    await state.clear()
    await callback.message.edit_text(get_text("address_apartments.handlers.action_cancelled", language=lang))

    await callback.message.answer(
        get_text("address_apartments.handlers.address_directory", language=lang),
        reply_markup=get_address_management_menu()
    )
