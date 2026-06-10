"""
Обработчики для процесса приёмки выполненных заявок заявителем

Включает:
- Просмотр списка заявок, ожидающих приёмки
- Просмотр деталей выполненной заявки
- Принятие заявки с оценкой (1-5 звёзд)
- Возврат заявки с причиной и медиа
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session
from datetime import datetime

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.rating import Rating
from uk_management_bot.keyboards.admin import (
    get_applicant_completed_request_actions_keyboard,
    get_rating_keyboard,
    get_skip_media_keyboard,
)
from uk_management_bot.states.request_acceptance import ApplicantAcceptanceStates
from uk_management_bot.database.session import get_db
from uk_management_bot.services.notification_service import async_notify_request_status_changed
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_EXECUTED, REQUEST_STATUS_COMPLETED, REQUEST_STATUS_APPROVED,
)
from uk_management_bot.utils.workflow_predicates import (
    awaiting_applicant_clause,
    can_accept,
    can_return,
    get_approved_apartment_ids,
    is_awaiting_applicant,
)

import logging

router = Router()
logger = logging.getLogger(__name__)

# Single Source of Truth for button texts - TASK 17
from uk_management_bot.utils.button_texts import get_acceptance_texts
from uk_management_bot.utils.helpers import get_text

# Константа для фильтрации сообщений "Ожидают приёмки"
ACCEPTANCE_TEXTS = get_acceptance_texts()


@router.message(F.text.in_(ACCEPTANCE_TEXTS))
async def show_pending_acceptance_requests(message: Message, db: Session = None):
    """Показать список заявок, ожидающих приёмки заявителем"""
    own_db = db is None  # ARCH-013: закрываем только сессию, которую открыли сами (не middleware)
    try:
        telegram_id = message.from_user.id

        if not db:
            db = next(get_db())

        # Получаем язык пользователя из базы данных
        from uk_management_bot.utils.helpers import get_user_language
        lang = get_user_language(telegram_id, db)

        # Получаем пользователя
        user = db.query(User).filter(User.telegram_id == telegram_id).first()

        if not user:
            await message.answer(get_text("common.user_not_found", language=lang))
            return

        # Получаем заявки, ожидающие приёмки:
        # 1. Свои заявки (user_id == user.id)
        # 2. Заявки соседей по квартире (apartment_id в квартирах пользователя)
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
        # Получаем язык для сообщения об ошибке (переиспользуем db, не открываем вторую сессию)
        try:
            lang = get_user_language(message.from_user.id, db) if (db and hasattr(message, 'from_user')) else 'ru'
        except Exception:
            lang = 'ru'
        await message.answer(get_text("requests.error_loading_requests", language=lang))
    finally:
        if own_db and db:
            db.close()


@router.callback_query(F.data.startswith("view_completed_"))
async def view_completed_request(callback: CallbackQuery, db: Session = None, language: str = "ru"):
    """Просмотр деталей выполненной заявки заявителем"""
    own_db = db is None  # ARCH-013: закрываем только свою сессию
    try:
        telegram_id = callback.from_user.id
        request_number = callback.data.replace("view_completed_", "")

        if not db:
            db = next(get_db())

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            lang = language
            await callback.answer(get_text("request_acceptance.handlers.request_not_found", language=lang), show_alert=True)
            return

        # HF-0: смотреть может владелец или одобренный сосед (та же семантика,
        # что у списка приёмки — иначе сосед из списка получает отказ).
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            lang = language
            await callback.answer(get_text("request_acceptance.handlers.user_not_found", language=lang), show_alert=True)
            return
        if not can_accept(request, user, get_approved_apartment_ids(db, user.id)):
            lang = language
            await callback.answer(get_text("request_acceptance.handlers.not_your_request", language=lang), show_alert=True)
            return

        # Получаем язык пользователя
        from uk_management_bot.utils.helpers import get_user_language
        lang = get_user_language(telegram_id, db)

        # Формируем информацию о заявке
        text = f"📋 <b>{get_text('request_acceptance.handlers.request_title', language=lang)} #{request.request_number}</b>\n\n"
        text += f"📂 {get_text('request_acceptance.handlers.category', language=lang)}: {request.category}\n"
        text += f"📍 {get_text('request_acceptance.handlers.address', language=lang)}: {request.address}\n"
        text += f"📝 {get_text('request_acceptance.handlers.description', language=lang)}: {request.description}\n\n"

        text += f"✅ <b>{get_text('request_acceptance.handlers.completion_report', language=lang)}:</b>\n"
        if request.completion_report:
            text += f"{request.completion_report}\n\n"
        else:
            text += get_text("request_acceptance.handlers.no_report", language=lang) + "\n\n"

        # Проверяем наличие медиа
        completion_media = request.completion_media if request.completion_media else []
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
        lang = language
        await callback.answer(get_text("request_acceptance.handlers.error_occurred", language=lang), show_alert=True)
    finally:
        if own_db and db:
            db.close()


@router.callback_query(F.data.startswith("view_completion_media_"))
async def view_completion_media(callback: CallbackQuery, db: Session = None, language: str = "ru"):
    """Просмотр медиафайлов выполненной заявки"""
    own_db = db is None  # ARCH-013: закрываем только свою сессию
    try:
        from aiogram.types import InputMediaPhoto, InputMediaDocument

        request_number = callback.data.replace("view_completion_media_", "")

        if not db:
            db = next(get_db())

        request = db.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            lang = language
            await callback.answer(get_text("request_acceptance.handlers.request_not_found", language=lang), show_alert=True)
            return

        # SEC: медиа выполненной заявки = потенциальный PII (интерьер квартиры,
        # данные жителя). Доступ — только владелец или одобренный сосед (та же
        # семантика, что view_completed_request); иначе любой по request_number
        # вытянет чужие медиафайлы.
        user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
        if not user:
            await callback.answer(get_text("request_acceptance.handlers.user_not_found", language=language), show_alert=True)
            return
        if not can_accept(request, user, get_approved_apartment_ids(db, user.id)):
            await callback.answer(get_text("request_acceptance.handlers.not_your_request", language=language), show_alert=True)
            return

        completion_media = request.completion_media if request.completion_media else []

        if not completion_media:
            lang = language
            await callback.answer(get_text("request_acceptance.handlers.media_not_found", language=lang), show_alert=True)
            return

        lang = language
        await callback.message.answer(
            get_text("request_acceptance.handlers.media_files_title", language=lang).format(request_number=request.request_number),
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
                except:
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
            except:
                try:
                    await callback.message.answer_document(document=completion_media[0])
                except Exception as e:
                    logger.error(f"Ошибка отправки медиафайла: {e}")
                    await callback.message.answer(get_text("request_acceptance.handlers.media_send_failed", language=lang))

        await callback.answer(get_text("request_acceptance.handlers.media_sent", language=lang))

        logger.info(f"Отправлены медиафайлы завершения заявки {request_number}")

    except Exception as e:
        logger.error(f"Ошибка просмотра медиафайлов завершения: {e}")
        lang = language
        await callback.answer(get_text("request_acceptance.handlers.error_occurred", language=lang), show_alert=True)
    finally:
        if own_db and db:
            db.close()


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
async def save_rating(callback: CallbackQuery, db: Session = None, language: str = "ru"):
    """Сохранение оценки и принятие заявки"""
    own_db = db is None  # ARCH-013: закрываем только свою сессию
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

        if not db:
            db = next(get_db())

        # Получаем пользователя
        user = db.query(User).filter(User.telegram_id == telegram_id).first()

        if not user:
            lang = language
            await callback.answer(get_text("request_acceptance.handlers.user_not_found", language=lang), show_alert=True)
            return

        # Канонический переход (PR2a-3): APPLICANT_ACCEPT (Исполнено→Принято)
        # через единый layer. run_command сам грузит под FOR UPDATE, грузит
        # ActorContext (вкл. одобренное соседство), авторизует (owner|сосед),
        # проверяет state и создаёт Rating + audit + outbox в одной tx.
        # HF-0-guard'ы (can_accept / is_awaiting_applicant / FOR UPDATE) теперь
        # внутри run_command; здесь — только маппинг ошибок на сообщения.
        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.services.workflow_runner import (
            run_command_sync, RequestNotFound)
        from uk_management_bot.utils.request_workflow import (
            Action, ActionCommand, PrincipalRef,
            NotAuthorized, InvalidTransition, RepeatRejected, RepeatConflict,
            WorkflowError)
        lang = language
        try:
            outcome = run_command_sync(
                SessionLocal, request_number,
                PrincipalRef(kind="user", user_id=user.id, source="telegram"),
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

        # Best-effort post-commit (PR0 Р7): уведомление + правка сообщения.
        request = db.query(Request).filter(Request.request_number == request_number).first()
        try:
            bot = callback.bot
            await async_notify_request_status_changed(bot, db, request, outcome.old_status, outcome.public_status)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления через сервис: {e}")

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

        logger.info(f"Заявка {request_number} принята с оценкой {rating_value} пользователем {user.id}")

    except Exception as e:
        logger.error(f"Ошибка сохранения оценки: {e}")
        if db:
            db.rollback()
        lang = language
        await callback.answer(get_text("request_acceptance.handlers.error_saving_rating", language=lang), show_alert=True)
    finally:
        if own_db and db:
            db.close()


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
async def save_return_reason(message: Message, state: FSMContext, db: Session = None, language: str = "ru"):
    """Сохранение причины возврата и запрос медиа"""
    try:
        telegram_id = message.from_user.id
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
async def skip_return_media(callback: CallbackQuery, state: FSMContext, db: Session = None, language: str = "ru"):
    """Пропуск медиа и завершение возврата заявки"""
    try:
        await process_return_request(callback.from_user.id, state, db, callback.message)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при пропуске медиа: {e}")
        lang = language
        await callback.answer(get_text("request_acceptance.handlers.error_occurred", language=lang), show_alert=True)


@router.message(ApplicantAcceptanceStates.awaiting_return_media, F.photo | F.video)
async def save_return_media(message: Message, state: FSMContext, db: Session = None, language: str = "ru"):
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


async def process_return_request(telegram_id: int, state: FSMContext, db: Session = None, message_obj=None):
    """Обработка возврата заявки"""
    own_db = db is None  # ARCH-013: закрываем только свою сессию
    try:
        data = await state.get_data()
        request_number = data.get('request_number')
        return_reason = data.get('return_reason')
        return_media = data.get('return_media', [])

        if not db:
            db = next(get_db())

        # Получаем пользователя
        user = db.query(User).filter(User.telegram_id == telegram_id).first()

        if not user:
            if message_obj:
                await message_obj.answer(get_text("request_acceptance.handlers.user_not_found", language="ru"))
            return

        # Канонический возврат (PR2a-3): APPLICANT_RETURN (Исполнено→Возвращена,
        # legacy-кодировка Исполнено+is_returned). run_command грузит под
        # FOR UPDATE, авторизует (ТОЛЬКО owner), проверяет state и пишет
        # is_returned/return_*/manager_confirmed + audit в одной tx. HF-0-guard'ы
        # (can_return / is_awaiting_applicant / FOR UPDATE) теперь внутри runner.
        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.services.workflow_runner import (
            run_command_sync, RequestNotFound)
        from uk_management_bot.utils.request_workflow import (
            Action, ActionCommand, PrincipalRef,
            NotAuthorized, InvalidTransition, RepeatRejected, RepeatConflict,
            WorkflowError)
        try:
            outcome = run_command_sync(
                SessionLocal, request_number,
                PrincipalRef(kind="user", user_id=user.id, source="telegram"),
                ActionCommand(
                    f"return-{user.id}-{request_number}",
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

        # Best-effort post-commit (PR0 Р7): перечитываем заявку свежей.
        request = db.query(Request).filter(Request.request_number == request_number).first()

        # Уведомление через сервис (отправит исполнителю и в канал)
        try:
            bot = message_obj.bot
            await async_notify_request_status_changed(bot, db, request, outcome.old_status, "Исполнено (возвращена)")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления через сервис: {e}")

        # Дополнительно уведомляем менеджеров напрямую с деталями
        try:
            import json
            bot = message_obj.bot

            # Получаем всех менеджеров из базы
            managers = db.query(User).filter(
                User.roles.contains('"manager"'),
                User.status == "approved"
            ).all()

            notification_text = get_text("request_acceptance.handlers.manager_return_notification", language="ru").format(
                request_number=request.format_number_for_display(),
                category=request.category,
                return_reason=return_reason
            )

            # Отправляем уведомления всем менеджерам
            for manager in managers:
                if manager.telegram_id:
                    try:
                        await bot.send_message(manager.telegram_id, notification_text)
                        logger.info(f"✅ Уведомление о возврате заявки {request.request_number} отправлено менеджеру {manager.telegram_id}")
                    except Exception as e:
                        logger.warning(f"Не удалось отправить уведомление менеджеру {manager.telegram_id}: {e}")
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомлений менеджерам: {e}")

        # Очищаем state
        await state.clear()

        if message_obj:
            await message_obj.answer(
                get_text("request_acceptance.handlers.request_returned_success", language="ru").format(
                    request_number=request_number
                ),
                parse_mode="HTML"
            )

        logger.info(f"Заявка {request_number} возвращена пользователем {user.id}")

    except Exception as e:
        logger.error(f"Ошибка обработки возврата заявки: {e}")
        if db:
            db.rollback()
        if message_obj:
            await message_obj.answer(get_text("request_acceptance.handlers.error_returning_request", language="ru"))
    finally:
        if own_db and db:
            db.close()


@router.callback_query(F.data == "back_to_pending_acceptance")
async def back_to_pending_acceptance(callback: CallbackQuery, language: str = "ru"):
    """Возврат к списку ожидающих приёмки заявок"""
    try:
        lang = language
        await callback.message.answer(get_text("request_acceptance.handlers.pending_acceptance_title", language=lang))
        # Trigger the show_pending_acceptance_requests handler
        from aiogram.types import Message as TgMessage
        fake_msg = type('obj', (object,), {
            'from_user': callback.from_user,
            'answer': callback.message.answer,
            'text': get_text("request_acceptance.handlers.pending_acceptance_title", language=lang)
        })()
        # Просто показываем сообщение, пользователь может снова нажать на кнопку
        await callback.message.edit_text(
            get_text("request_acceptance.handlers.press_pending_button", language=lang)
        )
    except Exception as e:
        logger.error(f"Ошибка возврата к списку: {e}")
        lang = language
        await callback.answer(get_text("request_acceptance.handlers.error_occurred", language=lang), show_alert=True)
