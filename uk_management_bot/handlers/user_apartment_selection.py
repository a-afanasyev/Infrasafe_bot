"""
Обработчики выбора квартиры пользователем при регистрации

Функционал:
- Выбор двора из доступных
- Выбор здания в выбранном дворе
- Выбор квартиры в выбранном здании
- Подтверждение выбора
- Отправка заявки на модерацию
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from uk_management_bot.database.session import get_db
from uk_management_bot.services.address_service import AddressService
from uk_management_bot.states.onboarding import OnboardingStates
from uk_management_bot.keyboards.address_management import (
    get_user_apartment_selection_keyboard,
    get_confirmation_keyboard
)
from uk_management_bot.keyboards.base import get_main_keyboard_for_role

logger = logging.getLogger(__name__)

router = Router()


# ═══════════════════════════════════════════════════════════════════════════════
# НАЧАЛО ВЫБОРА КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

async def start_apartment_selection(message: Message, state: FSMContext):
    """
    Начать процесс выбора квартиры (может вызываться из onboarding или профиля)

    Эта функция вызывается из onboarding.py после ввода телефона
    """
    db = next(get_db())
    try:
        yards = await AddressService.get_all_yards(db, only_active=True)

        if not yards:
            await message.answer(
                "❌ <b>К сожалению, справочник адресов пуст</b>\n\n"
                "Обратитесь к администратору для добавления адресов.\n\n"
                "Вы можете продолжить регистрацию без указания квартиры."
            )
            # Переход к документам
            await state.set_state(OnboardingStates.waiting_for_document_type)
            return

        await state.set_state(OnboardingStates.waiting_for_yard_selection)

        await message.answer(
            "🏘 <b>Выбор квартиры</b>\n\n"
            "Шаг 1 из 3: Выберите двор, в котором находится ваша квартира:",
            reply_markup=get_user_apartment_selection_keyboard(
                yards,
                "yard",
                "user_apartment_yard"
            )
        )

    except Exception as e:
        logger.error(f"Ошибка при начале выбора квартиры: {e}")
        await message.answer(
            "❌ Ошибка при загрузке списка дворов. Попробуйте позже."
        )
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ШАГ 1: ВЫБОР ДВОРА
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("user_apartment_yard:"))
async def process_yard_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора двора пользователем"""
    yard_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        yard = await AddressService.get_yard_by_id(db, yard_id)
        if not yard or not yard.is_active:
            await callback.answer("❌ Двор не найден", show_alert=True)
            return

        # Получаем здания этого двора
        buildings = await AddressService.get_buildings_by_yard(db, yard_id, only_active=True)

        if not buildings:
            await callback.answer(
                f"❌ В дворе '{yard.name}' пока нет зданий. Выберите другой двор.",
                show_alert=True
            )
            return

        await state.update_data(
            selected_yard_id=yard_id,
            selected_yard_name=yard.name
        )
        await state.set_state(OnboardingStates.waiting_for_building_selection)

        await callback.message.edit_text(
            f"✅ Двор: <b>{yard.name}</b>\n\n"
            f"🏢 Шаг 2 из 3: Выберите здание:",
            reply_markup=get_user_apartment_selection_keyboard(
                buildings,
                "building",
                "user_apartment_building"
            )
        )

    except Exception as e:
        logger.error(f"Ошибка при выборе двора {yard_id}: {e}")
        await callback.answer("❌ Ошибка обработки", show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ШАГ 2: ВЫБОР ЗДАНИЯ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("user_apartment_building:"))
async def process_building_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора здания пользователем"""
    building_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        building = await AddressService.get_building_by_id(db, building_id, include_yard=True)
        if not building or not building.is_active:
            await callback.answer("❌ Здание не найдено", show_alert=True)
            return

        # Получаем квартиры этого здания
        apartments = await AddressService.get_apartments_by_building(db, building_id, only_active=True)

        if not apartments:
            await callback.answer(
                f"❌ В здании по адресу '{building.address}' пока нет квартир. Выберите другое здание.",
                show_alert=True
            )
            return

        data = await state.get_data()
        yard_name = data.get('selected_yard_name', 'Не указан')

        await state.update_data(
            selected_building_id=building_id,
            selected_building_address=building.address
        )
        await state.set_state(OnboardingStates.waiting_for_apartment_selection)

        await callback.message.edit_text(
            f"✅ Двор: <b>{yard_name}</b>\n"
            f"✅ Здание: <b>{building.address}</b>\n\n"
            f"🏠 Шаг 3 из 3: Выберите вашу квартиру:",
            reply_markup=get_user_apartment_selection_keyboard(
                apartments,
                "apartment",
                "user_apartment_final"
            )
        )

    except Exception as e:
        logger.error(f"Ошибка при выборе здания {building_id}: {e}")
        await callback.answer("❌ Ошибка обработки", show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ШАГ 3: ВЫБОР КВАРТИРЫ И ПОДТВЕРЖДЕНИЕ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("user_apartment_final:"))
async def process_apartment_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка финального выбора квартиры - показать подтверждение"""
    apartment_id = int(callback.data.split(":")[1])

    db = next(get_db())
    try:
        # Получаем user.id из базы данных (не telegram_id!)
        from uk_management_bot.database.models.user import User
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return

        apartment = await AddressService.get_apartment_by_id(db, apartment_id, include_building=True)
        if not apartment or not apartment.is_active:
            await callback.answer("❌ Квартира не найдена", show_alert=True)
            return

        # Проверяем, не подавал ли пользователь уже заявку на эту квартиру
        from uk_management_bot.database.models import UserApartment
        from sqlalchemy import select

        existing = db.execute(
            select(UserApartment).where(
                UserApartment.user_id == user.id,  # ИСПРАВЛЕНО: используем user.id из БД
                UserApartment.apartment_id == apartment_id
            )
        ).scalar_one_or_none()

        if existing:
            status_text = {
                'pending': 'уже на рассмотрении',
                'approved': 'уже подтверждена',
                'rejected': 'была отклонена. Обратитесь к администратору'
            }.get(existing.status, 'уже существует')

            await callback.answer(
                f"⚠️ Ваша заявка на эту квартиру {status_text}",
                show_alert=True
            )
            return

        data = await state.get_data()
        yard_name = data.get('selected_yard_name', 'Не указан')
        building_address = data.get('selected_building_address', 'Не указан')

        await state.update_data(selected_apartment_id=apartment_id)
        await state.set_state(OnboardingStates.confirming_apartment)

        # Формируем информацию о квартире
        apartment_info = f"Квартира {apartment.apartment_number}"
        if apartment.entrance:
            apartment_info += f", подъезд {apartment.entrance}"
        if apartment.floor:
            apartment_info += f", {apartment.floor} этаж"

        await callback.message.edit_text(
            f"📋 <b>Подтверждение выбора квартиры</b>\n\n"
            f"🏘 <b>Двор:</b> {yard_name}\n"
            f"🏢 <b>Здание:</b> {building_address}\n"
            f"🏠 <b>Квартира:</b> {apartment_info}\n\n"
            f"❓ <b>Подтвердите выбор квартиры?</b>\n\n"
            f"После подтверждения ваша заявка будет отправлена на модерацию администратору.",
            reply_markup=get_confirmation_keyboard(
                confirm_callback="user_apartment_confirm",
                cancel_callback="user_apartment_cancel"
            )
        )

    except Exception as e:
        logger.error(f"Ошибка при выборе квартиры {apartment_id}: {e}")
        await callback.answer("❌ Ошибка обработки", show_alert=True)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ПОДТВЕРЖДЕНИЕ И СОЗДАНИЕ ЗАЯВКИ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "user_apartment_confirm")
async def confirm_apartment_request(callback: CallbackQuery, state: FSMContext):
    """Подтверждение выбора и создание заявки на модерацию"""
    data = await state.get_data()
    apartment_id = data.get('selected_apartment_id')

    if not apartment_id:
        await callback.answer("❌ Ошибка: квартира не выбрана", show_alert=True)
        return

    db = next(get_db())
    try:
        # Получаем user.id из базы данных (не telegram_id!)
        from uk_management_bot.database.models.user import User
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return

        # Создаем заявку на квартиру
        user_apartment, error = await AddressService.request_apartment(
            session=db,
            user_id=user.id,  # ИСПРАВЛЕНО: используем user.id из БД, а не telegram_id
            apartment_id=apartment_id,
            is_owner=False,  # По умолчанию - проживающий
            is_primary=True   # Первая квартира - основная
        )

        if error:
            await callback.message.edit_text(
                f"❌ <b>Ошибка создания заявки:</b>\n\n{error}"
            )
            await callback.answer("❌ Не удалось создать заявку", show_alert=True)
            return

        # Получаем данные для уведомления
        apartment = await AddressService.get_apartment_by_id(db, apartment_id, include_building=True)
        full_address = apartment.full_address if hasattr(apartment, 'full_address') else f"Квартира {apartment.apartment_number}"

        await callback.message.edit_text(
            f"✅ <b>Заявка успешно отправлена!</b>\n\n"
            f"🏠 <b>Адрес:</b> {full_address}\n\n"
            f"⏳ Ваша заявка отправлена на рассмотрение администратору.\n"
            f"Вы получите уведомление после проверки.\n\n"
            f"А пока продолжим регистрацию..."
        )

        logger.info(
            f"Пользователь {user.telegram_id} (DB ID: {user.id}) отправил заявку на квартиру {apartment_id} "
            f"(UserApartment ID: {user_apartment.id})"
        )

        # Отправляем уведомление администраторам
        await send_apartment_request_notification(
            user_apartment_id=user_apartment.id,
            user_id=user.telegram_id,  # ИСПРАВЛЕНО: используем user.telegram_id для Telegram API
            apartment_address=full_address
        )

        # Очищаем данные выбора квартиры из state
        await state.update_data(
            selected_yard_id=None,
            selected_yard_name=None,
            selected_building_id=None,
            selected_building_address=None,
            selected_apartment_id=None
        )

        # Переходим к следующему шагу регистрации (документы)
        await state.set_state(OnboardingStates.waiting_for_document_type)

        # Отправляем новое сообщение о документах
        from uk_management_bot.keyboards.onboarding import get_document_type_keyboard
        await callback.message.answer(
            "📄 <b>Загрузка документов</b>\n\n"
            "Для подтверждения личности загрузите один из документов:\n"
            "• Паспорт\n"
            "• Водительские права\n"
            "• Другой документ с фото\n\n"
            "Выберите тип документа:",
            reply_markup=get_document_type_keyboard()
        )

    except Exception as e:
        logger.error(f"Ошибка при подтверждении заявки на квартиру: {e}")
        await callback.message.edit_text(
            "❌ <b>Произошла ошибка</b>\n\n"
            "Не удалось отправить заявку. Попробуйте позже или обратитесь к администратору."
        )
    finally:
        db.close()


@router.callback_query(F.data == "user_apartment_cancel")
async def cancel_apartment_request(callback: CallbackQuery, state: FSMContext):
    """Отмена выбора квартиры"""
    await state.update_data(
        selected_yard_id=None,
        selected_yard_name=None,
        selected_building_id=None,
        selected_building_address=None,
        selected_apartment_id=None
    )

    await callback.message.edit_text(
        "❌ <b>Выбор квартиры отменен</b>\n\n"
        "Вы можете выбрать квартиру позже в настройках профиля.\n\n"
        "Продолжим регистрацию..."
    )

    # Переходим к следующему шагу регистрации (документы)
    await state.set_state(OnboardingStates.waiting_for_document_type)

    from uk_management_bot.keyboards.onboarding import get_document_type_keyboard
    await callback.message.answer(
        "📄 <b>Загрузка документов</b>\n\n"
        "Для подтверждения личности загрузите один из документов:\n"
        "• Паспорт\n"
        "• Водительские права\n"
        "• Другой документ с фото\n\n"
        "Выберите тип документа:",
        reply_markup=get_document_type_keyboard()
    )


# ═══════════════════════════════════════════════════════════════════════════════
# УВЕДОМЛЕНИЕ АДМИНИСТРАТОРОВ
# ═══════════════════════════════════════════════════════════════════════════════

async def send_apartment_request_notification(
    user_apartment_id: int,
    user_id: int,
    apartment_address: str
):
    """
    Отправить уведомление администраторам о новой заявке на квартиру

    Args:
        user_apartment_id: ID записи UserApartment
        user_id: Telegram ID пользователя
        apartment_address: Полный адрес квартиры
    """
    try:
        from aiogram import Bot
        from uk_management_bot.config.settings import settings
        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.database.models import User
        from sqlalchemy import select

        if not settings.ADMIN_USER_IDS:
            logger.warning("ADMIN_USER_IDS не настроены - уведомления не отправлены")
            return

        # Получаем информацию о пользователе
        db = SessionLocal()
        try:
            user = db.execute(
                select(User).where(User.telegram_id == user_id)
            ).scalar_one_or_none()

            if not user:
                return

            user_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
            if not user_name:
                user_name = f"ID: {user.telegram_id}"

            username = f"@{user.username}" if user.username else "Нет username"

            notification_text = (
                f"🔔 <b>Новая заявка на квартиру!</b>\n\n"
                f"👤 <b>Пользователь:</b> {user_name}\n"
                f"📱 <b>Username:</b> {username}\n"
                f"🆔 <b>ID:</b> <code>{user.telegram_id}</code>\n"
                f"🏠 <b>Квартира:</b> {apartment_address}\n\n"
                f"📋 Перейдите в раздел <b>Модерация заявок</b> для проверки."
            )

            # Используем бота из текущего контекста
            from aiogram import Bot
            bot = Bot.get_current()

            for admin_id in settings.ADMIN_USER_IDS:
                try:
                    await bot.send_message(admin_id, notification_text)
                    logger.info(f"Уведомление о заявке {user_apartment_id} отправлено админу {admin_id}")
                except Exception as e:
                    logger.warning(f"Не удалось отправить уведомление админу {admin_id}: {e}")

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Ошибка при отправке уведомлений о заявке {user_apartment_id}: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# АДАПТЕР ДЛЯ ВЫЗОВА ИЗ ПРОФИЛЯ
# ═══════════════════════════════════════════════════════════════════════════════

async def start_apartment_selection_for_profile(callback: CallbackQuery, state: FSMContext):
    """
    Начать выбор квартиры из профиля (для добавления дополнительной квартиры)

    Отличия от регистрации:
    - Вызывается через callback (не message)
    - Использует другие состояния (не onboarding states)
    - После завершения возвращает в профиль
    """
    # Используем те же состояния onboarding для простоты
    # Можно создать отдельные состояния, если нужна другая логика
    await state.set_state(OnboardingStates.waiting_for_yard_selection)

    db = next(get_db())
    try:
        yards = await AddressService.get_all_yards(db, only_active=True)

        if not yards:
            await callback.message.edit_text(
                "❌ <b>К сожалению, справочник адресов пуст</b>\n\n"
                "Обратитесь к администратору для добавления адресов."
            )
            return

        # Создаем клавиатуру выбора двора
        keyboard = get_user_apartment_selection_keyboard(
            items=yards,
            item_type='yard',
            callback_prefix='user_apartment_yard'
        )

        await callback.message.edit_text(
            "🏘️ <b>Добавление квартиры</b>\n\n"
            "Шаг 1 из 3: Выберите двор:",
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка начала выбора квартиры из профиля: {e}")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
    finally:
        db.close()
