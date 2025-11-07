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
from uk_management_bot.utils.constants import REQUEST_STATUS_APPROVED

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

        # Получаем заявки пользователя со статусом "Выполнена" (подтверждено менеджером, ждёт приёмки)
        requests = (
            db.query(Request)
            .filter(
                Request.user_id == user.id,
                Request.status == "Выполнена"
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
            address_text = req.address or get_text("requests.address_не_указан", language=lang, fallback="Не указан")
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
        # Получаем язык для сообщения об ошибке
        try:
            if not db:
                db = next(get_db())
            lang = get_user_language(message.from_user.id, db) if hasattr(message, 'from_user') else 'ru'
        except:
            lang = 'ru'
        await message.answer(get_text("requests.error_loading_requests", language=lang))
    finally:
        if db:
            db.close()


@router.callback_query(F.data.startswith("view_completed_"))
async def view_completed_request(callback: CallbackQuery, db: Session = None):
    """Просмотр деталей выполненной заявки заявителем"""
    try:
        telegram_id = callback.from_user.id
        request_number = callback.data.replace("view_completed_", "")

        if not db:
            db = next(get_db())

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Проверяем, что это заявка этого пользователя
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if request.user_id != user.id:
            await callback.answer("Это не ваша заявка", show_alert=True)
            return

        # Формируем информацию о заявке
        text = f"📋 <b>Заявка #{request.request_number}</b>\n\n"
        text += f"📂 Категория: {request.category}\n"
        text += f"📍 Адрес: {request.address}\n"
        text += f"📝 Описание: {request.description}\n\n"

        text += "✅ <b>Отчёт о выполнении:</b>\n"
        if request.completion_report:
            text += f"{request.completion_report}\n\n"
        else:
            text += "Отчёт не предоставлен\n\n"

        # Проверяем наличие медиа
        completion_media = request.completion_media if request.completion_media else []
        if len(completion_media) > 0:
            text += f"📎 Прикреплено медиафайлов: {len(completion_media)}\n"
            text += "Нажмите кнопку ниже для просмотра медиа\n\n"

        text += "Пожалуйста, ознакомьтесь с результатами работы и примите решение."

        # Кнопки действий
        keyboard = get_applicant_completed_request_actions_keyboard(request_number)

        # Добавляем кнопку для просмотра медиа если есть
        if len(completion_media) > 0:
            rows = list(keyboard.inline_keyboard)
            rows.insert(0, [InlineKeyboardButton(
                text="📎 Просмотреть медиа",
                callback_data=f"view_completion_media_{request_number}"
            )])
            keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

        logger.info(f"Показаны детали выполненной заявки {request_number} пользователю {telegram_id}")

    except Exception as e:
        logger.error(f"Ошибка просмотра выполненной заявки: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data.startswith("view_completion_media_"))
async def view_completion_media(callback: CallbackQuery, db: Session = None):
    """Просмотр медиафайлов выполненной заявки"""
    try:
        from aiogram.types import InputMediaPhoto, InputMediaDocument

        request_number = callback.data.replace("view_completion_media_", "")

        if not db:
            db = next(get_db())

        request = db.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        completion_media = request.completion_media if request.completion_media else []

        if not completion_media:
            await callback.answer("Медиафайлы не найдены", show_alert=True)
            return

        await callback.message.answer(
            f"📎 <b>Медиафайлы по заявке #{request.request_number}</b>",
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
                            caption=f"Фото {idx+1}/{len(completion_media)}"
                        ))
                    else:
                        media_group.append(InputMediaPhoto(media=file_id))
                except:
                    if idx == 0:
                        media_group.append(InputMediaDocument(
                            media=file_id,
                            caption=f"Файл {idx+1}/{len(completion_media)}"
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
                    await callback.message.answer("❌ Не удалось отправить медиафайл")

        await callback.answer("✅ Медиафайлы отправлены")

        logger.info(f"Отправлены медиафайлы завершения заявки {request_number}")

    except Exception as e:
        logger.error(f"Ошибка просмотра медиафайлов завершения: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data.startswith("accept_request_"))
async def accept_request(callback: CallbackQuery):
    """Принятие заявки заявителем - запрос оценки"""
    try:
        request_number = callback.data.replace("accept_request_", "")

        # Показываем клавиатуру с оценками
        keyboard = get_rating_keyboard(request_number)

        await callback.message.edit_text(
            "⭐ <b>Оцените выполнение заявки</b>\n\n"
            "Выберите оценку от 1 до 5 звёзд:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

        logger.info(f"Запрошена оценка для заявки {request_number}")

    except Exception as e:
        logger.error(f"Ошибка запроса оценки: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("rate_"))
async def save_rating(callback: CallbackQuery, db: Session = None):
    """Сохранение оценки и принятие заявки"""
    try:
        telegram_id = callback.from_user.id

        # Парсим данные: rate_251013-001_5
        parts = callback.data.replace("rate_", "").split("_")
        request_number = parts[0]
        rating_value = int(parts[1])

        if not db:
            db = next(get_db())

        # Получаем пользователя
        user = db.query(User).filter(User.telegram_id == telegram_id).first()

        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Проверяем, что это заявка этого пользователя
        if request.user_id != user.id:
            await callback.answer("Это не ваша заявка", show_alert=True)
            return

        # Создаём оценку
        rating = Rating(
            request_number=request_number,
            user_id=user.id,
            rating=rating_value
        )
        db.add(rating)

        # Изменяем статус заявки на "Принято"
        old_status = request.status
        request.status = REQUEST_STATUS_APPROVED  # "Принято"
        request.completed_at = datetime.now()

        db.commit()

        # Уведомление через сервис (отправит заявителю, исполнителю и в канал)
        try:
            from aiogram import Bot
            bot = Bot.get_current()
            await async_notify_request_status_changed(bot, db, request, old_status, REQUEST_STATUS_APPROVED)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления через сервис: {e}")

        # Формируем текст с звёздами
        stars = "⭐" * rating_value

        await callback.message.edit_text(
            f"✅ <b>Спасибо за оценку!</b>\n\n"
            f"Ваша оценка: {stars} ({rating_value} {'звезда' if rating_value == 1 else 'звезды' if rating_value < 5 else 'звёзд'})\n\n"
            f"Заявка #{request_number} принята и отправлена в архив.",
            parse_mode="HTML"
        )

        logger.info(f"Заявка {request_number} принята с оценкой {rating_value} пользователем {user.id}")

    except Exception as e:
        logger.error(f"Ошибка сохранения оценки: {e}")
        if db:
            db.rollback()
        await callback.answer("Произошла ошибка при сохранении оценки", show_alert=True)
    finally:
        if db:
            db.close()


@router.callback_query(F.data.startswith("return_request_"))
async def return_request(callback: CallbackQuery, state: FSMContext):
    """Возврат заявки заявителем - запрос причины"""
    try:
        request_number = callback.data.replace("return_request_", "")

        await state.update_data(request_number=request_number)
        await state.set_state(ApplicantAcceptanceStates.awaiting_return_reason)

        await callback.message.edit_text(
            "❌ <b>Возврат заявки</b>\n\n"
            "Опишите, что не устроило в выполнении заявки.\n"
            "Будьте максимально конкретны, чтобы исполнитель понял, что нужно исправить.",
            parse_mode="HTML"
        )

        logger.info(f"Запрошена причина возврата заявки {request_number}")

    except Exception as e:
        logger.error(f"Ошибка запроса причины возврата: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.message(ApplicantAcceptanceStates.awaiting_return_reason)
async def save_return_reason(message: Message, state: FSMContext, db: Session = None):
    """Сохранение причины возврата и запрос медиа"""
    try:
        telegram_id = message.from_user.id
        data = await state.get_data()
        request_number = data.get('request_number')

        if not request_number:
            await message.answer("Ошибка: заявка не найдена")
            await state.clear()
            return

        # Сохраняем причину в state
        await state.update_data(return_reason=message.text)

        # Переходим к запросу медиа
        await state.set_state(ApplicantAcceptanceStates.awaiting_return_media)

        keyboard = get_skip_media_keyboard()

        await message.answer(
            "📎 <b>Прикрепите фото или видео</b>\n\n"
            "Вы можете прикрепить фото или видео, демонстрирующие проблему.\n"
            "Или нажмите 'Пропустить', если медиа не требуется.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

        logger.info(f"Сохранена причина возврата заявки {request_number}")

    except Exception as e:
        logger.error(f"Ошибка сохранения причины возврата: {e}")
        await message.answer("Произошла ошибка")
        await state.clear()


@router.callback_query(F.data == "skip_return_media")
async def skip_return_media(callback: CallbackQuery, state: FSMContext, db: Session = None):
    """Пропуск медиа и завершение возврата заявки"""
    try:
        await process_return_request(callback.from_user.id, state, db, callback.message)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при пропуске медиа: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@router.message(ApplicantAcceptanceStates.awaiting_return_media, F.photo | F.video)
async def save_return_media(message: Message, state: FSMContext, db: Session = None):
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

            await message.answer(
                "✅ Медиа сохранено.\n\n"
                "Можете прикрепить ещё файлы или нажмите 'Пропустить' для завершения.",
                reply_markup=get_skip_media_keyboard()
            )
        else:
            await message.answer("Не удалось сохранить медиа. Попробуйте ещё раз.")

    except Exception as e:
        logger.error(f"Ошибка сохранения медиа возврата: {e}")
        await message.answer("Произошла ошибка при сохранении медиа")


async def process_return_request(telegram_id: int, state: FSMContext, db: Session = None, message_obj=None):
    """Обработка возврата заявки"""
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
                await message_obj.answer("Пользователь не найден")
            return

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()

        if not request:
            if message_obj:
                await message_obj.answer("Заявка не найдена")
            return

        # Устанавливаем флаг возврата
        old_status = request.status
        request.is_returned = True
        request.return_reason = return_reason
        request.return_media = return_media
        request.returned_by = user.id
        request.returned_at = datetime.now()
        request.status = "Исполнено"  # Возвращаем в статус "Исполнено" для повторной проверки менеджером
        request.manager_confirmed = False  # Сбрасываем подтверждение менеджера

        db.commit()

        # Уведомление через сервис (отправит исполнителю и в канал)
        try:
            from aiogram import Bot
            bot = Bot.get_current()
            await async_notify_request_status_changed(bot, db, request, old_status, "Исполнено (возвращена)")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления через сервис: {e}")

        # Дополнительно уведомляем менеджеров напрямую с деталями
        try:
            from aiogram import Bot
            import json
            bot = Bot.get_current()

            # Получаем всех менеджеров из базы
            managers = db.query(User).filter(
                User.roles.contains('"manager"'),
                User.status == "approved"
            ).all()

            notification_text = (
                f"⚠️ <b>Заявка возвращена заявителем!</b>\n\n"
                f"📋 Заявка #{request.format_number_for_display()}\n"
                f"📂 Категория: {request.category}\n\n"
                f"<b>Причина возврата:</b>\n{return_reason}\n\n"
                f"Требуется рассмотрение в разделе 'Исполненные заявки'."
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
                f"✅ <b>Заявка #{request_number} возвращена</b>\n\n"
                f"Ваши замечания отправлены менеджеру.\n"
                f"Заявка будет рассмотрена и исправлена.",
                parse_mode="HTML"
            )

        logger.info(f"Заявка {request_number} возвращена пользователем {user.id}")

    except Exception as e:
        logger.error(f"Ошибка обработки возврата заявки: {e}")
        if db:
            db.rollback()
        if message_obj:
            await message_obj.answer("Произошла ошибка при возврате заявки")
    finally:
        if db:
            db.close()


@router.callback_query(F.data == "back_to_pending_acceptance")
async def back_to_pending_acceptance(callback: CallbackQuery):
    """Возврат к списку ожидающих приёмки заявок"""
    try:
        await callback.message.answer("✅ Ожидают приёмки")
        # Trigger the show_pending_acceptance_requests handler
        from aiogram.types import Message as TgMessage
        fake_msg = type('obj', (object,), {
            'from_user': callback.from_user,
            'answer': callback.message.answer,
            'text': "✅ Ожидают приёмки"
        })()
        # Просто показываем сообщение, пользователь может снова нажать на кнопку
        await callback.message.edit_text(
            "Для просмотра списка заявок нажмите кнопку '✅ Ожидают приёмки' в меню."
        )
    except Exception as e:
        logger.error(f"Ошибка возврата к списку: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)
