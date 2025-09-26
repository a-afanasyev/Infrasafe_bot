#!/usr/bin/env python3
"""
Тест переключения специализаций в шаблонах
"""

import sys
import os
sys.path.append('/app')

from uk_management_bot.database.session import get_db
from uk_management_bot.database.models.shift_template import ShiftTemplate
from sqlalchemy.orm.attributes import flag_modified

def test_specialization_toggle():
    """Тестируем переключение специализаций"""
    
    db = next(get_db())
    
    try:
        # Находим шаблон
        template = db.query(ShiftTemplate).filter(ShiftTemplate.id == 4).first()
        if not template:
            print("❌ Шаблон не найден")
            return
        
        print(f"Шаблон: {template.name}")
        print(f"Начальные специализации: {template.required_specializations}")
        
        # Тестируем добавление специализации
        current_specs = template.required_specializations or []
        test_spec = "plumbing"
        
        print(f"\n🧪 Тестируем добавление '{test_spec}'...")
        
        if test_spec not in current_specs:
            current_specs.append(test_spec)
            template.required_specializations = current_specs
            flag_modified(template, 'required_specializations')
            db.commit()
            print(f"✅ Добавлено. Текущие: {template.required_specializations}")
        else:
            print(f"⏭️ Уже есть в списке")
        
        # Обновляем объект из базы
        db.refresh(template)
        print(f"После обновления из БД: {template.required_specializations}")
        
        # Тестируем удаление специализации
        print(f"\n🧪 Тестируем удаление '{test_spec}'...")
        current_specs = template.required_specializations or []
        
        if test_spec in current_specs:
            current_specs.remove(test_spec)
            template.required_specializations = current_specs
            flag_modified(template, 'required_specializations')
            db.commit()
            print(f"✅ Удалено. Текущие: {template.required_specializations}")
        else:
            print(f"⏭️ Нет в списке")
        
        # Финальная проверка
        db.refresh(template)
        print(f"Финальный результат: {template.required_specializations}")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    test_specialization_toggle()