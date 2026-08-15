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
from uk_management_bot.keyboards.address_management import (
    get_apartments_list_keyboard,
    get_apartments_menu,
    get_cancel_keyboard_inline
)

from ._router import router

logger = logging.getLogger(__name__)


# ==========================================================================
# DTO для async-слоя: наружу из run_db выходят примитивы, не ORM-строки
# (у ORM-объекта за пределами worker-потока нет живой сессии → lazy-load
# сломается DetachedInstanceError).
# ==========================================================================

@dataclass(frozen=True)
class _BuildingOption:
    """Строка выбора здания: ровно то, что читает разметка в хендлере."""
    id: int
    address: str
    yard_name: Optional[str]
    apartments_count: int


# ==========================================================================
# Sync unit-of-work (AUD3-07/AUD5-ARCH-1): исполняются в worker-потоке через
# run_db; сессию открывает и закрывает run_db, event loop БД не трогает.
# Тела запросов перенесены байт-в-байт.
#
# Клавиатура списка квартир собирается ВНУТРИ юнита и уходит наружу готовой
# разметкой (канон допускает InlineKeyboardMarkup через границу run_db):
# get_apartments_list_keyboard читает lazy-property строки и канонический адрес
# через address_helpers.apartment_address, а DTO с полем full_address означал бы
# прямое чтение `full_address` в коде показа — его запрещает FS-11-гейт
# (tests/services/test_address_i18n.py).
# ==========================================================================

def _load_buildings_with_counts(db) -> list:
    """-> [_BuildingOption] для меню выбора здания (список квартир)."""
    from uk_management_bot.database.models import Building
    from sqlalchemy import select, func
    from sqlalchemy.orm import joinedload

    # Получаем все здания с количеством квартир
    result = db.execute(
        select(Building)
        .options(joinedload(Building.yard))
        .where(Building.is_active.is_(True))
        .order_by(Building.address)
    )
    buildings = result.unique().scalars().all()

    # Считаем количество квартир для каждого здания
    from uk_management_bot.database.models import Apartment
    options = []
    for building in buildings:
        apartments_count = db.execute(
            select(func.count(Apartment.id))
            .where(Apartment.building_id == building.id)
            .where(Apartment.is_active.is_(True))
        ).scalar()
        options.append(_BuildingOption(
            id=building.id,
            address=building.address,
            yard_name=building.yard.name if building.yard else None,
            apartments_count=apartments_count,
        ))
    return options


def _load_building_apartments(db, building_id: int, page: int) -> Optional[tuple]:
    """-> (building_address, total, разметка списка) | None (здание не найдено)."""
    building = AddressService.get_building_by_id(db, building_id, include_yard=True)
    if not building:
        return None

    apartments = AddressService.get_apartments_by_building(db, building_id, only_active=False)
    # ⚠️ Предсуществующий дефект (сохранён 1:1): в клавиатуру не пробрасывается
    # language — подписи кнопок и адреса всегда рендерятся на ru.
    return (
        building.address,
        len(apartments),
        get_apartments_list_keyboard(apartments, page=page, building_id=building_id),
    )


def _search_apartments_markup(db, query_text: str) -> tuple:
    """-> (total, разметка списка | None при пустом результате)."""
    apartments = AddressService.search_apartments(db, query_text, only_active=True)
    if not apartments:
        return 0, None
    # ⚠️ Предсуществующие дефекты (сохранены 1:1): (1) language не пробрасывается
    # в клавиатуру — результаты поиска всегда на ru; (2) без building_id
    # пагинация генерит callback `addr_apartments_page:<n>`, хендлера которого
    # в проекте нет — кнопки страниц поиска мертвы.
    return len(apartments), get_apartments_list_keyboard(apartments, page=0)


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР СПИСКА КВАРТИР
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "addr_apartments_list")
async def show_apartments_list(callback: CallbackQuery, state: FSMContext | None = None, language: str = "ru", *, _db=None):
    """Показать выбор здания для просмотра квартир"""
    # delete_apartment вызывает без FSM-состояния (state=None) — чистить нечего.
    if state is not None:
        await state.clear()
    lang = language

    try:
        buildings = await run_db(_load_buildings_with_counts, db=_db)

        if not buildings:
            await callback.message.edit_text(
                get_text("address_apartments.handlers.no_buildings", language=lang),
                reply_markup=get_apartments_menu(language=lang)
            )
            return

        text = get_text("address_apartments.handlers.select_building", language=lang).format(
            total=len(buildings)
        )

        # Используем клавиатуру со списком зданий
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton

        builder = InlineKeyboardBuilder()

        apt_suffix = get_text("address_apartments.handlers.apt_suffix", language=lang)

        # Добавляем кнопки для каждого здания
        for building in buildings:
            yard_info = f" ({building.yard_name})" if building.yard_name else ""
            apt_count = building.apartments_count
            apartments_info = f" - {apt_count} {apt_suffix}" if apt_count > 0 else ""

            # Обрезаем длинный адрес
            address_short = building.address[:50] + "..." if len(building.address) > 50 else building.address

            builder.row(
                InlineKeyboardButton(
                    text=f"{address_short}{yard_info}{apartments_info}",
                    callback_data=f"addr_apartments_by_building:{building.id}"
                )
            )

        # Добавляем кнопки управления
        builder.row(
            InlineKeyboardButton(text=get_text("address_apartments.handlers.btn_add_apartment", language=lang), callback_data="addr_apartment_create")
        )
        builder.row(
            InlineKeyboardButton(text=get_text("address_apartments.handlers.btn_search_apartment", language=lang), callback_data="addr_apartment_search")
        )
        builder.row(
            InlineKeyboardButton(text=get_text("address_apartments.handlers.btn_back", language=lang), callback_data="addr_menu")
        )

        await callback.message.edit_text(
            text,
            reply_markup=builder.as_markup()
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке списка зданий для квартир: {e}")
        await callback.answer(get_text("address_apartments.handlers.error_loading_data", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("addr_apartments_by_building:"))
async def show_apartments_by_building(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Показать квартиры конкретного здания"""
    building_id = int(callback.data.split(":")[1])
    lang = language

    try:
        loaded = await run_db(lambda s: _load_building_apartments(s, building_id, 0), db=_db)
        if loaded is None:
            await callback.answer(get_text("address_apartments.handlers.building_not_found", language=lang), show_alert=True)
            return

        building_address, total, markup = loaded

        text = get_text("address_apartments.handlers.building_apartments", language=lang).format(
            address=building_address,
            total=total
        )

        if not total:
            text += "\n" + get_text("address_apartments.handlers.apartments_list_empty", language=lang)

        await callback.message.edit_text(
            text,
            reply_markup=markup
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке квартир здания {building_id}: {e}")
        await callback.answer(get_text("address_apartments.handlers.error_loading_data", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("addr_apartments_by_building_page:"))
async def paginate_apartments_by_building(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Пагинация квартир конкретного здания"""
    parts = callback.data.split(":")
    building_id = int(parts[1])
    page = int(parts[2])
    lang = language

    try:
        loaded = await run_db(lambda s: _load_building_apartments(s, building_id, page), db=_db)
        if loaded is None:
            await callback.answer(get_text("address_apartments.handlers.building_not_found", language=lang), show_alert=True)
            return

        building_address, total, markup = loaded

        text = get_text("address_apartments.handlers.building_apartments", language=lang).format(
            address=building_address,
            total=total
        )

        if not total:
            text += "\n" + get_text("address_apartments.handlers.apartments_list_empty", language=lang)

        await callback.message.edit_text(
            text,
            reply_markup=markup
        )

    except Exception as e:
        logger.error(f"Ошибка при пагинации квартир здания {building_id}: {e}")
        await callback.answer(get_text("address_apartments.handlers.error_loading_data", language=lang), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ПОИСК КВАРТИР
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "addr_apartment_search")
async def start_apartment_search(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Начать поиск квартиры"""
    # TASK 17: Localize apartment search prompt
    lang = language

    await state.set_state(ApartmentManagementStates.waiting_for_apartment_search)

    message_text = (
        f"{get_text('requests.apartment_search_title', language=lang)}\n\n"
        f"{get_text('requests.apartment_search_prompt', language=lang)}\n\n"
        f"{get_text('requests.apartment_search_examples', language=lang)}"
    )

    await callback.message.edit_text(
        message_text,
        reply_markup=get_cancel_keyboard_inline()
    )


@router.message(StateFilter(ApartmentManagementStates.waiting_for_apartment_search))
async def process_apartment_search(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработка поискового запроса"""
    # TASK 17: Localize search results
    lang = language
    query = message.text.strip()

    if len(query) < 1:
        await message.answer(
            get_text('requests.search_query_too_short', language=lang)
        )
        return

    try:
        total, markup = await run_db(lambda s: _search_apartments_markup(s, query), db=_db)

        if not total:
            no_results_text = (
                f"{get_text('requests.search_results_title', language=lang)}\n\n"
                f"{get_text('requests.search_no_results', language=lang, query=query)}\n\n"
                f"{get_text('requests.search_no_results_action', language=lang)}"
            )
            await message.answer(
                no_results_text,
                reply_markup=get_apartments_list_keyboard([], page=0)
            )
            await state.clear()
            return

        text = (
            f"{get_text('requests.search_results_title', language=lang)}\n\n"
            f"{get_text('requests.search_query_label', language=lang, query=query)}\n"
            f"{get_text('requests.search_found_count', language=lang, count=total)}\n\n"
            f"{get_text('requests.search_select_apartment', language=lang)}"
        )

        await message.answer(
            text,
            reply_markup=markup
        )

        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка при поиске квартир: {e}")
        await message.answer(get_text("errors.search_error", language=lang))
