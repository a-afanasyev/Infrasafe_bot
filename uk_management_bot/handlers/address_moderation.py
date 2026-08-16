"""
Обработчики для модерации заявок на квартиры (Apartment Moderation)

Функционал:
- Просмотр списка заявок на рассмотрении
- Просмотр детальной информации о заявке
- Подтверждение заявки (approve)
- Отклонение заявки (reject)
- Добавление комментариев к решению
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
from uk_management_bot.services.address_service import AddressService
from uk_management_bot.states.address_management import ApartmentModerationStates
from uk_management_bot.keyboards.address_management import (
    get_moderation_requests_keyboard,
    get_moderation_request_details_keyboard,
    get_cancel_keyboard_inline
)
from uk_management_bot.keyboards.base import get_main_keyboard_for_role
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

router = Router()


# ==========================================================================
# DTO для async-слоя: наружу из run_db выходят примитивы, не ORM-строки
# (у ORM-объекта за пределами worker-потока нет живой сессии).
# ==========================================================================

@dataclass(frozen=True)
class _RowUser:
    """Вложенный узел строки списка — ровно те атрибуты, что читает
    get_moderation_requests_keyboard через req.user.*"""
    first_name: Optional[str]
    last_name: Optional[str]
    telegram_id: int


@dataclass(frozen=True)
class _RowBuilding:
    """req.apartment.building.* в клавиатуре списка."""
    address: str


@dataclass(frozen=True)
class _RowApartment:
    """req.apartment.* в клавиатуре списка."""
    apartment_number: str
    building: Optional[_RowBuilding]


@dataclass(frozen=True)
class _ModerationRow:
    """Строка списка заявок для get_moderation_requests_keyboard."""
    id: int
    user: _RowUser
    apartment: _RowApartment
    requested_at: Optional[datetime]


@dataclass(frozen=True)
class _RequestDetails:
    """Карточка заявки для show_moderation_details."""
    status: str
    first_name: Optional[str]
    last_name: Optional[str]
    telegram_id: int
    username: Optional[str]
    phone: Optional[str]
    apartment_number: str
    building_address: Optional[str]
    yard_name: Optional[str]
    requested_at: Optional[datetime]
    is_owner: bool


@dataclass(frozen=True)
class _DecisionContext:
    """Данные для approve/reject: получатель уведомления + reviewer."""
    user_telegram_id: int
    apartment_address: str
    reviewer_id: int
    reviewer_telegram_id: int


# ==========================================================================
# Sync unit-of-work (AUD3-07/AUD5-ARCH-1): исполняются в worker-потоке через
# run_db; сессию открывает и закрывает run_db, event loop БД не трогает.
# Мутации (approve/reject_apartment_request) сюда НЕ входят: это async-методы
# AddressService с собственной async-сессией — их хендлер await'ит напрямую.
# ==========================================================================

def _load_pending_rows(db) -> list:
    """-> [_ModerationRow] заявок в статусе pending."""
    requests = AddressService.get_pending_requests(db, limit=50)
    rows = []
    for req in requests:
        building = req.apartment.building
        rows.append(_ModerationRow(
            id=req.id,
            user=_RowUser(
                first_name=req.user.first_name,
                last_name=req.user.last_name,
                telegram_id=req.user.telegram_id,
            ),
            apartment=_RowApartment(
                apartment_number=req.apartment.apartment_number,
                building=_RowBuilding(address=building.address) if building else None,
            ),
            requested_at=req.requested_at,
        ))
    return rows


def _load_user_apartment_full(db, user_apartment_id: int):
    """Общий запрос карточки заявки с joinedload user/apartment/building/yard."""
    from uk_management_bot.database.models import UserApartment, Apartment, Building
    from sqlalchemy import select
    from sqlalchemy.orm import joinedload

    result = db.execute(
        select(UserApartment)
        .options(
            joinedload(UserApartment.user),
            joinedload(UserApartment.apartment).joinedload(Apartment.building).joinedload(Building.yard)
        )
        .where(UserApartment.id == user_apartment_id)
    )
    return result.scalar_one_or_none()


def _load_request_details(db, user_apartment_id: int) -> Optional[_RequestDetails]:
    """-> _RequestDetails | None (None — заявка не найдена)."""
    user_apartment = _load_user_apartment_full(db, user_apartment_id)
    if not user_apartment:
        return None

    user = user_apartment.user
    apartment = user_apartment.apartment
    building = apartment.building
    return _RequestDetails(
        status=user_apartment.status,
        first_name=user.first_name,
        last_name=user.last_name,
        telegram_id=user.telegram_id,
        username=user.username,
        phone=user.phone,
        apartment_number=apartment.apartment_number,
        building_address=building.address if building else None,
        yard_name=building.yard.name if building and building.yard else None,
        requested_at=user_apartment.requested_at,
        is_owner=user_apartment.is_owner,
    )


def _load_decision_context(db, user_apartment_id: int, reviewer_telegram_id: int, lang: str) -> tuple:
    """-> ('not_found'|'admin_not_found', None) | ('ok', _DecisionContext).

    Текст адреса для уведомления рендерится здесь же (B3: тексты в юните),
    язык — язык модератора, как в историческом коде.
    """
    user_apartment = _load_user_apartment_full(db, user_apartment_id)
    if not user_apartment:
        return ("not_found", None)

    # Сохраняем данные для уведомления
    user_telegram_id = user_apartment.user.telegram_id
    apartment = user_apartment.apartment
    apartment_address = get_text("address_moderation.handlers.apartment_label", language=lang).format(number=apartment.apartment_number)
    if apartment.building:
        apartment_address = f"{apartment_address}, {apartment.building.address}"
        if apartment.building.yard:
            apartment_address = f"{apartment_address} ({apartment.building.yard.name})"

    # Получаем reviewer.id из базы данных (не telegram_id!)
    from uk_management_bot.database.models.user import User
    reviewer = db.query(User).filter(User.telegram_id == reviewer_telegram_id).first()
    if not reviewer:
        return ("admin_not_found", None)

    return (
        "ok",
        _DecisionContext(
            user_telegram_id=user_telegram_id,
            apartment_address=apartment_address,
            reviewer_id=reviewer.id,
            reviewer_telegram_id=reviewer.telegram_id,
        ),
    )


def _render_user_notification(db, user_telegram_id: int, template_key: str, **fmt) -> Optional[str]:
    """Фетч языка получателя + рендер текста уведомления (B3).

    -> текст | None (пользователь не найден).

    BUG-152 п.1: здесь стоял локальный ``from uk_management_bot.config.localization
    import get_text`` — такого модуля в репо нет, ModuleNotFoundError гасился
    broad-except вызывающего, и житель НИКОГДА не получал решение по своей
    квартире (модератор при этом видел успех). Канон — модульный ``get_text``
    из ``utils.helpers`` (импортирован в шапке файла).
    """
    from uk_management_bot.database.models import User
    from sqlalchemy import select

    user = db.execute(
        select(User).where(User.telegram_id == user_telegram_id)
    ).scalar_one_or_none()

    if not user:
        logger.warning(f"Пользователь {user_telegram_id} не найден для отправки уведомления")
        return None

    lang = user.language or 'ru'

    if template_key == "approval":
        # Формируем текст уведомления
        notification_text = get_text("address_moderation.handlers.approval_notification", language=lang).format(apartment_address=fmt["apartment_address"])

        if fmt.get("comment"):
            notification_text += "\n\n💬 <b>" + get_text("address_moderation.handlers.admin_comment_label", language=lang) + ":</b>\n" + fmt["comment"]

        notification_text += "\n\n" + get_text("address_moderation.handlers.can_create_requests", language=lang)
        return notification_text

    # Формируем текст уведомления
    return get_text("address_moderation.handlers.rejection_notification", language=lang).format(
        apartment_address=fmt["apartment_address"], comment=fmt["comment"]
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР СПИСКА ЗАЯВОК
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "addr_moderation_list")
async def show_moderation_list(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Показать список заявок на модерацию"""
    await state.clear()

    try:
        requests = await run_db(_load_pending_rows, db=_db)

        if not requests:
            lang = language
            await callback.message.edit_text(
                get_text("address_moderation.handlers.moderation_list_empty", language=lang),
                reply_markup=get_moderation_requests_keyboard([], page=0)
            )
            return

        lang = language
        text = get_text("address_moderation.handlers.moderation_list", language=lang).format(count=len(requests))

        await callback.message.edit_text(
            text,
            reply_markup=get_moderation_requests_keyboard(requests, page=0)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке списка заявок: {e}")
        await callback.answer(get_text("address_moderation.handlers.error_loading_data", language=language), show_alert=True)


@router.callback_query(F.data.startswith("addr_moderation_page:"))
async def show_moderation_page(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Показать конкретную страницу списка заявок"""
    page = int(callback.data.split(":")[1])

    try:
        requests = await run_db(_load_pending_rows, db=_db)

        lang = language
        text = get_text("address_moderation.handlers.moderation_list_page", language=lang).format(page=page + 1, total=len(requests))

        await callback.message.edit_text(
            text,
            reply_markup=get_moderation_requests_keyboard(requests, page=page)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке страницы заявок: {e}")
        await callback.answer(get_text("address_moderation.handlers.error_loading_data", language=language), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР ДЕТАЛЬНОЙ ИНФОРМАЦИИ О ЗАЯВКЕ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_moderation_view:"))
async def show_moderation_details(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Показать детальную информацию о заявке"""
    user_apartment_id = int(callback.data.split(":")[1])

    try:
        details = await run_db(lambda s: _load_request_details(s, user_apartment_id), db=_db)

        if not details:
            lang = language
            await callback.answer(get_text("address_moderation.handlers.request_not_found", language=lang), show_alert=True)
            return

        if details.status != 'pending':
            lang = language
            await callback.answer(
                get_text("address_moderation.handlers.request_already_processed", language=lang).format(status=details.status),
                show_alert=True
            )
            return

        # Информация о пользователе
        user_name = f"{details.first_name or ''} {details.last_name or ''}".strip()
        if not user_name:
            user_name = f"ID: {details.telegram_id}"

        lang = language
        username = f"@{details.username}" if details.username else get_text("address_moderation.handlers.no_username", language=lang)
        phone = details.phone if details.phone else get_text("address_moderation.handlers.not_specified", language=lang)

        # Информация о квартире
        apartment_info = get_text("address_moderation.handlers.apartment_label", language=lang).format(number=details.apartment_number)

        if details.building_address:
            apartment_info = f"{apartment_info}, {details.building_address}"
            if details.yard_name:
                apartment_info = f"{apartment_info} ({details.yard_name})"

        # Дополнительная информация
        requested_date = details.requested_at.strftime('%d.%m.%Y %H:%M') if details.requested_at else get_text("address_moderation.handlers.unknown", language=lang)
        is_owner_text = get_text("address_moderation.handlers.yes_owner", language=lang) if details.is_owner else get_text("address_moderation.handlers.no_resident", language=lang)

        text = get_text("address_moderation.handlers.request_details", language=lang).format(
                user_name=user_name, username=username, phone=phone,
                telegram_id=details.telegram_id, apartment_info=apartment_info,
                is_owner_text=is_owner_text, requested_date=requested_date
            )

        # Сохраняем ID заявки в состояние
        await state.update_data(user_apartment_id=user_apartment_id)
        await state.set_state(ApartmentModerationStates.viewing_request_details)

        await callback.message.edit_text(
            text,
            reply_markup=get_moderation_request_details_keyboard(user_apartment_id)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке информации о заявке {user_apartment_id}: {e}")
        await callback.answer(get_text("address_moderation.handlers.error_loading_data", language=language), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ПОДТВЕРЖДЕНИЕ ЗАЯВКИ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_moderation_approve:"))
async def start_approve_request(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Начать подтверждение заявки - запросить комментарий"""
    user_apartment_id = int(callback.data.split(":")[1])

    await state.update_data(user_apartment_id=user_apartment_id)
    await state.set_state(ApartmentModerationStates.waiting_for_approval_comment)

    lang = language
    await callback.message.edit_text(
        get_text("address_moderation.handlers.approve_comment_prompt", language=lang),
        reply_markup=get_cancel_keyboard_inline()
    )


@router.message(StateFilter(ApartmentModerationStates.waiting_for_approval_comment))
async def process_approve_comment(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработка комментария и подтверждение заявки"""
    comment = None if message.text == "/skip" else message.text.strip()

    data = await state.get_data()
    user_apartment_id = data['user_apartment_id']

    # WR-06 (класс): дефолт ДО try. `lang` присваивается после db-фазы,
    # и если она бросит (недоступна БД), `except` ниже сошлётся
    # на несвязанное имя → NameError вместо сообщения об ошибке.
    lang = "ru"
    try:
        verdict, ctx = await run_db(
            lambda s: _load_decision_context(s, user_apartment_id, message.from_user.id, language), db=_db
        )

        if verdict == "not_found":
            lang = language
            await message.answer(
                get_text("address_moderation.handlers.request_not_found", language=lang),
                reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
            )
            await state.clear()
            return

        lang = language
        if verdict == "admin_not_found":
            await message.answer(
                get_text("address_moderation.handlers.admin_not_found", language=lang),
                reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
            )
            await state.clear()
            return

        # Теперь подтверждаем заявку. approve_apartment_request — async-метод с
        # собственной async-сессией; параметр session им не используется
        # (пишет через _async_session()).
        success, error = await AddressService.approve_apartment_request(
            session=None,
            user_apartment_id=user_apartment_id,
            reviewer_id=ctx.reviewer_id,  # ИСПРАВЛЕНО: используем reviewer.id из БД, а не telegram_id
            comment=comment
        )

        if not success:
            await message.answer(
                get_text("address_moderation.handlers.approve_error", language=lang).format(error=error),
                reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
            )
            await state.clear()
            return

        # Отправляем уведомление пользователю
        await send_approval_notification(
            user_apartment_id=user_apartment_id,
            user_telegram_id=ctx.user_telegram_id,
            apartment_address=ctx.apartment_address,
            comment=comment,
            bot=message.bot,
            _db=_db
        )

        comment_text = "\n\n<b>" + get_text("address_moderation.handlers.comment_label", language=lang) + ":</b> " + comment if comment else ""

        await message.answer(
            get_text("address_moderation.handlers.approve_success", language=lang) + comment_text,
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
        )

        logger.info(f"Заявка {user_apartment_id} подтверждена администратором {ctx.reviewer_telegram_id} (DB ID: {ctx.reviewer_id})")

    except Exception:
        logger.exception("approve apartment request handler failed")
        await message.answer(
            get_text("address_moderation.handlers.approve_exception", language=lang),
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
        )
    finally:
        await state.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# ОТКЛОНЕНИЕ ЗАЯВКИ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("addr_moderation_reject:"))
async def start_reject_request(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Начать отклонение заявки - запросить причину"""
    user_apartment_id = int(callback.data.split(":")[1])

    await state.update_data(user_apartment_id=user_apartment_id)
    await state.set_state(ApartmentModerationStates.waiting_for_rejection_comment)

    lang = language
    await callback.message.edit_text(
        get_text("address_moderation.handlers.reject_reason_prompt", language=lang),
        reply_markup=get_cancel_keyboard_inline()
    )


@router.message(StateFilter(ApartmentModerationStates.waiting_for_rejection_comment))
async def process_reject_comment(message: Message, state: FSMContext, language: str = "ru", *, _db=None):
    """Обработка причины и отклонение заявки"""
    comment = message.text.strip()

    if len(comment) < 3:
        lang = language
        await message.answer(
            get_text("address_moderation.handlers.reject_reason_too_short", language=lang)
        )
        return

    data = await state.get_data()
    user_apartment_id = data['user_apartment_id']

    # WR-06 (класс): дефолт ДО try. `lang` присваивается после db-фазы,
    # и если она бросит (недоступна БД), `except` ниже сошлётся
    # на несвязанное имя → NameError вместо сообщения об ошибке.
    lang = "ru"
    try:
        verdict, ctx = await run_db(
            lambda s: _load_decision_context(s, user_apartment_id, message.from_user.id, language), db=_db
        )

        if verdict == "not_found":
            lang = language
            await message.answer(
                get_text("address_moderation.handlers.request_not_found", language=lang),
                reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
            )
            await state.clear()
            return

        lang = language
        if verdict == "admin_not_found":
            await message.answer(
                get_text("address_moderation.handlers.admin_not_found", language=lang),
                reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
            )
            await state.clear()
            return

        # Теперь отклоняем заявку. reject_apartment_request — async-метод с
        # собственной async-сессией; параметр session им не используется
        # (пишет через _async_session()).
        success, error = await AddressService.reject_apartment_request(
            session=None,
            user_apartment_id=user_apartment_id,
            reviewer_id=ctx.reviewer_id,  # ИСПРАВЛЕНО: используем reviewer.id из БД, а не telegram_id
            comment=comment
        )

        if not success:
            await message.answer(
                get_text("address_moderation.handlers.reject_error", language=lang).format(error=error),
                reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
            )
            await state.clear()
            return

        # Отправляем уведомление пользователю
        await send_rejection_notification(
            user_apartment_id=user_apartment_id,
            user_telegram_id=ctx.user_telegram_id,
            apartment_address=ctx.apartment_address,
            comment=comment,
            bot=message.bot,
            _db=_db
        )

        await message.answer(
            get_text("address_moderation.handlers.reject_success", language=lang).format(comment=comment),
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
        )

        logger.info(f"Заявка {user_apartment_id} отклонена администратором {ctx.reviewer_telegram_id} (DB ID: {ctx.reviewer_id})")

    except Exception:
        logger.exception("reject apartment request handler failed")
        await message.answer(
            get_text("address_moderation.handlers.reject_exception", language=lang),
            reply_markup=get_main_keyboard_for_role("manager", ["manager"], language=lang)
        )
    finally:
        await state.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# ОТМЕНА ДЕЙСТВИЙ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "cancel_action")
async def cancel_moderation_action(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Отмена действия модерации"""
    current_state = await state.get_state()

    if current_state:
        await state.clear()
        lang = language
        await callback.message.edit_text(get_text("address_moderation.handlers.action_cancelled", language=lang))

        # Вернуться к списку заявок
        # ⚠️ Предсуществующий дефект (сохранён 1:1): language не пробрасывается —
        # список после отмены рендерится на "ru".
        await show_moderation_list(callback, state, _db=_db)
    else:
        await callback.answer(get_text("address_moderation.handlers.no_active_actions", language=language))


# ═══════════════════════════════════════════════════════════════════════════════
# NOTIFICATION HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

async def send_approval_notification(user_apartment_id: int, user_telegram_id: int, apartment_address: str, comment: str = None, bot=None, *, _db=None):
    """
    Отправить уведомление пользователю об одобрении заявки на квартиру

    Args:
        user_apartment_id: ID заявки (UserApartment)
        user_telegram_id: Telegram ID пользователя
        apartment_address: Адрес квартиры
        comment: Комментарий администратора (необязательно)
        bot: Bot instance
    """
    try:
        # B3-раскрой: язык получателя + рендер текста — в worker-потоке
        # (run_db), сеть (send_message) — здесь, вне сессии.
        notification_text = await run_db(
            lambda s: _render_user_notification(
                s, user_telegram_id, "approval",
                apartment_address=apartment_address, comment=comment,
            ),
            db=_db,
        )

        if notification_text is None:
            return

        # Отправляем уведомление
        await bot.send_message(user_telegram_id, notification_text)
        logger.info(f"✅ Уведомление об одобрении заявки {user_apartment_id} отправлено пользователю {user_telegram_id}")

    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления об одобрении заявки {user_apartment_id}: {e}")


async def send_rejection_notification(user_apartment_id: int, user_telegram_id: int, apartment_address: str, comment: str, bot=None, *, _db=None):
    """
    Отправить уведомление пользователю об отклонении заявки на квартиру

    Args:
        user_apartment_id: ID заявки (UserApartment)
        user_telegram_id: Telegram ID пользователя
        apartment_address: Адрес квартиры
        comment: Причина отклонения (обязательно)
        bot: Bot instance
    """
    try:
        # B3-раскрой: язык получателя + рендер текста — в worker-потоке
        # (run_db), сеть (send_message) — здесь, вне сессии.
        notification_text = await run_db(
            lambda s: _render_user_notification(
                s, user_telegram_id, "rejection",
                apartment_address=apartment_address, comment=comment,
            ),
            db=_db,
        )

        if notification_text is None:
            return

        # Отправляем уведомление
        await bot.send_message(user_telegram_id, notification_text)
        logger.info(f"✅ Уведомление об отклонении заявки {user_apartment_id} отправлено пользователю {user_telegram_id}")

    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления об отклонении заявки {user_apartment_id}: {e}")
