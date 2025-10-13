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

logger = logging.getLogger(__name__)

router = Router()

# Примечание: Проверка ролей происходит на уровне глобальных middleware (auth_middleware)
# Дополнительная проверка в handlers при необходимости


# ═══════════════════════════════════════════════════════════════════════════════
# ГЛАВНОЕ МЕНЮ СПРАВОЧНИКА АДРЕСОВ
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "📍 Справочник адресов")
async def show_address_management_menu(message: Message, state: FSMContext):
    """Показать главное меню управления адресами"""
    await state.clear()

    from uk_management_bot.keyboards.address_management import get_address_management_menu

    await message.answer(
        "📍 <b>Справочник адресов</b>\n\n"
        "Управление структурой адресов:\n"
        "🏘 Дворы → 🏢 Здания → 🏠 Квартиры → 👤 Жители\n\n"
        "Выберите раздел:",
        reply_markup=get_address_management_menu()
    )


@router.callback_query(F.data == "addr_menu")
async def show_address_menu_callback(callback: CallbackQuery, state: FSMContext):
    """Показать главное меню управления адресами (callback)"""
    await state.clear()

    from uk_management_bot.keyboards.address_management import get_address_management_menu

    await callback.message.edit_text(
        "📍 <b>Справочник адресов</b>\n\n"
        "Управление структурой адресов:\n"
        "🏘 Дворы → 🏢 Здания → 🏠 Квартиры → 👤 Жители\n\n"
        "Выберите раздел:",
        reply_markup=get_address_management_menu()
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР СПИСКА ДВОРОВ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "addr_yards_list")
async def show_yards_list(callback: CallbackQuery, state: FSMContext):
    """Показать список всех дворов"""
    await state.clear()

    db = next(get_db())
    try:
        yards = await AddressService.get_all_yards(db, only_active=False, include_stats=True)

        if not yards:
            await callback.message.edit_text(
                "📋 <b>Список дворов пуст</b>\n\n"
                "Добавьте первый двор для начала работы.",
                reply_markup=get_yards_list_keyboard([], page=0)
            )
            return

        text = f"📋 <b>Список дворов</b>\n\n" \
               f"Всего дворов: {len(yards)}\n" \
               f"Активных: {len([y for y in yards if y.is_active])}\n\n" \
               f"Выберите двор для просмотра:"

        await callback.message.edit_text(
            text,
            reply_markup=get_yards_list_keyboard(yards, page=0)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке списка дворов: {e}")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
    finally:
        db.close()


@router.callback_query(F.data.startswith("addr_yards_page:"))
async def show_yards_page(callback: CallbackQuery):
    """Показать конкретную страницу списка дворов"""
    page = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        yards = await AddressService.get_all_yards(db, only_active=False, include_stats=True)

        text = f"📋 <b>Список дворов</b> (страница {page + 1})\n\n" \
               f"Всего дворов: {len(yards)}\n\n" \
               f"Выберите двор для просмотра:"

        await callback.message.edit_text(
            text,
            reply_markup=get_yards_list_keyboard(yards, page=page)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке страницы дворов: {e}")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР ДЕТАЛЬНОЙ ИНФОРМАЦИИ О ДВОРЕ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_yard_view:"))
async def show_yard_details(callback: CallbackQuery):
    """Показать детальную информацию о дворе"""
    yard_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        yard = await AddressService.get_yard_by_id(db, yard_id)

        if not yard:
            await callback.answer("❌ Двор не найден", show_alert=True)
            return

        status = "✅ Активен" if yard.is_active else "❌ Неактивен"
        gps = f"📍 {yard.gps_latitude}, {yard.gps_longitude}" if yard.gps_latitude and yard.gps_longitude else "📍 Не указаны"
        buildings_count = yard.buildings_count if hasattr(yard, 'buildings_count') else len(yard.buildings)

        text = f"🏘 <b>Двор: {yard.name}</b>\n\n" \
               f"<b>Статус:</b> {status}\n" \
               f"<b>Зданий:</b> {buildings_count}\n" \
               f"<b>GPS координаты:</b> {gps}\n"

        if yard.description:
            text += f"\n<b>Описание:</b>\n{yard.description}\n"

        if yard.created_at:
            text += f"\n<b>Создан:</b> {yard.created_at.strftime('%d.%m.%Y %H:%M')}"

        await callback.message.edit_text(
            text,
            reply_markup=get_yard_details_keyboard(yard_id)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке информации о дворе {yard_id}: {e}")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# СОЗДАНИЕ НОВОГО ДВОРА
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "addr_yard_create")
async def start_yard_creation(callback: CallbackQuery, state: FSMContext):
    """Начать создание нового двора"""
    await state.clear()
    await state.set_state(YardManagementStates.waiting_for_yard_name)

    await callback.message.edit_text(
        "➕ <b>Создание нового двора</b>\n\n"
        "Введите название двора:",
        reply_markup=get_cancel_keyboard_inline()
    )


@router.message(StateFilter(YardManagementStates.waiting_for_yard_name))
async def process_yard_name(message: Message, state: FSMContext):
    """Обработка названия двора"""
    name = message.text.strip()

    if len(name) < 3:
        await message.answer(
            "❌ Название двора должно содержать минимум 3 символа.\n\n"
            "Попробуйте еще раз:"
        )
        return

    if len(name) > 200:
        await message.answer(
            "❌ Название двора слишком длинное (максимум 200 символов).\n\n"
            "Попробуйте еще раз:"
        )
        return

    await state.update_data(name=name)
    await state.set_state(YardManagementStates.waiting_for_yard_description)

    await message.answer(
        f"✅ Название: <b>{name}</b>\n\n"
        "Теперь введите описание двора (или нажмите 'Пропустить'):",
        reply_markup=get_skip_or_cancel_keyboard()
    )


@router.message(StateFilter(YardManagementStates.waiting_for_yard_description))
async def process_yard_description(message: Message, state: FSMContext):
    """Обработка описания двора"""
    if message.text == "⏭ Пропустить":
        description = None
    elif message.text == "❌ Отмена":
        await state.clear()
        await message.answer(
            "❌ Создание двора отменено",
            reply_markup=get_main_keyboard_for_role("manager", ["manager"])
        )
        return
    else:
        description = message.text.strip()

    await state.update_data(description=description)
    await state.set_state(YardManagementStates.waiting_for_yard_gps)

    await message.answer(
        "Теперь введите GPS координаты двора в формате:\n"
        "широта, долгота\n\n"
        "Например: 41.2995, 69.2401\n\n"
        "Или нажмите 'Пропустить':",
        reply_markup=get_skip_or_cancel_keyboard()
    )


@router.message(StateFilter(YardManagementStates.waiting_for_yard_gps))
async def process_yard_gps(message: Message, state: FSMContext):
    """Обработка GPS координат двора"""
    gps_latitude = None
    gps_longitude = None

    if message.text == "⏭ Пропустить":
        pass
    elif message.text == "❌ Отмена":
        await state.clear()
        await message.answer(
            "❌ Создание двора отменено",
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

            # Проверка диапазона координат
            if not (-90 <= gps_latitude <= 90) or not (-180 <= gps_longitude <= 180):
                raise ValueError("Координаты вне допустимого диапазона")

        except ValueError as e:
            await message.answer(
                f"❌ Неверный формат координат: {e}\n\n"
                "Введите координаты в формате: широта, долгота\n"
                "Например: 41.2995, 69.2401\n\n"
                "Или нажмите 'Пропустить':"
            )
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
                "❌ Пользователь не найден",
                reply_markup=get_main_keyboard_for_role("manager", ["manager"])
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
                f"❌ Ошибка создания двора:\n{error}",
                reply_markup=get_main_keyboard_for_role("manager", ["manager"])
            )
            await state.clear()
            return

        gps_info = f"📍 {gps_latitude}, {gps_longitude}" if gps_latitude and gps_longitude else "📍 Не указаны"
        desc_info = f"\n<b>Описание:</b> {data.get('description')}" if data.get('description') else ""

        await message.answer(
            f"✅ <b>Двор успешно создан!</b>\n\n"
            f"🏘 <b>Название:</b> {yard.name}\n"
            f"<b>GPS координаты:</b> {gps_info}"
            f"{desc_info}\n\n"
            f"Выберите действие:",
            reply_markup=get_address_management_menu()
        )

        logger.info(f"Создан новый двор: {yard.name} (ID: {yard.id}) пользователем {message.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка при создании двора: {e}")
        await message.answer(
            f"❌ Ошибка при создании двора: {str(e)}",
            reply_markup=get_main_keyboard_for_role("manager", ["manager"])
        )
    finally:
        db.close()
        await state.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# РЕДАКТИРОВАНИЕ ДВОРА
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_yard_edit:"))
async def show_yard_edit_menu(callback: CallbackQuery):
    """Показать меню редактирования двора"""
    yard_id = int(callback.data.split(":")[1])

    await callback.message.edit_text(
        "✏️ <b>Редактирование двора</b>\n\n"
        "Выберите, что хотите изменить:",
        reply_markup=get_yard_edit_keyboard(yard_id)
    )


@router.callback_query(F.data.startswith("addr_yard_edit_name:"))
async def start_yard_name_edit(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование названия двора"""
    yard_id = int(callback.data.split(":")[1])

    await state.update_data(yard_id=yard_id)
    await state.set_state(YardManagementStates.waiting_for_new_yard_name)

    await callback.message.edit_text(
        "✏️ <b>Редактирование названия двора</b>\n\n"
        "Введите новое название:",
        reply_markup=get_cancel_keyboard_inline()
    )


@router.message(StateFilter(YardManagementStates.waiting_for_new_yard_name))
async def process_new_yard_name(message: Message, state: FSMContext):
    """Обработка нового названия двора"""
    new_name = message.text.strip()

    if len(new_name) < 3 or len(new_name) > 200:
        await message.answer(
            "❌ Название должно содержать от 3 до 200 символов.\n\n"
            "Попробуйте еще раз:"
        )
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
            await message.answer(f"❌ Ошибка: {error}")
            return

        await message.answer(
            f"✅ Название двора успешно изменено на:\n<b>{new_name}</b>",
            reply_markup=get_main_keyboard_for_role("manager", ["manager"])
        )

        logger.info(f"Двор {yard_id} переименован в '{new_name}' пользователем {message.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка при обновлении названия двора: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")
    finally:
        db.close()
        await state.clear()


@router.callback_query(F.data.startswith("addr_yard_toggle:"))
async def toggle_yard_status(callback: CallbackQuery):
    """Переключить активность двора"""
    yard_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        yard = await AddressService.get_yard_by_id(db, yard_id)
        if not yard:
            await callback.answer("❌ Двор не найден", show_alert=True)
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

        status_text = "активирован" if new_status else "деактивирован"
        await callback.answer(f"✅ Двор {status_text}")

        # Обновляем отображение
        await show_yard_details(callback)

    except Exception as e:
        logger.error(f"Ошибка при переключении статуса двора: {e}")
        await callback.answer("❌ Ошибка изменения статуса", show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# УДАЛЕНИЕ ДВОРА
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_yard_delete:"))
async def confirm_yard_deletion(callback: CallbackQuery):
    """Подтверждение удаления двора"""
    yard_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        yard = await AddressService.get_yard_by_id(db, yard_id)
        if not yard:
            await callback.answer("❌ Двор не найден", show_alert=True)
            return

        buildings_count = yard.buildings_count if hasattr(yard, 'buildings_count') else len(yard.buildings)

        warning = ""
        if buildings_count > 0:
            warning = f"\n\n⚠️ <b>Внимание:</b> В этом дворе {buildings_count} зданий. " \
                     f"Удаление возможно только после деактивации всех зданий."

        await callback.message.edit_text(
            f"❓ <b>Удаление двора</b>\n\n"
            f"Вы уверены, что хотите удалить двор:\n"
            f"<b>{yard.name}</b>?"
            f"{warning}",
            reply_markup=get_confirmation_keyboard(
                confirm_callback=f"addr_yard_delete_confirm:{yard_id}",
                cancel_callback=f"addr_yard_view:{yard_id}"
            )
        )

    except Exception as e:
        logger.error(f"Ошибка при подготовке удаления двора: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
    finally:
        db.close()


@router.callback_query(F.data.startswith("addr_yard_delete_confirm:"))
async def delete_yard(callback: CallbackQuery):
    """Удаление двора"""
    yard_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        success, error = await AddressService.delete_yard(db, yard_id)

        if not success:
            await callback.answer(f"❌ {error}", show_alert=True)
            return

        await callback.message.edit_text(
            "✅ <b>Двор успешно удален (деактивирован)</b>"
        )

        logger.info(f"Двор {yard_id} удален пользователем {callback.from_user.id}")

        # Показываем список дворов
        await show_yards_list(callback, None)

    except Exception as e:
        logger.error(f"Ошибка при удалении двора: {e}")
        await callback.answer("❌ Ошибка удаления", show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ОТМЕНА ДЕЙСТВИЙ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "cancel_action")
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    """Отмена текущего действия"""
    await state.clear()
    await callback.message.edit_text("❌ Действие отменено")
    await show_yards_list(callback, state)


@router.message(F.text == "❌ Отмена")
async def cancel_with_button(message: Message, state: FSMContext):
    """Отмена через кнопку"""
    await state.clear()
    await message.answer(
        "❌ Действие отменено",
        reply_markup=get_main_keyboard_for_role("manager", ["manager"])
    )


@router.callback_query(F.data == "admin_menu")
async def back_to_admin_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное админское меню"""
    await state.clear()

    from uk_management_bot.keyboards.admin import get_manager_main_keyboard

    await callback.message.answer(
        "👨‍💼 <b>Панель управления</b>\n\nВыберите раздел:",
        reply_markup=get_manager_main_keyboard()
    )

    # Удаляем предыдущее сообщение с inline-клавиатурой
    try:
        await callback.message.delete()
    except Exception:
        pass
