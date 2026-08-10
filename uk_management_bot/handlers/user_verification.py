"""
Обработчики для системы верификации пользователей

Содержит обработчики для:
- Управления верификацией пользователей
- Запроса дополнительной информации
- Проверки документов
- Управления правами доступа

AUD3-07 (канон B1/B4): DB-фаза каждого хендлера — цельный sync unit-of-work
(`_load_*`/`_apply_*`/`_collect_*` ниже), исполняемый в worker-потоке через
``run_db``. Сессия живёт только внутри юнита; наружу выходят DTO (dataclass'ы),
рендеринг текста — по ним. Сеть (Telegram-отправки, media-cleanup) — вне
юнитов, на event loop. Хендлеры НЕ объявляют параметр ``db`` (иначе aiogram DI
инъецирует middleware-сессию, и запрос исполняется на loop; гейт:
tests/services/test_aud337_async_handlers_gate.py). Тестовый seam —
keyword-only ``_db``: с ним юнит исполняется синхронно на переданной сессии.
"""

import logging

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.session import run_db
from uk_management_bot.services.user_verification_service import (
    UserVerificationService,
    cleanup_user_documents_media,
)
from uk_management_bot.services.notification_service import NotificationService
from uk_management_bot.utils.telegram_client import SEND_TIMEOUT
from uk_management_bot.keyboards.user_verification import (
    get_verification_main_keyboard,
    get_user_verification_keyboard,
    get_document_verification_keyboard,
    get_access_rights_keyboard,
    get_verification_request_keyboard,
    get_cancel_keyboard
)
from uk_management_bot.states.user_verification import UserVerificationStates
from uk_management_bot.database.models.user_verification import (
    VerificationStatus
)
from uk_management_bot.utils.address_helpers import apartment_address
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)
router = Router()


# ==========================================================================
# DTO + sync-юниты (AUD3-07). Сессия живёт только внутри юнита.
# ==========================================================================


@dataclass(frozen=True)
class _ApartmentRow:
    address: str
    is_primary: bool
    is_owner: bool


@dataclass(frozen=True)
class _DocumentRow:
    id: int
    type_value: str
    status: VerificationStatus
    file_id: str = ""
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    created_at: Optional[datetime] = None
    notes: Optional[str] = None


@dataclass(frozen=True)
class _AccessRightRow:
    level_value: str
    apartment_number: Optional[str]
    house_number: Optional[str]
    yard_name: Optional[str]


@dataclass(frozen=True)
class _UserCard:
    first_name: Optional[str]
    last_name: Optional[str]
    username: Optional[str]
    phone: Optional[str]
    verification_status: str
    verification_notes: Optional[str]
    has_apartment_links: bool
    approved_apartments: List[_ApartmentRow] = field(default_factory=list)
    documents: List[_DocumentRow] = field(default_factory=list)
    access_rights: List[_AccessRightRow] = field(default_factory=list)


def _document_row(doc, *, with_file: bool = False) -> _DocumentRow:
    return _DocumentRow(
        id=doc.id,
        type_value=doc.document_type.value,
        status=doc.verification_status,
        file_id=doc.file_id if with_file else "",
        file_name=doc.file_name,
        file_size=doc.file_size,
        created_at=doc.created_at,
        notes=doc.verification_notes,
    )


def _load_verification_stats(db) -> dict:
    return UserVerificationService(db).get_verification_stats()


def _load_user_card(db, user_id: int, lang: str) -> Optional[_UserCard]:
    """Пользователь + approved-квартиры + документы + активные права — одним юнитом."""
    from uk_management_bot.database.models.user import User
    from uk_management_bot.database.models.user_verification import UserDocument, AccessRights

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None

    documents = db.query(UserDocument).filter(UserDocument.user_id == user_id).all()
    access_rights = db.query(AccessRights).filter(
        AccessRights.user_id == user_id,
        AccessRights.is_active.is_(True)
    ).all()

    approved = []
    has_links = bool(user.user_apartments)
    if has_links:
        for ua in user.user_apartments:
            if ua.status == 'approved':
                approved.append(_ApartmentRow(
                    address=apartment_address(ua.apartment, lang),
                    is_primary=ua.is_primary,
                    is_owner=ua.is_owner,
                ))

    return _UserCard(
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        phone=user.phone,
        verification_status=user.verification_status,
        verification_notes=user.verification_notes,
        has_apartment_links=has_links,
        approved_apartments=approved,
        documents=[_document_row(d) for d in documents],
        access_rights=[
            _AccessRightRow(
                level_value=r.access_level.value,
                apartment_number=r.apartment_number,
                house_number=r.house_number,
                yard_name=r.yard_name,
            )
            for r in access_rights
        ],
    )


def _load_documents_page(db, user_id: int):
    """→ (display_name_источники, [документы новые→старые]) | None."""
    from uk_management_bot.database.models.user import User
    from uk_management_bot.database.models.user_verification import UserDocument

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    documents = (
        db.query(UserDocument)
        .filter(UserDocument.user_id == user_id)
        .order_by(UserDocument.created_at.desc())
        .all()
    )
    return (user.first_name, user.username), [_document_row(d) for d in documents]


def _load_document(db, document_id: int, *, with_file: bool = False) -> Optional[_DocumentRow]:
    from uk_management_bot.database.models.user_verification import UserDocument

    document = db.query(UserDocument).filter(UserDocument.id == document_id).first()
    if not document:
        return None
    return _document_row(document, with_file=with_file)


def _create_request_and_collect_notify(db, user_id: int, admin_id: int, requested_info: dict):
    """Создание запроса верификации + fetch-фаза уведомления (сеть — у вызывающего)."""
    UserVerificationService(db).create_verification_request(
        user_id=user_id,
        admin_id=admin_id,
        requested_info=requested_info,
    )
    return NotificationService(db).collect_verification_request_message(
        user_id, requested_info['type'], requested_info['comment']
    )


def _verify_document(db, document_id: int, admin_id: int, status: VerificationStatus,
                     notes: Optional[str] = None) -> bool:
    return UserVerificationService(db).verify_document(
        document_id=document_id, admin_id=admin_id, status=status, notes=notes
    )


def _load_access_rights_card(db, user_id: int):
    """→ (имя, [права]) | None."""
    from uk_management_bot.database.models.user import User
    from uk_management_bot.database.models.user_verification import AccessRights

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    current_rights = db.query(AccessRights).filter(
        AccessRights.user_id == user_id,
        AccessRights.is_active.is_(True)
    ).all()
    name = f"{user.first_name} {user.last_name or ''}".strip()
    return name, [
        _AccessRightRow(
            level_value=r.access_level.value,
            apartment_number=r.apartment_number,
            house_number=r.house_number,
            yard_name=r.yard_name,
        )
        for r in current_rights
    ]


def _approve_user_db(db, user_id: int, admin_id: int):
    """DB-фазы одобрения + fetch уведомлений. → (ok, telegram_id, notify_pair,
    restart_target). Сеть (media-cleanup, отправки) — у вызывающего."""
    from uk_management_bot.database.models.user import User

    service = UserVerificationService(db)
    ok, telegram_id = service.approve_verification_db(user_id, admin_id)
    if not ok:
        return False, None, None, None

    notify_pair = NotificationService(db).collect_verification_approved_message(user_id)

    restart_target = None
    target_user = db.query(User).filter(User.id == user_id).first()
    if target_user:
        restart_target = (target_user.telegram_id, target_user.language or "ru")

    return True, telegram_id, notify_pair, restart_target


def _purge_user_documents(db, user_id: int) -> None:
    UserVerificationService(db).purge_user_documents_db(user_id)


def _reject_user_db(db, user_id: int, admin_id: int, notes: str):
    """DB-фаза отклонения + fetch уведомления. → (ok, notify_pair)."""
    ok = UserVerificationService(db).reject_verification(
        user_id=user_id, admin_id=admin_id, notes=notes
    )
    if not ok:
        return False, None
    return True, NotificationService(db).collect_verification_rejected_message(user_id)


# ═══ ГЛАВНОЕ МЕНЮ ВЕРИФИКАЦИИ ═══

@router.callback_query(F.data == "user_verification_panel")
async def show_verification_panel(callback: CallbackQuery, roles: list = None, language: str = "ru", *, _db=None):
    """Показать панель верификации пользователей"""
    lang = language

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        # Получаем статистику верификации
        stats = await run_db(_load_verification_stats, db=_db)

        # Показываем главное меню
        await callback.message.edit_text(
            get_text('verification.main_title', language=lang),
            reply_markup=get_verification_main_keyboard(stats, lang)
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка отображения панели верификации: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ УПРАВЛЕНИЕ ВЕРИФИКАЦИЕЙ ПОЛЬЗОВАТЕЛЕЙ ═══

@router.callback_query(F.data.startswith("verification_user_"))
async def show_user_verification(callback: CallbackQuery, roles: list = None, language: str = "ru", *, _db=None):
    """Показать информацию о верификации пользователя"""
    lang = language
    user_id = int(callback.data.split("_")[2])

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        card = await run_db(lambda s: _load_user_card(s, user_id, lang), db=_db)
        if card is None:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return

        # Формируем информацию о пользователе
        not_specified = get_text("user_verification.handlers.not_specified", language=lang)
        user_info = get_text("user_verification.handlers.user_info_header", language=lang).format(
            first_name=card.first_name or not_specified,
            last_name=card.last_name or not_specified,
            username=card.username or not_specified,
            phone=card.phone or not_specified
        )

        # ОБНОВЛЕНО: Используем новую систему квартир
        if card.has_apartment_links:
            if card.approved_apartments:
                user_info += "\n"
                for apt in card.approved_apartments:
                    primary_marker = " ⭐" if apt.is_primary else ""
                    owner_marker = " (" + get_text("user_verification.handlers.owner", language=lang) + ")" if apt.is_owner else ""
                    user_info += f"• {apt.address}{primary_marker}{owner_marker}\n"
            else:
                user_info += "\n• " + get_text("user_verification.handlers.addresses_pending", language=lang) + "\n"
        else:
            user_info += "\n• " + get_text("user_verification.handlers.addresses_not_specified", language=lang) + "\n"

        verification_status = get_text(f'verification.status.{card.verification_status}', language=lang)
        user_info += "\n\n📋 <b>" + get_text("user_verification.handlers.verification_status_label", language=lang) + ":</b> " + verification_status

        if card.verification_notes:
            user_info += "\n📝 <b>" + get_text("user_verification.handlers.comments_label", language=lang) + ":</b> " + card.verification_notes

        # Добавляем информацию о документах
        if card.documents:
            user_info += "\n\n📄 <b>" + get_text("user_verification.handlers.documents_count", language=lang).format(count=len(card.documents)) + ":</b>"
            for doc in card.documents:
                status_emoji = "✅" if doc.status == VerificationStatus.APPROVED else "⏳" if doc.status == VerificationStatus.PENDING else "❌"
                doc_type_name = get_text(f'verification.document_types.{doc.type_value}', language=lang)
                user_info += f"\n{status_emoji} {doc_type_name}"
        else:
            user_info += "\n\n📄 <b>" + get_text("user_verification.handlers.documents_label", language=lang) + ":</b> " + get_text("user_verification.handlers.not_uploaded", language=lang)

        # Добавляем информацию о правах доступа
        if card.access_rights:
            user_info += "\n\n🔑 <b>" + get_text("user_verification.handlers.access_rights_count", language=lang).format(count=len(card.access_rights)) + ":</b>"
            for right in card.access_rights:
                user_info += f"\n• {right.level_value}"
                if right.apartment_number:
                    user_info += f" ({get_text('user_verification.handlers.apt_short', language=lang)} {right.apartment_number})"
                elif right.house_number:
                    user_info += f" ({get_text('user_verification.handlers.house_short', language=lang)} {right.house_number})"
                elif right.yard_name:
                    user_info += f" ({get_text('user_verification.handlers.yard_short', language=lang)} {right.yard_name})"

        await callback.message.edit_text(
            user_info,
            reply_markup=get_user_verification_keyboard(user_id, lang)
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка отображения верификации пользователя: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ЗАПРОС ДОПОЛНИТЕЛЬНОЙ ИНФОРМАЦИИ ═══

@router.callback_query(F.data.startswith("verification_request_"))
async def request_additional_info(callback: CallbackQuery, roles: list = None, language: str = "ru"):
    """Запросить дополнительную информацию от пользователя"""
    lang = language
    user_id = int(callback.data.split("_")[2])

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        # Переходим в состояние запроса информации
        await callback.message.edit_text(
            get_text('verification.request_info_title', language=lang),
            reply_markup=get_verification_request_keyboard(user_id, lang)
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка запроса дополнительной информации: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )

# ═══ ПРОСМОТР ДОКУМЕНТОВ ПОЛЬЗОВАТЕЛЯ ═══

@router.callback_query(F.data.startswith("view_user_documents_"))
async def view_user_documents(callback: CallbackQuery, roles: list = None, language: str = "ru", *, _db=None):
    """Показать документы пользователя"""
    lang = language
    user_id = int(callback.data.split("_")[3])

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        page = await run_db(lambda s: _load_documents_page(s, user_id), db=_db)
        if page is None:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return
        (first_name, username), documents = page

        unknown_name = get_text("user_verification.handlers.unknown", language=lang)
        user_display_name = first_name or username or unknown_name

        if not documents:
            await callback.message.edit_text(
                get_text("user_verification.handlers.user_documents_title", language=lang).format(name=user_display_name) + "\n\n" +
                get_text("user_verification.handlers.documents_not_loaded", language=lang),
                reply_markup=get_cancel_keyboard(lang)
            )
            await callback.answer()
            return

        # Формируем список документов
        documents_text = get_text("user_verification.handlers.user_documents_title", language=lang).format(name=user_display_name) + "\n\n"

        for i, doc in enumerate(documents, 1):
            status_emoji = "✅" if doc.status == VerificationStatus.APPROVED else "⏳" if doc.status == VerificationStatus.PENDING else "❌"
            doc_type_name = get_text(f'verification.document_types.{doc.type_value}', language=lang)

            documents_text += f"{i}. {status_emoji} <b>{doc_type_name}</b>\n"
            documents_text += f"   📁 {get_text('user_verification.handlers.file_label', language=lang)}: {doc.file_name or get_text('user_verification.handlers.no_title', language=lang)}\n"
            if doc.file_size:
                documents_text += f"   📏 {get_text('user_verification.handlers.size_label', language=lang)}: {doc.file_size // 1024} KB\n"
            documents_text += f"   📅 {get_text('user_verification.handlers.uploaded_date', language=lang)}: {doc.created_at.strftime('%d.%m.%Y %H:%M')}\n"

            if doc.notes:
                documents_text += f"   📝 {get_text('user_verification.handlers.comment_label', language=lang)}: {doc.notes}\n"

            documents_text += "\n"

        # Добавляем кнопки для управления документами
        from uk_management_bot.keyboards.user_verification import get_document_management_keyboard
        keyboard = get_document_management_keyboard(user_id, lang)

        await callback.message.edit_text(
            documents_text,
            reply_markup=keyboard
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка просмотра документов пользователя: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )

@router.callback_query(F.data.startswith("download_document_"))
async def download_user_document(callback: CallbackQuery, roles: list = None, language: str = "ru", *, _db=None):
    """Скачать документ пользователя"""
    lang = language
    document_id = int(callback.data.split("_")[2])

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        document = await run_db(
            lambda s: _load_document(s, document_id, with_file=True), db=_db
        )
        if document is None:
            await callback.answer(
                get_text("user_verification.handlers.document_not_found", language=lang),
                show_alert=True
            )
            return

        # Отправляем файл
        bot = callback.bot

        try:
            caption = (f"📄 {get_text(f'verification.document_types.{document.type_value}', language=lang)}\n"
                      f"📅 Загружен: {document.created_at.strftime('%d.%m.%Y %H:%M')}")

            # Пробуем отправить как документ, если не получится - как фото
            try:
                await bot.send_document(
                    chat_id=callback.from_user.id,
                    document=document.file_id,
                    caption=caption
                )
                await callback.answer(get_text("user_verification.handlers.document_sent_dm", language=lang))
            except Exception as doc_error:
                # Если ошибка "can't use file of type Photo", отправляем как фото
                if "can't use file of type Photo" in str(doc_error):
                    logger.info(f"Файл {document.file_id} является фото, отправляем как photo")
                    await bot.send_photo(
                        chat_id=callback.from_user.id,
                        photo=document.file_id,
                        caption=caption
                    )
                    await callback.answer(get_text("user_verification.handlers.document_sent_dm", language=lang))
                else:
                    raise  # Пробрасываем другие ошибки
        except Exception as e:
            logger.error(f"Ошибка отправки документа: {e}")
            await callback.answer(get_text("user_verification.handlers.error_sending_document", language=lang), show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка скачивания документа: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("request_info_"))
async def select_info_type(callback: CallbackQuery, state: FSMContext, roles: list = None, language: str = "ru"):
    """Выбрать тип запрашиваемой информации"""
    lang = language
    # AUD3-15: info_type сам содержит "_" (property_deed, rental_agreement,
    # utility_bill) — parts[3] обрезал его до первого сегмента. Префикс
    # request_info_{user_id}_ фиксирован, поэтому хвост склеиваем целиком.
    parts = callback.data.split("_")
    user_id = int(parts[2])
    info_type = "_".join(parts[3:])

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        # Сохраняем данные в состоянии
        await state.update_data(
            target_user_id=user_id,
            info_type=info_type
        )

        # Переходим в состояние ввода комментария
        await state.set_state(UserVerificationStates.enter_request_comment)

        await callback.message.edit_text(
            get_text('verification.enter_request_comment', language=lang),
            reply_markup=get_cancel_keyboard(lang)
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка выбора типа информации: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.message(UserVerificationStates.enter_request_comment)
async def process_request_comment(message: Message, state: FSMContext, roles: list = None, language: str = "ru", *, _db=None):
    """Обработать комментарий к запросу информации"""
    lang = language
    comment = message.text

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await message.answer(get_text('errors.permission_denied', language=lang))
        return

    try:
        # Получаем данные из состояния
        data = await state.get_data()
        user_id = data.get('target_user_id')
        info_type = data.get('info_type')

        # Создаем запрос верификации + fetch-фаза уведомления (одним юнитом)
        requested_info = {
            'type': info_type,
            'comment': comment
        }
        admin_id = message.from_user.id
        notify_pair = await run_db(
            lambda s: _create_request_and_collect_notify(s, user_id, admin_id, requested_info),
            db=_db,
        )

        # Отправляем уведомление пользователю (сеть — вне сессии; best-effort,
        # как в историческом send_verification_request_notification)
        if notify_pair is not None:
            telegram_id, text = notify_pair
            try:
                await message.bot.send_message(telegram_id, text, request_timeout=SEND_TIMEOUT)
                logger.info(f"Уведомление о запросе информации отправлено пользователю {user_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления о запросе информации: {e}")

        # Очищаем состояние
        await state.clear()

        await message.answer(
            get_text('verification.request_sent_successfully', language=lang),
            reply_markup=get_verification_main_keyboard({}, lang)
        )

    except Exception as e:
        logger.error(f"Ошибка обработки комментария запроса: {e}")
        await message.answer(get_text('errors.unknown_error', language=lang))


# ═══ УПРАВЛЕНИЕ ДОКУМЕНТАМИ ═══

@router.callback_query(F.data.startswith("document_verify_"))
async def verify_document(callback: CallbackQuery, roles: list = None, language: str = "ru", *, _db=None):
    """Проверить документ пользователя"""
    lang = language
    document_id = int(callback.data.split("_")[2])

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        document = await run_db(lambda s: _load_document(s, document_id), db=_db)
        if document is None:
            await callback.answer(
                get_text('errors.document_not_found', language=lang),
                show_alert=True
            )
            return

        # Показываем информацию о документе
        doc_size = str(document.file_size) if document.file_size else get_text("user_verification.handlers.unknown_value", language=lang)
        doc_status = get_text(f'verification.document_status.{document.status.value}', language=lang)
        document_info = get_text("user_verification.handlers.document_info", language=lang).format(
            doc_type=document.type_value,
            uploaded=document.created_at.strftime('%d.%m.%Y %H:%M'),
            size=doc_size,
            status=doc_status
        )

        if document.notes:
            document_info += "\n📝 <b>" + get_text("user_verification.handlers.comments_label", language=lang) + ":</b> " + document.notes

        await callback.message.edit_text(
            document_info,
            reply_markup=get_document_verification_keyboard(document_id, lang)
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка проверки документа: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("document_approve_"))
async def approve_document(callback: CallbackQuery, roles: list = None, language: str = "ru", *, _db=None):
    """Одобрить документ"""
    lang = language
    document_id = int(callback.data.split("_")[2])

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        admin_id = callback.from_user.id
        success = await run_db(
            lambda s: _verify_document(s, document_id, admin_id, VerificationStatus.APPROVED),
            db=_db,
        )

        if success:
            await callback.answer(
                get_text('verification.document_approved', language=lang),
                show_alert=True
            )
        else:
            await callback.answer(
                get_text('errors.operation_failed', language=lang),
                show_alert=True
            )

    except Exception as e:
        logger.error(f"Ошибка одобрения документа: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("document_reject_"))
async def reject_document(callback: CallbackQuery, roles: list = None, language: str = "ru", *, _db=None):
    """Отклонить документ"""
    lang = language
    document_id = int(callback.data.split("_")[2])

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        admin_id = callback.from_user.id
        reject_notes = get_text("user_verification.handlers.document_rejected_by_admin", language=lang)
        success = await run_db(
            lambda s: _verify_document(
                s, document_id, admin_id, VerificationStatus.REJECTED, notes=reject_notes
            ),
            db=_db,
        )

        if success:
            await callback.answer(
                get_text('verification.document_rejected', language=lang),
                show_alert=True
            )
        else:
            await callback.answer(
                get_text('errors.operation_failed', language=lang),
                show_alert=True
            )

    except Exception as e:
        logger.error(f"Ошибка отклонения документа: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ УПРАВЛЕНИЕ ПРАВАМИ ДОСТУПА ═══

@router.callback_query(F.data.startswith("access_rights_"))
async def manage_access_rights(callback: CallbackQuery, roles: list = None, language: str = "ru", *, _db=None):
    """Управление правами доступа пользователя"""
    lang = language
    user_id = int(callback.data.split("_")[2])

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        card = await run_db(lambda s: _load_access_rights_card(s, user_id), db=_db)
        if card is None:
            await callback.answer(
                get_text('errors.user_not_found', language=lang),
                show_alert=True
            )
            return
        name, current_rights = card

        # Формируем информацию о правах доступа
        rights_info = get_text("user_verification.handlers.access_rights_title", language=lang).format(
            name=name,
            count=len(current_rights)
        )

        if current_rights:
            for right in current_rights:
                rights_info += f"• {right.level_value}"
                if right.apartment_number:
                    rights_info += f" ({get_text('user_verification.handlers.apt_short', language=lang)} {right.apartment_number})"
                elif right.house_number:
                    rights_info += f" ({get_text('user_verification.handlers.house_short', language=lang)} {right.house_number})"
                elif right.yard_name:
                    rights_info += f" ({get_text('user_verification.handlers.yard_short', language=lang)} {right.yard_name})"
                rights_info += "\n"
        else:
            rights_info += "• " + get_text("user_verification.handlers.no_access_rights", language=lang) + "\n"

        await callback.message.edit_text(
            rights_info,
            reply_markup=get_access_rights_keyboard(user_id, lang)
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка управления правами доступа: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


# ═══ ОДОБРЕНИЕ/ОТКЛОНЕНИЕ ВЕРИФИКАЦИИ ═══

@router.callback_query(F.data.startswith("verify_approve_"))
async def approve_user_verification(callback: CallbackQuery, roles: list = None, language: str = "ru", *, _db=None):
    """Одобрить верификацию пользователя"""
    lang = language
    user_id = int(callback.data.split("_")[2])

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        admin_id = callback.from_user.id
        # DB-фазы (статусы + квартиры + fetch уведомлений) — в потоке; сеть ниже.
        success, telegram_id, notify_pair, restart_target = await run_db(
            lambda s: _approve_user_db(s, user_id, admin_id), db=_db
        )

        if success:
            # Зачистка документов в Media Service (сеть, best-effort) и затем
            # удаление записей о документах — порядок 1:1 с историческим
            # approve_verification.
            await cleanup_user_documents_media(telegram_id)
            await run_db(lambda s: _purge_user_documents(s, user_id), db=_db)

            # Отправляем уведомление пользователю (best-effort, как в
            # send_verification_approved_notification)
            if notify_pair is not None:
                notify_tg, notify_text = notify_pair
                try:
                    await callback.bot.send_message(notify_tg, notify_text, request_timeout=SEND_TIMEOUT)
                    logger.info(f"Уведомление об одобрении верификации отправлено пользователю {user_id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления об одобрении верификации: {e}")

            # Отправляем обновленное главное меню пользователю
            try:
                if restart_target is not None:
                    target_tg, target_lang = restart_target
                    # Создаем клавиатуру с кнопкой перезапуска
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                    restart_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=get_text("user_verification.handlers.btn_restart_bot", language=target_lang), callback_data="restart_bot")]
                    ])

                    # Отправляем уведомление об одобрении с кнопкой перезапуска
                    await callback.bot.send_message(
                        chat_id=target_tg,
                        text=get_text("user_verification.handlers.application_approved_notification", language=target_lang),
                        reply_markup=restart_keyboard
                    )

            except Exception as e:
                logger.error(f"Ошибка отправки обновленного меню пользователю {user_id}: {e}")

            await callback.answer(
                get_text('verification.user_approved', language=lang),
                show_alert=True
            )
        else:
            await callback.answer(
                get_text('errors.operation_failed', language=lang),
                show_alert=True
            )

    except Exception as e:
        logger.error(f"Ошибка одобрения верификации: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )


@router.callback_query(F.data.startswith("verify_reject_"))
async def reject_user_verification(callback: CallbackQuery, roles: list = None, language: str = "ru", *, _db=None):
    """Отклонить верификацию пользователя"""
    lang = language
    user_id = int(callback.data.split("_")[2])

    # Проверяем права доступа
    if not roles or not any(role in ['admin', 'manager'] for role in roles):
        await callback.answer(
            get_text('errors.permission_denied', language=lang),
            show_alert=True
        )
        return

    try:
        admin_id = callback.from_user.id
        reject_notes = get_text("user_verification.handlers.verification_rejected_by_admin", language=lang)
        success, notify_pair = await run_db(
            lambda s: _reject_user_db(s, user_id, admin_id, reject_notes), db=_db
        )

        if success:
            # Отправляем уведомление пользователю (best-effort, как в
            # send_verification_rejected_notification)
            if notify_pair is not None:
                notify_tg, notify_text = notify_pair
                try:
                    await callback.bot.send_message(notify_tg, notify_text, request_timeout=SEND_TIMEOUT)
                    logger.info(f"Уведомление об отклонении верификации отправлено пользователю {user_id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления об отклонении верификации: {e}")

            await callback.answer(
                get_text('verification.user_rejected', language=lang),
                show_alert=True
            )
        else:
            await callback.answer(
                get_text('errors.operation_failed', language=lang),
                show_alert=True
            )

    except Exception as e:
        logger.error(f"Ошибка отклонения верификации: {e}")
        await callback.answer(
            get_text('errors.unknown_error', language=lang),
            show_alert=True
        )
