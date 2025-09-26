"""
Тест недельного планирования
"""

import os
import sys
from datetime import datetime, date, timedelta

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from uk_management_bot.database.session import SessionLocal
from uk_management_bot.database.models.shift import Shift
from sqlalchemy import func

def test_weekly_planning():
    """Тестирует отображение смен в недельном планировании"""
    
    db = SessionLocal()
    try:
        tomorrow = date.today() + timedelta(days=1)
        
        # Проверяем смены на завтра
        print(f"🔍 Проверка смен на {tomorrow}...")
        shifts_on_date = db.query(Shift).filter(
            func.date(Shift.planned_start_time) == tomorrow
        ).all()
        
        print(f"✅ Найдено {len(shifts_on_date)} смен на {tomorrow}:")
        for shift in shifts_on_date:
            print(f"  📅 Смена ID {shift.id}:")
            print(f"     Время: {shift.planned_start_time} - {shift.planned_end_time}")
            print(f"     Статус: {shift.status}")
            print(f"     Исполнитель: {shift.user_id}")
            print(f"     Шаблон: {shift.shift_template_id}")
        
        # Проверяем все смены со статусом 'planned'
        print(f"\n🔍 Все запланированные смены:")
        planned_shifts = db.query(Shift).filter(Shift.status == 'planned').all()
        print(f"✅ Найдено {len(planned_shifts)} запланированных смен:")
        for shift in planned_shifts:
            print(f"  📅 Смена ID {shift.id} на {shift.planned_start_time.date() if shift.planned_start_time else 'Не установлено'}")
            
        if len(shifts_on_date) > 0:
            print(f"\n🎉 Смены на {tomorrow} найдены! Недельное планирование должно показать {len(shifts_on_date)} смен.")
        else:
            print(f"\n❌ Нет смен на {tomorrow}. Проверьте создание смен.")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_weekly_planning()