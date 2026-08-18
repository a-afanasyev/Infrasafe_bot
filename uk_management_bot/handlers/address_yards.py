"""
Обработчики для управления дворами (Yard Management)

Функционал:
- Просмотр списка дворов
- Создание нового двора
- Просмотр детальной информации о дворе
- Редактирование двора
- Удаление (деактивация) двора
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
from uk_management_bot.states.address_management import YardManagementStates
from uk_management_bot.keyboards.address_management import (
    get_yards_list_keyboard,
    get_yard_details_keyboard,
    get_yard_edit_keyboard,
    get_confirmation_keyboard,
    get_skip_or_cancel_keyboard,
    get_cancel_keyboard_inline,
    get_address_management_menu
)
from uk_management_bot.keyboards.base import get_main_keyboard_for_role
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.address_helpers import localize_address_error
from uk_management_bot.utils.button_texts import get_address_directory_texts, get_cancel_texts, get_skip_texts

logger = logging.getLogger(__name__)

router = Router()
# Гейт всего роутера: root-фильтр отрабатывает ДО хендлеров, отказ = UNHANDLED
# (апдейт уходит дальше по цепочке main.py, транзит не ломается).
router.callback_query.filter(RoleGate())
router.message.filter(RoleGate())

ADDRESS_DIRECTORY_TEXTS = get_address_directory_texts()
CANCEL_TEXTS = get_cancel_texts()
SKIP_TEXTS = get_skip_texts()


# ==========================================================================
# DTO для async-слоя: наружу из run_db выходят примитивы, не ORM-строки
# (у ORM-объекта за пределами worker-потока нет живой сессии).
# ==========================================================================

@dataclass(frozen=True)
class _YardRow:
    """Строка списка дворов — ровно те атрибуты, что читает
    get_yards_list_keyboard (hasattr(., 'buildings_count') остаётся True,
    как у property модели Yard)."""
    id: int
    name: str
    is_active: bool
    buildings_count: int


@dataclass(frozen=True)
class _YardView:
    """Карточка двора для show_yard_details / toggle / confirm-delete."""
    id: int
    name: str
    is_active: bool
    gps_latitude: Optional[float]
    gps_longitude: Optional[float]
    buildings_count: int
    description: Optional[str]
    created_at: Optional[datetime]


# ==========================================================================
# Sync unit-of-work (AUD3-07/AUD5-ARCH-1): исполняются в worker-потоке через
# run_db; сессию открывает и закрывает run_db, event loop БД не трогает.
# Мутации дворов (create/update/delete_yard) сюда НЕ входят: это async-методы
# AddressService с собственной async-сессией — их хендлер await'ит напрямую.
# ==========================================================================

def _user_id_by_tg(db, telegram_id: int) -> Optional[int]:
    from uk_management_bot.database.models.user import User
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    return user.id if user else None


def _load_address_stats(db) -> dict:
    """Агрегаты справочника адресов (BUG-BOT-013) -> dict примитивов."""
    from uk_management_bot.database.models import Yard, Building, Apartment, UserApartment
    from sqlalchemy import func as _sa_func

    # Aggregates — single roundtrip each, no Python-side loop over rows.
    total_yards = db.query(_sa_func.count(Yard.id)).scalar() or 0
    active_yards = db.query(_sa_func.count(Yard.id)).filter(Yard.is_active.is_(True)).scalar() or 0

    total_buildings = db.query(_sa_func.count(Building.id)).scalar() or 0
    active_buildings = db.query(_sa_func.count(Building.id)).filter(Building.is_active.is_(True)).scalar() or 0

    total_apartments = db.query(_sa_func.count(Apartment.id)).scalar() or 0
    active_apartments = db.query(_sa_func.count(Apartment.id)).filter(Apartment.is_active.is_(True)).scalar() or 0

    # Жители — group by status (pending / approved / rejected).
    residents_rows = (
        db.query(UserApartment.status, _sa_func.count(UserApartment.id))
        .group_by(UserApartment.status)
        .all()
    )
    residents_by_status = {status: count for status, count in residents_rows}

    return {
        "total_yards": total_yards,
        "active_yards": active_yards,
        "total_buildings": total_buildings,
        "active_buildings": active_buildings,
        "total_apartments": total_apartments,
        "active_apartments": active_apartments,
        "residents_by_status": residents_by_status,
    }


def _load_yards_overview(db) -> list:
    """-> [_YardRow] для списка/страницы дворов."""
    yards = AddressService.get_all_yards(db, only_active=False, include_stats=True)
    return [
        _YardRow(
            id=yard.id,
            name=yard.name,
            is_active=yard.is_active,
            buildings_count=yard.buildings_count if hasattr(yard, 'buildings_count') else len(yard.buildings),
        )
        for yard in yards
    ]


def _load_yard_view(db, yard_id: int) -> Optional[_YardView]:
    """-> _YardView | None (None — двор не найден)."""
    yard = AddressService.get_yard_by_id(db, yard_id)
    if not yard:
        return None
    return _YardView(
        id=yard.id,
        name=yard.name,
        is_active=yard.is_active,
        gps_latitude=yard.gps_latitude,
        gps_longitude=yard.gps_longitude,
        buildings_count=yard.buildings_count if hasattr(yard, 'buildings_count') else len(yard.buildings),
        description=yard.description,
        created_at=yard.created_at,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ГЛАВНОЕ МЕНЮ СПРАВОЧНИКА АДРЕСОВ
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(F.text.in_(ADDRESS_DIRECTORY_TEXTS))
async def show_address_management_menu(message: Message, state: FSMContext, language: str = "ru"):
    """Показать главное меню управления адресами"""
    await state.clear()

    from uk_management_bot.keyboards.address_management import get_address_management_menu

    lang = language
    await message.answer(
        get_text("address_yards.handlers.address_directory_menu", language=lang),
        reply_markup=get_address_management_menu()
    )


@router.callback_query(F.data == "addr_menu")
async def show_address_menu_callback(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Показать главное меню управления адресами (callback)"""
    await state.clear()

    from uk_management_bot.keyboards.address_management import get_address_management_menu

    lang = language
    await callback.message.edit_text(
        get_text("address_yards.handlers.address_directory_menu", language=lang),
        reply_markup=get_address_management_menu()
    )


@router.callback_query(F.data == "addr_stats")
async def show_address_stats(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Сводная статистика справочника адресов.

    BUG-BOT-013: ранее кнопка "📊 Статистика" в меню справочника адресов была
    silent click (handler отсутствовал, экран не менялся, callback answer пуст).
    Этот handler агрегирует: количество дворов / зданий / квартир / жителей с
    разбивкой по active/inactive и user_apartment.status.
    """
    from uk_management_bot.keyboards.address_management import get_address_management_menu

    await state.clear()
    lang = language

    try:
        stats = await run_db(_load_address_stats, db=_db)

        residents_by_status = stats["residents_by_status"]
        residents_total = sum(residents_by_status.values())
        residents_approved = residents_by_status.get("approved", 0)
        residents_pending = residents_by_status.get("pending", 0)
        residents_rejected = residents_by_status.get("rejected", 0)

        text = get_text("address_yards.handlers.address_stats_report", language=lang).format(
            total_yards=stats["total_yards"],
            active_yards=stats["active_yards"],
            inactive_yards=stats["total_yards"] - stats["active_yards"],
            total_buildings=stats["total_buildings"],
            active_buildings=stats["active_buildings"],
            inactive_buildings=stats["total_buildings"] - stats["active_buildings"],
            total_apartments=stats["total_apartments"],
            active_apartments=stats["active_apartments"],
            inactive_apartments=stats["total_apartments"] - stats["active_apartments"],
            residents_total=residents_total,
            residents_approved=residents_approved,
            residents_pending=residents_pending,
            residents_rejected=residents_rejected,
        )

        await callback.message.edit_text(
            text,
            reply_markup=get_address_management_menu(language=lang),
            parse_mode="HTML",
        )
        await callback.answer()
    except Exception as exc:
        logger.error(f"Ошибка показа статистики справочника адресов: {exc}", exc_info=True)
        await callback.answer(
            get_text("address_yards.handlers.address_stats_error", language=lang),
            show_alert=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР СПИСКА ДВОРОВ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "addr_yards_list")
async def show_yards_list(callback: CallbackQuery, state: FSMContext | None, language: str = "ru", *, _db=None):
    """Показать список всех дворов"""
    # delete_yard вызывает без FSM-состояния (state=None) — чистить нечего.
    if state is not None:
        await state.clear()

    try:
        yards = await run_db(_load_yards_overview, db=_db)

        if not yards:
            lang = language
            await callback.message.edit_text(
                get_text("address_yards.handlers.yards_list_empty", language=lang),
                reply_markup=get_yards_list_keyboard([], page=0)
            )
            return

        lang = language
        text = get_text("address_yards.handlers.yards_list_title", language=lang).format(
            total=len(yards), active=len([y for y in yards if y.is_active])
        )

        await callback.message.edit_text(
            text,
            reply_markup=get_yards_list_keyboard(yards, page=0)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке списка дворов: {e}")
        lang = language
        await callback.answer(get_text("address_yards.handlers.error_loading_data", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("addr_yards_page:"))
async def show_yards_page(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Показать конкретную страницу списка дворов"""
    page = int(callback.data.split(":")[1])

    try:
        yards = await run_db(_load_yards_overview, db=_db)

        lang = language
        text = get_text("address_yards.handlers.yards_list_page", language=lang).format(page=page + 1, total=len(yards))

        await callback.message.edit_text(
            text,
            reply_markup=get_yards_list_keyboard(yards, page=page)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке страницы дворов: {e}")
        lang = language
        await callback.answer(get_text("address_yards.handlers.error_loading_data", language=lang), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР ДЕТАЛЬНОЙ ИНФОРМАЦИИ О ДВОРЕ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_yard_view:"))
async def show_yard_details(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Показать детальную информацию о дворе"""
    yard_id = int(callback.data.split(":")[1])

    # WR-06 (класс): дефолт ДО try. `lang` присваивается после db-фазы,
    # и если она бросит (недоступна БД), `except` ниже сошлётся
    # на несвязанное имя → NameError вместо сообщения об ошибке.
    lang = "ru"
    try:
        yard = await run_db(lambda s: _load_yard_view(s, yard_id), db=_db)

        lang = language
        if not yard:
            await callback.answer(get_text("address_yards.handlers.yard_not_found", language=lang), show_alert=True)
            return

        status = get_text("address_yards.handlers.status_active", language=lang) if yard.is_active else get_text("address_yards.handlers.status_inactive", language=lang)
        gps = f"📍 {yard.gps_latitude}, {yard.gps_longitude}" if yard.gps_latitude and yard.gps_longitude else get_text("address_yards.handlers.gps_not_set", language=lang)
        buildings_count = yard.buildings_count

        text = get_text("address_yards.handlers.yard_details", language=lang).format(
            name=yard.name, status=status, buildings=buildings_count, gps=gps
        )

        if yard.description:
            text += get_text("address_yards.handlers.description_label", language=lang).format(description=yard.description)

        if yard.created_at:
            text += get_text("address_yards.handlers.created_label", language=lang).format(date=yard.created_at.strftime('%d.%m.%Y %H:%M'))

        await callback.message.edit_text(
            text,
            reply_markup=get_yard_details_keyboard(yard_id)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке информации о дворе {yard_id}: {e}")
        await callback.answer(get_text("address_yards.handlers.error_loading_data", language=lang), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# СОЗДАНИЕ НОВОГО ДВОРА
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "addr_yard_create")
async def start_yard_creation(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Начать создание нового двора"""
    await state.clear()
    await state.set_state(YardManagementStates.waiting_for_yard_name)

    lang = language
    await callback.message.edit_text(
        get_text("address_yards.handlers.create_yard_name", language=lang),
        reply_markup=get_cancel_keyboard_inline()
    )


@router.message(StateFilter(YardManagementStates.waiting_for_yard_name))
async def process_yard_name(message: Message, state: FSMContext, language: str = "ru"):
    """Обработка названия двора"""
    name = message.text.strip()

    lang = language
    if len(name) < 3:
        await message.answer(get_text("address_yards.handlers.name_too_short", language=lang))
        return

    if len(name) > 200:
        await message.answer(get_text("address_yards.handlers.name_too_long", language=lang))
        return

    await state.update_data(name=name)
    await state.set_state(YardManagementStates.waiting_for_yard_description)

    await message.answer(
        get_text("address_yards.handlers.create_yard_description", language=lang).format(name=name),
        reply_markup=get_skip_or_cancel_keyboard()
    )


@router.message(StateFilter(YardManagementStates.waiting_for_yard_description))
async def process_yard_description(message: Message, state: FSMContext, language: str = "ru"):
    """Обработка описания двора"""
    if message.text in SKIP_TEXTS:
        description = None
    elif message.text in CANCEL_TEXTS:
        lang = language
        await state.clear()
        await message.answer(
            get_text("address_yards.handlers.yard_creation_cancelled", language=lang),
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
        )
        return
    else:
        description = message.text.strip()

    lang = language
    await state.update_data(description=description)
    await state.set_state(YardManagementStates.waiting_for_yard_gps)

    await message.answer(
        get_text("address_yards.handlers.create_yard_gps", language=lang),
        reply_markup=get_skip_or_cancel_keyboard()
    )


@router.message(StateFilter(YardManagementStates.waiting_for_yard_gps))
async def process_yard_gps(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработка GPS координат двора"""
    gps_latitude = None
    gps_longitude = None

    lang = language
    if message.text in SKIP_TEXTS:
        pass
    elif message.text in CANCEL_TEXTS:
        await state.clear()
        await message.answer(
            get_text("address_yards.handlers.yard_creation_cancelled", language=lang),
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
            await message.answer(get_text("address_yards.handlers.invalid_gps_format", language=lang))
            return

    # Сохраняем двор в базу
    data = await state.get_data()

    try:
        # Получаем user.id из базы данных (не telegram_id!)
        user_id = await run_db(lambda s: _user_id_by_tg(s, message.from_user.id), db=_db)
        if user_id is None:
            await message.answer(
                get_text("address_yards.handlers.user_not_found", language=lang),
                reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
            )
            await state.clear()
            return

        # create_yard — async-метод с собственной async-сессией; параметр
        # session им не используется (пишет через _async_session()).
        yard, error = await AddressService.create_yard(
            session=None,
            name=data['name'],
            created_by=user_id,  # ИСПРАВЛЕНО: используем user.id из БД, а не telegram_id
            description=data.get('description'),
            gps_latitude=gps_latitude,
            gps_longitude=gps_longitude
        )

        if error:
            await message.answer(
                get_text("address_yards.handlers.yard_creation_error", language=lang).format(error=error),
                reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
            )
            await state.clear()
            return

        # ⚠️ Предсуществующий дефект (сохранён 1:1 при A2-конвертации): координата
        # 0.0 falsy — легитимный GPS "0.0, X" показался бы как «не задан».
        gps_info = f"📍 {gps_latitude}, {gps_longitude}" if gps_latitude and gps_longitude else get_text("address_yards.handlers.gps_not_set", language=lang)
        desc_info = get_text("address_yards.handlers.description_info", language=lang).format(desc=data.get('description')) if data.get('description') else ""

        await message.answer(
            get_text("address_yards.handlers.yard_created_success", language=lang).format(
                name=yard.name, gps=gps_info, desc_info=desc_info
            ),
            reply_markup=get_address_management_menu()
        )

        logger.info(f"Создан новый двор: {yard.name} (ID: {yard.id}) пользователем {message.from_user.id}")

    except Exception:
        logger.exception("create yard handler failed")
        await message.answer(
            get_text("address_yards.handlers.operation_failed", language=lang),
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
        )
    finally:
        await state.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# РЕДАКТИРОВАНИЕ ДВОРА
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_yard_edit:"))
async def show_yard_edit_menu(callback: CallbackQuery, language: str = "ru"):
    """Показать меню редактирования двора"""
    yard_id = int(callback.data.split(":")[1])

    lang = language
    await callback.message.edit_text(
        get_text("address_yards.handlers.edit_yard_menu", language=lang),
        reply_markup=get_yard_edit_keyboard(yard_id)
    )


@router.callback_query(F.data.startswith("addr_yard_edit_name:"))
async def start_yard_name_edit(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Начать редактирование названия двора"""
    yard_id = int(callback.data.split(":")[1])

    await state.update_data(yard_id=yard_id)
    await state.set_state(YardManagementStates.waiting_for_new_yard_name)

    lang = language
    await callback.message.edit_text(
        get_text("address_yards.handlers.edit_yard_name", language=lang),
        reply_markup=get_cancel_keyboard_inline()
    )


@router.message(StateFilter(YardManagementStates.waiting_for_new_yard_name))
async def process_new_yard_name(message: Message, state: FSMContext, language: str = "ru"):
    """Обработка нового названия двора"""
    new_name = message.text.strip()

    lang = language
    if len(new_name) < 3 or len(new_name) > 200:
        await message.answer(get_text("address_yards.handlers.name_invalid_length", language=lang))
        return

    data = await state.get_data()
    yard_id = data['yard_id']

    try:
        # update_yard — async-метод с собственной async-сессией; параметр
        # session им не используется. Sync-SQL здесь нет — run_db не нужен.
        yard, error = await AddressService.update_yard(
            session=None,
            yard_id=yard_id,
            name=new_name
        )

        if error:
            await message.answer(f"❌ {localize_address_error(error, lang)}")
            return

        await message.answer(
            get_text("address_yards.handlers.yard_name_updated", language=lang).format(name=new_name),
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
        )

        logger.info(f"Двор {yard_id} переименован в '{new_name}' пользователем {message.from_user.id}")

    except Exception:
        logger.exception("update yard name handler failed")
        await message.answer(
            get_text("address_yards.handlers.operation_failed", language=lang)
        )
    finally:
        await state.clear()


@router.callback_query(F.data.startswith("addr_yard_toggle:"))
async def toggle_yard_status(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Переключить активность двора"""
    yard_id = int(callback.data.split(":")[1])

    # WR-06 (класс): дефолт ДО try. `lang` присваивается после db-фазы,
    # и если она бросит (недоступна БД), `except` ниже сошлётся
    # на несвязанное имя → NameError вместо сообщения об ошибке.
    lang = "ru"
    try:
        yard = await run_db(lambda s: _load_yard_view(s, yard_id), db=_db)
        lang = language
        if not yard:
            await callback.answer(get_text("address_yards.handlers.yard_not_found", language=lang), show_alert=True)
            return

        new_status = not yard.is_active
        # update_yard — async-метод с собственной async-сессией; параметр
        # session им не используется.
        yard, error = await AddressService.update_yard(
            session=None,
            yard_id=yard_id,
            is_active=new_status
        )

        if error:
            await callback.answer(f"❌ Ошибка: {localize_address_error(error, lang)}", show_alert=True)
            return

        status_text = get_text("address_yards.handlers.activated", language=lang) if new_status else get_text("address_yards.handlers.deactivated", language=lang)
        await callback.answer(get_text("address_yards.handlers.yard_status_changed", language=lang).format(status=status_text))

        # Обновляем отображение
        # ⚠️ Предсуществующий дефект (сохранён байт-в-байт): language не
        # пробрасывается — карточка после переключения рендерится на "ru".
        await show_yard_details(callback)

    except Exception as e:
        logger.error(f"Ошибка при переключении статуса двора: {e}")
        await callback.answer(get_text("address_yards.handlers.error_status_change", language=lang), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# УДАЛЕНИЕ ДВОРА
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_yard_delete:"))
async def confirm_yard_deletion(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Подтверждение удаления двора"""
    yard_id = int(callback.data.split(":")[1])

    # WR-06 (класс): дефолт ДО try. `lang` присваивается после db-фазы,
    # и если она бросит (недоступна БД), `except` ниже сошлётся
    # на несвязанное имя → NameError вместо сообщения об ошибке.
    lang = "ru"
    try:
        yard = await run_db(lambda s: _load_yard_view(s, yard_id), db=_db)
        lang = language
        if not yard:
            await callback.answer(get_text("address_yards.handlers.yard_not_found", language=lang), show_alert=True)
            return

        buildings_count = yard.buildings_count

        warning = ""
        if buildings_count > 0:
            warning = get_text("address_yards.handlers.delete_warning_buildings", language=lang).format(
                count=buildings_count
            )

        confirm_text = get_text("address_yards.handlers.confirm_delete_yard", language=lang).format(
            name=yard.name
        ) + warning

        await callback.message.edit_text(
            confirm_text,
            reply_markup=get_confirmation_keyboard(
                confirm_callback=f"addr_yard_delete_confirm:{yard_id}",
                cancel_callback=f"addr_yard_view:{yard_id}"
            )
        )

    except Exception as e:
        logger.error(f"Ошибка при подготовке удаления двора: {e}")
        await callback.answer(get_text("address_yards.handlers.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("addr_yard_delete_confirm:"))
async def delete_yard(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Удаление двора"""
    yard_id = int(callback.data.split(":")[1])
    lang = language

    try:
        # delete_yard — async-метод с собственной async-сессией; параметр
        # session им не используется. Sync-SQL здесь нет — run_db не нужен.
        success, error = await AddressService.delete_yard(None, yard_id)

        if not success:
            await callback.answer(f"❌ {localize_address_error(error, lang)}", show_alert=True)
            return

        await callback.message.edit_text(
            get_text("address_yards.handlers.yard_deleted_success", language=lang)
        )

        logger.info(f"Двор {yard_id} удален пользователем {callback.from_user.id}")

        # ⚠️ Предсуществующий дефект (сохранён 1:1): show_yards_list без language —
        # заголовок списка после удаления всегда на ru.
        await show_yards_list(callback, None, _db=_db)

    except Exception:
        logger.exception("delete yard handler failed")
        await callback.answer(get_text("address_yards.handlers.error_deletion", language=language), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ОТМЕНА ДЕЙСТВИЙ
# ═══════════════════════════════════════════════════════════════════════════════

# BUG-155 п.3 (закрыто 2026-08-18): до сужения фильтров этот хендлер не получал
# апдейт НИКОГДА — `address_moderation` с голым `cancel_action` включён раньше
# (`main.py:391` против `:394`) и забирал отмену создания двора себе.
@router.callback_query(StateFilter(YardManagementStates), F.data == "cancel_action")
async def cancel_action(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Отмена текущего действия"""
    await state.clear()
    lang = language
    await callback.message.edit_text(get_text("address_yards.handlers.action_cancelled", language=lang))
    # ⚠️ Предсуществующий дефект (сохранён 1:1): без language — список на ru.
    await show_yards_list(callback, state)


@router.message(F.text.in_(CANCEL_TEXTS))
async def cancel_with_button(message: Message, state: FSMContext, language: str = "ru"):
    """Отмена через кнопку"""
    await state.clear()
    lang = language
    await message.answer(
        get_text("address_yards.handlers.action_cancelled", language=lang),
        reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
    )


@router.callback_query(F.data == "admin_menu")
async def back_to_admin_menu(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Возврат в главное админское меню"""
    await state.clear()

    from uk_management_bot.keyboards.admin import get_manager_main_keyboard

    lang = language
    await callback.message.answer(
        get_text("address_yards.handlers.admin_panel_menu", language=lang),
        reply_markup=get_manager_main_keyboard(language=lang)
    )

    # Удаляем предыдущее сообщение с inline-клавиатурой
    try:
        await callback.message.delete()
    except Exception:
        pass
