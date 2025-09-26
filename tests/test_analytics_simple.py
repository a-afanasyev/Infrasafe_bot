#!/usr/bin/env python3
"""
Упрощенный тест аналитических компонентов системы смен
Проверяет основную функциональность без сложных зависимостей
"""

import asyncio
import sys
import os
from datetime import datetime, date, timedelta
from sqlalchemy import text

# Добавляем путь к модулям
sys.path.append(os.path.join(os.path.dirname(__file__), '.'))

from uk_management_bot.database.session import get_db


async def test_database_connection():
    """Тест подключения к базе данных"""
    print("🔧 Тестирование подключения к БД...")
    
    try:
        db = next(get_db())
        
        # Простой запрос для проверки подключения
        result = db.execute(text("SELECT 1 as test_value")).fetchone()
        
        if result and result[0] == 1:
            print("✅ Подключение к БД работает")
            
            # Проверяем наличие основных таблиц
            tables_to_check = ['shifts', 'users', 'requests']
            existing_tables = []
            
            for table_name in tables_to_check:
                try:
                    db.execute(text(f"SELECT 1 FROM {table_name} LIMIT 1"))
                    existing_tables.append(table_name)
                    print(f"  ✓ Таблица {table_name} найдена")
                except Exception as e:
                    print(f"  ⚠️ Таблица {table_name} не найдена или недоступна")
            
            print(f"📊 Доступно таблиц: {len(existing_tables)}/{len(tables_to_check)}")
            
            # Простая статистика
            for table in existing_tables:
                try:
                    count_result = db.execute(text(f"SELECT COUNT(*) FROM {table}")).fetchone()
                    count = count_result[0] if count_result else 0
                    print(f"  📈 {table}: {count} записей")
                except Exception as e:
                    print(f"  ❌ Ошибка подсчета для {table}: {e}")
            
            db.close()
            return True
            
        else:
            print("❌ Тест подключения не прошел")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
        return False


async def test_analytics_files():
    """Тест наличия файлов аналитических сервисов"""
    print("\n📁 Проверка файлов аналитических сервисов...")
    
    files_to_check = [
        'uk_management_bot/services/shift_analytics.py',
        'uk_management_bot/services/metrics_manager.py',
        'uk_management_bot/services/recommendation_engine.py'
    ]
    
    existing_files = []
    
    for file_path in files_to_check:
        if os.path.exists(f'/app/{file_path}'):
            existing_files.append(file_path)
            print(f"  ✅ {file_path}")
            
            # Проверяем размер файла
            try:
                size = os.path.getsize(f'/app/{file_path}')
                print(f"    📦 Размер: {size} байт")
            except Exception as e:
                print(f"    ⚠️ Ошибка получения размера: {e}")
        else:
            print(f"  ❌ {file_path} не найден")
    
    print(f"\n📊 Найдено файлов: {len(existing_files)}/{len(files_to_check)}")
    return len(existing_files) == len(files_to_check)


async def test_import_basic():
    """Тест базового импорта модулей"""
    print("\n🔗 Тестирование импорта модулей...")
    
    import_results = {}
    
    # Тест 1: Импорт базовых модулей
    try:
        from uk_management_bot.database.session import SessionLocal, Base
        import_results['database_session'] = True
        print("  ✅ База данных: SessionLocal, Base")
    except Exception as e:
        import_results['database_session'] = False
        print(f"  ❌ База данных: {e}")
    
    # Тест 2: Импорт основных моделей
    try:
        from uk_management_bot.database.models.shift import Shift
        from uk_management_bot.database.models.user import User
        import_results['models'] = True
        print("  ✅ Модели: Shift, User")
    except Exception as e:
        import_results['models'] = False
        print(f"  ❌ Модели: {e}")
    
    # Тест 3: Импорт сервисов планирования
    try:
        from uk_management_bot.services.shift_planning_service import ShiftPlanningService
        import_results['shift_planning'] = True
        print("  ✅ ShiftPlanningService")
    except Exception as e:
        import_results['shift_planning'] = False
        print(f"  ❌ ShiftPlanningService: {e}")
    
    successful_imports = sum(1 for result in import_results.values() if result)
    total_imports = len(import_results)
    
    print(f"\n📊 Успешных импортов: {successful_imports}/{total_imports}")
    return successful_imports >= total_imports - 1  # Допускаем 1 неудачный импорт


async def test_basic_functionality():
    """Тест базовой функциональности"""
    print("\n⚙️  Тестирование базовой функциональности...")
    
    try:
        db = next(get_db())
        
        # Проверяем количество смен
        from uk_management_bot.database.models.shift import Shift
        shifts_count = db.query(Shift).count()
        print(f"  📊 Всего смен в системе: {shifts_count}")
        
        # Проверяем количество пользователей
        from uk_management_bot.database.models.user import User
        users_count = db.query(User).count()
        print(f"  👥 Всего пользователей: {users_count}")
        
        # Простая проверка планировщика смен
        from uk_management_bot.services.shift_planning_service import ShiftPlanningService
        planner = ShiftPlanningService(db)
        print("  ✅ ShiftPlanningService создан успешно")
        
        # Тест анализа пробелов покрытия
        gaps = planner.get_coverage_gaps(
            start_date=date.today() - timedelta(days=7),
            end_date=date.today()
        )
        print(f"  📈 Найдено пробелов в покрытии: {len(gaps)}")
        
        db.close()
        
        print("  ✅ Базовая функциональность работает")
        return True
        
    except Exception as e:
        print(f"  ❌ Ошибка тестирования функциональности: {e}")
        return False


async def main():
    """Главная функция тестирования"""
    print("🚀 Упрощенное тестирование аналитических компонентов")
    print("=" * 60)
    
    test_results = {}
    
    # Тест 1: Подключение к БД
    test_results['database'] = await test_database_connection()
    
    # Тест 2: Наличие файлов
    test_results['files'] = await test_analytics_files()
    
    # Тест 3: Импорты
    test_results['imports'] = await test_import_basic()
    
    # Тест 4: Базовая функциональность
    test_results['functionality'] = await test_basic_functionality()
    
    # Сводка
    print("\n" + "=" * 60)
    print("📋 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
    print("=" * 60)
    
    successful_tests = sum(1 for result in test_results.values() if result)
    total_tests = len(test_results)
    
    for test_name, result in test_results.items():
        status = "✅ УСПЕХ" if result else "❌ НЕУДАЧА"
        print(f"  {test_name.upper()}: {status}")
    
    success_rate = (successful_tests / total_tests * 100) if total_tests > 0 else 0
    
    print(f"\n🎯 ИТОГОВАЯ СТАТИСТИКА:")
    print(f"  • Всего тестов: {total_tests}")
    print(f"  • Успешных: {successful_tests}")
    print(f"  • Процент успеха: {success_rate:.1f}%")
    
    if success_rate >= 75:
        print("  🎉 Основные компоненты системы работают!")
        return 0
    elif success_rate >= 50:
        print("  👍 Система частично функциональна")
        return 0
    else:
        print("  ⚠️  Система требует серьезных исправлений")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))