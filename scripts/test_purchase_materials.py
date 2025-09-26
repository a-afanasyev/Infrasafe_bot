#!/usr/bin/env python3
"""
Тестирование функциональности закупа материалов
"""

import sys
import os
import logging

# Добавляем корневую директорию в path для контейнера
sys.path.insert(0, '/app')

from uk_management_bot.database.session import get_db
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request_comment import RequestComment
from uk_management_bot.services.comment_service import CommentService

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def test_purchase_materials():
    """Тестирование системы закупа материалов"""
    db = next(get_db())
    
    print('🔍 Тестируем систему закупа материалов...')
    
    try:
        # Создаем тестового пользователя если его нет
        user = db.query(User).filter(User.telegram_id == 12345).first()
        if not user:
            user = User(
                telegram_id=12345,
                first_name='Test',
                last_name='User', 
                username='testuser',
                role='admin'
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f'👤 Создан тестовый пользователь: {user.id}')
        else:
            print(f'👤 Используем существующего пользователя: {user.id}')
        
        # Создаем тестовую заявку
        request_number = Request.generate_request_number(db)
        request = Request(
            request_number=request_number,
            user_id=user.id,
            category='Сантехника',
            address='Тестовая улица, 1',
            description='Тестовая заявка для проверки закупа',
            status='Закуп'
        )
        db.add(request)
        db.commit()
        db.refresh(request)
        
        print(f'📝 Создана тестовая заявка: {request.request_number}')
        
        # Тестируем CommentService с новым номером
        comment_service = CommentService(db)
        
        # Добавляем комментарий о закупе
        materials = 'Трубы - 5 метров\nФитинги - 10 штук\nКлей - 1 тюбик'
        comment = comment_service.add_purchase_comment(request.request_number, user.id, materials)
        
        print(f'✅ Комментарий о закупе добавлен: ID {comment.id}')
        
        # Проверяем что комментарий привязан к правильной заявке
        saved_comment = db.query(RequestComment).filter(RequestComment.id == comment.id).first()
        print(f'✅ Комментарий сохранен для заявки: {saved_comment.request_number}')
        print(f'✅ Содержимое: {saved_comment.comment_text[:50]}...')
        
        # Проверяем связь с заявкой
        linked_request = db.query(Request).filter(Request.request_number == saved_comment.request_number).first()
        if linked_request:
            print(f'✅ Связь с заявкой установлена: {linked_request.request_number}')
            print(f'✅ Статус заявки: {linked_request.status}')
        else:
            print('❌ Ошибка связи с заявкой')
            return False
        
        print('\n🎉 УСПЕШНО: Система закупа материалов работает!')
        print('🎉 УСПЕШНО: CommentService совместим с новой нумерацией!')
        print('🎉 УСПЕШНО: Ошибка "type object Request has no attribute id" исправлена!')
        
        return True
        
    except Exception as e:
        print(f'❌ ОШИБКА в тесте: {e}')
        logger.exception('Ошибка в тесте закупа материалов')
        return False
    finally:
        db.close()

if __name__ == '__main__':
    success = test_purchase_materials()
    sys.exit(0 if success else 1)
