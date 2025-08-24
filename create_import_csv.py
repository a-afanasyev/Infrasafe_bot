#!/usr/bin/env python3
"""
Скрипт для создания CSV файла готового к импорту в Google Sheets

Создает файл requests_export.csv в корне проекта для быстрого импорта.
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


async def create_import_csv():
    """Создание CSV файла для импорта"""
    print("🚀 Создание CSV файла для импорта в Google Sheets")
    print("=" * 60)
    
    # Создаем экземпляр синхронизации
    csv_file = "requests_export.csv"
    sync = SimpleSheetsSync("", csv_file)
    
    # Получаем данные из базы
    db = next(get_db())
    
    # Получаем все заявки
    requests = db.query(Request).all()
    
    print(f"📊 Найдено заявок в базе: {len(requests)}")
    
    if not requests:
        print("❌ База данных пуста")
        return False
    
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
            'id': request.id,
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
        print("✅ CSV файл успешно создан!")
        
        # Показываем информацию о файле
        csv_path = Path(csv_file)
        if csv_path.exists():
            file_size = csv_path.stat().st_size
            print(f"\n📁 Информация о файле:")
            print(f"   - Имя файла: {csv_file}")
            print(f"   - Размер: {file_size} байт")
            print(f"   - Путь: {csv_path.absolute()}")
            
            # Показываем первые строки
            with open(csv_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                print(f"   - Всего строк: {len(lines)}")
                
                if len(lines) > 0:
                    print(f"   - Заголовки: {lines[0].strip()}")
                
                if len(lines) > 1:
                    print(f"   - Первая заявка: {lines[1].strip()[:100]}...")
        
        print(f"\n🎯 Файл готов к импорту!")
        print(f"📋 Следующие шаги:")
        print(f"   1. Откройте Google Sheets")
        print(f"   2. Создайте новую таблицу")
        print(f"   3. Импортируйте файл {csv_file}")
        print(f"   4. Следуйте инструкции в GOOGLE_SHEETS_IMPORT_GUIDE.md")
        
        return True
    else:
        print("❌ Ошибка создания CSV файла")
        return False


async def show_import_instructions():
    """Показать краткие инструкции по импорту"""
    print(f"\n📋 КРАТКАЯ ИНСТРУКЦИЯ ПО ИМПОРТУ:")
    print("=" * 50)
    
    print(f"1️⃣ Откройте Google Sheets")
    print(f"   https://sheets.google.com")
    
    print(f"\n2️⃣ Создайте новую таблицу")
    print(f"   - Нажмите '+' для создания")
    print(f"   - Назовите: 'UK Management - Заявки'")
    
    print(f"\n3️⃣ Импортируйте CSV файл")
    print(f"   - Файл → Импорт → Загрузить")
    print(f"   - Выберите: {Path('requests_export.csv').absolute()}")
    print(f"   - Настройки: Запятая, UTF-8")
    
    print(f"\n4️⃣ Проверьте результат")
    print(f"   - Все колонки на месте")
    print(f"   - Данные читаемы")
    print(f"   - Количество строк корректно")
    
    print(f"\n📖 Подробная инструкция: GOOGLE_SHEETS_IMPORT_GUIDE.md")


async def main():
    """Основная функция"""
    try:
        # Создаем CSV файл
        success = await create_import_csv()
        
        if success:
            # Показываем инструкции
            await show_import_instructions()
            
            print(f"\n🎉 Готово! Файл {Path('requests_export.csv').absolute()} создан")
            print(f"📊 Теперь можете импортировать его в Google Sheets")
        else:
            print(f"\n❌ Не удалось создать CSV файл")
            print(f"🔧 Проверьте подключение к базе данных")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        print(f"🔧 Убедитесь что база данных доступна")


if __name__ == "__main__":
    # Запускаем создание CSV
    asyncio.run(main())

