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
from dataclasses import dataclass
from typing import Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import run_db
from uk_management_bot.services.address_service import AddressService
from uk_management_bot.states.onboarding import OnboardingStates
from uk_management_bot.keyboards.contact import get_share_contact_keyboard
from uk_management_bot.keyboards.address_management import (
    get_user_apartment_selection_keyboard,
    get_confirmation_keyboard
)
from uk_management_bot.utils.address_helpers import apartment_address
from uk_management_bot.utils.button_texts import get_select_apartment_texts
from uk_management_bot.utils.telegram_client import SEND_TIMEOUT
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

router = Router()

SELECT_APARTMENT_TEXTS = get_select_apartment_texts()


# ==========================================================================
# DTO для async-слоя: наружу из run_db выходят примитивы, не ORM-строки
# (у ORM-объекта за пределами worker-потока нет живой сессии).
# ==========================================================================

@dataclass(frozen=True)
class _YardOpt:
    """Строка выбора двора — ровно те атрибуты, что читает
    get_user_apartment_selection_keyboard(item_type='yard')."""
    id: int
    name: str


@dataclass(frozen=True)
class _BuildingOpt:
    """Строка выбора здания (item_type='building')."""
    id: int
    address: str


@dataclass(frozen=True)
class _ApartmentOpt:
    """Строка выбора квартиры (item_type='apartment') + данные экрана
    подтверждения (number/entrance/floor)."""
    id: int
    apartment_number: str
    floor: Optional[int]
    entrance: Optional[str]


@dataclass(frozen=True)
class _YardBuildings:
    """Шаг 2: имя выбранного двора + его здания."""
    yard_name: str
    buildings: tuple


@dataclass(frozen=True)
class _BuildingApartments:
    """Шаг 3: адрес выбранного здания + его квартиры."""
    address: str
    apartments: tuple


# ==========================================================================
# Sync unit-of-work (AUD3-07/AUD5-ARCH-1): исполняются в worker-потоке через
# run_db; сессию открывает и закрывает run_db, event loop БД не трогает.
# Мутация (request_apartment) сюда НЕ входит: это async-метод AddressService
# с собственной async-сессией — его хендлер await'ит напрямую.
# ==========================================================================

def _load_user_phone(db, telegram_id: int) -> Optional[str]:
    """-> users.phone | None (нет пользователя или телефона). Гейт §3.3."""
    from uk_management_bot.database.models.user import User
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    return user.phone if user else None


def _load_active_yards(db) -> list:
    """-> [_YardOpt] активных дворов (шаг 1)."""
    yards = AddressService.get_all_yards(db, only_active=True)
    return [_YardOpt(id=yard.id, name=yard.name) for yard in yards]


def _load_yard_buildings(db, yard_id: int) -> Optional[_YardBuildings]:
    """-> _YardBuildings | None (None — двор не найден или неактивен)."""
    yard = AddressService.get_yard_by_id(db, yard_id)
    if not yard or not yard.is_active:
        return None

    # Получаем здания этого двора
    buildings = AddressService.get_buildings_by_yard(db, yard_id, only_active=True)
    return _YardBuildings(
        yard_name=yard.name,
        buildings=tuple(_BuildingOpt(id=b.id, address=b.address) for b in buildings),
    )


def _load_building_apartments(db, building_id: int) -> Optional[_BuildingApartments]:
    """-> _BuildingApartments | None (None — здание не найдено или неактивно)."""
    building = AddressService.get_building_by_id(db, building_id, include_yard=True)
    if not building or not building.is_active:
        return None

    # Получаем квартиры этого здания
    apartments = AddressService.get_apartments_by_building(db, building_id, only_active=True)
    return _BuildingApartments(
        address=building.address,
        apartments=tuple(
            _ApartmentOpt(
                id=a.id,
                apartment_number=a.apartment_number,
                floor=a.floor,
                entrance=a.entrance,
            )
            for a in apartments
        ),
    )


def _load_apartment_confirmation(db, telegram_id: int, apartment_id: int) -> tuple:
    """-> ('user_not_found'|'apartment_not_found', None)
        | ('exists', status: str)
        | ('ok', _ApartmentOpt)."""
    # Получаем user.id из базы данных (не telegram_id!)
    from uk_management_bot.database.models.user import User
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        return ("user_not_found", None)

    apartment = AddressService.get_apartment_by_id(db, apartment_id, include_building=True)
    if not apartment or not apartment.is_active:
        return ("apartment_not_found", None)

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
        return ("exists", existing.status)

    return (
        "ok",
        _ApartmentOpt(
            id=apartment.id,
            apartment_number=apartment.apartment_number,
            floor=apartment.floor,
            entrance=apartment.entrance,
        ),
    )


def _user_id_by_tg(db, telegram_id: int) -> Optional[int]:
    """-> users.id | None. Получаем user.id из базы данных (не telegram_id!)."""
    from uk_management_bot.database.models.user import User
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    return user.id if user else None


def _load_full_address(db, apartment_id: int, lang: str) -> str:
    """Локализованный адрес квартиры для экрана «заявка отправлена»."""
    # Получаем данные для уведомления
    apartment = AddressService.get_apartment_by_id(db, apartment_id, include_building=True)
    return apartment_address(apartment, lang)


def _load_admin_notification_texts(db, user_id: int, apartment_id: int) -> Optional[list]:
    """Fetch/рендер-фаза уведомления админам (B3-раскрой).

    -> [(admin_id, text)] | None (заявитель не найден). Отправка — в async-слое.
    """
    from uk_management_bot.config.settings import settings
    from uk_management_bot.database.models import User
    from uk_management_bot.database.models.apartment import Apartment
    from sqlalchemy import select

    # Получаем информацию о пользователе
    user = db.execute(
        select(User).where(User.telegram_id == user_id)
    ).scalar_one_or_none()

    if not user:
        return None

    user_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    if not user_name:
        user_name = f"ID: {user.telegram_id}"

    username = f"@{user.username}" if user.username else "N/A"

    apartment = db.get(Apartment, apartment_id)

    # AUD5-CODE-12: язык РАЗНЫЙ у разных админов — раньше здесь стоял
    # хардкод `language='ru'`, и UZ-администратор получал русский экран.
    # Один запрос на всех получателей вместо запроса на каждого.
    admin_languages = {
        row[0]: row[1]
        for row in db.execute(
            select(User.telegram_id, User.language).where(
                User.telegram_id.in_(settings.ADMIN_USER_IDS)
            )
        ).all()
    }

    notifications = []
    for admin_id in settings.ADMIN_USER_IDS:
        admin_lang = admin_languages.get(admin_id) or "ru"
        notification_text = get_text(
            "user_apt_selection.handlers.admin_new_apartment_request",
            language=admin_lang,
        ).format(
            user_name=user_name, username=username,
            telegram_id=user.telegram_id,
            apartment_address=(
                apartment_address(apartment, admin_lang) if apartment else "—"
            ),
        )
        notifications.append((admin_id, notification_text))
    return notifications


# ═══════════════════════════════════════════════════════════════════════════════
# НАЧАЛО ВЫБОРА КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(F.text.in_(SELECT_APARTMENT_TEXTS))
async def start_apartment_selection(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """
    Начать процесс выбора квартиры (может вызываться из onboarding или профиля)

    Вызывается двумя путями: программно из onboarding.py после ввода телефона и
    нажатием кнопки «🏠 Выбрать квартиру» на экране онбординга. Декоратора
    раньше не было — кнопка в base.py рисовалась, но не ловилась ничем, и
    нажатие первой кнопкой не давало ровным счётом ничего.
    """
    try:
        # Телефон обязателен ДО выбора квартиры (спека 2026-09-03 §3.3). Текст
        # кнопки шлёт клиент (BUG-169) — проверяем здесь, а не по клавиатуре.
        phone = await run_db(lambda s: _load_user_phone(s, message.from_user.id), db=_db)
        if not phone:
            await message.answer(
                get_text("onboarding.phone_required", language=language),
                reply_markup=get_share_contact_keyboard(language, with_cancel=False),
            )
            return

        yards = await run_db(_load_active_yards, db=_db)

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
                "user_apartment_yard",
                language=lang
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
async def process_yard_selection(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработка выбора двора пользователем"""
    yard_id = int(callback.data.split(":")[1])

    # WR-06 (класс): дефолт ДО try. `lang` присваивается после db-фазы,
    # и если она бросит (недоступна БД), `except` ниже сошлётся
    # на несвязанное имя → NameError вместо сообщения об ошибке.
    lang = "ru"
    try:
        yard = await run_db(lambda s: _load_yard_buildings(s, yard_id), db=_db)
        lang = language
        if not yard:
            await callback.answer(get_text("user_apt_selection.handlers.yard_not_found", language=lang), show_alert=True)
            return

        if not yard.buildings:
            await callback.answer(
                get_text("user_apt_selection.handlers.no_buildings_in_yard", language=lang).format(yard_name=yard.yard_name),
                show_alert=True
            )
            return

        await state.update_data(
            selected_yard_id=yard_id,
            selected_yard_name=yard.yard_name
        )
        await state.set_state(OnboardingStates.waiting_for_building_selection)

        await callback.message.edit_text(
            get_text("user_apt_selection.handlers.select_building_step2", language=lang).format(yard_name=yard.yard_name),
            reply_markup=get_user_apartment_selection_keyboard(
                yard.buildings,
                "building",
                "user_apartment_building",
                language=lang
            )
        )

    except Exception as e:
        logger.error(f"Ошибка при выборе двора {yard_id}: {e}")
        await callback.answer(get_text("user_apt_selection.handlers.error_processing", language=lang), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ШАГ 2: ВЫБОР ЗДАНИЯ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("user_apartment_building:"))
async def process_building_selection(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработка выбора здания пользователем"""
    building_id = int(callback.data.split(":")[1])

    # WR-06 (класс): дефолт ДО try. `lang` присваивается после db-фазы,
    # и если она бросит (недоступна БД), `except` ниже сошлётся
    # на несвязанное имя → NameError вместо сообщения об ошибке.
    lang = "ru"
    try:
        building = await run_db(lambda s: _load_building_apartments(s, building_id), db=_db)
        lang = language
        if not building:
            await callback.answer(get_text("user_apt_selection.handlers.building_not_found", language=lang), show_alert=True)
            return

        if not building.apartments:
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
                building.apartments,
                "apartment",
                "user_apartment_final",
                language=lang
            )
        )

    except Exception as e:
        logger.error(f"Ошибка при выборе здания {building_id}: {e}")
        await callback.answer(get_text("user_apt_selection.handlers.error_processing", language=lang), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ШАГ 3: ВЫБОР КВАРТИРЫ И ПОДТВЕРЖДЕНИЕ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("user_apartment_final:"))
async def process_apartment_selection(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработка финального выбора квартиры - показать подтверждение"""
    apartment_id = int(callback.data.split(":")[1])

    # WR-06 (класс): дефолт ДО try. `lang` присваивается после db-фазы,
    # и если она бросит (недоступна БД), `except` ниже сошлётся
    # на несвязанное имя → NameError вместо сообщения об ошибке.
    lang = "ru"
    try:
        verdict, payload = await run_db(
            lambda s: _load_apartment_confirmation(s, callback.from_user.id, apartment_id), db=_db
        )
        lang = language
        if verdict == "user_not_found":
            await callback.answer(get_text("user_apt_selection.handlers.user_not_found", language=lang), show_alert=True)
            return

        if verdict == "apartment_not_found":
            await callback.answer(get_text("user_apt_selection.handlers.apartment_not_found", language=lang), show_alert=True)
            return

        if verdict == "exists":
            status_key = {
                'pending': 'user_apt_selection.handlers.request_status_pending',
                'approved': 'user_apt_selection.handlers.request_status_approved',
                'rejected': 'user_apt_selection.handlers.request_status_rejected'
            }.get(payload, 'user_apt_selection.handlers.request_status_exists')
            status_text = get_text(status_key, language=lang)

            await callback.answer(
                get_text("user_apt_selection.handlers.request_already_exists", language=lang).format(status=status_text),
                show_alert=True
            )
            return

        apartment = payload

        data = await state.get_data()
        yard_name = data.get('selected_yard_name', get_text("user_apt_selection.handlers.not_specified", language=lang))
        building_address = data.get('selected_building_address') or get_text("user_apt_selection.handlers.not_specified", language=lang)

        await state.update_data(selected_apartment_id=apartment_id)
        await state.set_state(OnboardingStates.confirming_apartment)

        # Формируем информацию о квартире
        apartment_info = get_text("user_apt_selection.handlers.apartment_label", language=lang).format(number=apartment.apartment_number)
        # BUG-152 п.5: значение 0 легитимно — сравнение по is not None.
        if apartment.entrance is not None:
            apartment_info += get_text("user_apt_selection.handlers.entrance_label", language=lang).format(entrance=apartment.entrance)
        if apartment.floor is not None:
            apartment_info += get_text("user_apt_selection.handlers.floor_label", language=lang).format(floor=apartment.floor)

        await callback.message.edit_text(
            get_text("user_apt_selection.handlers.confirm_apartment_selection", language=lang).format(
                yard_name=yard_name, building_address=building_address, apartment_info=apartment_info
            ),
            reply_markup=get_confirmation_keyboard(
                confirm_callback="user_apartment_confirm",
                cancel_callback="user_apartment_cancel",
                language=lang
            )
        )

    except Exception as e:
        logger.error(f"Ошибка при выборе квартиры {apartment_id}: {e}")
        await callback.answer(get_text("user_apt_selection.handlers.error_processing", language=lang), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ПОДТВЕРЖДЕНИЕ И СОЗДАНИЕ ЗАЯВКИ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "user_apartment_confirm")
async def confirm_apartment_request(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Подтверждение выбора и создание заявки на модерацию"""
    data = await state.get_data()
    apartment_id = data.get('selected_apartment_id')

    lang = language
    if not apartment_id:
        await callback.answer(get_text("user_apt_selection.handlers.error_no_apartment_selected", language=lang), show_alert=True)
        return

    try:
        # Получаем user.id из базы данных (не telegram_id!)
        user_id = await run_db(lambda s: _user_id_by_tg(s, callback.from_user.id), db=_db)
        if user_id is None:
            await callback.answer(get_text("user_apt_selection.handlers.user_not_found", language=lang), show_alert=True)
            return

        # Создаем заявку на квартиру. request_apartment — async-метод с
        # собственной async-сессией; параметр session им не используется
        # (пишет через _async_session()).
        user_apartment, error = await AddressService.request_apartment(
            session=None,
            user_id=user_id,  # ИСПРАВЛЕНО: используем user.id из БД, а не telegram_id
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

        full_address = await run_db(lambda s: _load_full_address(s, apartment_id, lang), db=_db)

        await callback.message.edit_text(
            get_text("user_apt_selection.handlers.request_sent_success", language=lang).format(address=full_address)
        )

        logger.info(
            f"Пользователь {callback.from_user.id} (DB ID: {user_id}) отправил заявку на квартиру {apartment_id} "
            f"(UserApartment ID: {user_apartment.id})"
        )

        # Отправляем уведомление администраторам
        await send_apartment_request_notification(
            user_apartment_id=user_apartment.id,
            user_id=callback.from_user.id,  # ИСПРАВЛЕНО: используем telegram_id для Telegram API
            # AUD5-CODE-12: передаём ID, а не готовую строку. Уведомление
            # читает ДРУГОЙ человек, и адрес в нём должен быть на его языке —
            # значит и достаёт, и локализует его сама функция.
            apartment_id=apartment_id,
            bot=callback.bot,
            _db=_db
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
            reply_markup=get_document_type_keyboard(language=lang)
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
        reply_markup=get_document_type_keyboard(language=lang)
    )


# ═══════════════════════════════════════════════════════════════════════════════
# УВЕДОМЛЕНИЕ АДМИНИСТРАТОРОВ
# ═══════════════════════════════════════════════════════════════════════════════

async def send_apartment_request_notification(
    user_apartment_id: int,
    user_id: int,
    apartment_id: int,
    bot=None,
    *,
    _db=None
):
    """
    Отправить уведомление администраторам о новой заявке на квартиру

    Args:
        user_apartment_id: ID записи UserApartment
        user_id: Telegram ID пользователя
        apartment_id: ID квартиры — адрес достаётся и локализуется здесь, под
            язык каждого администратора (получатель — не заявитель)
    """
    try:
        from uk_management_bot.config.settings import settings

        if not settings.ADMIN_USER_IDS:
            logger.warning("ADMIN_USER_IDS не настроены - уведомления не отправлены")
            return

        # B3-раскрой: fetch + рендер текстов — в worker-потоке (run_db),
        # сеть (send_message) — здесь, вне сессии.
        notifications = await run_db(
            lambda s: _load_admin_notification_texts(s, user_id, apartment_id), db=_db
        )

        if notifications is None:
            return

        for admin_id, notification_text in notifications:
            try:
                # AUD3-09: цикл по получателям — per-call предел.
                await bot.send_message(
                    admin_id, notification_text, request_timeout=SEND_TIMEOUT
                )
                logger.info(f"Уведомление о заявке {user_apartment_id} отправлено админу {admin_id}")
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление админу {admin_id}: {e}")

    except Exception as e:
        logger.error(f"Ошибка при отправке уведомлений о заявке {user_apartment_id}: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# АДАПТЕР ДЛЯ ВЫЗОВА ИЗ ПРОФИЛЯ
# ═══════════════════════════════════════════════════════════════════════════════

async def start_apartment_selection_for_profile(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
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
    lang = language
    phone = await run_db(lambda s: _load_user_phone(s, callback.from_user.id), db=_db)
    if not phone:
        await callback.message.answer(
            get_text("onboarding.phone_required", language=lang),
            reply_markup=get_share_contact_keyboard(lang, with_cancel=False),
        )
        await callback.answer()
        return

    await state.update_data(entry_from="profile")
    await state.set_state(OnboardingStates.waiting_for_yard_selection)

    # WR-06 (класс): дефолт ДО try. `lang` присваивается после db-фазы,
    # и если она бросит (недоступна БД), `except` ниже сошлётся
    # на несвязанное имя → NameError вместо сообщения об ошибке.
    lang = "ru"
    try:
        yards = await run_db(_load_active_yards, db=_db)

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


# ═══════════════════════════════════════════════════════════════════════════════
# ЖИТЕЛЬСКАЯ ОТМЕНА ВЫБОРА КВАРТИРЫ (A3, аудит 2026-08-18)
# ═══════════════════════════════════════════════════════════════════════════════

# Состояния шага выбора (регистрация И профиль используют одни OnboardingStates,
# профиль дополнительно помечает entry_from="profile" — поэтому порядок веток:
# сначала profile, потом онбординг).
_SELECTION_STATES = {
    OnboardingStates.waiting_for_yard_selection.state,
    OnboardingStates.waiting_for_building_selection.state,
    OnboardingStates.waiting_for_apartment_selection.state,
}


@router.callback_query(F.data == "cancel_apartment_selection")
async def cancel_apartment_selection_user(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Отмена ЖИТЕЛЬСКОГО выбора квартиры.

    A3: отмена разделена по callback_data. Раньше единственный хендлер жил в
    address_apartments/navigation.py и различал рукава по entry_from из state —
    но state пишет флоу, а callback присылает клиент, и «иначе»-ветка отдавала
    жителю АДМИНСКОЕ меню справочника. Теперь:
      * из профиля (entry_from="profile") → «Мои квартиры»;
      * из онбординга → шаг документов (тот же переход, что у confirm-пути);
      * вне состояния (просроченная кнопка) → только «действие отменено».
    Админский рукав — addr_cancel_selection в navigation.py, под RoleGate.
    """
    lang = language
    data = await state.get_data()
    entry_from = data.get("entry_from")
    current_state = await state.get_state()

    await callback.message.edit_text(
        get_text("address_apartments.handlers.action_cancelled", language=lang)
    )

    if entry_from == "profile":
        await state.clear()
        from uk_management_bot.handlers.user_apartments import show_my_apartments
        await show_my_apartments(callback, state, language=lang)
        return

    if current_state in _SELECTION_STATES:
        # Онбординг: сохраняем регистрационные данные, чистим только выбор —
        # ровно как confirm-путь выше (переход к документам).
        await state.update_data(
            selected_yard_id=None,
            selected_yard_name=None,
            selected_building_id=None,
            selected_building_address=None,
            selected_apartment_id=None,
        )
        await state.set_state(OnboardingStates.waiting_for_document_type)
        from uk_management_bot.keyboards.onboarding import get_document_type_keyboard
        await callback.message.answer(
            get_text("user_apt_selection.handlers.upload_documents_prompt", language=lang),
            reply_markup=get_document_type_keyboard(language=lang),
        )
        return

    await state.clear()
