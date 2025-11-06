from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy.orm import Session
import re
import logging

from uk_management_bot.database.session import get_db
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.services.notification_service import NotificationService
from uk_management_bot.utils.helpers import get_text, get_user_language
from datetime import datetime

router = Router()
logger = logging.getLogger(__name__)

class ReplyStates(StatesGroup):
    waiting_for_reply_text = State()

@router.message(F.text.startswith("/reply_"))
async def handle_reply_command(message: Message, state: FSMContext, db: Session):
    """Обработка команды ответа на уточнение"""
    lang = get_user_language(message.from_user.id, db)

    try:
        # Извлекаем ID заявки из команды
        command_parts = message.text.split("_")
        if len(command_parts) != 2:
            await message.answer(get_text("clarification.invalid_command_format", language=lang))
            return

        request_number = command_parts[1]

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await message.answer(get_text("requests.request_not_found", language=lang))
            return

        # Проверяем, что пользователь является заявителем
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.id != request.user_id:
            await message.answer(get_text("clarification.no_permission_to_reply", language=lang))
            return

        # Проверяем, что заявка в статусе уточнения
        if request.status != "Уточнение":
            await message.answer(get_text("clarification.not_in_clarification_status", language=lang))
            return

        # Сохраняем ID заявки в состоянии
        await state.update_data(request_number=request_number)

        # Запрашиваем текст ответа
        await message.answer(
            get_text("clarification.enter_reply_prompt", language=lang).format(
                request_number=request_number,
                category=request.category,
                address=request.address
            ),
            reply_markup=None
        )

        # Устанавливаем состояние ожидания ответа
        await state.set_state(ReplyStates.waiting_for_reply_text)

        logger.info(f"Запрошен ответ на уточнение для заявки {request_number} от пользователя {message.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка обработки команды ответа: {e}")
        await message.answer(get_text("common.error", language=lang))

@router.message(ReplyStates.waiting_for_reply_text)
async def handle_reply_text(message: Message, state: FSMContext, db: Session):
    """Обработка текста ответа от заявителя"""
    lang = get_user_language(message.from_user.id, db)

    try:
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")

        if not request_number:
            await message.answer(get_text("clarification.error_request_not_found", language=lang))
            await state.clear()
            return

        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await message.answer(get_text("requests.request_not_found", language=lang))
            await state.clear()
            return

        # Получаем пользователя
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.id != request.user_id:
            await message.answer(get_text("clarification.no_permission_to_reply", language=lang))
            await state.clear()
            return

        # Получаем текст ответа
        reply_text = message.text.strip()

        if not reply_text:
            await message.answer(get_text("clarification.reply_text_empty", language=lang))
            return

        # Формируем имя заявителя
        applicant_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        if not applicant_name:
            applicant_label = get_text("clarification.applicant_label", language=lang)
            applicant_name = f"{applicant_label} {user.telegram_id}"

        # Добавляем ответ в примечания заявки
        timestamp = datetime.now().strftime('%d.%m.%Y %H:%M')
        reply_label = get_text("clarification.reply_label", language=lang)
        new_note = f"\n\n--- {reply_label} {timestamp} ---\n"
        new_note += f"👤 {applicant_name}:\n"
        new_note += f"{reply_text}\n"

        # Обновляем примечания
        if request.notes:
            request.notes += new_note
        else:
            request.notes = new_note

        request.updated_at = datetime.now()
        db.commit()

        # Отправляем уведомление менеджерам
        try:
            notification_service = NotificationService(db)

            # Находим всех менеджеров
            managers = db.query(User).filter(
                User.roles.contains('manager') | User.roles.contains('admin')
            ).all()

            # Send notification in each manager's language
            for manager in managers:
                try:
                    manager_lang = get_user_language(manager.telegram_id, db)
                    notification_text = get_text("clarification.manager_notification", language=manager_lang).format(
                        request_number=request.request_number,
                        category=request.category,
                        address=request.address,
                        reply_text=reply_text
                    )

                    notification_service.send_notification_to_user(
                        user_id=manager.id,
                        message=notification_text
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления менеджеру {manager.id}: {e}")

            logger.info(f"Уведомления об ответе отправлены менеджерам")

        except Exception as e:
            logger.error(f"Ошибка отправки уведомлений менеджерам: {e}")

        # Подтверждаем заявителю
        reply_preview = reply_text[:100] + ('...' if len(reply_text) > 100 else '')
        await message.answer(
            get_text("clarification.reply_sent_confirmation", language=lang).format(
                request_number=request_number,
                reply_preview=reply_preview
            )
        )

        # Очищаем состояние
        await state.clear()

        logger.info(f"Ответ на уточнение по заявке {request_number} добавлен пользователем {message.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка обработки ответа на уточнение: {e}")
        await message.answer(get_text("clarification.error_sending_reply", language=lang))
        await state.clear()
