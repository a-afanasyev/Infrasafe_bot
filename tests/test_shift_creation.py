"""
Тестовый скрипт для создания смены из шаблона
"""

import os
import sys
from datetime import datetime, date, timedelta

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from uk_management_bot.database.session import SessionLocal
from uk_management_bot.services.shift_planning_service import ShiftPlanningService

def test_shift_creation():
    """Тестирует создание смены из шаблона"""
    
    db = SessionLocal()
    try:
        shift_service = ShiftPlanningService(db)
        
        # Создаем смену из шаблона "дневной" (id=2) на завтра
        today = date.today()
        tomorrow = today + timedelta(days=1)
        
        print(f"🧪 Создаем смену из шаблона 'дневной' (id=2) на {tomorrow}...")
        
        created_shifts = shift_service.create_shift_from_template(
            template_id=2,
            target_date=tomorrow,
            executor_ids=None  # Автоназначение
        )
        
        if created_shifts:
            print(f"✅ Создано {len(created_shifts)} смен:")
            for shift in created_shifts:
                print(f"  - Смена ID {shift.id}: {shift.planned_start_time} - {shift.planned_end_time}")
                print(f"    Статус: {shift.status}, Исполнитель: {shift.user_id}")
        else:
            print("❌ Смены не созданы")
        
        # Проверяем созданные смены в базе данных
        print(f"\n🔍 Проверяем созданные смены в базе...")
        
        from uk_management_bot.database.models.shift import Shift
        from sqlalchemy import func
        
        shifts_on_date = db.query(Shift).filter(
            func.date(Shift.planned_start_time) == tomorrow
        ).all()
        
        print(f"Смены на {tomorrow}: {len(shifts_on_date)}")
        for shift in shifts_on_date:
            print(f"  📅 Смена ID {shift.id}: {shift.planned_start_time} - {shift.planned_end_time}")
            print(f"    Статус: {shift.status}, Исполнитель: {shift.user_id}")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_shift_creation()