#!/usr/bin/env python3
"""
Упрощенный тест для проверки фильтрации заявок для исполнителей
"""

import sys
import os
sys.path.append('/app')

from uk_management_bot.database.session import engine
from sqlalchemy import text
from datetime import datetime

def test_simple_filtering():
    """Тестирует упрощенную фильтрацию заявок для исполнителей"""
    
    with engine.connect() as connection:
        try:
            # Находим исполнителя-сантехника
            result = connection.execute(text("""
                SELECT id, telegram_id, specialization, active_role
                FROM users 
                WHERE specialization = 'plumber' 
                AND active_role = 'executor'
                LIMIT 1
            """))
            
            executor = result.fetchone()
            if not executor:
                print("❌ Исполнитель-сантехник не найден!")
                return False
            
            executor_id = executor[0]
            print(f"✅ Найден исполнитель-сантехник: ID {executor_id}")
            
            # Создаем только одну тестовую заявку с активным статусом
            connection.execute(text("""
                INSERT INTO requests 
                (user_id, category, status, address, description, urgency, created_at, updated_at)
                VALUES (:user_id, :category, :status, :address, 'Тестовая заявка', 'Обычная', :created_at, :updated_at)
            """), {
                "user_id": 2,
                "category": "Сантехника",
                "status": "В работе",
                "address": "Тестовый адрес активный",
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            })
            
            # Получаем ID созданной заявки
            result = connection.execute(text("""
                SELECT id FROM requests 
                WHERE address = 'Тестовый адрес активный'
                ORDER BY created_at DESC 
                LIMIT 1
            """))
            
            request = result.fetchone()
            if not request:
                print("❌ Не удалось создать тестовую заявку!")
                return False
            
            request_id = request[0]
            print(f"✅ Создана тестовая заявка: ID {request_id}")
            
            # Создаем назначение для заявки
            connection.execute(text("""
                INSERT INTO request_assignments 
                (request_id, assignment_type, group_specialization, status, created_by)
                VALUES (:request_id, 'group', 'plumber', 'active', :created_by)
            """), {
                "request_id": request_id,
                "created_by": executor_id
            })
            print(f"✅ Назначение создано для заявки {request_id}")
            
            connection.commit()
            
            # Проверяем, что заявка видна в активных
            result = connection.execute(text("""
                SELECT r.id, r.category, r.status, r.address
                FROM requests r
                JOIN request_assignments ra ON r.id = ra.request_id
                WHERE ra.status = 'active'
                AND (
                    ra.executor_id = :executor_id 
                    OR (ra.assignment_type = 'group' AND ra.group_specialization = 'plumber')
                )
                AND r.status IN ('В работе', 'Закуп', 'Уточнение')
                AND r.address = 'Тестовый адрес активный'
            """), {"executor_id": executor_id})
            
            active_requests = result.fetchall()
            print(f"\n👁️ Активные заявки с адресом 'Тестовый адрес активный':")
            
            for req in active_requests:
                print(f"   - ID: {req[0]}, Статус: {req[2]}, Адрес: {req[3]}")
            
            if len(active_requests) == 1:
                print("✅ Тестовая заявка найдена в активных заявках")
            else:
                print(f"❌ Ошибка: найдено {len(active_requests)} заявок вместо 1")
                return False
            
            # Теперь меняем статус заявки на финальный
            connection.execute(text("""
                UPDATE requests 
                SET status = 'Принято', updated_at = :updated_at
                WHERE id = :request_id
            """), {
                "request_id": request_id,
                "updated_at": datetime.now()
            })
            print(f"✅ Статус заявки изменен на 'Принято'")
            
            connection.commit()
            
            # Проверяем, что заявка НЕ видна в активных
            result = connection.execute(text("""
                SELECT r.id, r.category, r.status, r.address
                FROM requests r
                JOIN request_assignments ra ON r.id = ra.request_id
                WHERE ra.status = 'active'
                AND (
                    ra.executor_id = :executor_id 
                    OR (ra.assignment_type = 'group' AND ra.group_specialization = 'plumber')
                )
                AND r.status IN ('В работе', 'Закуп', 'Уточнение')
                AND r.address = 'Тестовый адрес активный'
            """), {"executor_id": executor_id})
            
            active_requests_after = result.fetchall()
            print(f"\n👁️ Активные заявки после изменения статуса:")
            
            for req in active_requests_after:
                print(f"   - ID: {req[0]}, Статус: {req[2]}, Адрес: {req[3]}")
            
            if len(active_requests_after) == 0:
                print("✅ Заявка больше не видна в активных (как и должно быть)")
            else:
                print(f"❌ Ошибка: заявка все еще видна в активных")
                return False
            
            # Очищаем тестовые данные
            connection.execute(text("DELETE FROM request_assignments WHERE request_id = :request_id"), {"request_id": request_id})
            connection.execute(text("DELETE FROM requests WHERE id = :request_id"), {"request_id": request_id})
            
            connection.commit()
            print(f"\n✅ Тестовые данные очищены")
            
            return True
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            connection.rollback()
            return False

if __name__ == "__main__":
    success = test_simple_filtering()
    if success:
        print("\n🎉 Тест фильтрации заявок пройден успешно!")
        sys.exit(0)
    else:
        print("\n❌ Тест фильтрации заявок не пройден!")
        sys.exit(1)
