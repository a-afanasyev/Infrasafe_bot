"""
Сервис для управления комментариями к заявкам
Обеспечивает систему комментариев с привязкой к изменениям статуса
"""

from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_comment import RequestComment
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.utils.constants import (
    COMMENT_TYPE_STATUS_CHANGE,
    COMMENT_TYPE_CLARIFICATION,
    COMMENT_TYPE_PURCHASE,
    COMMENT_TYPE_REPORT,
    AUDIT_ACTION_REQUEST_STATUS_CHANGED
)
from uk_management_bot.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

class CommentService:
    """Сервис для управления комментариями к заявкам"""
    
    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)
    
    def add_comment(self, request_id: str, user_id: int, comment_text: str, 
                   comment_type: str, previous_status: str = None, 
                   new_status: str = None) -> RequestComment:
        """
        Добавление комментария к заявке
        
        Args:
            request_id: Номер заявки (request_number)
            user_id: ID пользователя
            comment_text: Текст комментария
            comment_type: Тип комментария
            previous_status: Предыдущий статус (для изменений статуса)
            new_status: Новый статус (для изменений статуса)
            
        Returns:
            RequestComment: Созданный комментарий
            
        Raises:
            ValueError: При неверных данных
        """
        try:
            # Проверяем существование заявки по номеру
            request = self.db.query(Request).filter(Request.request_number == request_id).first()
            if not request:
                raise ValueError(f"Заявка с номером {request_id} не найдена")
            
            # Проверяем существование пользователя
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                raise ValueError(f"Пользователь с ID {user_id} не найден")
            
            # Валидация типа комментария
            valid_types = [COMMENT_TYPE_STATUS_CHANGE, COMMENT_TYPE_CLARIFICATION, 
                          COMMENT_TYPE_PURCHASE, COMMENT_TYPE_REPORT]
            if comment_type not in valid_types:
                raise ValueError(f"Неверный тип комментария: {comment_type}")
            
            # Создаем комментарий
            comment = RequestComment(
                request_number=request_id,  # Теперь это request_number
                user_id=user_id,
                comment_text=comment_text,
                comment_type=comment_type,
                previous_status=previous_status,
                new_status=new_status
            )
            
            self.db.add(comment)
            self.db.commit()
            self.db.refresh(comment)
            
            # Создаем запись в аудите
            self._create_audit_log(request_id, user_id, f"Добавлен комментарий: {comment_type}")
            
            # Отправляем уведомления
            self._notify_comment_added(request, comment)
            
            logger.info(f"Добавлен комментарий к заявке {request_id} пользователем {user_id}")
            return comment
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка добавления комментария: {e}")
            raise
    
    def get_request_comments(self, request_number: str, limit: int = 50) -> List[RequestComment]:
        """
        Получение всех комментариев заявки
        
        Args:
            request_number: Номер заявки
            limit: Максимальное количество комментариев
            
        Returns:
            List[RequestComment]: Список комментариев
        """
        return self.db.query(RequestComment).filter(
            RequestComment.request_number == request_number
        ).order_by(desc(RequestComment.created_at)).limit(limit).all()
    
    def get_comments_by_type(self, request_number: str, comment_type: str) -> List[RequestComment]:
        """
        Получение комментариев заявки по типу
        
        Args:
            request_number: Номер заявки
            comment_type: Тип комментария
            
        Returns:
            List[RequestComment]: Список комментариев
        """
        return self.db.query(RequestComment).filter(
            and_(
                RequestComment.request_number == request_number,
                RequestComment.comment_type == comment_type
            )
        ).order_by(desc(RequestComment.created_at)).all()
    
    def format_comments_for_display(self, comments: List[RequestComment], language: str = "ru") -> str:
        """
        Форматирование комментариев для отображения
        
        Args:
            comments: Список комментариев
            language: Язык отображения
            
        Returns:
            str: Отформатированный текст комментариев
        """
        if not comments:
            return "Комментариев пока нет"
        
        formatted_text = "📝 История комментариев:\n\n"
        
        for comment in comments:
            # Получаем информацию о пользователе
            user = self.db.query(User).filter(User.id == comment.user_id).first()
            if user:
                user_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
                if not user_name:
                    user_name = f"Пользователь {comment.user_id}"
            else:
                user_name = f"Пользователь {comment.user_id}"
            
            # Форматируем дату
            date_str = comment.created_at.strftime("%d.%m.%Y %H:%M") if comment.created_at else "Неизвестно"
            
            # Определяем тип комментария
            type_emoji = self._get_comment_type_emoji(comment.comment_type)
            
            # Форматируем текст комментария
            formatted_text += f"{type_emoji} **{user_name}** ({date_str})\n"
            
            # Добавляем информацию о статусе для изменений статуса
            if comment.comment_type == COMMENT_TYPE_STATUS_CHANGE and comment.previous_status and comment.new_status:
                formatted_text += f"📊 Статус изменен: {comment.previous_status} → {comment.new_status}\n"
            
            formatted_text += f"💬 {comment.comment_text}\n\n"
        
        return formatted_text
    
    def add_status_change_comment(self, request_number: str, user_id: int, 
                                previous_status: str, new_status: str, 
                                additional_comment: str = None) -> RequestComment:
        """
        Добавление комментария при изменении статуса
        
        Args:
            request_number: Номер заявки
            user_id: ID пользователя
            previous_status: Предыдущий статус
            new_status: Новый статус
            additional_comment: Дополнительный комментарий
            
        Returns:
            RequestComment: Созданный комментарий
        """
        # Получаем заявку по номеру
        request = self.db.query(Request).filter(Request.request_number == request_number).first()
        if not request:
            raise ValueError(f"Заявка с номером {request_number} не найдена")
        
        # Формируем текст комментария
        comment_text = f"Статус изменен с '{previous_status}' на '{new_status}'"
        if additional_comment:
            comment_text += f"\n\nДополнительно: {additional_comment}"
        
        return self.add_comment(
            request_id=request.request_number,
            user_id=user_id,
            comment_text=comment_text,
            comment_type=COMMENT_TYPE_STATUS_CHANGE,
            previous_status=previous_status,
            new_status=new_status
        )
    
    def add_purchase_comment(self, request_number: str, user_id: int, materials: str) -> RequestComment:
        """
        Добавление комментария о закупке материалов
        
        Args:
            request_number: Номер заявки
            user_id: ID пользователя
            materials: Список необходимых материалов
            
        Returns:
            RequestComment: Созданный комментарий
        """
        comment_text = f"Необходимо закупить материалы:\n{materials}"
        
        return self.add_comment(
            request_id=request_number,
            user_id=user_id,
            comment_text=comment_text,
            comment_type=COMMENT_TYPE_PURCHASE
        )
    
    def add_clarification_comment(self, request_number: str, user_id: int, clarification: str) -> RequestComment:
        """
        Добавление комментария с уточнением
        
        Args:
            request_number: Номер заявки
            user_id: ID пользователя
            clarification: Текст уточнения
            
        Returns:
            RequestComment: Созданный комментарий
        """
        return self.add_comment(
            request_id=request_number,
            user_id=user_id,
            comment_text=clarification,
            comment_type=COMMENT_TYPE_CLARIFICATION
        )
    
    def add_completion_report_comment(self, request_number: str, user_id: int, report: str) -> RequestComment:
        """
        Добавление комментария с отчетом о выполнении
        
        Args:
            request_number: Номер заявки
            user_id: ID пользователя
            report: Текст отчета
            
        Returns:
            RequestComment: Созданный комментарий
        """
        return self.add_comment(
            request_id=request_number,
            user_id=user_id,
            comment_text=report,
            comment_type=COMMENT_TYPE_REPORT
        )
    
    def get_latest_comment(self, request_number: str, comment_type: str = None) -> Optional[RequestComment]:
        """
        Получение последнего комментария заявки
        
        Args:
            request_number: Номер заявки
            comment_type: Тип комментария (опционально)
            
        Returns:
            Optional[RequestComment]: Последний комментарий или None
        """
        query = self.db.query(RequestComment).filter(RequestComment.request_number == request_number)
        
        if comment_type:
            query = query.filter(RequestComment.comment_type == comment_type)
        
        return query.order_by(desc(RequestComment.created_at)).first()
    
    def _get_comment_type_emoji(self, comment_type: str) -> str:
        """Получение эмодзи для типа комментария"""
        emoji_map = {
            COMMENT_TYPE_STATUS_CHANGE: "🔄",
            COMMENT_TYPE_CLARIFICATION: "❓",
            COMMENT_TYPE_PURCHASE: "🛒",
            COMMENT_TYPE_REPORT: "📋"
        }
        return emoji_map.get(comment_type, "💬")
    
    def _create_audit_log(self, request_number: str, user_id: int, action_description: str):
        """Создание записи в аудите"""
        try:
            audit_log = AuditLog(
                user_id=user_id,
                action=AUDIT_ACTION_REQUEST_STATUS_CHANGED,
                details=f"Заявка {request_number}: {action_description}",
                timestamp=datetime.now()
            )
            self.db.add(audit_log)
        except Exception as e:
            logger.warning(f"Не удалось создать запись в аудите: {e}")
    
    def _notify_comment_added(self, request: Request, comment: RequestComment):
        """Уведомление о добавлении комментария"""
        try:
            # Определяем получателей уведомления
            recipients = []
            
            # Заявитель
            if request.user_id != comment.user_id:
                recipients.append(request.user_id)
            
            # Исполнитель (если есть)
            if request.executor_id and request.executor_id != comment.user_id:
                recipients.append(request.executor_id)
            
            # Отправляем уведомления
            for recipient_id in recipients:
                self.notification_service.send_notification(
                    user_id=recipient_id,
                    notification_type="comment_added",
                    title="Новый комментарий к заявке",
                    message=f"Добавлен новый комментарий к заявке #{request.request_number}",
                    data={"request_number": request.request_number, "comment_id": comment.id}
                )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомления о комментарии: {e}")
