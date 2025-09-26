#!/usr/bin/env python3
"""
Тестовый скрипт для проверки выгрузки данных

Демонстрирует работу SimpleSheetsSync с реальными данными из базы.
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime

# Добавляем корневую директорию проекта в PYTHONPATH
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "uk_management_bot"))

from integrations.simple_sheets_sync import SimpleSheetsSync
from database.session import get_db
from database.models.request import Request
from database.models.user import User
from sqlalchemy.orm import Session


async def test_real_data_export():
    """Тест выгрузки реальных данных из базы"""
    print("🧪 Тест 1: Выгрузка реальных данных из базы")
    
    try:
        # Создаем экземпляр синхронизации
        sync = SimpleSheetsSync("", "test_real_data.csv")
        
        # Получаем данные из базы
        db = next(get_db())
        
        # Получаем все заявки с информацией о пользователях
        requests = db.query(Request).all()
        
        print(f"   - Найдено заявок в базе: {len(requests)}")
        
        if not requests:
            print("   - База данных пуста, создаем тестовые данные...")
            await create_test_data(db)
            requests = db.query(Request).all()
            print(f"   - Создано тестовых заявок: {len(requests)}")
        
        # Подготавливаем данные для экспорта
        export_data = []
        for request in requests:
            # Получаем информацию о заявителе
            applicant = db.query(User).filter(User.id == request.user_id).first()
            if applicant:
                applicant_name = f"{applicant.first_name or ''} {applicant.last_name or ''}".strip()
                if not applicant_name:
                    applicant_name = f"User_{request.user_id}"
            else:
                applicant_name = f"User_{request.user_id}"
            
            # Получаем информацию об исполнителе
            executor_name = ""
            if request.executor_id:
                executor = db.query(User).filter(User.id == request.executor_id).first()
                if executor:
                    executor_name = f"{executor.first_name or ''} {executor.last_name or ''}".strip()
                    if not executor_name:
                        executor_name = f"User_{request.executor_id}"
                else:
                    executor_name = f"User_{request.executor_id}"
            
            # Формируем данные заявки
            request_data = {
                'request_number': request.request_number,
                'created_at': request.created_at.strftime("%Y-%m-%d %H:%M:%S") if request.created_at else '',
                'status': request.status,
                'category': request.category,
                'address': request.address,
                'description': request.description,
                'urgency': request.urgency,
                'applicant_id': request.user_id,
                'applicant_name': applicant_name,
                'executor_id': request.executor_id,
                'executor_name': executor_name,
                'assigned_at': '',  # Поле не существует в модели
                'completed_at': request.completed_at.strftime("%Y-%m-%d %H:%M:%S") if request.completed_at else '',
                'comments': request.notes or '',
                'photo_urls': ','.join(request.media_files) if request.media_files else ''
            }
            
            export_data.append(request_data)
        
        # Экспортируем данные
        success = await sync.export_requests_to_csv(export_data)
        
        if success:
            print(f"✅ Данные успешно экспортированы в CSV")
            
            # Проверяем файл
            csv_path = Path("test_real_data.csv")
            if csv_path.exists():
                print(f"   - Файл создан: {csv_path}")
                print(f"   - Размер файла: {csv_path.stat().st_size} байт")
                
                # Показываем первые несколько строк
                with open(csv_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    print(f"   - Всего строк: {len(lines)}")
                    
                    if len(lines) > 0:
                        print(f"   - Заголовки: {lines[0].strip()}")
                    
                    if len(lines) > 1:
                        print(f"   - Первая заявка: {lines[1].strip()}")
                    
                    if len(lines) > 2:
                        print(f"   - Вторая заявка: {lines[2].strip()}")
                
                return True
            else:
                print(f"❌ Файл не создан")
                return False
        else:
            print(f"❌ Экспорт не удался")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка выгрузки данных: {e}")
        return False


async def create_test_data(db: Session):
    """Создание тестовых данных в базе"""
    try:
        # Создаем тестовых пользователей
        users = []
        for i in range(1, 4):
            user = User(
                id=i,
                telegram_id=1000 + i,
                first_name=f"Тест",
                last_name=f"Пользователь {i}",
                phone=f"+7 999 123-45-{i:02d}",
                status="approved",
                role="applicant"
            )
            users.append(user)
        
        # Добавляем пользователей в базу
        for user in users:
            db.add(user)
        
        # Создаем тестовые заявки
        requests = [
            Request(
                id=1,
                user_id=1,
                category="Электрика",
                address="ул. Тестовая, 1",
                description="Не работает освещение в подъезде",
                urgency="Срочная",
                status="Новая",
                created_at=datetime.now()
            ),
            Request(
                id=2,
                user_id=2,
                category="Сантехника",
                address="ул. Тестовая, 2",
                description="Протекает кран в квартире",
                urgency="Обычная",
                status="В работе",
                executor_id=3,
                created_at=datetime.now()
            ),
            Request(
                id=3,
                user_id=3,
                category="Отопление",
                address="ул. Тестовая, 3",
                description="Холодные батареи",
                urgency="Срочная",
                status="Выполнена",
                executor_id=2,
                completed_at=datetime.now(),
                notes="Работа выполнена, отопление восстановлено",
                created_at=datetime.now()
            )
        ]
        
        # Добавляем заявки в базу
        for request in requests:
            db.add(request)
        
        # Сохраняем изменения
        db.commit()
        
        print(f"   - Создано тестовых пользователей: {len(users)}")
        print(f"   - Создано тестовых заявок: {len(requests)}")
        
    except Exception as e:
        print(f"   - Ошибка создания тестовых данных: {e}")
        db.rollback()


async def test_statistics():
    """Тест получения статистики"""
    print("\n🧪 Тест 2: Статистика выгрузки")
    
    try:
        sync = SimpleSheetsSync("", "test_real_data.csv")
        
        # Получаем статистику
        stats = await sync.get_statistics()
        
        print(f"✅ Статистика получена")
        print(f"   - Всего заявок в CSV: {stats['total_requests']}")
        print(f"   - Размер файла: {stats['file_size']} байт")
        print(f"   - Последнее изменение: {stats['last_modified']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка получения статистики: {e}")
        return False


async def test_backup():
    """Тест создания резервной копии"""
    print("\n🧪 Тест 3: Резервная копия")
    
    try:
        sync = SimpleSheetsSync("", "test_real_data.csv")
        
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


async def show_csv_content():
    """Показать содержимое CSV файла"""
    print("\n📊 Содержимое CSV файла:")
    print("=" * 80)
    
    try:
        csv_path = Path("test_real_data.csv")
        if csv_path.exists():
            with open(csv_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
                for i, line in enumerate(lines):
                    if i == 0:
                        print(f"📋 ЗАГОЛОВКИ: {line.strip()}")
                    else:
                        print(f"📝 Заявка {i}: {line.strip()}")
                        
                    if i >= 5:  # Показываем только первые 5 строк
                        print(f"... и еще {len(lines) - 5} строк")
                        break
        else:
            print("❌ CSV файл не найден")
            
    except Exception as e:
        print(f"❌ Ошибка чтения CSV: {e}")


async def cleanup_test_files():
    """Очистка тестовых файлов"""
    print("\n🧹 Очистка тестовых файлов")
    
    test_files = [
        "test_real_data.csv"
    ]
    
    # Удаляем тестовые файлы
    for file_name in test_files:
        file_path = Path(file_name)
        if file_path.exists():
            file_path.unlink()
            print(f"   - Удален: {file_name}")
    
    # Удаляем backup файлы
    for file_path in Path(".").glob("test_real_data_backup_*.csv"):
        file_path.unlink()
        print(f"   - Удален backup: {file_path.name}")


async def main():
    """Основная функция тестирования"""
    print("🚀 Проверка выгрузки данных из UK Management Bot")
    print("=" * 60)
    
    tests = [
        test_real_data_export,
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
    
    # Показываем содержимое CSV
    await show_csv_content()
    
    # Очищаем тестовые файлы
    await cleanup_test_files()
    
    print("\n" + "=" * 60)
    print(f"📊 Результаты тестирования: {passed}/{total} тестов прошли")
    
    if passed == total:
        print("🎉 Все тесты прошли успешно!")
        print("✅ Выгрузка данных работает корректно")
        print("\n📋 Что было протестировано:")
        print("   - Выгрузка реальных данных из базы")
        print("   - Экспорт в CSV формат")
        print("   - Статистика синхронизации")
        print("   - Создание резервных копий")
        print("\n📋 Следующие шаги:")
        print("   1. Настройте Google Sheets таблицу")
        print("   2. Обновите переменные окружения")
        print("   3. Импортируйте CSV в Google Sheets")
        print("   4. Настройте автоматический импорт")
    else:
        print("⚠️  Некоторые тесты не прошли")
        print("🔧 Проверьте конфигурацию и базу данных")
    
    return passed == total


if __name__ == "__main__":
    # Запускаем тесты
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
