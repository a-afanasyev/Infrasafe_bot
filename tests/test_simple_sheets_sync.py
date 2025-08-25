#!/usr/bin/env python3
"""
Тестовый скрипт для Simple Google Sheets Sync (без API)

Тестирует простую синхронизацию через CSV файлы без использования Google Sheets API.
"""

import asyncio
import sys
import os
from pathlib import Path

# Добавляем корневую директорию проекта в PYTHONPATH
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "uk_management_bot"))

from integrations.simple_sheets_sync import SimpleSheetsSync


async def test_simple_sheets_initialization():
    """Тест инициализации SimpleSheetsSync"""
    print("🧪 Тест 1: Инициализация SimpleSheetsSync")
    
    try:
        # Тестируем с пустой ссылкой
        sync = SimpleSheetsSync("", "test_requests.csv")
        print(f"✅ SimpleSheetsSync создан успешно")
        print(f"   - Sync enabled: {sync.sync_enabled}")
        print(f"   - Spreadsheet URL: {sync.spreadsheet_url}")
        print(f"   - CSV file path: {sync.csv_file_path}")
        
        # Тестируем с реальной ссылкой
        test_url = "https://docs.google.com/spreadsheets/d/test123"
        sync2 = SimpleSheetsSync(test_url, "test_requests2.csv")
        print(f"   - With URL sync enabled: {sync2.sync_enabled}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка инициализации SimpleSheetsSync: {e}")
        return False


async def test_csv_export():
    """Тест экспорта в CSV"""
    print("\n🧪 Тест 2: Экспорт в CSV")
    
    try:
        sync = SimpleSheetsSync("", "test_export.csv")
        
        # Тестовые данные
        test_requests = [
            {
                'id': 1,
                'created_at': '2024-12-07 10:30:00',
                'status': 'Новая',
                'category': 'Электрика',
                'address': 'ул. Тестовая, 1',
                'description': 'Тестовая заявка 1',
                'urgency': 'Обычная',
                'applicant_id': 1,
                'applicant_name': 'Тест Пользователь 1',
                'executor_id': None,
                'executor_name': '',
                'assigned_at': '',
                'completed_at': '',
                'comments': '',
                'photo_urls': ''
            },
            {
                'id': 2,
                'created_at': '2024-12-07 11:00:00',
                'status': 'В работе',
                'category': 'Сантехника',
                'address': 'ул. Тестовая, 2',
                'description': 'Тестовая заявка 2',
                'urgency': 'Срочная',
                'applicant_id': 2,
                'applicant_name': 'Тест Пользователь 2',
                'executor_id': 3,
                'executor_name': 'Тест Исполнитель',
                'assigned_at': '2024-12-07 11:30:00',
                'completed_at': '',
                'comments': 'Назначена исполнителю',
                'photo_urls': ''
            }
        ]
        
        # Экспортируем данные
        success = await sync.export_requests_to_csv(test_requests)
        
        if success:
            print(f"✅ Экспорт в CSV успешен")
            
            # Проверяем файл
            csv_path = Path("test_export.csv")
            if csv_path.exists():
                print(f"   - Файл создан: {csv_path}")
                print(f"   - Размер файла: {csv_path.stat().st_size} байт")
                
                # Читаем и проверяем содержимое
                with open(csv_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    print(f"   - Количество строк: {len(lines)}")
                    print(f"   - Заголовки: {lines[0].strip()}")
                
                return True
            else:
                print(f"❌ Файл не создан")
                return False
        else:
            print(f"❌ Экспорт не удался")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка экспорта в CSV: {e}")
        return False


async def test_add_request():
    """Тест добавления заявки"""
    print("\n🧪 Тест 3: Добавление заявки")
    
    try:
        sync = SimpleSheetsSync("", "test_add.csv")
        
        # Добавляем заявку
        new_request = {
            'id': 3,
            'created_at': '2024-12-07 12:00:00',
            'status': 'Новая',
            'category': 'Отопление',
            'address': 'ул. Тестовая, 3',
            'description': 'Новая тестовая заявка',
            'urgency': 'Обычная',
            'applicant_id': 4,
            'applicant_name': 'Новый Пользователь',
            'executor_id': None,
            'executor_name': '',
            'assigned_at': '',
            'completed_at': '',
            'comments': '',
            'photo_urls': ''
        }
        
        success = await sync.add_request_to_csv(new_request)
        
        if success:
            print(f"✅ Заявка добавлена успешно")
            
            # Проверяем файл
            csv_path = Path("test_add.csv")
            if csv_path.exists():
                with open(csv_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    print(f"   - Всего строк: {len(lines)}")
                    print(f"   - Последняя строка: {lines[-1].strip()}")
                
                return True
            else:
                print(f"❌ Файл не создан")
                return False
        else:
            print(f"❌ Добавление не удалось")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка добавления заявки: {e}")
        return False


async def test_update_request():
    """Тест обновления заявки"""
    print("\n🧪 Тест 4: Обновление заявки")
    
    try:
        sync = SimpleSheetsSync("", "test_update.csv")
        
        # Сначала создаем файл с данными
        initial_requests = [
            {
                'id': 1,
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
        ]
        
        await sync.export_requests_to_csv(initial_requests)
        
        # Обновляем заявку
        changes = {
            'status': 'В работе',
            'executor_id': 2,
            'executor_name': 'Новый Исполнитель',
            'comments': 'Заявка взята в работу'
        }
        
        success = await sync.update_request_in_csv(1, changes)
        
        if success:
            print(f"✅ Заявка обновлена успешно")
            
            # Проверяем результат
            csv_path = Path("test_update.csv")
            with open(csv_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if len(lines) >= 2:
                    updated_line = lines[1].strip()
                    print(f"   - Обновленная строка: {updated_line}")
                    
                    # Проверяем, что статус изменился
                    if 'В работе' in updated_line:
                        print(f"   - Статус обновлен корректно")
                        return True
                    else:
                        print(f"   - Статус не обновлен")
                        return False
                else:
                    print(f"   - Файл пустой")
                    return False
        else:
            print(f"❌ Обновление не удалось")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка обновления заявки: {e}")
        return False


async def test_statistics():
    """Тест получения статистики"""
    print("\n🧪 Тест 5: Статистика")
    
    try:
        sync = SimpleSheetsSync("", "test_stats.csv")
        
        # Создаем файл с данными
        test_requests = [
            {
                'id': 1,
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
        ]
        
        await sync.export_requests_to_csv(test_requests)
        
        # Получаем статистику
        stats = await sync.get_statistics()
        
        print(f"✅ Статистика получена")
        print(f"   - Всего заявок: {stats['total_requests']}")
        print(f"   - Размер файла: {stats['file_size']} байт")
        print(f"   - Последнее изменение: {stats['last_modified']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка получения статистики: {e}")
        return False


async def test_backup():
    """Тест создания резервной копии"""
    print("\n🧪 Тест 6: Резервная копия")
    
    try:
        sync = SimpleSheetsSync("", "test_backup.csv")
        
        # Создаем файл с данными
        test_requests = [
            {
                'id': 1,
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
        ]
        
        await sync.export_requests_to_csv(test_requests)
        
        # Создаем резервную копию
        backup_path = await sync.create_backup()
        
        if backup_path:
            print(f"✅ Резервная копия создана")
            print(f"   - Путь к backup: {backup_path}")
            
            # Проверяем, что файл существует
            backup_file = Path(backup_path)
            if backup_file.exists():
                print(f"   - Backup файл существует")
                print(f"   - Размер backup: {backup_file.stat().st_size} байт")
                return True
            else:
                print(f"   - Backup файл не найден")
                return False
        else:
            print(f"❌ Создание backup не удалось")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка создания backup: {e}")
        return False


async def cleanup_test_files():
    """Очистка тестовых файлов"""
    print("\n🧹 Очистка тестовых файлов")
    
    test_files = [
        "test_export.csv",
        "test_add.csv", 
        "test_update.csv",
        "test_stats.csv",
        "test_backup.csv"
    ]
    
    # Удаляем тестовые файлы
    for file_name in test_files:
        file_path = Path(file_name)
        if file_path.exists():
            file_path.unlink()
            print(f"   - Удален: {file_name}")
    
    # Удаляем backup файлы
    for file_path in Path(".").glob("test_backup_backup_*.csv"):
        file_path.unlink()
        print(f"   - Удален backup: {file_path.name}")


async def main():
    """Основная функция тестирования"""
    print("🚀 Запуск тестов Simple Google Sheets Sync (без API)")
    print("=" * 60)
    
    tests = [
        test_simple_sheets_initialization,
        test_csv_export,
        test_add_request,
        test_update_request,
        test_statistics,
        test_backup
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
    
    # Очищаем тестовые файлы
    await cleanup_test_files()
    
    print("\n" + "=" * 60)
    print(f"📊 Результаты тестирования: {passed}/{total} тестов прошли")
    
    if passed == total:
        print("🎉 Все тесты прошли успешно!")
        print("✅ Simple Google Sheets Sync готов к использованию")
        print("\n📋 Преимущества простого подхода:")
        print("   - Не требует API ключей")
        print("   - Не требует Service Account")
        print("   - Простая настройка")
        print("   - Работает сразу")
        print("\n📋 Следующие шаги:")
        print("   1. Создайте Google Sheets таблицу")
        print("   2. Настройте публичный доступ")
        print("   3. Обновите переменные окружения")
        print("   4. Импортируйте CSV в Google Sheets")
    else:
        print("⚠️  Некоторые тесты не прошли")
        print("🔧 Проверьте конфигурацию и зависимости")
    
    return passed == total


if __name__ == "__main__":
    # Запускаем тесты
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
