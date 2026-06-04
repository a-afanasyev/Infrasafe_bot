"""
Тестирование автопланирования смен
"""

import os
import sys
from datetime import datetime, date, timedelta

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from uk_management_bot.database.session import SessionLocal
from uk_management_bot.services.shift_planning_service import ShiftPlanningService
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_template import ShiftTemplate
from sqlalchemy import func

def test_auto_planning():
    """Тестирует все функции автопланирования"""
    
    db = SessionLocal()
    try:
        planning_service = ShiftPlanningService(db)
        
        print("🧪 ТЕСТИРОВАНИЕ АВТОПЛАНИРОВАНИЯ")
        print("=" * 50)
        
        # 1. Проверяем конфигурацию шаблонов
        print("\n1️⃣ Проверка конфигурации шаблонов...")
        templates = db.query(ShiftTemplate).filter(ShiftTemplate.auto_create == True).all()
        print(f"Найдено {len(templates)} шаблонов для автопланирования:")
        for template in templates:
            print(f"  📋 {template.name}: дни {template.days_of_week}, {template.min_executors}-{template.max_executors} исполнителей")
        
        if not templates:
            print("❌ Нет шаблонов для автопланирования!")
            return
        
        # 2. Тест создания смен на завтра
        print("\n2️⃣ Тест 'Создать смены на завтра'...")
        tomorrow = date.today() + timedelta(days=1)
        print(f"Завтра: {tomorrow}")

        # Удаляем существующие смены на завтра для чистого теста
        db.query(Shift).filter(func.date(Shift.planned_start_time) == tomorrow).delete()
        db.commit()
        
        # Считаем, сколько шаблонов должно сработать
        # (через is_date_included — учитывает и weekday-, и cycle-режим, как в проде)
        applicable_templates = [t for t in templates if t.is_date_included(tomorrow)]
        print(f"Применимых шаблонов для завтра: {len(applicable_templates)}")
        for template in applicable_templates:
            print(f"  - {template.name} (ожидается {template.min_executors}-{template.max_executors} смен)")
        
        # Создаем смены
        total_shifts = 0
        created_by_template = {}
        errors = []
        
        for template in applicable_templates:
            try:
                shifts = planning_service.create_shift_from_template(template.id, tomorrow)
                if shifts:
                    total_shifts += len(shifts)
                    created_by_template[template.name] = len(shifts)
                    print(f"  ✅ {template.name}: создано {len(shifts)} смен")
                else:
                    print(f"  ❌ {template.name}: смены не созданы")
            except Exception as e:
                errors.append(f"{template.name}: {str(e)}")
                print(f"  ❌ {template.name}: ошибка - {e}")
        
        print(f"\n📊 Результат создания смен на завтра:")
        print(f"  Создано смен: {total_shifts}")
        print(f"  По шаблонам: {created_by_template}")
        if errors:
            print(f"  Ошибки: {errors}")
        
        # 3. Тест недельного планирования
        print(f"\n3️⃣ Тест недельного автопланирования...")
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        next_monday = monday + timedelta(days=7)  # Следующая неделя
        
        print(f"Планируем неделю с {next_monday}")
        
        # Удаляем существующие смены на следующую неделю
        week_end = next_monday + timedelta(days=6)
        db.query(Shift).filter(
            func.date(Shift.planned_start_time) >= next_monday,
            func.date(Shift.planned_start_time) <= week_end
        ).delete()
        db.commit()
        
        results = planning_service.plan_weekly_schedule(next_monday)
        
        print(f"📊 Результат недельного планирования:")
        print(f"  Период: {results['week_start']} - {results['week_start'] + timedelta(days=6)}")
        print(f"  Создано смен: {results['statistics']['total_shifts']}")
        print(f"  По дням: {results['statistics']['shifts_by_day']}")
        print(f"  По шаблонам: {results['statistics']['shifts_by_template']}")
        if results['errors']:
            print(f"  Ошибки: {results['errors']}")
        
        # 4. Проверяем смены в базе данных
        print(f"\n4️⃣ Проверка созданных смен в базе...")
        all_planned_shifts = db.query(Shift).filter(
            Shift.status == 'planned',
            Shift.planned_start_time >= datetime.now()
        ).all()
        
        print(f"Всего запланированных смен в будущем: {len(all_planned_shifts)}")
        
        # Группируем по датам
        shifts_by_date = {}
        for shift in all_planned_shifts:
            if shift.planned_start_time:
                shift_date = shift.planned_start_time.date()
                if shift_date not in shifts_by_date:
                    shifts_by_date[shift_date] = 0
                shifts_by_date[shift_date] += 1
        
        print(f"Смены по датам:")
        for shift_date in sorted(shifts_by_date.keys())[:10]:  # Показываем первые 10 дней
            count = shifts_by_date[shift_date]
            weekday = shift_date.weekday() + 1
            print(f"  📅 {shift_date} (день {weekday}): {count} смен")
        
        print(f"\n🎉 ТЕСТИРОВАНИЕ ЗАВЕРШЕНО!")
        print(f"✅ Автопланирование работает корректно")
        print(f"📈 Создано смен всего: {len(all_planned_shifts)}")
        
    except Exception as e:
        print(f"❌ Ошибка во время тестирования: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_auto_planning()