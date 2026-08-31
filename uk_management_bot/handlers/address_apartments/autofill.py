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
from uk_management_bot.utils.address_helpers import localize_address_error
from uk_management_bot.keyboards.address_management import (
    get_confirmation_keyboard,
    get_cancel_keyboard_inline,
    get_address_management_menu
)

from ._router import router

logger = logging.getLogger(__name__)


# ==========================================================================
# DTO для async-слоя: наружу из run_db выходят примитивы, не ORM-строки.
# ==========================================================================

@dataclass(frozen=True)
class _BuildingHead:
    """Шапка здания для приглашения к автозаполнению."""
    address: str
    yard_name: Optional[str]


# ==========================================================================
# Sync unit-of-work (AUD3-07/AUD5-ARCH-1): исполняются в worker-потоке через
# run_db. bulk_create_apartments сюда НЕ входит: это async-метод AddressService
# с собственной async-сессией (и собственным commit в services/addresses/core),
# параметр session им не используется — хендлер await'ит его с session=None.
# ==========================================================================

def _load_building_head(db, building_id: int) -> Optional[_BuildingHead]:
    """-> _BuildingHead | None (None — здание не найдено)."""
    building = AddressService.get_building_by_id(db, building_id, include_yard=True)
    if not building:
        return None
    return _BuildingHead(
        address=building.address,
        yard_name=building.yard.name if building.yard else None,
    )


def _user_id_by_tg(db, telegram_id: int) -> Optional[int]:
    """-> users.id | None. Запрос перенесён байт-в-байт."""
    from uk_management_bot.database.models import User
    from sqlalchemy import select

    user = db.execute(
        select(User).where(User.telegram_id == telegram_id)
    ).scalar_one_or_none()
    return user.id if user else None


# ═══════════════════════════════════════════════════════════════════════════════
# АВТОЗАПОЛНЕНИЕ КВАРТИР
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_building_autofill:"))
async def start_autofill_apartments(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Начать процесс автозаполнения квартир для здания"""
    building_id = int(callback.data.split(":")[1])
    lang = language

    try:
        building = await run_db(lambda s: _load_building_head(s, building_id), db=_db)
        if building is None:
            await callback.answer(get_text("address_apartments.handlers.building_not_found", language=lang), show_alert=True)
            return

        # Сохраняем ID здания в state
        await state.update_data(autofill_building_id=building_id)
        await state.set_state(ApartmentManagementStates.waiting_for_autofill_range)

        yard_line = f"<b>{get_text('address_apartments.handlers.yard_label', language=lang)}</b> {building.yard_name}" if building.yard_name else ""

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
    # BUG-156 п.6: нетекстовое сообщение (фото/стикер) в FSM-шаге давало
    # message.text is None -> AttributeError мимо обработчиков ошибок.
    if not message.text:
        await message.answer(get_text("errors.invalid_input", language=lang))
        return
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
        # BUG-147: рендер по коду ошибки на языке пользователя (сырой русский
        # str(e) — только фолбэк для plain-ValueError без кода).
        await message.answer(
            get_text("address_apartments.handlers.range_parse_error", language=lang).format(
                error=_localize_range_error(e, lang)
            )
        )
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
async def confirm_autofill_apartments(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Подтвердить и выполнить автозаполнение"""
    data = await state.get_data()
    building_id = data.get("autofill_building_id")
    apartment_numbers = data.get("apartment_numbers", [])

    lang = language

    if not building_id or not apartment_numbers:
        await callback.answer(get_text("address_apartments.handlers.autofill_data_not_found", language=lang), show_alert=True)
        await state.clear()
        return

    try:
        # Получаем user.id из базы данных по telegram_id
        user_id = await run_db(lambda s: _user_id_by_tg(s, callback.from_user.id), db=_db)

        if user_id is None:
            await callback.answer(get_text("address_apartments.handlers.autofill_user_not_found", language=lang), show_alert=True)
            await state.clear()
            return

        # Выполняем массовое создание квартир
        # bulk_create_apartments — async-метод с собственной async-сессией;
        # параметр session им не используется. Прежние db.commit()/db.rollback()
        # на sync-сессии хендлера были no-op: в ней выполнялся только SELECT
        # пользователя, а квартиры коммитит сам сервис (services/addresses/core).
        created_count, skipped_count, errors = await AddressService.bulk_create_apartments(
            None,
            building_id=building_id,
            apartment_numbers=apartment_numbers,
            created_by=user_id  # Используем user.id вместо telegram_id
        )

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

class ApartmentRangeError(ValueError):
    """BUG-147: локализуемая ошибка парсинга диапазона квартир.

    Несёт код ошибки (ключ в address_apartments.handlers.*) и параметры для
    format; str(exc) остаётся русским текстом — фолбэк для логов.
    """

    def __init__(self, message: str, code: str, **params):
        super().__init__(message)
        self.code = code
        self.params = params


def _localize_range_error(exc: ValueError, lang: str) -> str:
    """Рендерит ошибку диапазона на языке пользователя по коду ошибки."""
    code = getattr(exc, "code", None)
    if not code:
        return str(exc)
    return get_text(
        f"address_apartments.handlers.{code}", language=lang
    ).format(**getattr(exc, "params", {}))


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
            # BUG-139: проверка start>end вынесена из try — раньше её ValueError
            # ловился тем же except и оборачивался второй раз (вложенная ошибка).
            try:
                start, end = part.split("-")
                start_num = int(start.strip())
                end_num = int(end.strip())
            except ValueError:
                raise ApartmentRangeError(
                    f"Некорректный диапазон '{part}'",
                    code="range_invalid_chunk", part=part,
                )

            if start_num > end_num:
                raise ApartmentRangeError(
                    f"Некорректный диапазон: {start_num} > {end_num}",
                    code="range_reversed", start=start_num, end=end_num,
                )

            for num in range(start_num, end_num + 1):
                result.add(str(num))
        else:
            # Это одиночное число
            try:
                num = int(part)
                result.add(str(num))
            except ValueError:
                raise ApartmentRangeError(
                    f"Некорректный номер квартиры: '{part}'",
                    code="range_invalid_number", part=part,
                )

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
