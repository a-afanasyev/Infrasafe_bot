import logging
from aiogram import F
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from uk_management_bot.utils.helpers import get_text
from uk_management_bot.keyboards.address_management import get_address_management_menu
from uk_management_bot.states.address_management import (
    ApartmentManagementStates,
    BuildingManagementStates,
)

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


# BUG-155 п.3 (закрыто 2026-08-18): этот модуль — универсальный обработчик
# отмены для справочника адресов, и он же держит stateless-случай.
#
# Кнопку `cancel_action` рендерит единственный генератор
# `get_cancel_keyboard_inline`, но ДЕСЯТЬ раз в шести модулях. Своя отмена есть
# только у модерации и дворов; создание здания, создание квартиры,
# автозаполнение и поиск квартиры своей — не имеют, и их отмена доставалась
# первому подошедшему: раньше `address_moderation` (показывал список
# МОДЕРАЦИИ), а после сужения его фильтра провалилась бы до
# `user_management/actions` (панель ПОЛЬЗОВАТЕЛЕЙ) — оба экрана из чужого
# раздела. Поэтому фильтр покрывает обе группы справочника плюс «состояния
# нет»; меню справочника адресов — общий родитель зданий и квартир.
#
# ⚠️ `StateFilter(None)` обязателен в списке: без stateless-ветки клик без
# состояния не обработается вовсе, а молчаливый клик хуже неверного экрана.
@router.callback_query(
    StateFilter(None, ApartmentManagementStates, BuildingManagementStates),
    F.data == "cancel_action",
)
async def cancel_generic_action(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Отмена текущего действия (универсальный обработчик)"""
    lang = language
    await state.clear()
    await callback.message.edit_text(get_text("address_apartments.handlers.action_cancelled", language=lang))

    await callback.message.answer(
        get_text("address_apartments.handlers.address_directory", language=lang),
        reply_markup=get_address_management_menu()
    )
