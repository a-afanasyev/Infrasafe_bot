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

from uk_management_bot.database.session import session_scope
from uk_management_bot.services.address_service import AddressService
from uk_management_bot.states.onboarding import OnboardingStates
from uk_management_bot.keyboards.address_management import (
    get_user_apartment_selection_keyboard,
    get_confirmation_keyboard
)
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

router = Router()


# ═══════════════════════════════════════════════════════════════════════════════
# НАЧАЛО ВЫБОРА КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

async def start_apartment_selection(message: Message, state: FSMContext, language: str = "ru"):
    """
    Начать процесс выбора квартиры (может вызываться из onboarding или профиля)

    Эта функция вызывается из onboarding.py после ввода телефона
    """
    try:
        with session_scope() as db:
            yards = AddressService.get_all_yards(db, only_active=True)

            if not yards:
                lang = language
                await message.answer(
                    get_text("user_apt_selection.handlers.address_directory_empty", language=lang)
                )
                # Переход к документам
                await state.set_state(OnboardingStates.waiting_for_document_type)
                return

            await state.set_state(OnboardingStates.waiting_for_yard_selection)

            lang = language
            await message.answer(
                get_text("user_apt_selection.handlers.select_yard_step1", language=lang),
                reply_markup=get_user_apartment_selection_keyboard(
                    yards,
                    "yard",
                    "user_apartment_yard"
                )
            )

    except Exception as e:
        logger.error(f"Ошибка при начале выбора квартиры: {e}")
        lang = language
        await message.answer(
            get_text("user_apt_selection.handlers.error_loading_yards", language=lang)
        )


# ═══════════════════════════════════════════════════════════════════════════════
# ШАГ 1: ВЫБОР ДВОРА
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("user_apartment_yard:"))
async def process_yard_selection(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Обработка выбора двора пользователем"""
    yard_id = int(callback.data.split(":")[1])

    try:
        with session_scope() as db:
            yard = AddressService.get_yard_by_id(db, yard_id)
            lang = language
            if not yard or not yard.is_active:
                await callback.answer(get_text("user_apt_selection.handlers.yard_not_found", language=lang), show_alert=True)
                return

            # Получаем здания этого двора
            buildings = AddressService.get_buildings_by_yard(db, yard_id, only_active=True)

            if not buildings:
                await callback.answer(
                    get_text("user_apt_selection.handlers.no_buildings_in_yard", language=lang).format(yard_name=yard.name),
                    show_alert=True
                )
                return

            await state.update_data(
                selected_yard_id=yard_id,
                selected_yard_name=yard.name
            )
            await state.set_state(OnboardingStates.waiting_for_building_selection)

            await callback.message.edit_text(
                get_text("user_apt_selection.handlers.select_building_step2", language=lang).format(yard_name=yard.name),
                reply_markup=get_user_apartment_selection_keyboard(
                    buildings,
                    "building",
                    "user_apartment_building"
                )
            )

    except Exception as e:
        logger.error(f"Ошибка при выборе двора {yard_id}: {e}")
        await callback.answer(get_text("user_apt_selection.handlers.error_processing", language=lang), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ШАГ 2: ВЫБОР ЗДАНИЯ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("user_apartment_building:"))
async def process_building_selection(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Обработка выбора здания пользователем"""
    building_id = int(callback.data.split(":")[1])

    try:
        with session_scope() as db:
            building = AddressService.get_building_by_id(db, building_id, include_yard=True)
            lang = language
            if not building or not building.is_active:
                await callback.answer(get_text("user_apt_selection.handlers.building_not_found", language=lang), show_alert=True)
                return

            # Получаем квартиры этого здания
            apartments = AddressService.get_apartments_by_building(db, building_id, only_active=True)

            if not apartments:
                await callback.answer(
                    get_text("user_apt_selection.handlers.no_apartments_in_building", language=lang).format(address=building.address),
                    show_alert=True
                )
                return

            data = await state.get_data()
            yard_name = data.get('selected_yard_name', get_text("user_apt_selection.handlers.not_specified", language=lang))

            await state.update_data(
                selected_building_id=building_id,
                selected_building_address=building.address
            )
            await state.set_state(OnboardingStates.waiting_for_apartment_selection)

            await callback.message.edit_text(
                get_text("user_apt_selection.handlers.select_apartment_step3", language=lang).format(
                    yard_name=yard_name, building_address=building.address
                ),
                reply_markup=get_user_apartment_selection_keyboard(
                    apartments,
                    "apartment",
                    "user_apartment_final"
                )
            )

    except Exception as e:
        logger.error(f"Ошибка при выборе здания {building_id}: {e}")
        await callback.answer(get_text("user_apt_selection.handlers.error_processing", language=lang), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ШАГ 3: ВЫБОР КВАРТИРЫ И ПОДТВЕРЖДЕНИЕ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("user_apartment_final:"))
async def process_apartment_selection(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Обработка финального выбора квартиры - показать подтверждение"""
    apartment_id = int(callback.data.split(":")[1])

    try:
        with session_scope() as db:
            # Получаем user.id из базы данных (не telegram_id!)
            from uk_management_bot.database.models.user import User
            user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
            lang = language
            if not user:
                await callback.answer(get_text("user_apt_selection.handlers.user_not_found", language=lang), show_alert=True)
                return

            apartment = AddressService.get_apartment_by_id(db, apartment_id, include_building=True)
            if not apartment or not apartment.is_active:
                await callback.answer(get_text("user_apt_selection.handlers.apartment_not_found", language=lang), show_alert=True)
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
                status_key = {
                    'pending': 'user_apt_selection.handlers.request_status_pending',
                    'approved': 'user_apt_selection.handlers.request_status_approved',
                    'rejected': 'user_apt_selection.handlers.request_status_rejected'
                }.get(existing.status, 'user_apt_selection.handlers.request_status_exists')
                status_text = get_text(status_key, language=lang)

                await callback.answer(
                    get_text("user_apt_selection.handlers.request_already_exists", language=lang).format(status=status_text),
                    show_alert=True
                )
                return

            data = await state.get_data()
            yard_name = data.get('selected_yard_name', get_text("user_apt_selection.handlers.not_specified", language=lang))
            building_address = data.get('selected_building_address', 'Не указан')

            await state.update_data(selected_apartment_id=apartment_id)
            await state.set_state(OnboardingStates.confirming_apartment)

            # Формируем информацию о квартире
            apartment_info = get_text("user_apt_selection.handlers.apartment_label", language=lang).format(number=apartment.apartment_number)
            if apartment.entrance:
                apartment_info += get_text("user_apt_selection.handlers.entrance_label", language=lang).format(entrance=apartment.entrance)
            if apartment.floor:
                apartment_info += get_text("user_apt_selection.handlers.floor_label", language=lang).format(floor=apartment.floor)

            await callback.message.edit_text(
                get_text("user_apt_selection.handlers.confirm_apartment_selection", language=lang).format(
                    yard_name=yard_name, building_address=building_address, apartment_info=apartment_info
                ),
                reply_markup=get_confirmation_keyboard(
                    confirm_callback="user_apartment_confirm",
                    cancel_callback="user_apartment_cancel"
                )
            )

    except Exception as e:
        logger.error(f"Ошибка при выборе квартиры {apartment_id}: {e}")
        await callback.answer(get_text("user_apt_selection.handlers.error_processing", language=lang), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ПОДТВЕРЖДЕНИЕ И СОЗДАНИЕ ЗАЯВКИ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "user_apartment_confirm")
async def confirm_apartment_request(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Подтверждение выбора и создание заявки на модерацию"""
    data = await state.get_data()
    apartment_id = data.get('selected_apartment_id')

    lang = language
    if not apartment_id:
        await callback.answer(get_text("user_apt_selection.handlers.error_no_apartment_selected", language=lang), show_alert=True)
        return

    try:
        with session_scope() as db:
            # Получаем user.id из базы данных (не telegram_id!)
            from uk_management_bot.database.models.user import User
            user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
            if not user:
                await callback.answer(get_text("user_apt_selection.handlers.user_not_found", language=lang), show_alert=True)
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
                    get_text("user_apt_selection.handlers.request_creation_error", language=lang).format(error=error)
                )
                await callback.answer(get_text("user_apt_selection.handlers.error_request_failed", language=lang), show_alert=True)
                return

            # Получаем данные для уведомления
            apartment = AddressService.get_apartment_by_id(db, apartment_id, include_building=True)
            full_address = apartment.full_address if hasattr(apartment, 'full_address') else get_text("user_apt_selection.handlers.apartment_label", language=lang).format(number=apartment.apartment_number)

            await callback.message.edit_text(
                get_text("user_apt_selection.handlers.request_sent_success", language=lang).format(address=full_address)
            )

            logger.info(
                f"Пользователь {user.telegram_id} (DB ID: {user.id}) отправил заявку на квартиру {apartment_id} "
                f"(UserApartment ID: {user_apartment.id})"
            )

            # Отправляем уведомление администраторам
            await send_apartment_request_notification(
                user_apartment_id=user_apartment.id,
                user_id=user.telegram_id,  # ИСПРАВЛЕНО: используем user.telegram_id для Telegram API
                apartment_address=full_address,
                bot=callback.bot
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
                get_text("user_apt_selection.handlers.upload_documents_prompt", language=lang),
                reply_markup=get_document_type_keyboard()
            )

    except Exception as e:
        logger.error(f"Ошибка при подтверждении заявки на квартиру: {e}")
        await callback.message.edit_text(
            get_text("user_apt_selection.handlers.error_sending_request", language=lang)
        )


@router.callback_query(F.data == "user_apartment_cancel")
async def cancel_apartment_request(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Отмена выбора квартиры"""
    await state.update_data(
        selected_yard_id=None,
        selected_yard_name=None,
        selected_building_id=None,
        selected_building_address=None,
        selected_apartment_id=None
    )

    lang = language
    await callback.message.edit_text(
        get_text("user_apt_selection.handlers.apartment_selection_cancelled", language=lang)
    )

    # Переходим к следующему шагу регистрации (документы)
    await state.set_state(OnboardingStates.waiting_for_document_type)

    from uk_management_bot.keyboards.onboarding import get_document_type_keyboard
    await callback.message.answer(
        get_text("user_apt_selection.handlers.upload_documents_prompt", language=lang),
        reply_markup=get_document_type_keyboard()
    )


# ═══════════════════════════════════════════════════════════════════════════════
# УВЕДОМЛЕНИЕ АДМИНИСТРАТОРОВ
# ═══════════════════════════════════════════════════════════════════════════════

async def send_apartment_request_notification(
    user_apartment_id: int,
    user_id: int,
    apartment_address: str,
    bot=None
):
    """
    Отправить уведомление администраторам о новой заявке на квартиру

    Args:
        user_apartment_id: ID записи UserApartment
        user_id: Telegram ID пользователя
        apartment_address: Полный адрес квартиры
    """
    try:
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

            username = f"@{user.username}" if user.username else "N/A"

            notification_text = get_text("user_apt_selection.handlers.admin_new_apartment_request", language='ru').format(
                user_name=user_name, username=username,
                telegram_id=user.telegram_id, apartment_address=apartment_address
            )

            # bot передаётся как параметр

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

async def start_apartment_selection_for_profile(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """
    Начать выбор квартиры из профиля (для добавления дополнительной квартиры)

    Отличия от регистрации:
    - Вызывается через callback (не message)
    - Использует другие состояния (не onboarding states)
    - После завершения возвращает в профиль
    """
    # Используем те же состояния onboarding для простоты
    # Можно создать отдельные состояния, если нужна другая логика
    # BUG-BOT-021: помечаем entry-point, чтобы cancel мог вернуться в профиль,
    # а не утечь в admin-вью справочника адресов.
    await state.update_data(entry_from="profile")
    await state.set_state(OnboardingStates.waiting_for_yard_selection)

    try:
        with session_scope() as db:
            yards = AddressService.get_all_yards(db, only_active=True)

            if not yards:
                lang = language
                await callback.message.edit_text(
                    get_text("user_apt_selection.handlers.address_directory_empty_short", language=lang)
                )
                return

            # Создаем клавиатуру выбора двора
            keyboard = get_user_apartment_selection_keyboard(
                items=yards,
                item_type='yard',
                callback_prefix='user_apartment_yard'
            )

            lang = language
            await callback.message.edit_text(
                get_text("user_apt_selection.handlers.add_apartment_step1", language=lang),
                reply_markup=keyboard
            )

    except Exception as e:
        logger.error(f"Ошибка начала выбора квартиры из профиля: {e}")
        await callback.answer(get_text("user_apt_selection.handlers.error_loading_data", language=lang), show_alert=True)
