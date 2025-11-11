"""
Обработчики для управления квартирами (Apartment Management)

Функционал:
- Просмотр списка квартир
- Создание новой квартиры
- Просмотр детальной информации о квартире
- Редактирование квартиры
- Удаление (деактивация) квартиры
- Поиск квартир по номеру или адресу
- Просмотр жителей квартиры
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from uk_management_bot.database.session import get_db
from uk_management_bot.services.address_service import AddressService
from uk_management_bot.states.address_management import ApartmentManagementStates
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.language_helpers import get_language_for_user
from uk_management_bot.keyboards.address_management import (
    get_apartments_list_keyboard,
    get_apartment_details_keyboard,
    get_apartment_edit_keyboard,
    get_confirmation_keyboard,
    get_skip_or_cancel_keyboard,
    get_cancel_keyboard_inline,
    get_user_apartment_selection_keyboard,
    get_address_management_menu
)
from uk_management_bot.keyboards.base import get_cancel_keyboard
from uk_management_bot.keyboards.base import get_main_keyboard_for_role

logger = logging.getLogger(__name__)

router = Router()


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР СПИСКА КВАРТИР
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "addr_apartments_list")
async def show_apartments_list(callback: CallbackQuery, state: FSMContext):
    """Показать выбор здания для просмотра квартир"""
    await state.clear()

    db = next(get_db())
    try:
        from uk_management_bot.database.models import Building
        from sqlalchemy import select, func
        from sqlalchemy.orm import joinedload

        # Получаем все здания с количеством квартир
        result = db.execute(
            select(Building)
            .options(joinedload(Building.yard))
            .where(Building.is_active == True)
            .order_by(Building.address)
        )
        buildings = result.unique().scalars().all()

        if not buildings:
            await callback.message.edit_text(
                "📋 <b>Управление квартирами</b>\n\n"
                "❌ Нет доступных зданий.\n"
                "Сначала добавьте здание в разделе 'Управление зданиями'.",
                reply_markup=get_apartments_menu()
            )
            return

        # Считаем количество квартир для каждого здания
        from uk_management_bot.database.models import Apartment
        apartments_counts = {}
        for building in buildings:
            apartments_count = db.execute(
                select(func.count(Apartment.id))
                .where(Apartment.building_id == building.id)
                .where(Apartment.is_active == True)
            ).scalar()
            apartments_counts[building.id] = apartments_count

        text = (
            f"🏠 <b>Управление квартирами</b>\n\n"
            f"Выберите здание для просмотра квартир:\n\n"
            f"<b>Всего зданий:</b> {len(buildings)}"
        )

        # Используем клавиатуру со списком зданий
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton

        builder = InlineKeyboardBuilder()

        # Добавляем кнопки для каждого здания
        for building in buildings:
            yard_info = f" ({building.yard.name})" if building.yard else ""
            apt_count = apartments_counts.get(building.id, 0)
            apartments_info = f" - {apt_count} кв." if apt_count > 0 else ""

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
            InlineKeyboardButton(text="➕ Добавить квартиру", callback_data="addr_apartment_create")
        )
        builder.row(
            InlineKeyboardButton(text="🔍 Поиск квартиры", callback_data="addr_apartment_search")
        )
        builder.row(
            InlineKeyboardButton(text="◀️ Назад", callback_data="addr_menu")
        )

        await callback.message.edit_text(
            text,
            reply_markup=builder.as_markup()
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке списка зданий для квартир: {e}")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
    finally:
        db.close()


@router.callback_query(F.data.startswith("addr_apartments_by_building:"))
async def show_apartments_by_building(callback: CallbackQuery):
    """Показать квартиры конкретного здания"""
    building_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        building = await AddressService.get_building_by_id(db, building_id, include_yard=True)
        if not building:
            await callback.answer("❌ Здание не найдено", show_alert=True)
            return

        apartments = await AddressService.get_apartments_by_building(db, building_id, only_active=False)

        text = f"🏠 <b>Квартиры здания</b>\n\n" \
               f"<b>Адрес:</b> {building.address}\n" \
               f"<b>Всего квартир:</b> {len(apartments)}\n"

        if not apartments:
            text += "\nСписок квартир пуст."

        await callback.message.edit_text(
            text,
            reply_markup=get_apartments_list_keyboard(apartments, page=0, building_id=building_id)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке квартир здания {building_id}: {e}")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
    finally:
        db.close()


@router.callback_query(F.data.startswith("addr_apartments_by_building_page:"))
async def paginate_apartments_by_building(callback: CallbackQuery):
    """Пагинация квартир конкретного здания"""
    parts = callback.data.split(":")
    building_id = int(parts[1])
    page = int(parts[2])

    db = next(get_db())
    try:
        building = await AddressService.get_building_by_id(db, building_id, include_yard=True)
        if not building:
            await callback.answer("❌ Здание не найдено", show_alert=True)
            return

        apartments = await AddressService.get_apartments_by_building(db, building_id, only_active=False)

        text = f"🏠 <b>Квартиры здания</b>\n\n" \
               f"<b>Адрес:</b> {building.address}\n" \
               f"<b>Всего квартир:</b> {len(apartments)}\n"

        if not apartments:
            text += "\nСписок квартир пуст."

        await callback.message.edit_text(
            text,
            reply_markup=get_apartments_list_keyboard(apartments, page=page, building_id=building_id)
        )

    except Exception as e:
        logger.error(f"Ошибка при пагинации квартир здания {building_id}: {e}")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ПОИСК КВАРТИР
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "addr_apartment_search")
async def start_apartment_search(callback: CallbackQuery, state: FSMContext):
    """Начать поиск квартиры"""
    # TASK 17: Localize apartment search prompt
    lang = await get_language_for_user(callback.from_user.id)

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
async def process_apartment_search(message: Message, state: FSMContext):
    """Обработка поискового запроса"""
    # TASK 17: Localize search results
    lang = await get_language_for_user(message.from_user.id)
    query = message.text.strip()

    if len(query) < 1:
        await message.answer(
            get_text('requests.search_query_too_short', language=lang)
        )
        return

    db = next(get_db())
    try:
        apartments = await AddressService.search_apartments(db, query, only_active=True)

        if not apartments:
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
            f"{get_text('requests.search_found_count', language=lang, count=len(apartments))}\n\n"
            f"{get_text('requests.search_select_apartment', language=lang)}"
        )

        await message.answer(
            text,
            reply_markup=get_apartments_list_keyboard(apartments, page=0)
        )

        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка при поиске квартир: {e}")
        await message.answer("❌ Ошибка поиска. Попробуйте еще раз.")
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР ДЕТАЛЬНОЙ ИНФОРМАЦИИ О КВАРТИРЕ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_apartment_view:"))
async def show_apartment_details(callback: CallbackQuery):
    """Показать детальную информацию о квартире"""
    apartment_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        apartment = await AddressService.get_apartment_by_id(db, apartment_id, include_building=True)

        if not apartment:
            await callback.answer("❌ Квартира не найдена", show_alert=True)
            return

        status = "✅ Активна" if apartment.is_active else "❌ Неактивна"
        residents_count = apartment.residents_count if hasattr(apartment, 'residents_count') else 0
        pending_count = apartment.pending_requests_count if hasattr(apartment, 'pending_requests_count') else 0

        text = f"🏠 <b>Квартира {apartment.apartment_number}</b>\n\n"

        if apartment.building:
            text += f"<b>Адрес:</b> {apartment.building.address}\n"
            if apartment.building.yard:
                text += f"<b>Двор:</b> {apartment.building.yard.name}\n"

        text += f"<b>Статус:</b> {status}\n\n"

        if apartment.entrance:
            text += f"<b>Подъезд:</b> {apartment.entrance}\n"
        if apartment.floor:
            text += f"<b>Этаж:</b> {apartment.floor}\n"
        if apartment.rooms_count:
            text += f"<b>Комнат:</b> {apartment.rooms_count}\n"
        if apartment.area:
            text += f"<b>Площадь:</b> {apartment.area} м²\n"

        text += f"\n<b>Жителей (подтвержденных):</b> {residents_count}\n"

        if pending_count > 0:
            text += f"<b>Заявок на рассмотрении:</b> {pending_count}\n"

        if apartment.description:
            text += f"\n<b>Описание:</b>\n{apartment.description}\n"

        if apartment.created_at:
            text += f"\n<b>Создана:</b> {apartment.created_at.strftime('%d.%m.%Y %H:%M')}"

        await callback.message.edit_text(
            text,
            reply_markup=get_apartment_details_keyboard(apartment_id)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке информации о квартире {apartment_id}: {e}")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР ЖИТЕЛЕЙ КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_apartment_residents:"))
async def show_apartment_residents(callback: CallbackQuery):
    """Показать список жителей квартиры"""
    apartment_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        apartment = await AddressService.get_apartment_by_id(db, apartment_id, include_building=True)
        if not apartment:
            await callback.answer("❌ Квартира не найдена", show_alert=True)
            return

        residents = await AddressService.get_apartment_residents(db, apartment_id, only_approved=False)

        text = f"👥 <b>Жители квартиры {apartment.apartment_number}</b>\n\n"

        if apartment.building:
            text += f"<b>Адрес:</b> {apartment.building.address}\n\n"

        if not residents:
            text += "Список жителей пуст."
        else:
            approved = [r for r in residents if r.status == 'approved']
            pending = [r for r in residents if r.status == 'pending']
            rejected = [r for r in residents if r.status == 'rejected']

            if approved:
                text += "<b>✅ Подтвержденные жители:</b>\n"
                for r in approved:
                    user_name = f"{r.user.first_name or ''} {r.user.last_name or ''}".strip() or f"ID: {r.user.telegram_id}"
                    owner_mark = " 👑" if r.is_owner else ""
                    primary_mark = " ⭐" if r.is_primary else ""
                    text += f"• {user_name}{owner_mark}{primary_mark}\n"
                text += "\n"

            if pending:
                text += f"<b>⏳ На рассмотрении ({len(pending)}):</b>\n"
                for r in pending:
                    user_name = f"{r.user.first_name or ''} {r.user.last_name or ''}".strip() or f"ID: {r.user.telegram_id}"
                    text += f"• {user_name}\n"
                text += "\n"

            if rejected:
                text += f"<b>❌ Отклоненные ({len(rejected)}):</b>\n"

        from uk_management_bot.keyboards.address_management import get_confirmation_keyboard
        keyboard = get_confirmation_keyboard(
            confirm_callback=f"addr_apartment_view:{apartment_id}",
            cancel_callback=f"addr_apartment_view:{apartment_id}"
        )

        await callback.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка при загрузке жителей квартиры {apartment_id}: {e}")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# СОЗДАНИЕ НОВОЙ КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "addr_apartment_create")
async def start_apartment_creation(callback: CallbackQuery, state: FSMContext):
    """Начать создание новой квартиры - выбор здания"""
    await state.clear()

    db = next(get_db())
    try:
        from uk_management_bot.database.models import Building
        from sqlalchemy import select

        result = db.execute(
            select(Building)
            .where(Building.is_active == True)
            .order_by(Building.address)
            .limit(50)
        )
        buildings = result.scalars().all()

        if not buildings:
            await callback.message.edit_text(
                "❌ <b>Нет доступных зданий</b>\n\n"
                "Сначала создайте хотя бы одно здание.",
                reply_markup=get_cancel_keyboard_inline()
            )
            return

        await state.set_state(ApartmentManagementStates.waiting_for_building_selection)

        await callback.message.edit_text(
            "➕ <b>Создание новой квартиры</b>\n\n"
            "Шаг 1: Выберите здание:",
            reply_markup=get_user_apartment_selection_keyboard(buildings, "building", "apartment_create_building")
        )

    except Exception as e:
        logger.error(f"Ошибка при начале создания квартиры: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
    finally:
        db.close()


@router.callback_query(F.data.startswith("apartment_create_building:"))
async def process_apartment_building_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора здания для новой квартиры"""
    building_id = int(callback.data.split(":")[1])

    await state.update_data(building_id=building_id)
    await state.set_state(ApartmentManagementStates.waiting_for_apartment_number)

    db = next(get_db())
    try:
        building = await AddressService.get_building_by_id(db, building_id)
        building_addr = building.address if building else "Неизвестное здание"

        await callback.message.edit_text(
            f"✅ Здание: <b>{building_addr}</b>\n\n"
            "Шаг 2: Введите номер квартиры:",
            reply_markup=get_cancel_keyboard_inline()
        )
    finally:
        db.close()


@router.message(StateFilter(ApartmentManagementStates.waiting_for_apartment_number))
async def process_apartment_number(message: Message, state: FSMContext):
    """Обработка номера квартиры"""
    number = message.text.strip()

    if len(number) < 1 or len(number) > 20:
        await message.answer(
            "❌ Номер квартиры должен содержать от 1 до 20 символов.\n\n"
            "Попробуйте еще раз:"
        )
        return

    await state.update_data(apartment_number=number)
    await state.set_state(ApartmentManagementStates.waiting_for_entrance_number)

    await message.answer(
        f"✅ Номер квартиры: <b>{number}</b>\n\n"
        "Шаг 3: Введите номер подъезда (или нажмите 'Пропустить'):",
        reply_markup=get_skip_or_cancel_keyboard()
    )


@router.message(StateFilter(ApartmentManagementStates.waiting_for_entrance_number))
async def process_apartment_entrance(message: Message, state: FSMContext):
    """Обработка номера подъезда"""
    if message.text == "⏭ Пропустить":
        entrance = None
    elif message.text == "❌ Отмена":
        await state.clear()
        await message.answer(
            "❌ Создание квартиры отменено",
            reply_markup=get_main_keyboard_for_role("manager", ["manager"])
        )
        return
    else:
        try:
            entrance = int(message.text.strip())
            if entrance < 1 or entrance > 50:
                raise ValueError("Номер подъезда вне допустимого диапазона")
        except ValueError:
            await message.answer(
                "❌ Неверный формат. Введите число от 1 до 50 или нажмите 'Пропустить':"
            )
            return

    await state.update_data(entrance=entrance)
    await state.set_state(ApartmentManagementStates.waiting_for_floor_number)

    entrance_text = f"<b>{entrance}</b>" if entrance else "Не указан"
    await message.answer(
        f"✅ Подъезд: {entrance_text}\n\n"
        "Шаг 4: Введите номер этажа (или нажмите 'Пропустить'):",
        reply_markup=get_skip_or_cancel_keyboard()
    )


@router.message(StateFilter(ApartmentManagementStates.waiting_for_floor_number))
async def process_apartment_floor(message: Message, state: FSMContext):
    """Обработка номера этажа"""
    if message.text == "⏭ Пропустить":
        floor = None
    elif message.text == "❌ Отмена":
        await state.clear()
        await message.answer(
            "❌ Создание квартиры отменено",
            reply_markup=get_main_keyboard_for_role("manager", ["manager"])
        )
        return
    else:
        try:
            floor = int(message.text.strip())
            if floor < 1 or floor > 100:
                raise ValueError("Номер этажа вне допустимого диапазона")
        except ValueError:
            await message.answer(
                "❌ Неверный формат. Введите число от 1 до 100 или нажмите 'Пропустить':"
            )
            return

    await state.update_data(floor=floor)
    await state.set_state(ApartmentManagementStates.waiting_for_rooms_count)

    floor_text = f"<b>{floor}</b>" if floor else "Не указан"
    await message.answer(
        f"✅ Этаж: {floor_text}\n\n"
        "Шаг 5: Введите количество комнат (или нажмите 'Пропустить'):",
        reply_markup=get_skip_or_cancel_keyboard()
    )


@router.message(StateFilter(ApartmentManagementStates.waiting_for_rooms_count))
async def process_apartment_rooms(message: Message, state: FSMContext):
    """Обработка количества комнат и переход к вводу площади"""
    if message.text == "⏭ Пропустить":
        rooms_count = None
    elif message.text == "❌ Отмена":
        await state.clear()
        await message.answer(
            "❌ Создание квартиры отменено",
            reply_markup=get_main_keyboard_for_role("manager", ["manager"])
        )
        return
    else:
        try:
            rooms_count = int(message.text.strip())
            if rooms_count < 1 or rooms_count > 20:
                raise ValueError("Количество комнат вне допустимого диапазона")
        except ValueError:
            await message.answer(
                "❌ Неверный формат. Введите число от 1 до 20 или нажмите 'Пропустить':"
            )
            return

    await state.update_data(rooms_count=rooms_count)
    await state.set_state(ApartmentManagementStates.waiting_for_area)

    rooms_text = f"<b>{rooms_count}</b>" if rooms_count else "Не указано"
    await message.answer(
        f"✅ Количество комнат: {rooms_text}\n\n"
        "Шаг 6: Введите площадь квартиры в кв.м (например, 65.5 или нажмите 'Пропустить'):",
        reply_markup=get_skip_or_cancel_keyboard()
    )


@router.message(StateFilter(ApartmentManagementStates.waiting_for_area))
async def process_apartment_area(message: Message, state: FSMContext):
    """Обработка площади квартиры и создание квартиры"""
    if message.text == "⏭ Пропустить":
        area = None
    elif message.text == "❌ Отмена":
        await state.clear()
        await message.answer(
            "❌ Создание квартиры отменено",
            reply_markup=get_main_keyboard_for_role("manager", ["manager"])
        )
        return
    else:
        try:
            area = float(message.text.strip().replace(',', '.'))
            if area <= 0 or area > 1000:
                raise ValueError("Площадь вне допустимого диапазона")
        except ValueError:
            await message.answer(
                "❌ Неверный формат. Введите площадь в кв.м (например, 65.5) или нажмите 'Пропустить':"
            )
            return

    # Сохраняем квартиру в базу
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

        apartment, error = await AddressService.create_apartment(
            session=db,
            building_id=data['building_id'],
            apartment_number=data['apartment_number'],
            created_by=user.id,  # ИСПРАВЛЕНО: используем user.id из БД, а не telegram_id
            entrance=data.get('entrance'),
            floor=data.get('floor'),
            rooms_count=data.get('rooms_count'),
            area=area  # ДОБАВЛЕНО: передаём площадь
        )

        if error:
            await message.answer(
                f"❌ Ошибка создания квартиры:\n{error}",
                reply_markup=get_main_keyboard_for_role("manager", ["manager"])
            )
            await state.clear()
            return

        text = f"✅ <b>Квартира успешно создана!</b>\n\n" \
               f"🏠 <b>Номер:</b> {apartment.apartment_number}\n"

        if apartment.entrance:
            text += f"<b>Подъезд:</b> {apartment.entrance}\n"
        if apartment.floor:
            text += f"<b>Этаж:</b> {apartment.floor}\n"
        if apartment.rooms_count:
            text += f"<b>Комнат:</b> {apartment.rooms_count}\n"
        if apartment.area:
            text += f"<b>Площадь:</b> {apartment.area} кв.м\n"

        text += "\nВыберите действие:"

        await message.answer(
            text,
            reply_markup=get_address_management_menu()
        )

        logger.info(f"Создана новая квартира: {apartment.apartment_number} (ID: {apartment.id}) пользователем {message.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка при создании квартиры: {e}")
        await message.answer(
            f"❌ Ошибка при создании квартиры: {str(e)}",
            reply_markup=get_main_keyboard_for_role("manager", ["manager"])
        )
    finally:
        db.close()
        await state.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# РЕДАКТИРОВАНИЕ КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_apartment_edit:"))
async def show_apartment_edit_menu(callback: CallbackQuery):
    """Показать меню редактирования квартиры"""
    apartment_id = int(callback.data.split(":")[1])

    await callback.message.edit_text(
        "✏️ <b>Редактирование квартиры</b>\n\n"
        "Выберите, что хотите изменить:",
        reply_markup=get_apartment_edit_keyboard(apartment_id)
    )


@router.callback_query(F.data.startswith("addr_apartment_toggle:"))
async def toggle_apartment_status(callback: CallbackQuery):
    """Переключить активность квартиры"""
    apartment_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        apartment = await AddressService.get_apartment_by_id(db, apartment_id)
        if not apartment:
            await callback.answer("❌ Квартира не найдена", show_alert=True)
            return

        new_status = not apartment.is_active
        apartment, error = await AddressService.update_apartment(
            session=db,
            apartment_id=apartment_id,
            is_active=new_status
        )

        if error:
            await callback.answer(f"❌ Ошибка: {error}", show_alert=True)
            return

        status_text = "активирована" if new_status else "деактивирована"
        await callback.answer(f"✅ Квартира {status_text}")

        # Обновляем отображение
        await show_apartment_details(callback)

    except Exception as e:
        logger.error(f"Ошибка при переключении статуса квартиры: {e}")
        await callback.answer("❌ Ошибка изменения статуса", show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# УДАЛЕНИЕ КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_apartment_delete:"))
async def confirm_apartment_deletion(callback: CallbackQuery):
    """Подтверждение удаления квартиры"""
    apartment_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        apartment = await AddressService.get_apartment_by_id(db, apartment_id, include_building=True)
        if not apartment:
            await callback.answer("❌ Квартира не найдена", show_alert=True)
            return

        residents_count = apartment.residents_count if hasattr(apartment, 'residents_count') else 0

        warning = ""
        if residents_count > 0:
            warning = f"\n\n⚠️ <b>Внимание:</b> В этой квартире {residents_count} подтвержденных жителей. " \
                     f"Удаление возможно только после удаления всех жителей."

        full_address = apartment.full_address if hasattr(apartment, 'full_address') else f"Квартира {apartment.apartment_number}"

        await callback.message.edit_text(
            f"❓ <b>Удаление квартиры</b>\n\n"
            f"Вы уверены, что хотите удалить:\n"
            f"<b>{full_address}</b>?"
            f"{warning}",
            reply_markup=get_confirmation_keyboard(
                confirm_callback=f"addr_apartment_delete_confirm:{apartment_id}",
                cancel_callback=f"addr_apartment_view:{apartment_id}"
            )
        )

    except Exception as e:
        logger.error(f"Ошибка при подготовке удаления квартиры: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
    finally:
        db.close()


@router.callback_query(F.data.startswith("addr_apartment_delete_confirm:"))
async def delete_apartment(callback: CallbackQuery):
    """Удаление квартиры"""
    apartment_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        success, error = await AddressService.delete_apartment(db, apartment_id)

        if not success:
            await callback.answer(f"❌ {error}", show_alert=True)
            return

        await callback.message.edit_text(
            "✅ <b>Квартира успешно удалена (деактивирована)</b>"
        )

        logger.info(f"Квартира {apartment_id} удалена пользователем {callback.from_user.id}")

        # Показываем список квартир
        await show_apartments_list(callback, None)

    except Exception as e:
        logger.error(f"Ошибка при удалении квартиры: {e}")
        await callback.answer("❌ Ошибка удаления", show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# РЕДАКТИРОВАНИЕ ПОЛЕЙ КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_apartment_edit_area:"))
async def start_edit_apartment_area(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование площади квартиры"""
    apartment_id = int(callback.data.split(":")[1])

    await state.update_data(editing_apartment_id=apartment_id)
    await state.set_state(ApartmentManagementStates.waiting_for_new_area)

    await callback.message.answer(
        "📐 <b>Редактирование площади квартиры</b>\n\n"
        "Введите новую площадь в кв.м (например, 65.5):",
        reply_markup=get_cancel_keyboard()
    )
    await callback.answer()


@router.message(StateFilter(ApartmentManagementStates.waiting_for_new_area))
async def process_new_apartment_area(message: Message, state: FSMContext):
    """Обработка новой площади квартиры"""
    if message.text == "❌ Отмена":
        data = await state.get_data()
        apartment_id = data.get('editing_apartment_id')
        await state.clear()

        if apartment_id:
            # Возвращаемся к меню редактирования
            keyboard = get_apartment_edit_keyboard(apartment_id)
            await message.answer(
                "✏️ <b>Редактирование квартиры</b>\n\n"
                "Выберите, что хотите изменить:",
                reply_markup=keyboard
            )
        return

    try:
        area = float(message.text.strip().replace(',', '.'))
        if area <= 0 or area > 1000:
            raise ValueError("Площадь вне допустимого диапазона")
    except ValueError:
        await message.answer(
            "❌ Неверный формат. Введите площадь в кв.м (например, 65.5):"
        )
        return

    data = await state.get_data()
    apartment_id = data.get('editing_apartment_id')

    if not apartment_id:
        await message.answer("❌ Ошибка: квартира не найдена")
        await state.clear()
        return

    db = next(get_db())
    try:
        apartment, error = await AddressService.update_apartment(
            session=db,
            apartment_id=apartment_id,
            area=area
        )

        if error:
            await message.answer(
                f"❌ Ошибка обновления площади:\n{error}",
                reply_markup=get_main_keyboard_for_role("manager", ["manager"])
            )
            await state.clear()
            return

        await message.answer(
            f"✅ <b>Площадь квартиры обновлена!</b>\n\n"
            f"Новая площадь: <b>{area} кв.м</b>",
            reply_markup=get_main_keyboard_for_role("manager", ["manager"])
        )

        logger.info(f"Площадь квартиры {apartment_id} обновлена на {area} кв.м пользователем {message.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка при обновлении площади квартиры: {e}")
        await message.answer(
            f"❌ Ошибка при обновлении площади: {str(e)}",
            reply_markup=get_main_keyboard_for_role("manager", ["manager"])
        )
    finally:
        db.close()
        await state.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# АВТОЗАПОЛНЕНИЕ КВАРТИР
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_building_autofill:"))
async def start_autofill_apartments(callback: CallbackQuery, state: FSMContext):
    """Начать процесс автозаполнения квартир для здания"""
    building_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        building = await AddressService.get_building_by_id(db, building_id, include_yard=True)
        if not building:
            await callback.answer("❌ Здание не найдено", show_alert=True)
            return

        # Сохраняем ID здания в state
        await state.update_data(autofill_building_id=building_id)
        await state.set_state(ApartmentManagementStates.waiting_for_autofill_range)

        text = (
            f"🔢 <b>Автозаполнение квартир</b>\n\n"
            f"<b>Здание:</b> {building.address}\n"
            f"{f'<b>Двор:</b> {building.yard.name}' if building.yard else ''}\n\n"
            f"Введите диапазон номеров квартир для создания.\n\n"
            f"<b>Примеры форматов:</b>\n"
            f"• <b>1-50</b> — создаст квартиры с 1 по 50\n"
            f"• <b>1,5,10,15</b> — создаст квартиры 1, 5, 10, 15\n"
            f"• <b>1-10,15,20-25</b> — комбинированный формат\n\n"
            f"⚠️ Квартиры с уже существующими номерами будут пропущены.\n"
        )

        await callback.message.edit_text(
            text,
            reply_markup=get_cancel_keyboard_inline()
        )

    except Exception as e:
        logger.error(f"Ошибка при начале автозаполнения: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
    finally:
        db.close()


@router.message(StateFilter(ApartmentManagementStates.waiting_for_autofill_range))
async def process_autofill_range(message: Message, state: FSMContext):
    """Обработать ввод диапазона номеров квартир"""
    range_text = message.text.strip()

    if range_text in ["❌ Отмена", "/cancel"]:
        await state.clear()
        await message.answer(
            "❌ Автозаполнение отменено",
            reply_markup=get_address_management_menu()
        )
        return

    # Парсим диапазон и получаем список номеров квартир
    try:
        apartment_numbers = parse_apartment_range(range_text)

        if not apartment_numbers:
            await message.answer(
                "❌ Некорректный формат. Пожалуйста, введите диапазон в формате:\n"
                "• 1-50\n"
                "• 1,5,10,15\n"
                "• 1-10,15,20-25"
            )
            return

        if len(apartment_numbers) > 500:
            await message.answer(
                f"❌ Слишком много квартир ({len(apartment_numbers)}). "
                f"Максимум — 500 за одну операцию."
            )
            return

    except ValueError as e:
        await message.answer(f"❌ Ошибка разбора диапазона: {e}")
        return

    # Получаем данные из state
    data = await state.get_data()
    building_id = data.get("autofill_building_id")

    if not building_id:
        await message.answer("❌ Ошибка: здание не найдено. Начните заново.")
        await state.clear()
        return

    # Подтверждение
    await state.update_data(apartment_numbers=apartment_numbers)

    text = (
        f"✅ <b>Подтверждение автозаполнения</b>\n\n"
        f"Будет создано квартир: <b>{len(apartment_numbers)}</b>\n"
        f"Номера: {format_numbers_preview(apartment_numbers)}\n\n"
        f"Продолжить?"
    )

    await message.answer(
        text,
        reply_markup=get_confirmation_keyboard(
            confirm_callback="addr_autofill_confirm",
            cancel_callback="addr_autofill_cancel"
        )
    )


@router.callback_query(F.data == "addr_autofill_confirm")
async def confirm_autofill_apartments(callback: CallbackQuery, state: FSMContext):
    """Подтвердить и выполнить автозаполнение"""
    data = await state.get_data()
    building_id = data.get("autofill_building_id")
    apartment_numbers = data.get("apartment_numbers", [])

    if not building_id or not apartment_numbers:
        await callback.answer("❌ Ошибка: данные не найдены", show_alert=True)
        await state.clear()
        return

    db = next(get_db())
    try:
        # Получаем user.id из базы данных по telegram_id
        from uk_management_bot.database.models import User
        from sqlalchemy import select

        user = db.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        ).scalar_one_or_none()

        if not user:
            await callback.answer("❌ Пользователь не найден в базе данных", show_alert=True)
            await state.clear()
            db.close()
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
        text = (
            f"✅ <b>Автозаполнение завершено!</b>\n\n"
            f"<b>Создано квартир:</b> {created_count}\n"
        )

        if skipped_count > 0:
            text += f"<b>Пропущено (уже существуют):</b> {skipped_count}\n"

        if errors:
            text += f"\n⚠️ <b>Ошибки:</b>\n"
            for error in errors[:5]:  # Показываем только первые 5 ошибок
                text += f"• {error}\n"
            if len(errors) > 5:
                text += f"• и ещё {len(errors) - 5}...\n"

        text += f"\nВыберите действие:"

        await callback.message.edit_text(
            text,
            reply_markup=get_address_management_menu()
        )

    except Exception as e:
        logger.error(f"Ошибка при автозаполнении квартир: {e}")
        await callback.answer("❌ Ошибка создания квартир", show_alert=True)
        db.rollback()
    finally:
        db.close()
        await state.clear()


@router.callback_query(F.data == "addr_autofill_cancel")
async def cancel_autofill_apartments(callback: CallbackQuery, state: FSMContext):
    """Отменить автозаполнение"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Автозаполнение отменено",
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


def format_numbers_preview(numbers: list[str], max_show: int = 10) -> str:
    """
    Форматирует список номеров для предпросмотра

    Args:
        numbers: Список номеров
        max_show: Максимальное количество отображаемых номеров

    Returns:
        Строка с номерами
    """
    if len(numbers) <= max_show:
        return ", ".join(numbers)
    else:
        shown = ", ".join(numbers[:max_show])
        return f"{shown}... (и ещё {len(numbers) - max_show})"


# ═══════════════════════════════════════════════════════════════════════════════
# ОТМЕНА ДЕЙСТВИЙ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "cancel_apartment_selection")
async def cancel_apartment_action(callback: CallbackQuery, state: FSMContext):
    """Отмена выбора квартиры или создания"""
    await state.clear()
    await callback.message.edit_text("❌ Действие отменено")

    await callback.message.answer(
        "📍 <b>Справочник адресов</b>",
        reply_markup=get_address_management_menu()
    )


@router.callback_query(F.data == "cancel_action")
async def cancel_generic_action(callback: CallbackQuery, state: FSMContext):
    """Отмена текущего действия (универсальный обработчик)"""
    await state.clear()
    await callback.message.edit_text("❌ Действие отменено")

    await callback.message.answer(
        "📍 <b>Справочник адресов</b>",
        reply_markup=get_address_management_menu()
    )
