"""
Сервис для управления комментариями к заявкам
Обеспечивает систему комментариев с привязкой к изменениям статуса
"""

from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from typing import List, Optional
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
from uk_management_bot.utils.helpers import get_text
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommentNotice:
    """Адресат уведомления о комментарии + текст на ЕГО языке (B3).

    Собирается sync-фазой внутри сессии; отправляет async-слой вызывающего
    хендлера через `send_to_user` — в worker-потоке `run_db` нет event loop,
    слать оттуда нечем (BUG-174).
    """

    telegram_id: int
    text: str


class CommentService:
    """Сервис для управления комментариями к заявкам"""

    def __init__(self, db: Session):
        self.db = db
    
    def add_comment(self, request_id: str, user_id: int, comment_text: str,
                   comment_type: str, previous_status: str = None,
                   new_status: str = None) -> tuple[RequestComment, list[CommentNotice]]:
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
            (созданный комментарий, notices для отправки async-слоем).
            Возврат кортежем НАМЕРЕННО: вызывающий, забывший про доставку,
            ломается на распаковке, а не молчит (класс BUG-174/BUG-155 п.2).

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

            # Собираем notices; шлёт async-слой вызывающего (B3, BUG-174)
            notices = self._collect_notices(request, comment)

            logger.info(f"Добавлен комментарий к заявке {request_id} пользователем {user_id}")
            return comment, notices

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
                                additional_comment: str = None) -> tuple[RequestComment, list[CommentNotice]]:
        """
        Добавление комментария при изменении статуса
        
        Args:
            request_number: Номер заявки
            user_id: ID пользователя
            previous_status: Предыдущий статус
            new_status: Новый статус
            additional_comment: Дополнительный комментарий
            
        Returns:
            (созданный комментарий, notices — шлёт async-слой вызывающего)
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
    
    def add_purchase_comment(self, request_number: str, user_id: int, materials: str) -> tuple[RequestComment, list[CommentNotice]]:
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
    
    def add_clarification_comment(self, request_number: str, user_id: int, clarification: str) -> tuple[RequestComment, list[CommentNotice]]:
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
    
    def add_completion_report_comment(self, request_number: str, user_id: int, report: str) -> tuple[RequestComment, list[CommentNotice]]:
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
            # CODE-09: убран битый kwarg timestamp= (нет такой колонки у
            # AuditLog → TypeError молча гасился except'ом, аудит НЕ писался).
            # created_at заполняется server_default=func.now() (UTC).
            audit_log = AuditLog(
                user_id=user_id,
                action=AUDIT_ACTION_REQUEST_STATUS_CHANGED,
                details=f"Заявка {request_number}: {action_description}",
            )
            self.db.add(audit_log)
        except Exception as e:
            logger.warning(f"Не удалось создать запись в аудите: {e}")
    
    def _collect_notices(self, request: Request, comment: RequestComment) -> list[CommentNotice]:
        """Адресаты уведомления о комментарии + текст на языке КАЖДОГО (B3).

        Закрытие BUG-174: раньше здесь стоял вызов несуществующего
        `NotificationService.send_notification` — `AttributeError` гасился
        except'ом, и ни заявитель, ни исполнитель не узнавали о комментарии
        никогда. Отправка из sync-фазы невозможна в принципе (worker-поток
        `run_db` без event loop), поэтому метод только СОБИРАЕТ; шлёт
        async-слой вызывающего через `send_to_user` — образец
        `clarification_replies._apply_reply`.
        """
        notices: list[CommentNotice] = []
        try:
            recipient_ids = []

            # Заявитель
            if request.user_id != comment.user_id:
                recipient_ids.append(request.user_id)

            # Исполнитель (если есть)
            if request.executor_id and request.executor_id != comment.user_id:
                recipient_ids.append(request.executor_id)

            if not recipient_ids:
                return notices

            users = self.db.query(User).filter(User.id.in_(recipient_ids)).all()
            for user in users:
                try:
                    if not user.telegram_id:
                        continue
                    lang = user.language or "ru"
                    type_key = f"comments.type_{comment.comment_type}"
                    type_label = get_text(type_key, language=lang)
                    if type_label == type_key:
                        # ключа локали нет — показываем сырой тип, а не ключ
                        type_label = comment.comment_type
                    text = get_text("comments.notification", language=lang).format(
                        request_number=request.request_number,
                        type_label=type_label,
                        comment_text=comment.comment_text,
                    )
                    notices.append(CommentNotice(telegram_id=user.telegram_id, text=text))
                except Exception as e:
                    # Сбой подготовки одного получателя не лишает остальных
                    logger.warning(
                        f"Не удалось подготовить уведомление о комментарии для user_id={user.id}: {e}"
                    )
        except Exception as e:
            logger.warning(f"Не удалось собрать уведомления о комментарии: {e}")
        return notices
