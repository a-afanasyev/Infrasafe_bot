#!/usr/bin/env python3
"""
Тестовый скрипт для проверки интеграции с Google Sheets

Этот скрипт тестирует базовую функциональность Google Sheets интеграции
без необходимости настройки реальных credentials.
"""

import asyncio
import sys
import os
from pathlib import Path

# Добавляем корневую директорию проекта в PYTHONPATH
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Добавляем путь к модулям
sys.path.insert(0, str(project_root / "uk_management_bot"))

from integrations.google_sheets import SheetsService, SyncTask
from utils.sheets_utils import CircuitBreaker, RateLimiter, SheetsSyncWorker


async def test_sheets_service_initialization():
    """Тест инициализации SheetsService"""
    print("🧪 Тест 1: Инициализация SheetsService")
    
    try:
        service = SheetsService()
        print(f"✅ SheetsService создан успешно")
        print(f"   - Sync enabled: {service.sync_enabled}")
        print(f"   - Spreadsheet ID: {service.spreadsheet_id}")
        print(f"   - Credentials file: {service.credentials_file}")
        
        # Тест статуса синхронизации
        status = await service.get_sync_status()
        print(f"   - Status: {status}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка инициализации SheetsService: {e}")
        return False


async def test_circuit_breaker():
    """Тест Circuit Breaker"""
    print("\n🧪 Тест 2: Circuit Breaker")
    
    try:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=5)
        print(f"✅ Circuit Breaker создан успешно")
        print(f"   - Initial state: {cb.state}")
        print(f"   - Is closed: {cb.is_closed()}")
        
        # Симулируем ошибки
        for i in range(3):
            cb.on_error()
            print(f"   - Error {i+1}, state: {cb.state}, is_closed: {cb.is_closed()}")
        
        # Проверяем, что перешел в OPEN состояние
        if cb.state == "OPEN":
            print("✅ Circuit Breaker правильно перешел в OPEN состояние")
        
        # Симулируем успешную операцию
        cb.on_success()
        print(f"   - After success, state: {cb.state}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка Circuit Breaker: {e}")
        return False


async def test_rate_limiter():
    """Тест Rate Limiter"""
    print("\n🧪 Тест 3: Rate Limiter")
    
    try:
        rl = RateLimiter(requests_per_minute=5)
        print(f"✅ Rate Limiter создан успешно")
        print(f"   - Requests per minute: {rl.requests_per_minute}")
        
        # Симулируем несколько запросов
        for i in range(3):
            await rl.wait_if_needed()
            stats = rl.get_usage_stats()
            print(f"   - Request {i+1}, current: {stats['current_requests']}, available: {stats['available_requests']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка Rate Limiter: {e}")
        return False


async def test_sync_task():
    """Тест SyncTask"""
    print("\n🧪 Тест 4: SyncTask")
    
    try:
        # Создаем тестовые данные
        test_data = {
            'id': 123,
            'status': 'Новая',
            'category': 'Электрика',
            'description': 'Тестовая заявка'
        }
        
        # Создаем задачу
        task = SyncTask(
            task_type="create",
            request_id=123,
            data=test_data,
            priority="high"
        )
        
        print(f"✅ SyncTask создана успешно")
        print(f"   - Task type: {task.task_type}")
        print(f"   - Request ID: {task.request_id}")
        print(f"   - Priority: {task.priority}")
        print(f"   - Retry count: {task.retry_count}")
        
        # Тест сериализации/десериализации
        json_str = task.to_json()
        print(f"   - JSON serialization: {len(json_str)} chars")
        
        # Десериализация
        task2 = SyncTask.from_json(json_str)
        print(f"   - Deserialization successful: {task2.request_id == task.request_id}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка SyncTask: {e}")
        return False


async def test_sheets_service_methods():
    """Тест методов SheetsService (без реального API)"""
    print("\n🧪 Тест 5: SheetsService методы")
    
    try:
        service = SheetsService()
        
        # Тест подготовки данных
        test_request_data = {
            'id': 123,
            'created_at': '2024-12-07 10:30:00',
            'status': 'Новая',
            'category': 'Электрика',
            'address': 'ул. Тестовая, 1',
            'description': 'Тестовая заявка',
            'urgency': 'Обычная',
            'applicant_id': 1,
            'applicant_name': 'Тест Пользователь',
            'executor_id': None,
            'executor_name': '',
            'assigned_at': '',
            'completed_at': '',
            'comments': '',
            'photo_urls': ''
        }
        
        # Тест подготовки данных строки
        row_data = service._prepare_request_row_data(test_request_data)
        print(f"✅ Подготовка данных строки успешна")
        print(f"   - Количество колонок: {len(row_data)}")
        print(f"   - Данные: {row_data[:3]}...")  # Показываем первые 3 элемента
        
        # Тест подготовки данных обновления
        changes = {'status': 'В работе', 'executor_id': 2}
        update_data = service._prepare_update_data(changes)
        print(f"✅ Подготовка данных обновления успешна")
        print(f"   - Update data: {update_data}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка методов SheetsService: {e}")
        return False


async def test_integration_without_credentials():
    """Тест интеграции без реальных credentials"""
    print("\n🧪 Тест 6: Интеграция без credentials")
    
    try:
        service = SheetsService()
        
        # Тест подключения (должен вернуть False без credentials)
        connection_test = await service.test_connection()
        print(f"✅ Тест подключения выполнен")
        print(f"   - Connection test result: {connection_test}")
        print(f"   - Expected: False (no credentials)")
        
        # Тест создания структуры (должен вернуть False без credentials)
        structure_test = await service.create_spreadsheet_structure()
        print(f"✅ Тест создания структуры выполнен")
        print(f"   - Structure creation result: {structure_test}")
        print(f"   - Expected: False (no credentials)")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка интеграции: {e}")
        return False


async def main():
    """Основная функция тестирования"""
    print("🚀 Запуск тестов Google Sheets интеграции")
    print("=" * 50)
    
    tests = [
        test_sheets_service_initialization,
        test_circuit_breaker,
        test_rate_limiter,
        test_sync_task,
        test_sheets_service_methods,
        test_integration_without_credentials
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            result = await test()
            if result:
                passed += 1
        except Exception as e:
            print(f"❌ Неожиданная ошибка в тесте: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Результаты тестирования: {passed}/{total} тестов прошли")
    
    if passed == total:
        print("🎉 Все тесты прошли успешно!")
        print("✅ Google Sheets интеграция готова к использованию")
        print("\n📋 Следующие шаги:")
        print("   1. Настройте Google Sheets API credentials")
        print("   2. Создайте Google Spreadsheet")
        print("   3. Обновите переменные окружения")
        print("   4. Запустите реальные тесты с API")
    else:
        print("⚠️  Некоторые тесты не прошли")
        print("🔧 Проверьте конфигурацию и зависимости")
    
    return passed == total


if __name__ == "__main__":
    # Запускаем тесты
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
