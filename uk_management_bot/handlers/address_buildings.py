"""
Обработчики для управления зданиями (Building Management)

Функционал:
- Просмотр списка зданий
- Создание нового здания
- Просмотр детальной информации о здании
- Редактирование здания
- Удаление (деактивация) здания
- Фильтрация зданий по двору
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from uk_management_bot.database.session import run_db
from uk_management_bot.handlers._role_gate import RoleGate
from uk_management_bot.services.address_service import AddressService
from uk_management_bot.states.address_management import BuildingManagementStates
from uk_management_bot.keyboards.address_management import (
    get_buildings_list_keyboard,
    get_building_details_keyboard,
    get_building_edit_keyboard,
    get_confirmation_keyboard,
    get_skip_or_cancel_keyboard,
    get_cancel_keyboard_inline,
    get_user_apartment_selection_keyboard,
    get_address_management_menu
)
from uk_management_bot.keyboards.base import get_main_keyboard_for_role
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.address_helpers import localize_address_error
from uk_management_bot.utils.button_texts import get_skip_texts, get_cancel_texts

logger = logging.getLogger(__name__)

router = Router()
# Гейт всего роутера (см. handlers/_role_gate.py): отказ = UNHANDLED, транзит цел.
router.callback_query.filter(RoleGate())
router.message.filter(RoleGate())

SKIP_TEXTS = get_skip_texts()
CANCEL_TEXTS = get_cancel_texts()


# ==========================================================================
# DTO для async-слоя: наружу из run_db выходят примитивы, не ORM-строки
# (у ORM-объекта за пределами worker-потока нет живой сессии).
# ==========================================================================

@dataclass(frozen=True)
class _BuildingRow:
    """Строка списка зданий — ровно те атрибуты, что читает
    get_buildings_list_keyboard (hasattr(., 'apartments_count') остаётся True,
    как у property модели Building)."""
    id: int
    address: str
    is_active: bool
    apartments_count: int


@dataclass(frozen=True)
class _BuildingView:
    """Карточка здания для show_building_details / toggle / confirm-delete."""
    id: int
    address: str
    is_active: bool
    gps_latitude: Optional[float]
    gps_longitude: Optional[float]
    entrance_count: Optional[int]
    floor_count: Optional[int]
    apartments_count: int
    yard_name: Optional[str]
    description: Optional[str]
    created_at: Optional[datetime]


@dataclass(frozen=True)
class _YardOption:
    """Пункт выбора двора для get_user_apartment_selection_keyboard."""
    id: int
    name: str


# ==========================================================================
# Sync unit-of-work (AUD3-07/AUD5-ARCH-1): исполняются в worker-потоке через
# run_db; сессию открывает и закрывает run_db, event loop БД не трогает.
# Мутации зданий (create/update/delete_building) сюда НЕ входят: это
# async-методы AddressService с собственной async-сессией — их хендлер
# await'ит напрямую (sync-параметр session ими не используется).
# ==========================================================================

def _user_id_by_tg(db, telegram_id: int) -> Optional[int]:
    from uk_management_bot.database.models.user import User
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    return user.id if user else None


def _building_row_from(building) -> _BuildingRow:
    return _BuildingRow(
        id=building.id,
        address=building.address,
        is_active=building.is_active,
        apartments_count=building.apartments_count if hasattr(building, 'apartments_count') else len(building.apartments),
    )


def _load_buildings_overview(db) -> list:
    """-> [_BuildingRow] для списка/страницы зданий.

    BUG-151 п.5: без фильтра is_active (паттерн списка дворов, only_active=False)
    — неактивные здания видны с ❌, заголовок «всего/активных» различает их."""
    from uk_management_bot.database.models import Building
    from sqlalchemy import select

    result = db.execute(
        select(Building)
        .order_by(Building.address)
    )
    buildings = result.scalars().all()
    return [_building_row_from(b) for b in buildings]


def _load_yard_buildings(db, yard_id: int) -> Optional[tuple]:
    """-> (yard_name, [_BuildingRow]) | None (None — двор не найден)."""
    yard = AddressService.get_yard_by_id(db, yard_id)
    if not yard:
        return None
    buildings = AddressService.get_buildings_by_yard(db, yard_id, only_active=False)
    return yard.name, [_building_row_from(b) for b in buildings]


def _load_building_view(db, building_id: int, include_yard: bool = False) -> Optional[_BuildingView]:
    """-> _BuildingView | None (None — здание не найдено)."""
    building = AddressService.get_building_by_id(db, building_id, include_yard=include_yard)
    if not building:
        return None
    return _BuildingView(
        id=building.id,
        address=building.address,
        is_active=building.is_active,
        gps_latitude=building.gps_latitude,
        gps_longitude=building.gps_longitude,
        entrance_count=building.entrance_count,
        floor_count=building.floor_count,
        apartments_count=building.apartments_count if hasattr(building, 'apartments_count') else len(building.apartments),
        yard_name=(building.yard.name if building.yard else None) if include_yard else None,
        description=building.description,
        created_at=building.created_at,
    )


def _load_active_yards(db) -> list:
    """-> [_YardOption] для выбора двора при создании здания."""
    yards = AddressService.get_all_yards(db, only_active=True)
    return [_YardOption(id=yard.id, name=yard.name) for yard in yards]


def _load_yard_name(db, yard_id: int) -> Optional[str]:
    yard = AddressService.get_yard_by_id(db, yard_id)
    return yard.name if yard else None


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР СПИСКА ЗДАНИЙ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "addr_buildings_list")
async def show_buildings_list(callback: CallbackQuery, state: Optional[FSMContext] = None, language: str = "ru", *, _db=None):
    """Показать список всех зданий"""
    if state is not None:
        await state.clear()

    try:
        buildings = await run_db(_load_buildings_overview, db=_db)

        if not buildings:
            lang = language
            await callback.message.edit_text(
                get_text("address_buildings.handlers.buildings_list_empty", language=lang),
                reply_markup=get_buildings_list_keyboard([], page=0)
            )
            return

        lang = language
        active_count = sum(1 for b in buildings if b.is_active)
        text = get_text("address_buildings.handlers.buildings_list_title", language=lang).format(
            total=len(buildings), active=active_count
        )

        await callback.message.edit_text(
            text,
            reply_markup=get_buildings_list_keyboard(buildings, page=0)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке списка зданий: {e}")
        lang = language
        await callback.answer(get_text("address_buildings.handlers.error_loading_data", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("addr_buildings_page:"))
async def show_buildings_page(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Показать конкретную страницу списка зданий"""
    page = int(callback.data.split(":")[1])

    try:
        buildings = await run_db(_load_buildings_overview, db=_db)

        lang = language
        text = get_text("address_buildings.handlers.buildings_list_page", language=lang).format(page=page + 1, total=len(buildings))

        await callback.message.edit_text(
            text,
            reply_markup=get_buildings_list_keyboard(buildings, page=page)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке страницы зданий: {e}")
        lang = language
        await callback.answer(get_text("address_buildings.handlers.error_loading_data", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("addr_buildings_by_yard:"))
async def show_buildings_by_yard(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Показать здания конкретного двора"""
    yard_id = int(callback.data.split(":")[1])

    # WR-06 (класс): дефолт ДО try. `lang` присваивается после db-фазы,
    # и если она бросит (недоступна БД), `except` ниже сошлётся
    # на несвязанное имя → NameError вместо сообщения об ошибке.
    lang = "ru"
    try:
        loaded = await run_db(lambda s: _load_yard_buildings(s, yard_id), db=_db)
        lang = language
        if loaded is None:
            await callback.answer(get_text("address_buildings.handlers.yard_not_found", language=lang), show_alert=True)
            return

        yard_name, buildings = loaded

        text = get_text("address_buildings.handlers.buildings_by_yard", language=lang).format(yard=yard_name, total=len(buildings))

        if not buildings:
            text += "\n" + get_text("address_buildings.handlers.buildings_list_empty_short", language=lang)

        await callback.message.edit_text(
            text,
            reply_markup=get_buildings_list_keyboard(buildings, page=0, yard_id=yard_id)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке зданий двора {yard_id}: {e}")
        await callback.answer(get_text("address_buildings.handlers.error_loading_data", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("addr_buildings_by_yard_page:"))
async def show_buildings_by_yard_page(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Страница списка зданий двора (BUG-151 п.6).

    Клавиатура генерила `addr_buildings_by_yard_page:<yard_id>:<page>` всегда,
    а хендлера не было — кнопки страниц по двору были мертвы (silent click).
    Зеркало пары show_buildings_by_yard / show_buildings_page."""
    _, raw_yard_id, raw_page = callback.data.split(":")
    yard_id, page = int(raw_yard_id), int(raw_page)

    lang = "ru"  # WR-06: дефолт ДО try (см. show_buildings_by_yard)
    try:
        loaded = await run_db(lambda s: _load_yard_buildings(s, yard_id), db=_db)
        lang = language
        if loaded is None:
            await callback.answer(get_text("address_buildings.handlers.yard_not_found", language=lang), show_alert=True)
            return

        yard_name, buildings = loaded
        text = get_text("address_buildings.handlers.buildings_by_yard", language=lang).format(yard=yard_name, total=len(buildings))

        await callback.message.edit_text(
            text,
            reply_markup=get_buildings_list_keyboard(buildings, page=page, yard_id=yard_id)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке страницы зданий двора {yard_id}: {e}")
        await callback.answer(get_text("address_buildings.handlers.error_loading_data", language=lang), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР ДЕТАЛЬНОЙ ИНФОРМАЦИИ О ЗДАНИИ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_building_view:"))
async def show_building_details(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Показать детальную информацию о здании"""
    building_id = int(callback.data.split(":")[1])

    # WR-06 (класс): дефолт ДО try. `lang` присваивается после db-фазы,
    # и если она бросит (недоступна БД), `except` ниже сошлётся
    # на несвязанное имя → NameError вместо сообщения об ошибке.
    lang = "ru"
    try:
        building = await run_db(lambda s: _load_building_view(s, building_id, include_yard=True), db=_db)
        lang = language

        if not building:
            await callback.answer(get_text("address_buildings.handlers.building_not_found", language=lang), show_alert=True)
            return

        status = get_text("address_buildings.handlers.status_active", language=lang) if building.is_active else get_text("address_buildings.handlers.status_inactive", language=lang)
        # BUG-151 п.7: координата 0.0 легитимна — сравнение по is not None.
        gps = f"📍 {building.gps_latitude}, {building.gps_longitude}" if building.gps_latitude is not None and building.gps_longitude is not None else get_text("address_buildings.handlers.gps_not_set", language=lang)
        apartments_count = building.apartments_count
        yard_name = building.yard_name if building.yard_name else get_text("address_buildings.handlers.not_specified", language=lang)

        text = get_text("address_buildings.handlers.building_details", language=lang).format(
            address=building.address, yard=yard_name, status=status,
            entrances=building.entrance_count, floors=building.floor_count,
            apartments=apartments_count, gps=gps
        )

        if building.description:
            text += get_text("address_buildings.handlers.description_label", language=lang).format(description=building.description)

        if building.created_at:
            text += get_text("address_buildings.handlers.created_label", language=lang).format(date=building.created_at.strftime('%d.%m.%Y %H:%M'))

        await callback.message.edit_text(
            text,
            reply_markup=get_building_details_keyboard(building_id)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке информации о здании {building_id}: {e}")
        await callback.answer(get_text("address_buildings.handlers.error_loading_data", language=lang), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# СОЗДАНИЕ НОВОГО ЗДАНИЯ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "addr_building_create")
async def start_building_creation(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Начать создание нового здания - выбор двора"""
    await state.clear()

    # WR-06 (класс): дефолт ДО try. `lang` присваивается после db-фазы,
    # и если она бросит (недоступна БД), `except` ниже сошлётся
    # на несвязанное имя → NameError вместо сообщения об ошибке.
    lang = "ru"
    try:
        yards = await run_db(_load_active_yards, db=_db)

        lang = language
        if not yards:
            await callback.message.edit_text(
                get_text("address_buildings.handlers.no_yards_available", language=lang),
                reply_markup=get_cancel_keyboard_inline()
            )
            return

        await state.set_state(BuildingManagementStates.waiting_for_yard_selection)

        await callback.message.edit_text(
            get_text("address_buildings.handlers.create_building_step1", language=lang),
            reply_markup=get_user_apartment_selection_keyboard(yards, "yard", "building_create_yard", cancel_callback="addr_cancel_selection")
        )

    except Exception as e:
        logger.error(f"Ошибка при начале создания здания: {e}")
        await callback.answer(get_text("address_buildings.handlers.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("building_create_yard:"))
async def process_building_yard_selection(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработка выбора двора для нового здания"""
    yard_id = int(callback.data.split(":")[1])

    lang = language
    loaded_name = await run_db(lambda s: _load_yard_name(s, yard_id), db=_db)
    yard_name = loaded_name if loaded_name else get_text("address_buildings.handlers.unknown_yard", language=lang)

    await state.update_data(yard_id=yard_id, yard_name=yard_name)
    await state.set_state(BuildingManagementStates.waiting_for_building_address)

    await callback.message.edit_text(
        get_text("address_buildings.handlers.create_building_step2", language=lang).format(yard=yard_name),
        reply_markup=get_cancel_keyboard_inline()
    )


@router.message(StateFilter(BuildingManagementStates.waiting_for_building_address))
async def process_building_address(message: Message, state: FSMContext, language: str = "ru"):
    """Обработка адреса здания"""
    address = message.text.strip()

    lang = language
    if len(address) < 5:
        await message.answer(
            get_text("address_buildings.handlers.address_too_short", language=lang)
        )
        return

    if len(address) > 300:
        await message.answer(
            get_text("address_buildings.handlers.address_too_long", language=lang)
        )
        return

    await state.update_data(address=address)
    await state.set_state(BuildingManagementStates.waiting_for_floor_count)

    data = await state.get_data()
    await message.answer(
        get_text("address_buildings.handlers.create_building_step3", language=lang).format(
            yard=data.get('yard_name', ''), address=address
        ),
        reply_markup=get_skip_or_cancel_keyboard()
    )


@router.message(StateFilter(BuildingManagementStates.waiting_for_entrance_count))
async def process_entrance_count(message: Message, state: FSMContext, language: str = "ru"):
    """Обработка количества подъездов"""
    if message.text in SKIP_TEXTS:
        entrance_count = 1
    elif message.text in CANCEL_TEXTS:
        lang = language
        await state.clear()
        await message.answer(
            get_text("address_buildings.handlers.building_creation_cancelled", language=lang),
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
        )
        return
    else:
        lang = language
        try:
            entrance_count = int(message.text.strip())
            if entrance_count < 1 or entrance_count > 50:
                raise ValueError("out of range")
        except ValueError:
            await message.answer(
                get_text("address_buildings.handlers.invalid_number_1_50", language=lang)
            )
            return

    lang = language
    await state.update_data(entrance_count=entrance_count)
    await state.set_state(BuildingManagementStates.waiting_for_building_gps)

    await message.answer(
        get_text("address_buildings.handlers.create_building_step5", language=lang),
        reply_markup=get_skip_or_cancel_keyboard()
    )


@router.message(StateFilter(BuildingManagementStates.waiting_for_floor_count))
async def process_floor_count(message: Message, state: FSMContext, language: str = "ru"):
    """Обработка количества этажей"""
    lang = language
    if message.text in SKIP_TEXTS:
        floor_count = 1
    elif message.text in CANCEL_TEXTS:
        await state.clear()
        await message.answer(
            get_text("address_buildings.handlers.building_creation_cancelled", language=lang),
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
        )
        return
    else:
        try:
            floor_count = int(message.text.strip())
            if floor_count < 1 or floor_count > 100:
                raise ValueError("out of range")
        except ValueError:
            await message.answer(
                get_text("address_buildings.handlers.invalid_number_1_100", language=lang)
            )
            return

    await state.update_data(floor_count=floor_count)
    await state.set_state(BuildingManagementStates.waiting_for_entrance_count)

    data = await state.get_data()
    await message.answer(
        get_text("address_buildings.handlers.create_building_step4", language=lang).format(
            yard=data.get('yard_name', ''), address=data.get('address', ''), floors=floor_count
        ),
        reply_markup=get_skip_or_cancel_keyboard()
    )


@router.message(StateFilter(BuildingManagementStates.waiting_for_building_gps))
async def process_building_gps(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработка GPS координат здания и создание записи"""
    gps_latitude = None
    gps_longitude = None

    lang = language
    if message.text in SKIP_TEXTS:
        pass
    elif message.text in CANCEL_TEXTS:
        await state.clear()
        await message.answer(
            get_text("address_buildings.handlers.building_creation_cancelled", language=lang),
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
        )
        return
    else:
        try:
            parts = message.text.strip().replace(" ", "").split(",")
            if len(parts) != 2:
                raise ValueError("invalid format")

            gps_latitude = float(parts[0])
            gps_longitude = float(parts[1])

            if not (-90 <= gps_latitude <= 90) or not (-180 <= gps_longitude <= 180):
                raise ValueError("out of range")

        except ValueError:
            await message.answer(
                get_text("address_buildings.handlers.invalid_gps_format", language=lang)
            )
            return

    # Сохраняем здание в базу
    data = await state.get_data()

    try:
        # Получаем user.id из базы данных (не telegram_id!)
        user_id = await run_db(lambda s: _user_id_by_tg(s, message.from_user.id), db=_db)
        if user_id is None:
            await message.answer(
                get_text("address_buildings.handlers.user_not_found", language=lang),
                reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
            )
            await state.clear()
            return

        # create_building — async-метод с собственной async-сессией; параметр
        # session им не используется (пишет через _async_session()).
        building, error = await AddressService.create_building(
            session=None,
            address=data['address'],
            yard_id=data['yard_id'],
            created_by=user_id,  # ИСПРАВЛЕНО: используем user.id из БД, а не telegram_id
            gps_latitude=gps_latitude,
            gps_longitude=gps_longitude,
            entrance_count=data.get('entrance_count', 1),
            floor_count=data.get('floor_count', 1)
        )

        if error:
            await message.answer(
                get_text("address_buildings.handlers.building_creation_error", language=lang).format(error=error),
                reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
            )
            await state.clear()
            return

        # BUG-151 п.7: координата 0.0 легитимна — сравнение по is not None.
        gps_info = f"📍 {gps_latitude}, {gps_longitude}" if gps_latitude is not None and gps_longitude is not None else get_text("address_buildings.handlers.gps_not_set", language=lang)

        await message.answer(
            get_text("address_buildings.handlers.building_created_success", language=lang).format(
                address=building.address, yard=data.get('yard_name', ''),
                entrances=building.entrance_count, floors=building.floor_count, gps=gps_info
            ),
            reply_markup=get_address_management_menu()
        )

        logger.info(f"Создано новое здание: {building.address} (ID: {building.id}) пользователем {message.from_user.id}")

    except Exception:
        logger.exception("create building handler failed")
        await message.answer(
            get_text("address_buildings.handlers.operation_failed", language=lang),
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
        )
    finally:
        await state.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# РЕДАКТИРОВАНИЕ ЗДАНИЯ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_building_edit:"))
async def show_building_edit_menu(callback: CallbackQuery, language: str = "ru"):
    """Показать меню редактирования здания"""
    building_id = int(callback.data.split(":")[1])

    lang = language
    await callback.message.edit_text(
        get_text("address_buildings.handlers.edit_building_menu", language=lang),
        reply_markup=get_building_edit_keyboard(building_id)
    )


@router.callback_query(F.data.startswith("addr_building_toggle:"))
async def toggle_building_status(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Переключить активность здания"""
    building_id = int(callback.data.split(":")[1])

    # WR-06 (класс): дефолт ДО try. `lang` присваивается после db-фазы,
    # и если она бросит (недоступна БД), `except` ниже сошлётся
    # на несвязанное имя → NameError вместо сообщения об ошибке.
    lang = "ru"
    try:
        building = await run_db(lambda s: _load_building_view(s, building_id), db=_db)
        lang = language
        if not building:
            await callback.answer(get_text("address_buildings.handlers.building_not_found", language=lang), show_alert=True)
            return

        new_status = not building.is_active
        # update_building — async-метод с собственной async-сессией; параметр
        # session им не используется.
        building, error = await AddressService.update_building(
            session=None,
            building_id=building_id,
            is_active=new_status
        )

        if error:
            await callback.answer(f"❌ {localize_address_error(error, lang)}", show_alert=True)
            return

        status_text = get_text("address_buildings.handlers.activated", language=lang) if new_status else get_text("address_buildings.handlers.deactivated", language=lang)
        await callback.answer(get_text("address_buildings.handlers.building_status_changed", language=lang).format(status=status_text))

        # Обновляем отображение (BUG-165: язык пробрасывается)
        await show_building_details(callback, language=lang)

    except Exception as e:
        logger.error(f"Ошибка при переключении статуса здания: {e}")
        await callback.answer(get_text("address_buildings.handlers.error_status_change", language=lang), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# УДАЛЕНИЕ ЗДАНИЯ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_building_delete:"))
async def confirm_building_deletion(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Подтверждение удаления здания"""
    building_id = int(callback.data.split(":")[1])

    # WR-06 (класс): дефолт ДО try. `lang` присваивается после db-фазы,
    # и если она бросит (недоступна БД), `except` ниже сошлётся
    # на несвязанное имя → NameError вместо сообщения об ошибке.
    lang = "ru"
    try:
        building = await run_db(lambda s: _load_building_view(s, building_id), db=_db)
        lang = language
        if not building:
            await callback.answer(get_text("address_buildings.handlers.building_not_found", language=lang), show_alert=True)
            return

        apartments_count = building.apartments_count

        warning = ""
        if apartments_count > 0:
            warning = get_text("address_buildings.handlers.delete_warning_apartments", language=lang).format(
                count=apartments_count
            )

        confirm_text = get_text("address_buildings.handlers.confirm_delete_building", language=lang).format(
            address=building.address
        ) + warning

        await callback.message.edit_text(
            confirm_text,
            reply_markup=get_confirmation_keyboard(
                confirm_callback=f"addr_building_delete_confirm:{building_id}",
                cancel_callback=f"addr_building_view:{building_id}"
            )
        )

    except Exception as e:
        logger.error(f"Ошибка при подготовке удаления здания: {e}")
        await callback.answer(get_text("address_buildings.handlers.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("addr_building_delete_confirm:"))
async def delete_building(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Удаление здания"""
    building_id = int(callback.data.split(":")[1])
    lang = language

    try:
        # delete_building — async-метод с собственной async-сессией; параметр
        # session им не используется. Sync-SQL здесь нет — run_db не нужен.
        success, error = await AddressService.delete_building(None, building_id)

        if not success:
            await callback.answer(f"❌ {localize_address_error(error, lang)}", show_alert=True)
            return

        await callback.message.edit_text(
            get_text("address_buildings.handlers.building_deleted_success", language=lang)
        )

        logger.info(f"Здание {building_id} удалено пользователем {callback.from_user.id}")

        # Показываем список зданий (BUG-165: язык пробрасывается)
        await show_buildings_list(callback, None, language=lang, _db=_db)

    except Exception:
        logger.exception("delete building handler failed")
        await callback.answer(get_text("address_buildings.handlers.error_deletion", language=language), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ОТМЕНА ДЕЙСТВИЙ
# ═══════════════════════════════════════════════════════════════════════════════
# Примечание: Обработчик cancel_apartment_selection перенесён в address_apartments.py
# так как он используется для отмены создания квартир, а не зданий
