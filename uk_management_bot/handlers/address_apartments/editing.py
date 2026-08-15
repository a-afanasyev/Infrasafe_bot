import logging
from dataclasses import dataclass
from typing import Optional
from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from uk_management_bot.database.session import run_db
from uk_management_bot.services.address_service import AddressService
from uk_management_bot.states.address_management import ApartmentManagementStates
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.address_helpers import apartment_address
from uk_management_bot.keyboards.address_management import (
    get_apartment_edit_keyboard,
    get_confirmation_keyboard
)
from uk_management_bot.keyboards.base import get_cancel_keyboard
from uk_management_bot.keyboards.base import get_main_keyboard_for_role

from ._router import router
from .details import show_apartment_details
from .viewing import show_apartments_list

logger = logging.getLogger(__name__)


# ==========================================================================
# DTO для async-слоя: наружу из run_db выходят примитивы, не ORM-строки.
# ==========================================================================

@dataclass(frozen=True)
class _ApartmentStatus:
    """Состояние квартиры для переключения активности."""
    is_active: bool


@dataclass(frozen=True)
class _ApartmentDeleteCard:
    """Карточка подтверждения удаления. ``full_address`` — property модели,
    читающая lazy-связь building, поэтому вычисляется внутри юнита;
    apartment_address() локализует её уже в async-слое (это рендер, не БД)."""
    residents_count: int
    full_address: str


# ==========================================================================
# Sync unit-of-work (AUD3-07/AUD5-ARCH-1): исполняются в worker-потоке через
# run_db. Мутации квартир (update_apartment/delete_apartment) сюда НЕ входят:
# это async-методы AddressService с собственной async-сессией
# (services/address_service/apartments.py) — параметр session ими не
# используется ни на одном пути, поэтому хендлер await'ит их с session=None.
# ==========================================================================

def _load_apartment_status(db, apartment_id: int) -> Optional[_ApartmentStatus]:
    """-> _ApartmentStatus | None (None — квартира не найдена)."""
    apartment = AddressService.get_apartment_by_id(db, apartment_id)
    if not apartment:
        return None
    return _ApartmentStatus(is_active=apartment.is_active)


def _load_apartment_delete_card(db, apartment_id: int) -> Optional[_ApartmentDeleteCard]:
    """-> _ApartmentDeleteCard | None (None — квартира не найдена)."""
    apartment = AddressService.get_apartment_by_id(db, apartment_id, include_building=True)
    if not apartment:
        return None
    return _ApartmentDeleteCard(
        residents_count=apartment.residents_count if hasattr(apartment, 'residents_count') else 0,
        full_address=apartment.full_address,
    )


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
async def toggle_apartment_status(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Переключить активность квартиры"""
    apartment_id = int(callback.data.split(":")[1])
    lang = language

    try:
        status = await run_db(lambda s: _load_apartment_status(s, apartment_id), db=_db)
        if status is None:
            await callback.answer(get_text("address_apartments.handlers.apartment_not_found", language=lang), show_alert=True)
            return

        new_status = not status.is_active
        # update_apartment — async-метод с собственной async-сессией; параметр
        # session им не используется.
        apartment, error = await AddressService.update_apartment(
            session=None,
            apartment_id=apartment_id,
            is_active=new_status
        )

        if error:
            # ⚠️ Предсуществующий дефект (сохранён 1:1): наружу уходит сырой код
            # ошибки сервиса ("save_failed"/"not_found"), без localize_address_error —
            # ср. address_buildings.toggle_building_status.
            await callback.answer(get_text("address_apartments.handlers.error_with_details", language=lang).format(error=error), show_alert=True)
            return

        status_text = get_text("address_apartments.handlers.status_activated", language=lang) if new_status else get_text("address_apartments.handlers.status_deactivated", language=lang)
        await callback.answer(get_text("address_apartments.handlers.apartment_status_changed", language=lang).format(status=status_text))

        # Обновляем отображение (BUG-139: язык пробрасываем, иначе карточка ru)
        # Тестовый seam _db через границу модулей не прокидываем: в проде он
        # всегда None, а тесты патчат сам вызов show_apartment_details.
        await show_apartment_details(callback, language=lang)

    except Exception as e:
        logger.error(f"Ошибка при переключении статуса квартиры: {e}")
        await callback.answer(get_text("address_apartments.handlers.error_status_change", language=lang), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# УДАЛЕНИЕ КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_apartment_delete:"))
async def confirm_apartment_deletion(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Подтверждение удаления квартиры"""
    apartment_id = int(callback.data.split(":")[1])
    lang = language

    try:
        card = await run_db(lambda s: _load_apartment_delete_card(s, apartment_id), db=_db)
        if card is None:
            await callback.answer(get_text("address_apartments.handlers.apartment_not_found", language=lang), show_alert=True)
            return

        residents_count = card.residents_count

        warning = ""
        if residents_count > 0:
            warning = "\n\n" + get_text("address_apartments.handlers.delete_warning_residents", language=lang).format(count=residents_count)

        full_address = apartment_address(card, lang)

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


@router.callback_query(F.data.startswith("addr_apartment_delete_confirm:"))
async def delete_apartment(callback: CallbackQuery, language: str = "ru"):
    """Удаление квартиры"""
    apartment_id = int(callback.data.split(":")[1])
    lang = language

    try:
        # delete_apartment — async-метод с собственной async-сессией; параметр
        # session им не используется. Sync-SQL здесь нет — run_db не нужен.
        success, error = await AddressService.delete_apartment(None, apartment_id)

        if not success:
            # ⚠️ Предсуществующий дефект (сохранён 1:1): в текст подставляется
            # сырой код ошибки сервиса, без localize_address_error.
            await callback.answer(get_text("address_apartments.handlers.delete_error", language=lang).format(error=error), show_alert=True)
            return

        await callback.message.edit_text(
            get_text("address_apartments.handlers.delete_success", language=lang)
        )

        logger.info(f"Квартира {apartment_id} удалена пользователем {callback.from_user.id}")

        # Показываем список квартир (BUG-139: язык пробрасываем, иначе список ru)
        await show_apartments_list(callback, None, language=lang)

    except Exception as e:
        logger.error(f"Ошибка при удалении квартиры: {e}")
        await callback.answer(get_text("address_apartments.handlers.error_deletion", language=lang), show_alert=True)


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
async def process_new_apartment_area(message: Message, state: FSMContext, language: str = "ru",
                                     roles: list = None, active_role: str = None):
    """Обработка новой площади квартиры"""
    # BUG-139: роли из middleware-контекста (DI), не хардкод "manager".
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

    try:
        # update_apartment — async-метод с собственной async-сессией; параметр
        # session им не используется. Sync-SQL здесь нет — run_db не нужен.
        apartment, error = await AddressService.update_apartment(
            session=None,
            apartment_id=apartment_id,
            area=area
        )

        if error:
            # ⚠️ Предсуществующий дефект (сохранён 1:1): сырой код ошибки
            # сервиса в тексте пользователю, без localize_address_error.
            await message.answer(
                get_text("address_apartments.handlers.area_update_error", language=lang).format(error=error),
                reply_markup=get_main_keyboard_for_role(active_role or "manager", roles or ["manager"], language=lang)
            )
            await state.clear()
            return

        await message.answer(
            get_text("address_apartments.handlers.area_update_success", language=lang).format(area=area),
            reply_markup=get_main_keyboard_for_role(active_role or "manager", roles or ["manager"], language=lang)
        )

        logger.info(f"Площадь квартиры {apartment_id} обновлена на {area} кв.м пользователем {message.from_user.id}")

    except Exception:
        logger.exception("update apartment area handler failed")
        await message.answer(
            get_text("address_apartments.handlers.area_update_exception", language=lang),
            reply_markup=get_main_keyboard_for_role(active_role or "manager", roles or ["manager"], language=lang)
        )
    finally:
        await state.clear()
