#!/usr/bin/env python3
"""
Скрипт для очистки и форматирования notes в заявке 250917-006
"""

import sys
sys.path.insert(0, '/app')

from uk_management_bot.database.session import get_db
from uk_management_bot.database.models.request import Request

def clean_notes_format():
    """Очистка и форматирование notes"""
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
        
        print(f"📝 Исходные заметки:\n{repr(request.notes)}")
        
        # Разбиваем на строки и убираем лишние пробелы
        lines = request.notes.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Убираем пробелы в начале и конце каждой строки
            cleaned_line = line.strip()
            cleaned_lines.append(cleaned_line)
        
        # Объединяем обратно, убирая лишние пустые строки
        cleaned_notes = '\n'.join(cleaned_lines)
        
        # Убираем множественные переносы строк (больше 2 подряд)
        import re
        cleaned_notes = re.sub(r'\n{3,}', '\n\n', cleaned_notes)
        
        # Убираем пробелы в начале и конце всего текста
        cleaned_notes = cleaned_notes.strip()
        
        print(f"\n🧹 Очищенные заметки:\n{repr(cleaned_notes)}")
        print(f"\n📝 Результат:\n{cleaned_notes}")
        
        # Сохраняем изменения
        request.notes = cleaned_notes
        db.commit()
        
        print("✅ Заметки очищены и отформатированы")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при очистке: {e}")
        return False
    finally:
        db.close()

if __name__ == '__main__':
    success = clean_notes_format()
    sys.exit(0 if success else 1)