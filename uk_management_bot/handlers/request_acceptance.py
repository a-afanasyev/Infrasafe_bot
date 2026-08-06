"""
Обработчики для процесса приёмки выполненных заявок заявителем

Включает:
- Просмотр списка заявок, ожидающих приёмки
- Просмотр деталей выполненной заявки
- Принятие заявки с оценкой (1-5 звёзд)
- Возврат заявки с причиной и медиа

AUD3-37 (вариант (б), волна B3): DB-фаза каждого хендлера — sync unit-of-work
в worker-потоке через ``run_db``; наружу DTO/скаляры. Канонический переход
``run_command_sync`` (своя сессия из SessionLocal, FOR UPDATE) уезжает в поток
через ``asyncio.to_thread`` целиком. Post-commit-уведомления разрезаны на
fetch/render-фазу в потоке (``collect_notify_messages_sync`` /
``render_channel_status_text``) и send-фазу на loop — Telegram-IO больше не
держит сессию БД. Хендлеры НЕ объявляют ``db`` (aiogram DI иначе инъецирует
middleware-сессию); тестовый seam — keyword-only ``_db``.
"""

import asyncio
from dataclasses import dataclass
from typing import Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.keyboards.admin import (
    get_applicant_completed_request_actions_keyboard,
    get_rating_keyboard,
    get_skip_media_keyboard,
)
from uk_management_bot.states.request_acceptance import ApplicantAcceptanceStates
from uk_management_bot.database.session import run_db
# AUD6-P1-6: адресные уведомления — матрицей интентов (общей с API-путём),
# канальная лента — отдельным хелпером. AUD3-37: fetch/render-фазы — в потоке,
# send-фазы — на loop.
from uk_management_bot.services.workflow_notifications import (
    collect_notify_messages_sync,
    render_channel_status_text,
    send_channel_status_text,
    send_notify_messages,
)
from uk_management_bot.utils.workflow_predicates import (
    awaiting_applicant_clause,
    can_accept,
    get_approved_apartment_ids,
)

from uk_management_bot.utils.button_texts import get_acceptance_texts
from uk_management_bot.utils.helpers import get_text

import logging

router = Router()
logger = logging.getLogger(__name__)


# Single Source of Truth for button texts - TASK 17
# Константа для фильтрации сообщений "Ожидают приёмки"
ACCEPTANCE_TEXTS = get_acceptance_texts()


# ==========================================================================
# DTO для рендера (клавиатуры этого экрана строятся по скалярам).
# ==========================================================================

@dataclass(frozen=True)
class _PendingRow:
    request_number: str
    category: Optional[str]
    address: Optional[str]
    updated_at: object


@dataclass(frozen=True)
class _CompletedView:
    request_number: str
    category: Optional[str]
    address: Optional[str]
    description: Optional[str]
    completion_report: Optional[str]
    completion_media: list


# ==========================================================================
# Sync unit-of-work (исполняются в worker-потоке через run_db).
# ==========================================================================

def _user_id_by_tg(db, telegram_id: int) -> Optional[int]:
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    return user.id if user else None


def _lang_by_tg(db, telegram_id: int) -> str:
    from uk_management_bot.utils.helpers import get_user_language
    return get_user_language(telegram_id, db)


def _load_pending_acceptance(db, telegram_id: int):
    """-> (lang, user_found, [_PendingRow])."""
    from uk_management_bot.utils.helpers import get_user_language
    lang = get_user_language(telegram_id, db)

    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        return lang, False, []

    # Заявки, ожидающие приёмки: свои + одобренных соседей по квартире.
    from sqlalchemy import or_
    from uk_management_bot.database.models.user_apartment import UserApartment

    user_apartment_ids = [
        ua.apartment_id for ua in
        db.query(UserApartment.apartment_id)
        .filter(UserApartment.user_id == user.id, UserApartment.status == "approved")
        .all()
    ]

    ownership_filter = [Request.user_id == user.id]
    if user_apartment_ids:
        ownership_filter.append(Request.apartment_id.in_(user_apartment_ids))

    # HF-0: dual-filter — обе живые кодировки «ожидает приёмки»
    # (web: Исполнено; telegram: Выполнена+manager_confirmed), возвращённые
    # исключены (ждут reconfirm менеджера, а не приёмки).
    requests = (
        db.query(Request)
        .filter(
            or_(*ownership_filter),
            awaiting_applicant_clause(),
        )
        .order_by(Request.updated_at.desc())
        .limit(10)
        .all()
    )
    rows = [
        _PendingRow(request_number=r.request_number, category=r.category,
                    address=r.address, updated_at=r.updated_at)
        for r in requests
    ]
    return lang, True, rows


def _load_completed_view(db, telegram_id: int, request_number: str):
    """-> (lang, "no_request" | "no_user" | "forbidden" | "ok", _CompletedView | None)."""
    request = db.query(Request).filter(Request.request_number == request_number).first()
    if not request:
        return None, "no_request", None

    # HF-0: смотреть может владелец или одобренный сосед (та же семантика,
    # что у списка приёмки — иначе сосед из списка получает отказ).
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        return None, "no_user", None
    if not can_accept(request, user, get_approved_apartment_ids(db, user.id)):
        return None, "forbidden", None

    from uk_management_bot.utils.helpers import get_user_language
    lang = get_user_language(telegram_id, db)
    view = _CompletedView(
        request_number=request.request_number,
        category=request.category,
        address=request.address,
        description=request.description,
        completion_report=request.completion_report,
        completion_media=list(request.completion_media or []),
    )
    return lang, "ok", view


def _load_completion_media(db, telegram_id: int, request_number: str):
    """-> ("no_request" | "no_user" | "forbidden" | "ok", request_number, [file_id])."""
    request = db.query(Request).filter(Request.request_number == request_number).first()
    if not request:
        return "no_request", request_number, []

    # SEC: медиа выполненной заявки = потенциальный PII (интерьер квартиры,
    # данные жителя). Доступ — только владелец или одобренный сосед (та же
    # семантика, что view_completed_request); иначе любой по request_number
    # вытянет чужие медиафайлы.
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        return "no_user", request_number, []
    if not can_accept(request, user, get_approved_apartment_ids(db, user.id)):
        return "forbidden", request_number, []

    return "ok", request.request_number, list(request.completion_media or [])


def _collect_status_change_notifications(db, request_number: str, outcome, channel_new_status: str):
    """Post-commit fetch/render: (messages, channel_text). Свежая сессия потока —
    заявка перечитывается уже закоммиченной (PR0 Р7)."""
    request = db.query(Request).filter(Request.request_number == request_number).first()
    messages = collect_notify_messages_sync(db, request_number, outcome.post_commit_intents)
    channel_text = render_channel_status_text(request, outcome.old_status, channel_new_status)
    return messages, channel_text


def _collect_return_notifications(db, request_number: str, outcome, return_reason):
    """Post-commit fetch/render возврата: (messages, channel_text,
    [manager_telegram_id], manager_text | None)."""
    messages, channel_text = _collect_status_change_notifications(
        db, request_number, outcome, "Исполнено (возвращена)")

    request = db.query(Request).filter(Request.request_number == request_number).first()
    manager_ids: list[int] = []
    manager_text = None
    if request is not None:
        managers = db.query(User).filter(
            User.roles.contains('"manager"'),
            User.status == "approved"
        ).all()
        manager_ids = [m.telegram_id for m in managers if m.telegram_id]
        manager_text = get_text(
            "request_acceptance.handlers.manager_return_notification", language="ru"
        ).format(
            request_number=request.format_number_for_display(),
            category=request.category,
            return_reason=return_reason,
        )
    return messages, channel_text, manager_ids, manager_text


# ==========================================================================
# Handlers: Telegram-IO и рендеринг по DTO.
# ==========================================================================

@router.message(F.text.in_(ACCEPTANCE_TEXTS))
async def show_pending_acceptance_requests(message: Message, *, _db=None):
    """Показать список заявок, ожидающих приёмки заявителем"""
    try:
        telegram_id = message.from_user.id

        lang, user_found, requests = await run_db(
            lambda s: _load_pending_acceptance(s, telegram_id), db=_db,
        )
        if not user_found:
            await message.answer(get_text("common.user_not_found", language=lang))
            return

        if not requests:
            await message.answer(
                get_text("requests.no_pending_acceptance", language=lang)
            )
            return

        # Формируем список заявок
        text = f"{get_text('requests.pending_acceptance_title', language=lang)}\n\n"
        text += f"{get_text('requests.select_request_for_acceptance', language=lang)}\n\n"

        builder = []
        for req in requests:
            text += f"📋 <b>#{req.request_number}</b>\n"
            text += f"   {get_text('requests.category_label', language=lang)} {req.category}\n"
            address_text = req.address or get_text("requests.address_not_specified", language=lang) or "Не указан"
            text += f"   {get_text('requests.address_label', language=lang)} {address_text}\n"
            text += f"   {get_text('requests.updated_at', language=lang)} {req.updated_at.strftime('%d.%m.%Y %H:%M')}\n\n"

            builder.append([
                InlineKeyboardButton(
                    text=f"📋 #{req.request_number} - {req.category}",
                    callback_data=f"view_completed_{req.request_number}"
                )
            ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=builder)

        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

        logger.info(f"Показан список заявок, ожидающих приёмки пользователю {telegram_id}")

    except Exception as e:
        logger.error(f"Ошибка показа списка ожидающих приёмки заявок: {e}")
        try:
            lang = await run_db(lambda s: _lang_by_tg(s, message.from_user.id), db=_db)
        except Exception:
            lang = 'ru'
        await message.answer(get_text("requests.error_loading_requests", language=lang))


@router.callback_query(F.data.startswith("view_completed_"))
async def view_completed_request(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Просмотр деталей выполненной заявки заявителем"""
    try:
        telegram_id = callback.from_user.id
        request_number = callback.data.replace("view_completed_", "")

        lang_db, verdict, view = await run_db(
            lambda s: _load_completed_view(s, telegram_id, request_number), db=_db,
        )
        if verdict == "no_request":
            await callback.answer(get_text("request_acceptance.handlers.request_not_found", language=language), show_alert=True)
            return
        if verdict == "no_user":
            await callback.answer(get_text("request_acceptance.handlers.user_not_found", language=language), show_alert=True)
            return
        if verdict == "forbidden":
            await callback.answer(get_text("request_acceptance.handlers.not_your_request", language=language), show_alert=True)
            return

        lang = lang_db

        # Формируем информацию о заявке
        text = f"📋 <b>{get_text('request_acceptance.handlers.request_title', language=lang)} #{view.request_number}</b>\n\n"
        text += f"📂 {get_text('request_acceptance.handlers.category', language=lang)}: {view.category}\n"
        text += f"📍 {get_text('request_acceptance.handlers.address', language=lang)}: {view.address}\n"
        text += f"📝 {get_text('request_acceptance.handlers.description', language=lang)}: {view.description}\n\n"

        text += f"✅ <b>{get_text('request_acceptance.handlers.completion_report', language=lang)}:</b>\n"
        if view.completion_report:
            text += f"{view.completion_report}\n\n"
        else:
            text += get_text("request_acceptance.handlers.no_report", language=lang) + "\n\n"

        # Проверяем наличие медиа
        completion_media = view.completion_media
        if len(completion_media) > 0:
            text += get_text("request_acceptance.handlers.media_attached", language=lang).format(count=len(completion_media)) + "\n"
            text += get_text("request_acceptance.handlers.press_to_view_media", language=lang) + "\n\n"

        text += get_text("request_acceptance.handlers.review_and_decide", language=lang)

        # Кнопки действий
        keyboard = get_applicant_completed_request_actions_keyboard(request_number)

        # Добавляем кнопку для просмотра медиа если есть
        if len(completion_media) > 0:
            rows = list(keyboard.inline_keyboard)
            rows.insert(0, [InlineKeyboardButton(
                text=get_text("request_acceptance.handlers.btn_view_media", language=lang),
                callback_data=f"view_completion_media_{request_number}"
            )])
            keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

        logger.info(f"Показаны детали выполненной заявки {request_number} пользователю {telegram_id}")

    except Exception as e:
        logger.error(f"Ошибка просмотра выполненной заявки: {e}")
        await callback.answer(get_text("request_acceptance.handlers.error_occurred", language=language), show_alert=True)


@router.callback_query(F.data.startswith("view_completion_media_"))
async def view_completion_media(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Просмотр медиафайлов выполненной заявки"""
    try:
        from aiogram.types import InputMediaPhoto, InputMediaDocument

        request_number = callback.data.replace("view_completion_media_", "")

        verdict, request_number_display, completion_media = await run_db(
            lambda s: _load_completion_media(s, callback.from_user.id, request_number), db=_db,
        )
        if verdict == "no_request":
            await callback.answer(get_text("request_acceptance.handlers.request_not_found", language=language), show_alert=True)
            return
        if verdict == "no_user":
            await callback.answer(get_text("request_acceptance.handlers.user_not_found", language=language), show_alert=True)
            return
        if verdict == "forbidden":
            await callback.answer(get_text("request_acceptance.handlers.not_your_request", language=language), show_alert=True)
            return

        if not completion_media:
            await callback.answer(get_text("request_acceptance.handlers.media_not_found", language=language), show_alert=True)
            return

        # AUD3-37: отправка медиа — после закрытия сессии (раньше media-group
        # уходила при открытом session_scope).
        lang = language
        await callback.message.answer(
            get_text("request_acceptance.handlers.media_files_title", language=lang).format(request_number=request_number_display),
            parse_mode="HTML"
        )

        # Отправляем медиафайлы
        if len(completion_media) > 1:
            media_group = []
            for idx, file_id in enumerate(completion_media):
                try:
                    if idx == 0:
                        media_group.append(InputMediaPhoto(
                            media=file_id,
                            caption=get_text("request_acceptance.handlers.media_photo_caption", language=lang).format(
                                index=idx + 1, total=len(completion_media)
                            )
                        ))
                    else:
                        media_group.append(InputMediaPhoto(media=file_id))
                except Exception:
                    if idx == 0:
                        media_group.append(InputMediaDocument(
                            media=file_id,
                            caption=get_text("request_acceptance.handlers.media_file_caption", language=lang).format(
                                index=idx + 1, total=len(completion_media)
                            )
                        ))
                    else:
                        media_group.append(InputMediaDocument(media=file_id))

            if media_group:
                await callback.message.answer_media_group(media=media_group)
        else:
            try:
                await callback.message.answer_photo(photo=completion_media[0])
            except Exception:
                try:
                    await callback.message.answer_document(document=completion_media[0])
                except Exception as e:
                    logger.error(f"Ошибка отправки медиафайла: {e}")
                    await callback.message.answer(get_text("request_acceptance.handlers.media_send_failed", language=lang))

        await callback.answer(get_text("request_acceptance.handlers.media_sent", language=lang))

        logger.info(f"Отправлены медиафайлы завершения заявки {request_number}")

    except Exception as e:
        logger.error(f"Ошибка просмотра медиафайлов завершения: {e}")
        await callback.answer(get_text("request_acceptance.handlers.error_occurred", language=language), show_alert=True)


@router.callback_query(F.data.startswith("accept_request_"))
async def accept_request(callback: CallbackQuery, language: str = "ru"):
    """Принятие заявки заявителем - запрос оценки"""
    try:
        request_number = callback.data.replace("accept_request_", "")

        # Показываем клавиатуру с оценками
        keyboard = get_rating_keyboard(request_number)

        lang = language
        await callback.message.edit_text(
            get_text("request_acceptance.handlers.rate_request", language=lang),
            reply_markup=keyboard,
            parse_mode="HTML"
        )

        logger.info(f"Запрошена оценка для заявки {request_number}")

    except Exception as e:
        logger.error(f"Ошибка запроса оценки: {e}")
        lang = language
        await callback.answer(get_text("request_acceptance.handlers.error_occurred", language=lang), show_alert=True)


@router.callback_query(F.data.startswith("rate_"))
async def save_rating(callback: CallbackQuery, language: str = "ru", *, _db=None):
    """Сохранение оценки и принятие заявки"""
    try:
        telegram_id = callback.from_user.id

        # Парсим данные: rate_251013-001_5
        parts = callback.data.replace("rate_", "").split("_")
        request_number = parts[0]
        # SEC: оценка приходит из callback_data — клиент может прислать любое
        # значение мимо кнопок 1–5. Валидируем тип и диапазон до записи в БД.
        try:
            rating_value = int(parts[1])
        except (IndexError, ValueError):
            await callback.answer(get_text("request_acceptance.handlers.error_occurred", language=language), show_alert=True)
            return
        if not (1 <= rating_value <= 5):
            await callback.answer(get_text("request_acceptance.handlers.error_occurred", language=language), show_alert=True)
            return

        user_id = await run_db(lambda s: _user_id_by_tg(s, telegram_id), db=_db)
        if user_id is None:
            await callback.answer(get_text("request_acceptance.handlers.user_not_found", language=language), show_alert=True)
            return

        # Канонический переход (PR2a-3): APPLICANT_ACCEPT (Исполнено→Принято)
        # через единый layer. run_command сам грузит под FOR UPDATE, грузит
        # ActorContext (вкл. одобренное соседство), авторизует (owner|сосед),
        # проверяет state и создаёт Rating + audit + outbox в одной tx.
        # AUD3-37: run_command_sync открывает СВОЮ сессию из SessionLocal и
        # весь синхронный — уводим его в поток целиком.
        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.services.workflow_runner import (
            run_command_sync, RequestNotFound)
        from uk_management_bot.utils.request_workflow import (
            Action, ActionCommand, PrincipalRef,
            NotAuthorized, InvalidTransition, RepeatRejected, RepeatConflict,
            WorkflowError)
        lang = language
        try:
            outcome = await asyncio.to_thread(
                run_command_sync,
                SessionLocal, request_number,
                PrincipalRef(kind="user", user_id=user_id, source="telegram"),
                ActionCommand(callback.id, Action.APPLICANT_ACCEPT,
                              {"rating": rating_value}),
            )
        except RequestNotFound:
            await callback.answer(get_text("request_acceptance.handlers.request_not_found", language=lang), show_alert=True)
            return
        except NotAuthorized:
            await callback.answer(get_text("request_acceptance.handlers.not_your_request", language=lang), show_alert=True)
            return
        except (InvalidTransition, RepeatRejected, RepeatConflict):
            await callback.answer(get_text("request_acceptance.handlers.not_awaiting_acceptance", language=lang), show_alert=True)
            return
        except WorkflowError as e:
            logger.error(f"APPLICANT_ACCEPT отклонён для {request_number}: {e}")
            await callback.answer(get_text("request_acceptance.handlers.error_saving_rating", language=lang), show_alert=True)
            return

        # Best-effort post-commit (PR0 Р7): fetch/render в потоке, отправка тут.
        # APPLICANT_ACCEPT в адресной матрице осознанно отсутствует (житель
        # принял сам); канал по-прежнему видит смену статуса.
        # Переход УЖЕ закоммичен — любой сбой уведомлений (сбор ИЛИ отправка)
        # не имеет права превратиться в ложную ошибку пользователю (находка
        # ревью B3: старые dispatch/notify_channel глотали свои исключения).
        try:
            messages, channel_text = await run_db(
                lambda s: _collect_status_change_notifications(
                    s, request_number, outcome, outcome.public_status), db=_db,
            )
            await send_notify_messages(callback.bot, messages)
            await send_channel_status_text(callback.bot, channel_text, request_number)
        except Exception as e:
            logger.warning(f"Post-commit уведомления по заявке {request_number} не отправлены: {e}")

        # Формируем текст с звёздами
        stars = "⭐" * rating_value

        await callback.message.edit_text(
            get_text("request_acceptance.handlers.thanks_for_rating", language=lang).format(
                stars=stars,
                rating=rating_value,
                request_number=request_number
            ),
            parse_mode="HTML"
        )

        logger.info(f"Заявка {request_number} принята с оценкой {rating_value} пользователем {user_id}")

    except Exception as e:
        logger.error(f"Ошибка сохранения оценки: {e}")
        await callback.answer(get_text("request_acceptance.handlers.error_saving_rating", language=language), show_alert=True)


@router.callback_query(F.data.startswith("return_request_"))
async def return_request(callback: CallbackQuery, state: FSMContext, language: str = "ru"):
    """Возврат заявки заявителем - запрос причины"""
    try:
        request_number = callback.data.replace("return_request_", "")

        await state.update_data(request_number=request_number)
        await state.set_state(ApplicantAcceptanceStates.awaiting_return_reason)

        lang = language
        await callback.message.edit_text(
            get_text("request_acceptance.handlers.return_request_prompt", language=lang),
            parse_mode="HTML"
        )

        logger.info(f"Запрошена причина возврата заявки {request_number}")

    except Exception as e:
        logger.error(f"Ошибка запроса причины возврата: {e}")
        lang = language
        await callback.answer(get_text("request_acceptance.handlers.error_occurred", language=lang), show_alert=True)


@router.message(ApplicantAcceptanceStates.awaiting_return_reason)
async def save_return_reason(message: Message, state: FSMContext, language: str = "ru"):
    """Сохранение причины возврата и запрос медиа"""
    try:
        data = await state.get_data()
        request_number = data.get('request_number')

        if not request_number:
            lang = language
            await message.answer(get_text("request_acceptance.handlers.request_not_found", language=lang))
            await state.clear()
            return

        # Сохраняем причину в state
        await state.update_data(return_reason=message.text)

        # Переходим к запросу медиа
        await state.set_state(ApplicantAcceptanceStates.awaiting_return_media)

        keyboard = get_skip_media_keyboard()

        lang = language
        await message.answer(
            get_text("request_acceptance.handlers.attach_media_prompt", language=lang),
            reply_markup=keyboard,
            parse_mode="HTML"
        )

        logger.info(f"Сохранена причина возврата заявки {request_number}")

    except Exception as e:
        logger.error(f"Ошибка сохранения причины возврата: {e}")
        lang = language
        await message.answer(get_text("request_acceptance.handlers.error_occurred", language=lang))
        await state.clear()


@router.callback_query(F.data == "skip_return_media")
async def skip_return_media(callback: CallbackQuery, state: FSMContext, language: str = "ru", *, _db=None):
    """Пропуск медиа и завершение возврата заявки"""
    try:
        await process_return_request(callback.from_user.id, state, callback.message, _db=_db)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при пропуске медиа: {e}")
        lang = language
        await callback.answer(get_text("request_acceptance.handlers.error_occurred", language=lang), show_alert=True)


@router.message(ApplicantAcceptanceStates.awaiting_return_media, F.photo | F.video)
async def save_return_media(message: Message, state: FSMContext, language: str = "ru"):
    """Сохранение медиа при возврате заявки"""
    try:
        # Получаем file_id
        file_id = None
        if message.photo:
            file_id = message.photo[-1].file_id
        elif message.video:
            file_id = message.video.file_id

        if file_id:
            # Сохраняем file_id в state
            data = await state.get_data()
            return_media = data.get('return_media', [])
            return_media.append(file_id)
            await state.update_data(return_media=return_media)

            lang = language
            await message.answer(
                get_text("request_acceptance.handlers.media_saved", language=lang),
                reply_markup=get_skip_media_keyboard()
            )
        else:
            lang = language
            await message.answer(get_text("request_acceptance.handlers.media_save_failed", language=lang))

    except Exception as e:
        logger.error(f"Ошибка сохранения медиа возврата: {e}")
        lang = language
        await message.answer(get_text("request_acceptance.handlers.error_saving_media", language=lang))


async def process_return_request(telegram_id: int, state: FSMContext, message_obj=None, *, _db=None):
    """Обработка возврата заявки"""
    try:
        data = await state.get_data()
        request_number = data.get('request_number')
        return_reason = data.get('return_reason')
        return_media = data.get('return_media', [])

        user_id = await run_db(lambda s: _user_id_by_tg(s, telegram_id), db=_db)
        if user_id is None:
            if message_obj:
                await message_obj.answer(get_text("request_acceptance.handlers.user_not_found", language="ru"))
            return

        # Канонический возврат (PR2a-3): APPLICANT_RETURN (Исполнено→Возвращена,
        # legacy-кодировка Исполнено+is_returned). run_command грузит под
        # FOR UPDATE, авторизует (ТОЛЬКО owner), проверяет state и пишет
        # is_returned/return_*/manager_confirmed + audit в одной tx.
        # AUD3-37: своя сессия runner'а — весь вызов в поток.
        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.services.workflow_runner import (
            run_command_sync, RequestNotFound)
        from uk_management_bot.utils.request_workflow import (
            Action, ActionCommand, PrincipalRef,
            NotAuthorized, InvalidTransition, RepeatRejected, RepeatConflict,
            WorkflowError)
        try:
            outcome = await asyncio.to_thread(
                run_command_sync,
                SessionLocal, request_number,
                PrincipalRef(kind="user", user_id=user_id, source="telegram"),
                ActionCommand(
                    f"return-{user_id}-{request_number}",
                    Action.APPLICANT_RETURN,
                    {"return_reason": return_reason, "return_media": return_media},
                ),
            )
        except RequestNotFound:
            if message_obj:
                await message_obj.answer(get_text("request_acceptance.handlers.request_not_found", language="ru"))
            return
        except NotAuthorized:
            if message_obj:
                await message_obj.answer(get_text("request_acceptance.handlers.not_your_request", language="ru"))
            return
        except (InvalidTransition, RepeatRejected, RepeatConflict):
            if message_obj:
                await message_obj.answer(get_text("request_acceptance.handlers.not_awaiting_acceptance", language="ru"))
            return
        except WorkflowError as e:
            logger.error(f"APPLICANT_RETURN отклонён для {request_number}: {e}")
            if message_obj:
                await message_obj.answer(get_text("request_acceptance.handlers.error_returning_request", language="ru"))
            return

        # Best-effort post-commit (PR0 Р7): fetch/render в потоке (заявка
        # перечитывается свежей), отправки — тут.
        # APPLICANT_RETURN: исполнителю — по матрице интентов («возвращена
        # в работу», AUD6-P1-6 — тот же текст, что при возврате менеджером);
        # каналу — прежняя кастомная подпись; менеджерам — прямые детали.
        # Возврат УЖЕ закоммичен — сбой уведомлений не должен ни показать
        # ложную ошибку, ни помешать state.clear() ниже (находка ревью B3).
        try:
            messages, channel_text, manager_ids, manager_text = await run_db(
                lambda s: _collect_return_notifications(s, request_number, outcome, return_reason), db=_db,
            )
            await send_notify_messages(message_obj.bot, messages)
            await send_channel_status_text(message_obj.bot, channel_text, request_number)

            if manager_text is not None:
                bot = message_obj.bot
                for manager_tg_id in manager_ids:
                    try:
                        await bot.send_message(manager_tg_id, manager_text)
                        logger.info(f"✅ Уведомление о возврате заявки {request_number} отправлено менеджеру {manager_tg_id}")
                    except Exception as e:
                        logger.warning(f"Не удалось отправить уведомление менеджеру {manager_tg_id}: {e}")
        except Exception as e:
            logger.warning(f"Post-commit уведомления по возврату {request_number} не отправлены: {e}")

        # Очищаем state
        await state.clear()

        if message_obj:
            await message_obj.answer(
                get_text("request_acceptance.handlers.request_returned_success", language="ru").format(
                    request_number=request_number
                ),
                parse_mode="HTML"
            )

        logger.info(f"Заявка {request_number} возвращена пользователем {user_id}")

    except Exception as e:
        logger.error(f"Ошибка обработки возврата заявки: {e}")
        if message_obj:
            await message_obj.answer(get_text("request_acceptance.handlers.error_returning_request", language="ru"))


@router.callback_query(F.data == "back_to_pending_acceptance")
async def back_to_pending_acceptance(callback: CallbackQuery, language: str = "ru"):
    """Возврат к списку ожидающих приёмки заявок"""
    try:
        lang = language
        await callback.message.answer(get_text("request_acceptance.handlers.pending_acceptance_title", language=lang))
        # Просто показываем сообщение, пользователь может снова нажать на кнопку
        await callback.message.edit_text(
            get_text("request_acceptance.handlers.press_pending_button", language=lang)
        )
    except Exception as e:
        logger.error(f"Ошибка возврата к списку: {e}")
        lang = language
        await callback.answer(get_text("request_acceptance.handlers.error_occurred", language=lang), show_alert=True)
