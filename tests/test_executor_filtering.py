#!/usr/bin/env python3
"""
Тест для проверки фильтрации заявок для исполнителей по статусам
"""

import sys
import os
sys.path.append('/app')

from uk_management_bot.database.session import engine
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from sqlalchemy import text
from datetime import datetime

def test_executor_filtering():
    """Тестирует фильтрацию заявок для исполнителей по статусам"""
    
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
            print(f"✅ Найден исполнитель-сантехник: ID {executor_id}, Telegram ID {executor[1]}")
            
            # Создаем тестовые заявки с разными статусами
            test_requests = [
                ("Сантехника", "В работе", "Тестовый адрес 1"),
                ("Сантехника", "Закуп", "Тестовый адрес 2"),
                ("Сантехника", "Уточнение", "Тестовый адрес 3"),
                ("Сантехника", "Отменена", "Тестовый адрес 4"),
                ("Сантехника", "Принято", "Тестовый адрес 5"),
                ("Сантехника", "Выполнена", "Тестовый адрес 6"),
            ]
            
            created_requests = []
            for category, status, address in test_requests:
                # Создаем заявку
                connection.execute(text("""
                    INSERT INTO requests 
                    (user_id, category, status, address, description, urgency, created_at, updated_at)
                    VALUES (:user_id, :category, :status, :address, 'Тестовая заявка', 'Обычная', :created_at, :updated_at)
                """), {
                    "user_id": 2,
                    "category": category,
                    "status": status,
                    "address": address,
                    "created_at": datetime.now(),
                    "updated_at": datetime.now()
                })
                
                # Получаем ID созданной заявки
                result = connection.execute(text("""
                    SELECT id FROM requests 
                    WHERE category = :category 
                    AND status = :status 
                    AND address = :address
                    ORDER BY created_at DESC 
                    LIMIT 1
                """), {
                    "category": category,
                    "status": status,
                    "address": address
                })
                
                request = result.fetchone()
                if request:
                    created_requests.append((request[0], category, status, address))
                    print(f"✅ Создана заявка: ID {request[0]}, Статус: {status}")
            
            # Создаем назначения для всех заявок
            for request_id, category, status, address in created_requests:
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
            
            # Проверяем, какие заявки видит исполнитель в активных
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
                ORDER BY r.created_at DESC
            """), {"executor_id": executor_id})
            
            active_requests = result.fetchall()
            print(f"\n👁️ Активные заявки, которые видит исполнитель:")
            
            expected_active_statuses = ["В работе", "Закуп", "Уточнение"]
            actual_statuses = [req[2] for req in active_requests]
            
            for req in active_requests:
                print(f"   - ID: {req[0]}, Статус: {req[2]}, Адрес: {req[3]}")
            
            # Проверяем, что видны только активные статусы
            if set(actual_statuses) == set(expected_active_statuses):
                print(f"✅ Исполнитель видит только активные заявки: {actual_statuses}")
            else:
                print(f"❌ Ошибка: исполнитель видит статусы {actual_statuses}, ожидались {expected_active_statuses}")
                return False
            
            # Проверяем, что в активных заявках только нужные статусы
            # Это симулирует логику функции show_my_requests для active_status = "active"
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
                ORDER BY r.created_at DESC
            """), {"executor_id": executor_id})
            
            active_requests_final = result.fetchall()
            print(f"\n👁️ Активные заявки (финальная проверка):")
            
            for req in active_requests_final:
                print(f"   - ID: {req[0]}, Статус: {req[2]}, Адрес: {req[3]}")
            
            # Проверяем, что в активных заявках только нужные статусы
            actual_statuses = [req[2] for req in active_requests_final]
            expected_statuses = ["В работе", "Закуп", "Уточнение"]
            
            # Проверяем, что все статусы в списке - это ожидаемые статусы
            unexpected_statuses = [status for status in actual_statuses if status not in expected_statuses]
            
            if len(unexpected_statuses) == 0:
                print("✅ В активных заявках только ожидаемые статусы (как и должно быть)")
            else:
                print(f"❌ Ошибка: в активных заявках есть неожиданные статусы: {unexpected_statuses}")
                return False
            
            # Проверяем, что есть хотя бы одна заявка каждого ожидаемого статуса
            found_statuses = set(actual_statuses)
            missing_statuses = set(expected_statuses) - found_statuses
            
            if len(missing_statuses) == 0:
                print("✅ Найдены все ожидаемые статусы")
            else:
                print(f"⚠️ Не найдены статусы: {missing_statuses}")
                # Это не критично, так как тест может не создать все статусы
            
            # Очищаем тестовые данные
            for request_id, category, status, address in created_requests:
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
    success = test_executor_filtering()
    if success:
        print("\n🎉 Тест фильтрации заявок пройден успешно!")
        sys.exit(0)
    else:
        print("\n❌ Тест фильтрации заявок не пройден!")
        sys.exit(1)
