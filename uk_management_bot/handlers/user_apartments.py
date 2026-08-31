"""
Обработчики для управления квартирами пользователя

Функционал:
- Просмотр всех квартир пользователя
- Запрос привязки к дополнительной квартире
- Смена основной квартиры
- Просмотр истории модерации
"""
import html
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import run_db
from uk_management_bot.middlewares.auth import require_role
from uk_management_bot.services.address_service import AddressService
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)
router = Router()


# ==========================================================================
# DTO для async-слоя: наружу из run_db выходят примитивы, не ORM-строки
# (у ORM-объекта за пределами worker-потока нет живой сессии).
# ==========================================================================

@dataclass(frozen=True)
class _ApartmentRow:
    """Строка списка квартир — ровно те атрибуты, что читают рендеры списков
    и локальные клавиатуры (get_my_apartments_keyboard / admin-варианты)."""
    id: int
    status: str
    is_primary: bool
    is_owner: bool
    admin_comment: Optional[str]
    address: str


@dataclass(frozen=True)
class _ApartmentView:
    """Карточка user_apartment для view_apartment_details / admin_apartment_detail."""
    id: int
    status: str
    is_primary: bool
    is_owner: bool
    admin_comment: Optional[str]
    address: str
    user_telegram_id: int
    entrance: Optional[str]
    floor: Optional[int]
    rooms_count: Optional[int]
    area: Optional[float]
    requested_at: Optional[datetime]
    reviewed_at: Optional[datetime]
    has_reviewer: bool
    reviewer_first_name: Optional[str]
    reviewer_username: Optional[str]


@dataclass(frozen=True)
class _AdminApartmentsOverview:
    """Шапка пользователя + строки квартир для admin_manage_user_apartments."""
    user_internal_id: int
    user_first_name: Optional[str]
    user_last_name: Optional[str]
    rows: tuple


# ==========================================================================
# Sync unit-of-work (AUD3-07/AUD5-ARCH-1): исполняются в worker-потоке через
# run_db; сессию открывает и закрывает run_db, event loop БД не трогает.
# ==========================================================================

def _apartment_row_from(ua) -> _ApartmentRow:
    return _ApartmentRow(
        id=ua.id,
        status=ua.status,
        is_primary=ua.is_primary,
        is_owner=ua.is_owner,
        admin_comment=ua.admin_comment,
        address=AddressService.format_apartment_address(ua.apartment),
    )


def _apartment_view_from(ua) -> _ApartmentView:
    apartment = ua.apartment
    reviewer = ua.reviewer
    return _ApartmentView(
        id=ua.id,
        status=ua.status,
        is_primary=ua.is_primary,
        is_owner=ua.is_owner,
        admin_comment=ua.admin_comment,
        address=AddressService.format_apartment_address(apartment),
        user_telegram_id=ua.user.telegram_id,
        entrance=apartment.entrance,
        floor=apartment.floor,
        rooms_count=apartment.rooms_count,
        area=apartment.area,
        requested_at=ua.requested_at,
        reviewed_at=ua.reviewed_at,
        has_reviewer=reviewer is not None,
        reviewer_first_name=reviewer.first_name if reviewer else None,
        reviewer_username=reviewer.username if reviewer else None,
    )


def _load_my_apartments(db, telegram_id: int) -> Optional[list]:
    """-> [_ApartmentRow] | None (None — пользователь не найден)."""
    from uk_management_bot.database.models import User
    from sqlalchemy import select

    user = db.execute(
        select(User).where(User.telegram_id == telegram_id)
    ).scalar_one_or_none()

    if not user:
        return None

    # Получаем все квартиры пользователя (одобренные, ожидающие, отклоненные)
    user_apartments = AddressService.get_user_apartments(
        session=db,
        user_id=user.id,
        only_approved=False
    )
    return [_apartment_row_from(ua) for ua in user_apartments]


def _set_primary_apartment(db, user_apartment_id: int, telegram_id: int) -> str:
    """-> 'not_found' | 'access_denied' | 'not_approved' | 'ok'."""
    from uk_management_bot.database.models import UserApartment
    from sqlalchemy import select, text

    user_apartment = db.execute(
        select(UserApartment).where(UserApartment.id == user_apartment_id)
    ).scalar_one_or_none()

    if not user_apartment:
        return "not_found"

    if user_apartment.user.telegram_id != telegram_id:
        return "access_denied"

    if user_apartment.status != 'approved':
        return "not_approved"

    # Снимаем флаг is_primary со всех ОСТАЛЬНЫХ квартир пользователя.
    # BUG-151 п.1: здесь стояла сырая SQL-строка без text() — SQLAlchemy 2.x
    # бросает ArgumentError ещё до запроса, поэтому «Сделать основной» всегда
    # уходила в except с generic error_update.
    #
    # Целевая квартира исключена из сброса намеренно. Сырой UPDATE идёт мимо
    # identity map, а установка True ниже — присваивание ORM-атрибута: если он
    # в памяти уже был True (повторный клик по уже основной квартире — двойной
    # тап, пока Telegram не перерисовал клавиатуру), SQLAlchemy не увидел бы
    # изменения и UPDATE не эмитил, а сырой сброс уже обнулил бы строку —
    # у пользователя не осталось бы НИ ОДНОЙ основной квартиры при вердикте "ok".
    db.execute(
        text(
            """
        UPDATE user_apartments
        SET is_primary = false
        WHERE user_id = :user_id AND id != :user_apartment_id
        """
        ),
        {"user_id": user_apartment.user_id, "user_apartment_id": user_apartment.id}
    )

    # Устанавливаем новую основную квартиру
    user_apartment.is_primary = True
    db.commit()
    return "ok"


def _load_apartment_view(db, user_apartment_id: int) -> Optional[_ApartmentView]:
    """-> _ApartmentView | None. Карточка квартиры жителя (view_apartment:<id>)."""
    # BUG-BOT-027: исходный joinedload(UserApartment.apartment.property.mapper.class_.building...)
    # был некорректным SQLAlchemy-выражением и валил handler в except → юзер видел
    # generic "ошибка загрузки данных". Заменено на корректные nested joinedload.
    from uk_management_bot.database.models import UserApartment, Apartment, Building
    from sqlalchemy import select
    from sqlalchemy.orm import joinedload

    user_apartment = db.execute(
        select(UserApartment)
        .options(
            joinedload(UserApartment.user),
            joinedload(UserApartment.apartment)
                .joinedload(Apartment.building)
                .joinedload(Building.yard),
            joinedload(UserApartment.reviewer),
        )
        .where(UserApartment.id == user_apartment_id)
    ).scalar_one_or_none()

    if not user_apartment:
        return None
    return _apartment_view_from(user_apartment)


def _load_admin_overview(db, user_telegram_id: int) -> Optional[_AdminApartmentsOverview]:
    """-> _AdminApartmentsOverview | None (None — пользователь не найден)."""
    from uk_management_bot.database.models import User
    from sqlalchemy import select

    user = db.execute(
        select(User).where(User.telegram_id == user_telegram_id)
    ).scalar_one_or_none()

    if not user:
        return None

    # Получаем все квартиры пользователя
    user_apartments = AddressService.get_user_apartments(
        session=db,
        user_id=user.id,
        only_approved=False
    )
    return _AdminApartmentsOverview(
        user_internal_id=user.id,
        user_first_name=user.first_name,
        user_last_name=user.last_name,
        rows=tuple(_apartment_row_from(ua) for ua in user_apartments),
    )


def _load_admin_apartment_view(db, user_apartment_id: int) -> Optional[_ApartmentView]:
    """-> _ApartmentView | None. Карточка для админа (admin_apartment_detail_<id>)."""
    from uk_management_bot.database.models import UserApartment
    from sqlalchemy import select

    user_apartment = db.execute(
        select(UserApartment).where(UserApartment.id == user_apartment_id)
    ).scalar_one_or_none()

    if not user_apartment:
        return None
    return _apartment_view_from(user_apartment)


def _admin_approve_apartment(db, user_apartment_id: int, admin_telegram_id: int) -> str:
    """-> 'not_found' | 'admin_not_found' | 'ok'."""
    from uk_management_bot.database.models import UserApartment, User
    from sqlalchemy import select
    from datetime import timezone

    user_apartment = db.execute(
        select(UserApartment).where(UserApartment.id == user_apartment_id)
    ).scalar_one_or_none()

    if not user_apartment:
        return "not_found"

    # Получаем администратора
    admin = db.execute(
        select(User).where(User.telegram_id == admin_telegram_id)
    ).scalar_one_or_none()

    if not admin:
        return "admin_not_found"

    # BUG-177 (второй рубеж, канон BUG-172): роль перепроверяется В ЮНИТЕ
    # ЗАПИСИ — @require_role хендлера не единственная защита. Плюс guard
    # состояния: решение принимается только по pending-заявке (паритет с
    # канон-путём _review_apartment_request).
    from uk_management_bot.utils.auth_helpers import get_user_roles
    if not ({"manager", "admin"} & set(get_user_roles(admin) or [])):
        return "admin_not_found"
    if user_apartment.status != "pending":
        return "not_pending"

    # Одобряем квартиру. BUG-151 п.3: комментарий хранится строкой и читает
    # его ЖИТЕЛЬ (reason в списке квартир) — рендерим на языке владельца.
    owner = db.execute(
        select(User).where(User.id == user_apartment.user_id)
    ).scalar_one_or_none()
    owner_lang = (owner.language if owner else None) or "ru"
    user_apartment.status = 'approved'
    user_apartment.reviewed_at = datetime.now(timezone.utc)
    user_apartment.reviewed_by = admin.id
    user_apartment.admin_comment = get_text(
        "user_apartments.admin_comment_approved", language=owner_lang
    ).format(name=admin.first_name or admin_telegram_id)

    db.commit()
    return "ok"


def _admin_reject_apartment(db, user_apartment_id: int, admin_telegram_id: int) -> str:
    """-> 'not_found' | 'admin_not_found' | 'ok'."""
    from uk_management_bot.database.models import UserApartment, User
    from sqlalchemy import select
    from datetime import timezone

    user_apartment = db.execute(
        select(UserApartment).where(UserApartment.id == user_apartment_id)
    ).scalar_one_or_none()

    if not user_apartment:
        return "not_found"

    # Получаем администратора
    admin = db.execute(
        select(User).where(User.telegram_id == admin_telegram_id)
    ).scalar_one_or_none()

    if not admin:
        return "admin_not_found"

    # BUG-177 (второй рубеж, канон BUG-172): роль перепроверяется В ЮНИТЕ
    # ЗАПИСИ — @require_role хендлера не единственная защита. Плюс guard
    # состояния: решение принимается только по pending-заявке (паритет с
    # канон-путём _review_apartment_request).
    from uk_management_bot.utils.auth_helpers import get_user_roles
    if not ({"manager", "admin"} & set(get_user_roles(admin) or [])):
        return "admin_not_found"
    if user_apartment.status != "pending":
        return "not_pending"

    # Отклоняем квартиру. BUG-151 п.3: язык владельца — как в approve выше.
    owner = db.execute(
        select(User).where(User.id == user_apartment.user_id)
    ).scalar_one_or_none()
    owner_lang = (owner.language if owner else None) or "ru"
    user_apartment.status = 'rejected'
    user_apartment.reviewed_at = datetime.now(timezone.utc)
    user_apartment.reviewed_by = admin.id
    user_apartment.admin_comment = get_text(
        "user_apartments.admin_comment_rejected", language=owner_lang
    ).format(name=admin.first_name or admin_telegram_id)

    db.commit()
    return "ok"


def _admin_toggle_owner(db, user_apartment_id: int) -> Optional[bool]:
    """-> новое значение is_owner | None (не найдена)."""
    from uk_management_bot.database.models import UserApartment
    from sqlalchemy import select

    user_apartment = db.execute(
        select(UserApartment).where(UserApartment.id == user_apartment_id)
    ).scalar_one_or_none()

    if not user_apartment:
        return None

    # Переключаем статус
    user_apartment.is_owner = not user_apartment.is_owner
    db.commit()
    return user_apartment.is_owner


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР КВАРТИР ПОЛЬЗОВАТЕЛЯ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "my_apartments")
async def show_my_apartments(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Показать список квартир пользователя"""
    await state.clear()
    lang = language

    try:
        user_apartments = await run_db(lambda s: _load_my_apartments(s, callback.from_user.id), db=_db)

        if user_apartments is None:
            await callback.answer(get_text("user_apartments.user_not_found", language=lang), show_alert=True)
            return

        if not user_apartments:
            await callback.message.edit_text(
                get_text("user_apartments.no_apartments", language=lang),
                reply_markup=get_my_apartments_empty_keyboard(lang)
            )
            return

        # Формируем текст со списком квартир
        text = get_text("user_apartments.my_apartments_title", language=lang) + "\n\n"

        # Группируем по статусам
        approved = [ua for ua in user_apartments if ua.status == 'approved']
        pending = [ua for ua in user_apartments if ua.status == 'pending']
        rejected = [ua for ua in user_apartments if ua.status == 'rejected']

        if approved:
            text += get_text("user_apartments.approved_header", language=lang) + "\n"
            for ua in approved:
                address = ua.address
                primary_mark = " ⭐" if ua.is_primary else ""
                owner_mark = " " + get_text("user_apartments.owner_label", language=lang) if ua.is_owner else ""
                text += f"  • {address}{primary_mark}{owner_mark}\n"
            text += "\n"

        if pending:
            text += get_text("user_apartments.pending_header", language=lang) + "\n"
            for ua in pending:
                address = ua.address
                text += f"  • {address}\n"
            text += "\n"

        if rejected:
            text += get_text("user_apartments.rejected_header", language=lang) + "\n"
            for ua in rejected:
                address = ua.address
                # Секревью A2: admin_comment несёт свободный first_name
                # админа, сообщение уходит с parse_mode=HTML (класс BUG-174).
                reason = f" ({html.escape(ua.admin_comment)})" if ua.admin_comment else ""
                text += f"  • {address}{reason}\n"
            text += "\n"

        text += get_text("user_apartments.choose_action", language=lang)

        await callback.message.edit_text(
            text,
            reply_markup=get_my_apartments_keyboard(user_apartments, lang)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке квартир пользователя {callback.from_user.id}: {e}")
        await callback.answer(get_text("user_apartments.error_loading", language=lang), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ДОБАВЛЕНИЕ НОВОЙ КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "add_apartment")
async def start_add_apartment(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Начать процесс добавления квартиры.

    BUG-163: ``language`` не было в сигнатуре вовсе — middleware его не
    прокидывал, и узбекоязычный житель получал русские шаги выбора квартиры.
    """
    # Используем тот же flow, что и при регистрации
    from uk_management_bot.handlers.user_apartment_selection import start_apartment_selection_for_profile

    await start_apartment_selection_for_profile(callback, state, language=language)


# ═══════════════════════════════════════════════════════════════════════════════
# СМЕНА ОСНОВНОЙ КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("set_primary:"))
async def set_primary_apartment(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Установить квартиру как основную"""
    user_apartment_id = int(callback.data.split(":")[1])
    lang = language

    try:
        result = await run_db(
            lambda s: _set_primary_apartment(s, user_apartment_id, callback.from_user.id), db=_db
        )

        if result == "not_found":
            await callback.answer(get_text("user_apartments.apartment_not_found", language=lang), show_alert=True)
            return

        if result == "access_denied":
            await callback.answer(get_text("user_apartments.access_denied", language=lang), show_alert=True)
            return

        if result == "not_approved":
            await callback.answer(get_text("user_apartments.only_approved_primary", language=lang), show_alert=True)
            return

        await callback.answer(get_text("user_apartments.primary_changed", language=lang), show_alert=True)

        # Обновляем отображение (BUG-165: язык пробрасывается)
        await show_my_apartments(callback, state, language=lang, _db=_db)

    except Exception as e:
        logger.error(f"Ошибка установки основной квартиры {user_apartment_id}: {e}")
        await callback.answer(get_text("user_apartments.error_update", language=lang), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОСМОТР ДЕТАЛЕЙ КВАРТИРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("view_apartment:"))
async def view_apartment_details(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Показать детальную информацию о квартире"""
    user_apartment_id = int(callback.data.split(":")[1])
    lang = language

    try:
        user_apartment = await run_db(lambda s: _load_apartment_view(s, user_apartment_id), db=_db)

        if not user_apartment:
            # BUG-BOT-027: контекст-specific сообщение, а не generic "Заявка не найдена"
            await callback.answer(get_text("user_apartments.apartment_not_found", language=lang), show_alert=True)
            return

        if user_apartment.user_telegram_id != callback.from_user.id:
            await callback.answer(get_text("user_apartments.access_denied", language=lang), show_alert=True)
            return

        # Формируем детальную информацию
        address = user_apartment.address

        status_emoji = {
            'approved': '✅',
            'pending': '⏳',
            'rejected': '❌'
        }

        status_text = {
            'approved': get_text("user_apartments.status_approved", language=lang),
            'pending': get_text("user_apartments.status_pending", language=lang),
            'rejected': get_text("user_apartments.status_rejected", language=lang)
        }

        text = get_text("user_apartments.details_title", language=lang) + "\n\n"
        text += get_text("user_apartments.address_label", language=lang).format(address=address) + "\n"
        text += get_text("user_apartments.status_label", language=lang).format(
            emoji=status_emoji.get(user_apartment.status, '❓'),
            status=status_text.get(user_apartment.status, user_apartment.status)
        ) + "\n"

        if user_apartment.is_primary:
            text += get_text("user_apartments.is_primary_yes", language=lang) + "\n"

        if user_apartment.is_owner:
            text += get_text("user_apartments.is_owner_yes", language=lang) + "\n"

        # Детали квартиры
        if user_apartment.entrance or user_apartment.floor or user_apartment.rooms_count or user_apartment.area:
            text += "\n" + get_text("user_apartments.characteristics_header", language=lang) + "\n"
            if user_apartment.entrance:
                text += get_text("user_apartments.entrance_label", language=lang).format(value=user_apartment.entrance) + "\n"
            if user_apartment.floor:
                text += get_text("user_apartments.floor_label", language=lang).format(value=user_apartment.floor) + "\n"
            if user_apartment.rooms_count:
                text += get_text("user_apartments.rooms_label", language=lang).format(value=user_apartment.rooms_count) + "\n"
            if user_apartment.area:
                text += get_text("user_apartments.area_label", language=lang).format(value=user_apartment.area) + "\n"

        # История модерации. BUG-151 п.2: NULL-guard на requested_at (BUG-144).
        text += "\n" + get_text("user_apartments.history_header", language=lang) + "\n"
        text += get_text("user_apartments.requested_at_label", language=lang).format(
            date=user_apartment.requested_at.strftime('%d.%m.%Y %H:%M')
            if user_apartment.requested_at else "—"
        ) + "\n"

        if user_apartment.reviewed_at:
            text += get_text("user_apartments.reviewed_at_label", language=lang).format(
                date=user_apartment.reviewed_at.strftime('%d.%m.%Y %H:%M')
            ) + "\n"

        if user_apartment.has_reviewer:
            reviewer_name = user_apartment.reviewer_first_name or user_apartment.reviewer_username or get_text("user_apartments.admin_default_name", language=lang)
            # Секревью A2: имя из Telegram-профиля — свободный текст (BUG-174).
            text += get_text("user_apartments.reviewed_by_label", language=lang).format(name=html.escape(reviewer_name)) + "\n"

        if user_apartment.admin_comment:
            text += "\n" + get_text("user_apartments.admin_comment_label", language=lang).format(comment=html.escape(user_apartment.admin_comment)) + "\n"

        await callback.message.edit_text(
            text,
            reply_markup=get_apartment_details_keyboard(user_apartment, lang)
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке деталей квартиры {user_apartment_id}: {e}")
        await callback.answer(get_text("user_apartments.error_loading", language=lang), show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ КЛАВИАТУР
# ═══════════════════════════════════════════════════════════════════════════════

def get_my_apartments_empty_keyboard(lang: str = "ru"):
    """Клавиатура для пустого списка квартир"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    keyboard = [
        [InlineKeyboardButton(text=get_text("user_apartments.btn_add_apartment", language=lang), callback_data="add_apartment")],
        [InlineKeyboardButton(text=get_text("user_apartments.btn_back_to_profile", language=lang), callback_data="back_to_profile")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_my_apartments_keyboard(user_apartments, lang: str = "ru"):
    """Клавиатура для списка квартир (принимает [_ApartmentRow])"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    keyboard = []

    # Кнопки для квартир (только одобренные показываем для действий)
    approved = [ua for ua in user_apartments if ua.status == 'approved']

    for ua in approved[:5]:  # Максимум 5 кнопок
        address = ua.address
        # Укорачиваем для кнопки
        button_text = address[:30] + "..." if len(address) > 30 else address
        if ua.is_primary:
            button_text = "⭐ " + button_text

        keyboard.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"view_apartment:{ua.id}"
            )
        ])

    # Кнопки действий
    keyboard.append([InlineKeyboardButton(text=get_text("user_apartments.btn_add_apartment", language=lang), callback_data="add_apartment")])
    keyboard.append([InlineKeyboardButton(text=get_text("user_apartments.btn_back_to_profile", language=lang), callback_data="back_to_profile")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_apartment_details_keyboard(user_apartment, lang: str = "ru"):
    """Клавиатура для деталей квартиры (принимает _ApartmentView)"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    keyboard = []

    # Кнопка "Сделать основной" только если квартира одобрена и не основная
    if user_apartment.status == 'approved' and not user_apartment.is_primary:
        keyboard.append([
            InlineKeyboardButton(
                text=get_text("user_apartments.btn_set_primary", language=lang),
                callback_data=f"set_primary:{user_apartment.id}"
            )
        ])

    # Кнопка возврата
    keyboard.append([
        InlineKeyboardButton(text=get_text("user_apartments.btn_back_to_list", language=lang), callback_data="my_apartments")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ═══════════════════════════════════════════════════════════════════════════════
# ВОЗВРАТ К ПРОФИЛЮ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "back_to_profile")
async def back_to_profile(callback: CallbackQuery, state: FSMContext, *, _db=None):
    """Вернуться к редактированию профиля"""
    await state.clear()

    # Импортируем обработчик профиля
    from uk_management_bot.handlers.profile_editing import handle_edit_profile_start

    # Вызываем показ меню редактирования профиля (сессию откроет run_db внутри)
    await handle_edit_profile_start(callback, state, _db=_db)

# ═══════════════════════════════════════════════════════════════════════════════
# АДМИН: УПРАВЛЕНИЕ КВАРТИРАМИ ПОЛЬЗОВАТЕЛЯ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("admin_manage_apartments_"))
@require_role(['admin', 'manager'])
async def admin_manage_user_apartments(callback: CallbackQuery, state: FSMContext, language: str = "ru", roles: list = None, user=None, *, _db=None):
    """Админ: просмотр и управление квартирами пользователя"""
    await state.clear()
    lang = language

    try:
        user_telegram_id = int(callback.data.split("_")[-1])

        overview = await run_db(lambda s: _load_admin_overview(s, user_telegram_id), db=_db)

        if overview is None:
            await callback.answer(get_text("user_apartments.user_not_found", language=lang), show_alert=True)
            return

        user_apartments = overview.rows

        # Формируем текст
        text = get_text("user_apartments.admin_manage_title", language=lang) + "\n\n"
        # Секревью A2: имя из Telegram-профиля жителя — свободный текст,
        # обзор уходит с parse_mode=HTML (класс BUG-174).
        text += get_text("user_apartments.admin_user_info", language=lang).format(
            first_name=html.escape(overview.user_first_name or ''),
            last_name=html.escape(overview.user_last_name or '')
        ) + "\n"
        text += get_text("user_apartments.admin_telegram_id", language=lang).format(telegram_id=user_telegram_id) + "\n\n"

        if not user_apartments:
            text += get_text("user_apartments.admin_no_apartments", language=lang) + "\n\n"
        else:
            # Группируем по статусам
            approved = [ua for ua in user_apartments if ua.status == 'approved']
            pending = [ua for ua in user_apartments if ua.status == 'pending']
            rejected = [ua for ua in user_apartments if ua.status == 'rejected']

            if approved:
                text += get_text("user_apartments.admin_approved_header", language=lang) + "\n"
                for ua in approved:
                    address = ua.address
                    owner_status = get_text("user_apartments.owner_status_owner", language=lang) if ua.is_owner else get_text("user_apartments.owner_status_resident", language=lang)
                    primary_mark = " ⭐" if ua.is_primary else ""
                    text += f"  • {address}\n"
                    text += f"    {owner_status}{primary_mark}\n"
                text += "\n"

            if pending:
                text += get_text("user_apartments.pending_header", language=lang) + "\n"
                for ua in pending:
                    address = ua.address
                    owner_status = get_text("user_apartments.owner_status_owner", language=lang) if ua.is_owner else get_text("user_apartments.owner_status_resident", language=lang)
                    text += f"  • {address} ({owner_status})\n"
                text += "\n"

            if rejected:
                text += get_text("user_apartments.rejected_header", language=lang) + "\n"
                for ua in rejected:
                    address = ua.address
                    reason = f" - {html.escape(ua.admin_comment)}" if ua.admin_comment else ""
                    text += f"  • {address}{reason}\n"
                text += "\n"

        text += get_text("user_apartments.choose_action", language=lang)

        await callback.message.edit_text(
            text,
            reply_markup=get_admin_apartments_keyboard(user_apartments, user_telegram_id, overview.user_internal_id, lang),
            parse_mode="HTML"
        )
        await callback.answer()


    except Exception as e:
        logger.error(f"Ошибка при загрузке квартир пользователя {callback.data}: {e}")
        import traceback
        traceback.print_exc()
        await callback.answer(get_text("user_apartments.error_loading", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("admin_apartment_detail_"))
@require_role(['admin', 'manager'])
async def admin_apartment_detail(callback: CallbackQuery, state: FSMContext, language: str = "ru", roles: list = None, user=None, *, _db=None):
    """Админ: просмотр деталей квартиры"""
    await state.clear()
    lang = language

    try:
        parts = callback.data.split("_")
        user_apartment_id = int(parts[-1])

        user_apartment = await run_db(lambda s: _load_admin_apartment_view(s, user_apartment_id), db=_db)

        if not user_apartment:
            await callback.answer(get_text("user_apartments.apartment_not_found", language=lang), show_alert=True)
            return

        address = user_apartment.address

        # Формируем детальную информацию
        text = get_text("user_apartments.details_title", language=lang) + "\n\n"
        text += get_text("user_apartments.admin_detail_address", language=lang).format(address=address) + "\n"
        text += get_text("user_apartments.admin_detail_status_label", language=lang) + " "

        if user_apartment.status == 'approved':
            text += get_text("user_apartments.admin_status_approved", language=lang) + "\n"
        elif user_apartment.status == 'pending':
            text += get_text("user_apartments.admin_status_pending", language=lang) + "\n"
        elif user_apartment.status == 'rejected':
            text += get_text("user_apartments.admin_status_rejected", language=lang) + "\n"

        residence_type = get_text("user_apartments.residence_owner", language=lang) if user_apartment.is_owner else get_text("user_apartments.residence_resident", language=lang)
        text += get_text("user_apartments.admin_detail_residence", language=lang).format(type=residence_type) + "\n"

        is_primary_text = get_text("user_apartments.yes", language=lang) if user_apartment.is_primary else get_text("user_apartments.no", language=lang)
        text += get_text("user_apartments.admin_detail_primary", language=lang).format(value=is_primary_text) + "\n\n"

        if user_apartment.requested_at:
            text += get_text("user_apartments.admin_detail_requested", language=lang).format(
                date=user_apartment.requested_at.strftime('%d.%m.%Y %H:%M')
            ) + "\n"

        if user_apartment.reviewed_at:
            text += get_text("user_apartments.admin_detail_reviewed", language=lang).format(
                date=user_apartment.reviewed_at.strftime('%d.%m.%Y %H:%M')
            ) + "\n"

        if user_apartment.admin_comment:
            text += get_text("user_apartments.admin_detail_comment", language=lang).format(
                comment=html.escape(user_apartment.admin_comment)
            ) + "\n"

        await callback.message.edit_text(
            text,
            reply_markup=get_admin_apartment_detail_keyboard(user_apartment, lang),
            parse_mode="HTML"
        )
        await callback.answer()


    except Exception as e:
        logger.error(f"Ошибка при загрузке деталей квартиры: {e}")
        await callback.answer(get_text("user_apartments.error_loading", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("admin_approve_apartment_"))
@require_role(['admin', 'manager'])
async def admin_approve_apartment(callback: CallbackQuery, state: FSMContext, language: str = "ru", roles: list = None, user=None, *, _db=None):
    """Админ: одобрить квартиру"""
    lang = language
    try:
        user_apartment_id = int(callback.data.split("_")[-1])

        result = await run_db(
            lambda s: _admin_approve_apartment(s, user_apartment_id, callback.from_user.id), db=_db
        )

        if result == "not_found":
            await callback.answer(get_text("user_apartments.apartment_not_found", language=lang), show_alert=True)
            return

        if result == "admin_not_found":
            await callback.answer(get_text("user_apartments.admin_not_found", language=lang), show_alert=True)
            return

        if result == "not_pending":
            # Стейл-клавиатура/чужой callback: решение уже принято.
            await callback.answer(get_text("user_apartments.already_processed", language=lang), show_alert=True)
            return

        await callback.answer(get_text("user_apartments.apartment_approved", language=lang), show_alert=True)

        # Возвращаемся к деталям (BUG-165: язык пробрасывается).
        # roles/user обязательны: require_role читает kwargs, без них менеджер
        # получил бы отказ сразу после успешного действия.
        await admin_apartment_detail(callback, state, language=lang,
                                     roles=roles, user=user, _db=_db)


    except Exception as e:
        logger.error(f"Ошибка одобрения квартиры: {e}")
        await callback.answer(get_text("user_apartments.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("admin_reject_apartment_"))
@require_role(['admin', 'manager'])
async def admin_reject_apartment(callback: CallbackQuery, state: FSMContext, language: str = "ru", roles: list = None, user=None, *, _db=None):
    """Админ: отклонить квартиру"""
    lang = language
    try:
        user_apartment_id = int(callback.data.split("_")[-1])

        result = await run_db(
            lambda s: _admin_reject_apartment(s, user_apartment_id, callback.from_user.id), db=_db
        )

        if result == "not_found":
            await callback.answer(get_text("user_apartments.apartment_not_found", language=lang), show_alert=True)
            return

        if result == "admin_not_found":
            await callback.answer(get_text("user_apartments.admin_not_found", language=lang), show_alert=True)
            return

        if result == "not_pending":
            # Стейл-клавиатура/чужой callback: решение уже принято.
            await callback.answer(get_text("user_apartments.already_processed", language=lang), show_alert=True)
            return

        await callback.answer(get_text("user_apartments.apartment_rejected", language=lang), show_alert=True)

        # Возвращаемся к деталям (BUG-165: язык пробрасывается).
        # roles/user обязательны: require_role читает kwargs (см. approve выше).
        await admin_apartment_detail(callback, state, language=lang,
                                     roles=roles, user=user, _db=_db)


    except Exception as e:
        logger.error(f"Ошибка отклонения квартиры: {e}")
        await callback.answer(get_text("user_apartments.error_generic", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("admin_toggle_owner_"))
@require_role(['admin', 'manager'])
async def admin_toggle_owner_status(callback: CallbackQuery, state: FSMContext, language: str = "ru", roles: list = None, user=None, *, _db=None):
    """Админ: переключить статус владелец/жилец"""
    lang = language
    try:
        user_apartment_id = int(callback.data.split("_")[-1])

        is_owner = await run_db(lambda s: _admin_toggle_owner(s, user_apartment_id), db=_db)

        if is_owner is None:
            await callback.answer(get_text("user_apartments.apartment_not_found", language=lang), show_alert=True)
            return

        new_status = get_text("user_apartments.toggle_to_owner", language=lang) if is_owner else get_text("user_apartments.toggle_to_resident", language=lang)
        await callback.answer(get_text("user_apartments.status_changed_to", language=lang).format(status=new_status), show_alert=True)

        # Обновляем детали (BUG-165: язык пробрасывается).
        # roles/user обязательны: require_role читает kwargs (см. approve выше).
        await admin_apartment_detail(callback, state, language=lang,
                                     roles=roles, user=user, _db=_db)


    except Exception as e:
        logger.error(f"Ошибка переключения статуса владельца: {e}")
        await callback.answer(get_text("user_apartments.error_generic", language=lang), show_alert=True)


def get_admin_apartments_keyboard(user_apartments, user_telegram_id, user_internal_id=None, lang: str = "ru"):
    """Клавиатура управления квартирами для админа (принимает [_ApartmentRow])"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    keyboard = []

    # Кнопки для квартир
    for ua in user_apartments[:10]:  # Максимум 10
        address = ua.address

        # Укорачиваем для кнопки
        button_text = address[:35] + "..." if len(address) > 35 else address

        # Добавляем иконки статуса
        if ua.status == 'approved':
            button_text = "✅ " + button_text
        elif ua.status == 'pending':
            button_text = "⏳ " + button_text
        elif ua.status == 'rejected':
            button_text = "❌ " + button_text

        keyboard.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"admin_apartment_detail_{ua.id}"
            )
        ])

    # Кнопка возврата
    keyboard.append([InlineKeyboardButton(
        text=get_text("user_apartments.btn_back_to_user", language=lang),
        callback_data=f"user_mgmt_user_{user_internal_id if user_internal_id else user_telegram_id}"
    )])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_admin_apartment_detail_keyboard(user_apartment, lang: str = "ru"):
    """Клавиатура деталей квартиры для админа (принимает _ApartmentView)"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    keyboard = []

    # Кнопки действий в зависимости от статуса
    if user_apartment.status == 'pending':
        keyboard.append([
            InlineKeyboardButton(
                text=get_text("user_apartments.btn_approve", language=lang),
                callback_data=f"admin_approve_apartment_{user_apartment.id}"
            ),
            InlineKeyboardButton(
                text=get_text("user_apartments.btn_reject", language=lang),
                callback_data=f"admin_reject_apartment_{user_apartment.id}"
            )
        ])

    # Переключение статуса владелец/жилец
    owner_text = get_text("user_apartments.btn_make_resident", language=lang) if user_apartment.is_owner else get_text("user_apartments.btn_make_owner", language=lang)
    keyboard.append([
        InlineKeyboardButton(
            text=owner_text,
            callback_data=f"admin_toggle_owner_{user_apartment.id}"
        )
    ])

    # Кнопка возврата
    keyboard.append([
        InlineKeyboardButton(
            text=get_text("user_apartments.btn_back_to_list", language=lang),
            callback_data=f"admin_manage_apartments_{user_apartment.user_telegram_id}"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)
