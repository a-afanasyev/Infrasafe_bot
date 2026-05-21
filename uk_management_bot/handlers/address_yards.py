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
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from uk_management_bot.database.session import get_db
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
from uk_management_bot.utils.button_texts import get_address_directory_texts, get_cancel_texts, get_skip_texts

logger = logging.getLogger(__name__)

router = Router()

ADDRESS_DIRECTORY_TEXTS = get_address_directory_texts()
CANCEL_TEXTS = get_cancel_texts()
SKIP_TEXTS = get_skip_texts()

# Примечание: Проверка ролей происходит на уровне глобальных middleware (auth_middleware)
# Дополнительная проверка в handlers при необходимости


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
async def show_address_stats(callback: CallbackQuery, state: FSMContext, language: str = "ru", db=None):
    """Сводная статистика справочника адресов.

    BUG-BOT-013: ранее кнопка "📊 Статистика" в меню справочника адресов была
    silent click (handler отсутствовал, экран не менялся, callback answer пуст).
    Этот handler агрегирует: количество дворов / зданий / квартир / жителей с
    разбивкой по active/inactive и user_apartment.status.
    """
    from uk_management_bot.keyboards.address_management import get_address_management_menu
    from uk_management_bot.database.models import Yard, Building, Apartment, UserApartment
    from sqlalchemy import func as _sa_func

    await state.clear()
    lang = language

    own_db = False
    try:
        if db is None:
            db = next(get_db())
            own_db = True

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
        residents_total = sum(residents_by_status.values())
        residents_approved = residents_by_status.get("approved", 0)
        residents_pending = residents_by_status.get("pending", 0)
        residents_rejected = residents_by_status.get("rejected", 0)

        text = get_text("address_yards.handlers.address_stats_report", language=lang).format(
            total_yards=total_yards,
            active_yards=active_yards,
            inactive_yards=total_yards - active_yards,
            total_buildings=total_buildings,
            active_buildings=active_buildings,
            inactive_buildings=total_buildings - active_buildings,
            total_apartments=total_apartments,
            active_apartments=active_apartments,
            inactive_apartments=total_apartments - active_apartments,
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
    finally:
        if own_db and db is not None:
            try:
                db.close()
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР СПИСКА ДВОРОВ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "addr_yards_list")
async def show_yards_list(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Показать список всех дворов"""
    await state.clear()

    db = next(get_db())
    try:
        yards = await AddressService.get_all_yards(db, only_active=False, include_stats=True)

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
    finally:
        db.close()


@router.callback_query(F.data.startswith("addr_yards_page:"))
async def show_yards_page(callback: CallbackQuery, language: str = "ru"):
    """Показать конкретную страницу списка дворов"""
    page = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        yards = await AddressService.get_all_yards(db, only_active=False, include_stats=True)

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
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР ДЕТАЛЬНОЙ ИНФОРМАЦИИ О ДВОРЕ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_yard_view:"))
async def show_yard_details(callback: CallbackQuery, language: str = "ru"):
    """Показать детальную информацию о дворе"""
    yard_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        yard = await AddressService.get_yard_by_id(db, yard_id)

        lang = language
        if not yard:
            await callback.answer(get_text("address_yards.handlers.yard_not_found", language=lang), show_alert=True)
            return

        status = get_text("address_yards.handlers.status_active", language=lang) if yard.is_active else get_text("address_yards.handlers.status_inactive", language=lang)
        gps = f"📍 {yard.gps_latitude}, {yard.gps_longitude}" if yard.gps_latitude and yard.gps_longitude else get_text("address_yards.handlers.gps_not_set", language=lang)
        buildings_count = yard.buildings_count if hasattr(yard, 'buildings_count') else len(yard.buildings)

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
    finally:
        db.close()


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
async def process_yard_gps(message: Message, state: FSMContext, language: str = "ru"):
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

        except ValueError as e:
            await message.answer(get_text("address_yards.handlers.invalid_gps_format", language=lang))
            return

    # Сохраняем двор в базу
    data = await state.get_data()
    db = next(get_db())

    try:
        # Получаем user.id из базы данных (не telegram_id!)
        from uk_management_bot.database.models.user import User
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer(
                get_text("address_yards.handlers.user_not_found", language=lang),
                reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
            )
            await state.clear()
            return

        yard, error = await AddressService.create_yard(
            session=db,
            name=data['name'],
            created_by=user.id,  # ИСПРАВЛЕНО: используем user.id из БД, а не telegram_id
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

        gps_info = f"📍 {gps_latitude}, {gps_longitude}" if gps_latitude and gps_longitude else get_text("address_yards.handlers.gps_not_set", language=lang)
        desc_info = get_text("address_yards.handlers.description_info", language=lang).format(desc=data.get('description')) if data.get('description') else ""

        await message.answer(
            get_text("address_yards.handlers.yard_created_success", language=lang).format(
                name=yard.name, gps=gps_info, desc_info=desc_info
            ),
            reply_markup=get_address_management_menu()
        )

        logger.info(f"Создан новый двор: {yard.name} (ID: {yard.id}) пользователем {message.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка при создании двора: {e}")
        await message.answer(
            get_text("address_yards.handlers.yard_creation_error", language=lang).format(error=str(e)),
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
        )
    finally:
        db.close()
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

    db = next(get_db())
    try:
        yard, error = await AddressService.update_yard(
            session=db,
            yard_id=yard_id,
            name=new_name
        )

        if error:
            await message.answer(f"❌ {error}")
            return

        await message.answer(
            get_text("address_yards.handlers.yard_name_updated", language=lang).format(name=new_name),
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
        )

        logger.info(f"Двор {yard_id} переименован в '{new_name}' пользователем {message.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка при обновлении названия двора: {e}")
        await message.answer(f"❌ {str(e)}")
    finally:
        db.close()
        await state.clear()


@router.callback_query(F.data.startswith("addr_yard_toggle:"))
async def toggle_yard_status(callback: CallbackQuery, language: str = "ru"):
    """Переключить активность двора"""
    yard_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        lang = language
        yard = await AddressService.get_yard_by_id(db, yard_id)
        if not yard:
            await callback.answer(get_text("address_yards.handlers.yard_not_found", language=lang), show_alert=True)
            return

        new_status = not yard.is_active
        yard, error = await AddressService.update_yard(
            session=db,
            yard_id=yard_id,
            is_active=new_status
        )

        if error:
            await callback.answer(f"❌ Ошибка: {error}", show_alert=True)
            return

        status_text = get_text("address_yards.handlers.activated", language=lang) if new_status else get_text("address_yards.handlers.deactivated", language=lang)
        await callback.answer(get_text("address_yards.handlers.yard_status_changed", language=lang).format(status=status_text))

        # Обновляем отображение
        await show_yard_details(callback)

    except Exception as e:
        logger.error(f"Ошибка при переключении статуса двора: {e}")
        await callback.answer(get_text("address_yards.handlers.error_status_change", language=lang), show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# УДАЛЕНИЕ ДВОРА
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_yard_delete:"))
async def confirm_yard_deletion(callback: CallbackQuery, language: str = "ru"):
    """Подтверждение удаления двора"""
    yard_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        lang = language
        yard = await AddressService.get_yard_by_id(db, yard_id)
        if not yard:
            await callback.answer(get_text("address_yards.handlers.yard_not_found", language=lang), show_alert=True)
            return

        buildings_count = yard.buildings_count if hasattr(yard, 'buildings_count') else len(yard.buildings)

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
    finally:
        db.close()


@router.callback_query(F.data.startswith("addr_yard_delete_confirm:"))
async def delete_yard(callback: CallbackQuery, language: str = "ru"):
    """Удаление двора"""
    yard_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        success, error = await AddressService.delete_yard(db, yard_id)

        if not success:
            await callback.answer(f"❌ {error}", show_alert=True)
            return

        lang = language
        await callback.message.edit_text(
            get_text("address_yards.handlers.yard_deleted_success", language=lang)
        )

        logger.info(f"Двор {yard_id} удален пользователем {callback.from_user.id}")

        # Показываем список дворов
        await show_yards_list(callback, None)

    except Exception as e:
        logger.error(f"Ошибка при удалении двора: {e}")
        await callback.answer(get_text("address_yards.handlers.error_deletion", language=lang), show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ОТМЕНА ДЕЙСТВИЙ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "cancel_action")
async def cancel_action(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Отмена текущего действия"""
    await state.clear()
    lang = language
    await callback.message.edit_text(get_text("address_yards.handlers.action_cancelled", language=lang))
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
