"""
Обработчики для управления комментариями к заявкам
Обеспечивает функциональность добавления и просмотра комментариев
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from uk_management_bot.database.session import get_db
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.states.request_comments import RequestCommentStates
from uk_management_bot.services.comment_service import CommentService
from uk_management_bot.keyboards.request_comments import (
    get_comment_type_keyboard,
    get_comment_confirmation_keyboard,
    get_comments_list_keyboard
)
from uk_management_bot.utils.helpers import get_text, get_language_from_event
from uk_management_bot.utils.auth_helpers import check_user_role
from uk_management_bot.utils.constants import (
    ROLE_MANAGER, ROLE_EXECUTOR, ROLE_APPLICANT,
    COMMENT_TYPE_CLARIFICATION, COMMENT_TYPE_PURCHASE, COMMENT_TYPE_REPORT
)

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data.startswith("add_comment_"))
async def handle_add_comment_start(callback: CallbackQuery, state: FSMContext, db: Session):
    """Начало процесса добавления комментария"""
    try:
        # Получаем ID заявки
        request_number = callback.data.split("_")[-1]
        
        # Проверяем существование заявки
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Проверяем права доступа
        user_id = callback.from_user.id
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        # Проверяем, что пользователь имеет отношение к заявке
        user_roles = user.roles if user.roles else []
        has_access = (
            request.user_id == user_id or  # Заявитель
            request.executor_id == user_id or  # Исполнитель
            ROLE_MANAGER in user_roles  # Менеджер
        )
        
        if not has_access:
            await callback.answer("У вас нет прав для добавления комментариев к этой заявке", show_alert=True)
            return
        
        # Сохраняем данные в состоянии
        await state.update_data(
            request_number=request_number,
            user_roles=user_roles
        )
        
        # Показываем выбор типа комментария
        lang = get_language_from_event(callback, db)
        keyboard = get_comment_type_keyboard(lang)
        
        await callback.message.edit_text(
            get_text("comments.select_type", language=lang),
            reply_markup=keyboard
        )
        
        # Переходим в состояние выбора типа комментария
        await state.set_state(RequestCommentStates.waiting_for_comment_type)
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка начала добавления комментария: {e}")
        await callback.answer(f"Произошла ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("comment_type_"))
async def handle_comment_type_selection(callback: CallbackQuery, state: FSMContext, db: Session):
    """Обработка выбора типа комментария"""
    try:
        # Получаем тип комментария из callback data
        comment_type = callback.data.split("_", 2)[2]
        
        # Сохраняем тип комментария в состоянии
        await state.update_data(comment_type=comment_type)
        
        # Получаем промпт для комментария
        lang = get_language_from_event(callback, db)
        comment_prompt = get_comment_prompt(comment_type, lang)
        
        await callback.message.edit_text(comment_prompt)
        
        # Переходим в состояние ввода комментария
        await state.set_state(RequestCommentStates.waiting_for_comment)
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка выбора типа комментария: {e}")
        await callback.answer(f"Произошла ошибка: {str(e)}", show_alert=True)

@router.message(RequestCommentStates.waiting_for_comment)
async def handle_comment_input(message: Message, state: FSMContext, db: Session):
    """Обработка ввода комментария"""
    try:
        # Получаем текст комментария
        comment_text = message.text.strip()
        
        if not comment_text:
            await message.answer("Пожалуйста, введите текст комментария")
            return
        
        if len(comment_text) < 5:
            await message.answer("Комментарий должен содержать минимум 5 символов")
            return
        
        # Сохраняем комментарий в состоянии
        await state.update_data(comment_text=comment_text)
        
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")
        comment_type = data.get("comment_type")
        
        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await message.answer("Заявка не найдена")
            return
        
        # Показываем подтверждение
        lang = get_language_from_event(message, db)
        keyboard = get_comment_confirmation_keyboard(lang)
        
        confirmation_text = get_text("comments.confirmation", language=lang).format(
            request_id=request_number,
            comment_type=get_comment_type_display_name(comment_type, lang),
            comment_text=comment_text[:100] + "..." if len(comment_text) > 100 else comment_text
        )
        
        await message.answer(confirmation_text, reply_markup=keyboard)
        
        # Переходим в состояние подтверждения
        await state.set_state(RequestCommentStates.waiting_for_confirmation)
        
    except Exception as e:
        logger.error(f"Ошибка ввода комментария: {e}")
        await message.answer(f"Произошла ошибка: {str(e)}")

@router.callback_query(F.data == "confirm_comment")
async def handle_comment_confirmation(callback: CallbackQuery, state: FSMContext, db: Session):
    """Подтверждение добавления комментария"""
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        request_number = data.get("request_number")
        comment_type = data.get("comment_type")
        comment_text = data.get("comment_text")
        
        if not all([request_number, comment_type, comment_text]):
            await callback.answer("Ошибка: данные комментария не найдены", show_alert=True)
            return
        
        # Получаем заявку для получения ID
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Создаем сервис комментариев
        comment_service = CommentService(db)
        
        # Добавляем комментарий
        comment = comment_service.add_comment(
            request_id=request.request_number,
            user_id=callback.from_user.id,
            comment_text=comment_text,
            comment_type=comment_type
        )
        
        # Показываем сообщение об успехе
        lang = get_language_from_event(callback, db)
        success_text = get_text("comments.success", language=lang).format(
            request_id=request_number,
            comment_type=get_comment_type_display_name(comment_type, lang)
        )
        
        await callback.message.edit_text(success_text)
        
        # Очищаем состояние
        await state.clear()
        
        await callback.answer("Комментарий успешно добавлен!")
        
    except Exception as e:
        logger.error(f"Ошибка подтверждения комментария: {e}")
        await callback.answer(f"Произошла ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data == "cancel_comment")
async def handle_comment_cancellation(callback: CallbackQuery, state: FSMContext, db: Session):
    """Отмена добавления комментария"""
    try:
        # Очищаем состояние
        await state.clear()
        
        await callback.message.edit_text("Добавление комментария отменено")
        await callback.answer("Добавление комментария отменено")
        
    except Exception as e:
        logger.error(f"Ошибка отмены комментария: {e}")
        await callback.answer(f"Произошла ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("view_comments_"))
async def handle_view_comments(callback: CallbackQuery, state: FSMContext, db: Session):
    """Просмотр комментариев заявки"""
    try:
        # Получаем ID заявки
        request_number = callback.data.split("_")[-1]
        
        # Проверяем существование заявки
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Проверяем права доступа
        user_id = callback.from_user.id
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        # Проверяем, что пользователь имеет отношение к заявке
        user_roles = user.roles if user.roles else []
        has_access = (
            request.user_id == user_id or  # Заявитель
            request.executor_id == user_id or  # Исполнитель
            ROLE_MANAGER in user_roles  # Менеджер
        )
        
        if not has_access:
            await callback.answer("У вас нет прав для просмотра комментариев к этой заявке", show_alert=True)
            return
        
        # Получаем комментарии
        comment_service = CommentService(db)
        comments = comment_service.get_request_comments(request.request_number, limit=20)
        
        if not comments:
            await callback.answer("Комментариев пока нет", show_alert=True)
            return
        
        # Форматируем комментарии для отображения
        formatted_comments = comment_service.format_comments_for_display(comments, "ru")
        
        # Показываем комментарии
        lang = get_language_from_event(callback, db)
        keyboard = get_comments_list_keyboard(request.request_number, lang)
        
        await callback.message.edit_text(
            formatted_comments,
            reply_markup=keyboard
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка просмотра комментариев: {e}")
        await callback.answer(f"Произошла ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("view_comments_by_type_"))
async def handle_view_comments_by_type(callback: CallbackQuery, state: FSMContext, db: Session):
    """Просмотр комментариев определенного типа"""
    try:
        # Получаем данные из callback
        parts = callback.data.split("_")
        request_number = parts[-1]
        comment_type = "_".join(parts[4:-1])  # Объединяем части типа комментария
        
        # Проверяем существование заявки
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Получаем комментарии определенного типа
        comment_service = CommentService(db)
        comments = comment_service.get_comments_by_type(request.request_number, comment_type)
        
        if not comments:
            await callback.answer("Комментариев такого типа не найдено", show_alert=True)
            return
        
        # Форматируем комментарии для отображения
        formatted_comments = comment_service.format_comments_for_display(comments, "ru")
        
        # Показываем комментарии
        lang = get_language_from_event(callback, db)
        keyboard = get_comments_list_keyboard(request.request_number, lang)
        
        await callback.message.edit_text(
            formatted_comments,
            reply_markup=keyboard
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка просмотра комментариев по типу: {e}")
        await callback.answer(f"Произошла ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("back_to_comments_"))
async def handle_back_to_comments(callback: CallbackQuery, state: FSMContext, db: Session):
    """Возврат к списку комментариев"""
    try:
        # Получаем ID заявки
        request_number = callback.data.split("_")[-1]
        
        # Получаем заявку
        request = db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        
        # Получаем все комментарии
        comment_service = CommentService(db)
        comments = comment_service.get_request_comments(request.request_number, limit=20)
        
        if not comments:
            await callback.answer("Комментариев пока нет", show_alert=True)
            return
        
        # Форматируем комментарии для отображения
        formatted_comments = comment_service.format_comments_for_display(comments, "ru")
        
        # Показываем комментарии
        lang = get_language_from_event(callback, db)
        keyboard = get_comments_list_keyboard(request.request_number, lang)
        
        await callback.message.edit_text(
            formatted_comments,
            reply_markup=keyboard
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка возврата к комментариям: {e}")
        await callback.answer(f"Произошла ошибка: {str(e)}", show_alert=True)

# Вспомогательные функции

def get_comment_prompt(comment_type: str, language: str = "ru") -> str:
    """Получение промпта для комментария в зависимости от типа"""
    prompts = {
        COMMENT_TYPE_CLARIFICATION: "Введите уточнение по заявке:",
        COMMENT_TYPE_PURCHASE: "Введите информацию о необходимых материалах:",
        COMMENT_TYPE_REPORT: "Введите отчет о выполнении работы:",
        "general": "Введите комментарий к заявке:"
    }
    
    return prompts.get(comment_type, prompts["general"])

def get_comment_type_display_name(comment_type: str, language: str = "ru") -> str:
    """Получение отображаемого названия типа комментария"""
    display_names = {
        COMMENT_TYPE_CLARIFICATION: "уточнение",
        COMMENT_TYPE_PURCHASE: "закупка материалов",
        COMMENT_TYPE_REPORT: "отчет о выполнении",
        "general": "общий комментарий"
    }
    
    return display_names.get(comment_type, "комментарий")
