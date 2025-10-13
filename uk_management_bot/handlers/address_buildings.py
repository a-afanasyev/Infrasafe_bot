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
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from uk_management_bot.database.session import get_db
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

logger = logging.getLogger(__name__)

router = Router()


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР СПИСКА ЗДАНИЙ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "addr_buildings_list")
async def show_buildings_list(callback: CallbackQuery, state: FSMContext):
    """Показать список всех зданий"""
    await state.clear()

    db = next(get_db())
    try:
        # Загружаем все здания
        from uk_management_bot.database.models import Building
        from sqlalchemy import select

        result = db.execute(
            select(Building)
            .where(Building.is_active == True)
            .order_by(Building.address)
        )
        buildings = result.scalars().all()

        if not buildings:
            await callback.message.edit_text(
                "📋 <b>Список зданий пуст</b>\n\n"
                "Добавьте первое здание для начала работы.",
                reply_markup=get_buildings_list_keyboard([], page=0)
            )
            return

        text = f"📋 <b>Список зданий</b>\n\n" \
               f"Всего зданий: {len(buildings)}\n\n" \
               f"Выберите здание для просмотра:"

        await callback.message.edit_text(
            text,
            reply_markup=get_buildings_list_keyboard(buildings, page=0)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке списка зданий: {e}")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
    finally:
        db.close()


@router.callback_query(F.data.startswith("addr_buildings_page:"))
async def show_buildings_page(callback: CallbackQuery):
    """Показать конкретную страницу списка зданий"""
    page = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        from uk_management_bot.database.models import Building
        from sqlalchemy import select

        result = db.execute(
            select(Building)
            .where(Building.is_active == True)
            .order_by(Building.address)
        )
        buildings = result.scalars().all()

        text = f"📋 <b>Список зданий</b> (страница {page + 1})\n\n" \
               f"Всего зданий: {len(buildings)}\n\n" \
               f"Выберите здание для просмотра:"

        await callback.message.edit_text(
            text,
            reply_markup=get_buildings_list_keyboard(buildings, page=page)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке страницы зданий: {e}")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
    finally:
        db.close()


@router.callback_query(F.data.startswith("addr_buildings_by_yard:"))
async def show_buildings_by_yard(callback: CallbackQuery):
    """Показать здания конкретного двора"""
    yard_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        yard = await AddressService.get_yard_by_id(db, yard_id)
        if not yard:
            await callback.answer("❌ Двор не найден", show_alert=True)
            return

        buildings = await AddressService.get_buildings_by_yard(db, yard_id, only_active=False)

        text = f"🏢 <b>Здания двора: {yard.name}</b>\n\n" \
               f"Всего зданий: {len(buildings)}\n"

        if not buildings:
            text += "\nСписок зданий пуст."

        await callback.message.edit_text(
            text,
            reply_markup=get_buildings_list_keyboard(buildings, page=0, yard_id=yard_id)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке зданий двора {yard_id}: {e}")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР ДЕТАЛЬНОЙ ИНФОРМАЦИИ О ЗДАНИИ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_building_view:"))
async def show_building_details(callback: CallbackQuery):
    """Показать детальную информацию о здании"""
    building_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        building = await AddressService.get_building_by_id(db, building_id, include_yard=True)

        if not building:
            await callback.answer("❌ Здание не найдено", show_alert=True)
            return

        status = "✅ Активно" if building.is_active else "❌ Неактивно"
        gps = f"📍 {building.gps_latitude}, {building.gps_longitude}" if building.gps_latitude and building.gps_longitude else "📍 Не указаны"
        apartments_count = building.apartments_count if hasattr(building, 'apartments_count') else len(building.apartments)
        yard_name = building.yard.name if building.yard else "Не указан"

        text = f"🏢 <b>Здание</b>\n\n" \
               f"<b>Адрес:</b> {building.address}\n" \
               f"<b>Двор:</b> {yard_name}\n" \
               f"<b>Статус:</b> {status}\n\n" \
               f"<b>Подъездов:</b> {building.entrance_count}\n" \
               f"<b>Этажей:</b> {building.floor_count}\n" \
               f"<b>Квартир:</b> {apartments_count}\n" \
               f"<b>GPS координаты:</b> {gps}\n"

        if building.description:
            text += f"\n<b>Описание:</b>\n{building.description}\n"

        if building.created_at:
            text += f"\n<b>Создано:</b> {building.created_at.strftime('%d.%m.%Y %H:%M')}"

        await callback.message.edit_text(
            text,
            reply_markup=get_building_details_keyboard(building_id)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке информации о здании {building_id}: {e}")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# СОЗДАНИЕ НОВОГО ЗДАНИЯ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "addr_building_create")
async def start_building_creation(callback: CallbackQuery, state: FSMContext):
    """Начать создание нового здания - выбор двора"""
    await state.clear()

    db = next(get_db())
    try:
        yards = await AddressService.get_all_yards(db, only_active=True)

        if not yards:
            await callback.message.edit_text(
                "❌ <b>Нет доступных дворов</b>\n\n"
                "Сначала создайте хотя бы один двор.",
                reply_markup=get_cancel_keyboard_inline()
            )
            return

        await state.set_state(BuildingManagementStates.waiting_for_yard_selection)

        await callback.message.edit_text(
            "➕ <b>Создание нового здания</b>\n\n"
            "Шаг 1: Выберите двор, к которому относится здание:",
            reply_markup=get_user_apartment_selection_keyboard(yards, "yard", "building_create_yard")
        )

    except Exception as e:
        logger.error(f"Ошибка при начале создания здания: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
    finally:
        db.close()


@router.callback_query(F.data.startswith("building_create_yard:"))
async def process_building_yard_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора двора для нового здания"""
    yard_id = int(callback.data.split(":")[1])

    await state.update_data(yard_id=yard_id)
    await state.set_state(BuildingManagementStates.waiting_for_building_address)

    db = next(get_db())
    try:
        yard = await AddressService.get_yard_by_id(db, yard_id)
        yard_name = yard.name if yard else "Неизвестный двор"

        await callback.message.edit_text(
            f"✅ Двор: <b>{yard_name}</b>\n\n"
            "Шаг 2: Введите полный адрес здания:",
            reply_markup=get_cancel_keyboard_inline()
        )
    finally:
        db.close()


@router.message(StateFilter(BuildingManagementStates.waiting_for_building_address))
async def process_building_address(message: Message, state: FSMContext):
    """Обработка адреса здания"""
    address = message.text.strip()

    if len(address) < 5:
        await message.answer(
            "❌ Адрес здания должен содержать минимум 5 символов.\n\n"
            "Попробуйте еще раз:"
        )
        return

    if len(address) > 300:
        await message.answer(
            "❌ Адрес здания слишком длинный (максимум 300 символов).\n\n"
            "Попробуйте еще раз:"
        )
        return

    await state.update_data(address=address)
    await state.set_state(BuildingManagementStates.waiting_for_entrance_count)

    await message.answer(
        f"✅ Адрес: <b>{address}</b>\n\n"
        "Шаг 3: Введите количество подъездов (число от 1 до 50):",
        reply_markup=get_skip_or_cancel_keyboard()
    )


@router.message(StateFilter(BuildingManagementStates.waiting_for_entrance_count))
async def process_entrance_count(message: Message, state: FSMContext):
    """Обработка количества подъездов"""
    if message.text == "⏭ Пропустить":
        entrance_count = 1
    elif message.text == "❌ Отмена":
        await state.clear()
        await message.answer(
            "❌ Создание здания отменено",
            reply_markup=get_main_keyboard_for_role("manager", ["manager"])
        )
        return
    else:
        try:
            entrance_count = int(message.text.strip())
            if entrance_count < 1 or entrance_count > 50:
                raise ValueError("Количество подъездов вне допустимого диапазона")
        except ValueError:
            await message.answer(
                "❌ Неверный формат. Введите число от 1 до 50:"
            )
            return

    await state.update_data(entrance_count=entrance_count)
    await state.set_state(BuildingManagementStates.waiting_for_floor_count)

    await message.answer(
        f"✅ Подъездов: <b>{entrance_count}</b>\n\n"
        "Шаг 4: Введите количество этажей (число от 1 до 100):",
        reply_markup=get_skip_or_cancel_keyboard()
    )


@router.message(StateFilter(BuildingManagementStates.waiting_for_floor_count))
async def process_floor_count(message: Message, state: FSMContext):
    """Обработка количества этажей"""
    if message.text == "⏭ Пропустить":
        floor_count = 1
    elif message.text == "❌ Отмена":
        await state.clear()
        await message.answer(
            "❌ Создание здания отменено",
            reply_markup=get_main_keyboard_for_role("manager", ["manager"])
        )
        return
    else:
        try:
            floor_count = int(message.text.strip())
            if floor_count < 1 or floor_count > 100:
                raise ValueError("Количество этажей вне допустимого диапазона")
        except ValueError:
            await message.answer(
                "❌ Неверный формат. Введите число от 1 до 100:"
            )
            return

    await state.update_data(floor_count=floor_count)
    await state.set_state(BuildingManagementStates.waiting_for_building_gps)

    await message.answer(
        f"✅ Этажей: <b>{floor_count}</b>\n\n"
        "Шаг 5: Введите GPS координаты здания в формате:\n"
        "широта, долгота\n\n"
        "Например: 41.2995, 69.2401\n\n"
        "Или нажмите 'Пропустить':",
        reply_markup=get_skip_or_cancel_keyboard()
    )


@router.message(StateFilter(BuildingManagementStates.waiting_for_building_gps))
async def process_building_gps(message: Message, state: FSMContext):
    """Обработка GPS координат здания и создание записи"""
    gps_latitude = None
    gps_longitude = None

    if message.text == "⏭ Пропустить":
        pass
    elif message.text == "❌ Отмена":
        await state.clear()
        await message.answer(
            "❌ Создание здания отменено",
            reply_markup=get_main_keyboard_for_role("manager", ["manager"])
        )
        return
    else:
        try:
            parts = message.text.strip().replace(" ", "").split(",")
            if len(parts) != 2:
                raise ValueError("Неверный формат")

            gps_latitude = float(parts[0])
            gps_longitude = float(parts[1])

            if not (-90 <= gps_latitude <= 90) or not (-180 <= gps_longitude <= 180):
                raise ValueError("Координаты вне допустимого диапазона")

        except ValueError as e:
            await message.answer(
                f"❌ Неверный формат координат: {e}\n\n"
                "Введите координаты в формате: широта, долгота\n"
                "Или нажмите 'Пропустить':"
            )
            return

    # Сохраняем здание в базу
    data = await state.get_data()
    db = next(get_db())

    try:
        # Получаем user.id из базы данных (не telegram_id!)
        from uk_management_bot.database.models.user import User
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer(
                "❌ Пользователь не найден",
                reply_markup=get_main_keyboard_for_role("manager", ["manager"])
            )
            await state.clear()
            return

        building, error = await AddressService.create_building(
            session=db,
            address=data['address'],
            yard_id=data['yard_id'],
            created_by=user.id,  # ИСПРАВЛЕНО: используем user.id из БД, а не telegram_id
            gps_latitude=gps_latitude,
            gps_longitude=gps_longitude,
            entrance_count=data.get('entrance_count', 1),
            floor_count=data.get('floor_count', 1)
        )

        if error:
            await message.answer(
                f"❌ Ошибка создания здания:\n{error}",
                reply_markup=get_main_keyboard_for_role("manager", ["manager"])
            )
            await state.clear()
            return

        gps_info = f"📍 {gps_latitude}, {gps_longitude}" if gps_latitude and gps_longitude else "📍 Не указаны"

        await message.answer(
            f"✅ <b>Здание успешно создано!</b>\n\n"
            f"🏢 <b>Адрес:</b> {building.address}\n"
            f"<b>Подъездов:</b> {building.entrance_count}\n"
            f"<b>Этажей:</b> {building.floor_count}\n"
            f"<b>GPS координаты:</b> {gps_info}\n\n"
            f"Выберите действие:",
            reply_markup=get_address_management_menu()
        )

        logger.info(f"Создано новое здание: {building.address} (ID: {building.id}) пользователем {message.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка при создании здания: {e}")
        await message.answer(
            f"❌ Ошибка при создании здания: {str(e)}",
            reply_markup=get_main_keyboard_for_role("manager", ["manager"])
        )
    finally:
        db.close()
        await state.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# РЕДАКТИРОВАНИЕ ЗДАНИЯ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_building_edit:"))
async def show_building_edit_menu(callback: CallbackQuery):
    """Показать меню редактирования здания"""
    building_id = int(callback.data.split(":")[1])

    await callback.message.edit_text(
        "✏️ <b>Редактирование здания</b>\n\n"
        "Выберите, что хотите изменить:",
        reply_markup=get_building_edit_keyboard(building_id)
    )


@router.callback_query(F.data.startswith("addr_building_toggle:"))
async def toggle_building_status(callback: CallbackQuery):
    """Переключить активность здания"""
    building_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        building = await AddressService.get_building_by_id(db, building_id)
        if not building:
            await callback.answer("❌ Здание не найдено", show_alert=True)
            return

        new_status = not building.is_active
        building, error = await AddressService.update_building(
            session=db,
            building_id=building_id,
            is_active=new_status
        )

        if error:
            await callback.answer(f"❌ Ошибка: {error}", show_alert=True)
            return

        status_text = "активировано" if new_status else "деактивировано"
        await callback.answer(f"✅ Здание {status_text}")

        # Обновляем отображение
        await show_building_details(callback)

    except Exception as e:
        logger.error(f"Ошибка при переключении статуса здания: {e}")
        await callback.answer("❌ Ошибка изменения статуса", show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# УДАЛЕНИЕ ЗДАНИЯ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_building_delete:"))
async def confirm_building_deletion(callback: CallbackQuery):
    """Подтверждение удаления здания"""
    building_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        building = await AddressService.get_building_by_id(db, building_id)
        if not building:
            await callback.answer("❌ Здание не найдено", show_alert=True)
            return

        apartments_count = building.apartments_count if hasattr(building, 'apartments_count') else len(building.apartments)

        warning = ""
        if apartments_count > 0:
            warning = f"\n\n⚠️ <b>Внимание:</b> В этом здании {apartments_count} квартир. " \
                     f"Удаление возможно только после деактивации всех квартир."

        await callback.message.edit_text(
            f"❓ <b>Удаление здания</b>\n\n"
            f"Вы уверены, что хотите удалить здание:\n"
            f"<b>{building.address}</b>?"
            f"{warning}",
            reply_markup=get_confirmation_keyboard(
                confirm_callback=f"addr_building_delete_confirm:{building_id}",
                cancel_callback=f"addr_building_view:{building_id}"
            )
        )

    except Exception as e:
        logger.error(f"Ошибка при подготовке удаления здания: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
    finally:
        db.close()


@router.callback_query(F.data.startswith("addr_building_delete_confirm:"))
async def delete_building(callback: CallbackQuery):
    """Удаление здания"""
    building_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        success, error = await AddressService.delete_building(db, building_id)

        if not success:
            await callback.answer(f"❌ {error}", show_alert=True)
            return

        await callback.message.edit_text(
            "✅ <b>Здание успешно удалено (деактивировано)</b>"
        )

        logger.info(f"Здание {building_id} удалено пользователем {callback.from_user.id}")

        # Показываем список зданий
        await show_buildings_list(callback, None)

    except Exception as e:
        logger.error(f"Ошибка при удалении здания: {e}")
        await callback.answer("❌ Ошибка удаления", show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ОТМЕНА ДЕЙСТВИЙ
# ═══════════════════════════════════════════════════════════════════════════════
# Примечание: Обработчик cancel_apartment_selection перенесён в address_apartments.py
# так как он используется для отмены создания квартир, а не зданий
