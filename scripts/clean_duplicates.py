#!/usr/bin/env python3
"""
Скрипт для очистки дублированных сообщений в поле notes заявки 250917-006
"""

import sys
sys.path.insert(0, '/app')

from uk_management_bot.database.session import get_db
from uk_management_bot.database.models.request import Request

def clean_duplicate_notes():
    """Очистка дублированных записей в notes"""
    db = next(get_db())
    
    try:
        # Получаем заявку 250917-006
        request = db.query(Request).filter(Request.request_number == "250917-006").first()
        
        if not request:
            print("❌ Заявка 250917-006 не найдена")
            return False
        
        if not request.notes:
            print("✅ У заявки нет заметок для очистки")
            return True
        
        print(f"📝 Текущие заметки:\n{request.notes}")
        print(f"\n📏 Длина: {len(request.notes)} символов")
        
        # Разбиваем на строки
        lines = request.notes.split('\n')
        print(f"📊 Всего строк: {len(lines)}")
        
        # Удаляем дубликаты, сохраняя порядок
        seen = set()
        unique_lines = []
        for line in lines:
            if line.strip() and line not in seen:
                seen.add(line)
                unique_lines.append(line)
            elif not line.strip():  # Сохраняем пустые строки для форматирования
                unique_lines.append(line)
        
        # Объединяем обратно
        cleaned_notes = '\n'.join(unique_lines)
        
        # Убираем лишние пустые строки в конце
        cleaned_notes = cleaned_notes.rstrip('\n')
        
        print(f"\n🧹 После очистки:")
        print(f"📝 Очищенные заметки:\n{cleaned_notes}")
        print(f"📏 Новая длина: {len(cleaned_notes)} символов")
        print(f"📊 Строк после очистки: {len(cleaned_notes.split(chr(10)))}")
        
        # Сохраняем изменения
        request.notes = cleaned_notes
        db.commit()
        
        print("✅ Дубликаты удалены, заявка обновлена")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при очистке: {e}")
        return False
    finally:
        db.close()

if __name__ == '__main__':
    success = clean_duplicate_notes()
    sys.exit(0 if success else 1)