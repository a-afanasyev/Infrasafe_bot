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
from datetime import datetime

router = Router()
logger = logging.getLogger(__name__)

class ReplyStates(StatesGroup):
    waiting_for_reply_text = State()

@router.message(F.text.startswith("/reply_"))
async def handle_reply_command(message: Message, state: FSMContext, db: Session):
    """Обработка команды ответа на уточнение"""
    try:
        # Извлекаем ID заявки из команды
        command_parts = message.text.split("_")
        if len(command_parts) != 2:
            await message.answer("❌ Неверный формат команды. Используйте: /reply_<номер_заявки>")
            return
        
        try:
            request_id = int(command_parts[1])
        except ValueError:
            await message.answer("❌ Неверный номер заявки")
            return
        
        # Получаем заявку
        request = db.query(Request).filter(Request.id == request_id).first()
        if not request:
            await message.answer("❌ Заявка не найдена")
            return
        
        # Проверяем, что пользователь является заявителем
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.id != request.user_id:
            await message.answer("❌ У вас нет прав для ответа на эту заявку")
            return
        
        # Проверяем, что заявка в статусе уточнения
        if request.status != "Уточнение":
            await message.answer("❌ Заявка не находится в статусе уточнения")
            return
        
        # Сохраняем ID заявки в состоянии
        await state.update_data(request_id=request_id)
        
        # Запрашиваем текст ответа
        await message.answer(
            f"💬 Введите ваш ответ на уточнение по заявке #{request_id}:\n\n"
            f"📋 Заявка: {request.category}\n"
            f"📍 Адрес: {request.address}\n\n"
            f"💬 Введите ваш ответ:",
            reply_markup=None
        )
        
        # Устанавливаем состояние ожидания ответа
        await state.set_state(ReplyStates.waiting_for_reply_text)
        
        logger.info(f"Запрошен ответ на уточнение для заявки {request_id} от пользователя {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки команды ответа: {e}")
        await message.answer("❌ Произошла ошибка")

@router.message(ReplyStates.waiting_for_reply_text)
async def handle_reply_text(message: Message, state: FSMContext, db: Session):
    """Обработка текста ответа от заявителя"""
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        request_id = data.get("request_id")
        
        if not request_id:
            await message.answer("❌ Ошибка: не найдена заявка")
            await state.clear()
            return
        
        # Получаем заявку
        request = db.query(Request).filter(Request.id == request_id).first()
        if not request:
            await message.answer("❌ Заявка не найдена")
            await state.clear()
            return
        
        # Получаем пользователя
        user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user or user.id != request.user_id:
            await message.answer("❌ У вас нет прав для ответа на эту заявку")
            await state.clear()
            return
        
        # Получаем текст ответа
        reply_text = message.text.strip()
        
        if not reply_text:
            await message.answer("❌ Текст ответа не может быть пустым. Попробуйте еще раз.")
            return
        
        # Формируем имя заявителя
        applicant_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        if not applicant_name:
            applicant_name = f"Заявитель {user.telegram_id}"
        
        # Добавляем ответ в примечания заявки
        timestamp = datetime.now().strftime('%d.%m.%Y %H:%M')
        new_note = f"\n\n--- ОТВЕТ {timestamp} ---\n"
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
            
            notification_text = f"💬 Получен ответ на уточнение по заявке #{request.id}:\n\n"
            notification_text += f"📋 Заявка: {request.category}\n"
            notification_text += f"📍 Адрес: {request.address}\n\n"
            notification_text += f"👤 Ответ от заявителя:\n{reply_text}"
            
            for manager in managers:
                try:
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
        await message.answer(
            f"✅ Ответ отправлен!\n\n"
            f"📋 Заявка #{request_id}\n"
            f"💬 Ваш ответ: {reply_text[:100]}{'...' if len(reply_text) > 100 else ''}\n\n"
            f"📱 Менеджеры получили уведомление."
        )
        
        # Очищаем состояние
        await state.clear()
        
        logger.info(f"Ответ на уточнение по заявке {request_id} добавлен пользователем {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки ответа на уточнение: {e}")
        await message.answer("❌ Произошла ошибка при отправке ответа")
        await state.clear()
