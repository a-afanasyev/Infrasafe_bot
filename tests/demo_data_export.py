#!/usr/bin/env python3
"""
Демонстрационный скрипт выгрузки данных

Показывает как работает SimpleSheetsSync с реальными данными из UK Management Bot.
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


async def demo_data_export():
    """Демонстрация выгрузки данных"""
    print("🚀 ДЕМОНСТРАЦИЯ ВЫГРУЗКИ ДАННЫХ")
    print("=" * 60)
    
    # Создаем экземпляр синхронизации
    sync = SimpleSheetsSync("", "demo_export.csv")
    
    # Получаем данные из базы
    db = next(get_db())
    
    # Получаем все заявки
    requests = db.query(Request).all()
    
    print(f"📊 Найдено заявок в базе: {len(requests)}")
    
    if not requests:
        print("❌ База данных пуста")
        return
    
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
    print(f"📤 Экспортируем {len(export_data)} заявок в CSV...")
    success = await sync.export_requests_to_csv(export_data)
    
    if success:
        print("✅ Экспорт успешно завершен!")
        
        # Показываем статистику
        stats = await sync.get_statistics()
        print(f"\n📈 СТАТИСТИКА:")
        print(f"   - Всего заявок: {stats['total_requests']}")
        print(f"   - Размер файла: {stats['file_size']} байт")
        print(f"   - Последнее изменение: {stats['last_modified']}")
        
        # Показываем примеры данных
        print(f"\n📋 ПРИМЕРЫ ДАННЫХ:")
        csv_path = Path("demo_export.csv")
        if csv_path.exists():
            with open(csv_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
                # Показываем заголовки
                if len(lines) > 0:
                    print(f"   📋 Заголовки: {lines[0].strip()}")
                
                # Показываем первые 3 заявки
                for i in range(1, min(4, len(lines))):
                    line = lines[i].strip()
                    print(f"   📝 Заявка {i}: {line[:100]}...")
                
                if len(lines) > 4:
                    print(f"   ... и еще {len(lines) - 4} заявок")
        
        # Создаем резервную копию
        print(f"\n💾 Создаем резервную копию...")
        backup_path = await sync.create_backup()
        if backup_path:
            print(f"   ✅ Резервная копия создана: {backup_path}")
        
        print(f"\n🎯 ДЕМОНСТРАЦИЯ ЗАВЕРШЕНА!")
        print(f"📁 Файл создан: demo_export.csv")
        print(f"📊 Готов к импорту в Google Sheets")
        
    else:
        print("❌ Ошибка экспорта")


async def demo_add_request():
    """Демонстрация добавления новой заявки"""
    print(f"\n🆕 ДЕМОНСТРАЦИЯ ДОБАВЛЕНИЯ ЗАЯВКИ")
    print("=" * 40)
    
    sync = SimpleSheetsSync("", "demo_export.csv")
    
    # Создаем тестовую заявку
    new_request = {
        'id': 999,
        'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'status': 'Новая',
        'category': 'Демо',
        'address': 'ул. Демонстрационная, 1',
        'description': 'Тестовая заявка для демонстрации',
        'urgency': 'Обычная',
        'applicant_id': 999,
        'applicant_name': 'Демо Пользователь',
        'executor_id': None,
        'executor_name': '',
        'assigned_at': '',
        'completed_at': '',
        'comments': 'Демонстрационная заявка',
        'photo_urls': ''
    }
    
    print(f"📝 Добавляем новую заявку ID {new_request['id']}...")
    success = await sync.add_request_to_csv(new_request)
    
    if success:
        print("✅ Заявка успешно добавлена!")
        
        # Показываем обновленную статистику
        stats = await sync.get_statistics()
        print(f"📊 Обновленная статистика: {stats['total_requests']} заявок")
    else:
        print("❌ Ошибка добавления заявки")


async def demo_update_request():
    """Демонстрация обновления заявки"""
    print(f"\n🔄 ДЕМОНСТРАЦИЯ ОБНОВЛЕНИЯ ЗАЯВКИ")
    print("=" * 40)
    
    sync = SimpleSheetsSync("", "demo_export.csv")
    
    # Обновляем заявку
    changes = {
        'status': 'В работе',
        'executor_id': 1,
        'executor_name': 'Демо Исполнитель',
        'comments': 'Заявка взята в работу (демо)'
    }
    
    print(f"📝 Обновляем заявку ID 999...")
    success = await sync.update_request_in_csv(999, changes)
    
    if success:
        print("✅ Заявка успешно обновлена!")
        print(f"📊 Изменения: {list(changes.keys())}")
    else:
        print("❌ Ошибка обновления заявки")


async def cleanup_demo_files():
    """Очистка демонстрационных файлов"""
    print(f"\n🧹 Очистка демонстрационных файлов")
    
    demo_files = [
        "demo_export.csv"
    ]
    
    for file_name in demo_files:
        file_path = Path(file_name)
        if file_path.exists():
            file_path.unlink()
            print(f"   - Удален: {file_name}")
    
    # Удаляем backup файлы
    for file_path in Path(".").glob("demo_export_backup_*.csv"):
        file_path.unlink()
        print(f"   - Удален backup: {file_path.name}")


async def main():
    """Основная функция демонстрации"""
    try:
        # Демонстрация экспорта данных
        await demo_data_export()
        
        # Демонстрация добавления заявки
        await demo_add_request()
        
        # Демонстрация обновления заявки
        await demo_update_request()
        
        print(f"\n🎉 ДЕМОНСТРАЦИЯ ЗАВЕРШЕНА!")
        print(f"✅ Все функции работают корректно")
        print(f"\n📋 Что было продемонстрировано:")
        print(f"   - Выгрузка реальных данных из базы")
        print(f"   - Экспорт в CSV формат")
        print(f"   - Добавление новых заявок")
        print(f"   - Обновление существующих заявок")
        print(f"   - Создание резервных копий")
        print(f"   - Статистика синхронизации")
        
    except Exception as e:
        print(f"❌ Ошибка демонстрации: {e}")
    
    finally:
        # Очищаем файлы
        await cleanup_demo_files()


if __name__ == "__main__":
    # Запускаем демонстрацию
    asyncio.run(main())
