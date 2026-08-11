import logging
from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from uk_management_bot.database.session import session_scope
from uk_management_bot.services.address_service import AddressService
from uk_management_bot.states.address_management import ApartmentManagementStates
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.address_helpers import localize_address_error
from uk_management_bot.keyboards.address_management import (
    get_confirmation_keyboard,
    get_cancel_keyboard_inline,
    get_address_management_menu
)

from ._router import router

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# АВТОЗАПОЛНЕНИЕ КВАРТИР
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_building_autofill:"))
async def start_autofill_apartments(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Начать процесс автозаполнения квартир для здания"""
    building_id = int(callback.data.split(":")[1])
    lang = language

    try:
        with session_scope() as db:
            building = AddressService.get_building_by_id(db, building_id, include_yard=True)
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

    # ARC-05: with оборачивает весь try/except, чтобы db оставался открыт для
    # db.rollback() в except (session_scope закрывает сессию только на выходе из with).
    with session_scope() as db:
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
                    text += f"• {localize_address_error(error, lang)}\n"
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
