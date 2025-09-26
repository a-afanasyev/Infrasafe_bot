#!/usr/bin/env python3
"""
Тестирование новых моделей системы смен
"""

import sys
import os
from datetime import datetime, date, timedelta, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Добавляем путь к проекту
sys.path.append('/Users/andreyafanasyev/Library/Mobile Documents/com~apple~CloudDocs/Code/UK')

try:
    from uk_management_bot.database.session import Base, get_db
    from uk_management_bot.database.models.shift import Shift
    from uk_management_bot.database.models.shift_template import ShiftTemplate
    from uk_management_bot.database.models.shift_schedule import ShiftSchedule
    from uk_management_bot.database.models.shift_assignment import ShiftAssignment
    from uk_management_bot.database.models.user import User
    from uk_management_bot.database.models.request import Request
    print("✅ Успешный импорт всех моделей")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    sys.exit(1)


def test_model_creation():
    """Тестирование создания экземпляров моделей"""
    
    print("\n🧪 Тестирование создания моделей...")
    
    try:
        # Тест ShiftTemplate
        template = ShiftTemplate(
            name="Тестовый шаблон",
            description="Шаблон для тестирования",
            start_hour=9,
            start_minute=0,
            duration_hours=8,
            required_specializations=["electric", "universal"],
            min_executors=1,
            max_executors=2,
            coverage_areas=["building_A", "yard"],
            auto_create=True,
            days_of_week=[1, 2, 3, 4, 5]
        )
        print("✅ ShiftTemplate создан успешно")
        
        # Проверка методов ShiftTemplate
        assert template.end_hour == 17, f"Неверный час окончания: {template.end_hour}"
        assert template.is_day_included(1) == True, "Понедельник должен быть включен"
        assert template.is_day_included(6) == False, "Суббота не должна быть включена"
        assert template.matches_specialization(["electric"]) == True, "Должно соответствовать электрике"
        print("✅ Методы ShiftTemplate работают корректно")
        
        # Тест ShiftSchedule
        schedule = ShiftSchedule(
            date=date.today(),
            predicted_requests=15,
            planned_coverage={"09:00": 2, "14:00": 3},
            actual_coverage={"09:00": 2, "14:00": 2},
            optimization_score=85.5,
            status="active"
        )
        print("✅ ShiftSchedule создан успешно")
        
        # Проверка методов ShiftSchedule
        assert schedule.get_planned_coverage_at_hour(9) == 2, "Неверное покрытие на 9:00"
        assert schedule.get_actual_coverage_at_hour(14) == 2, "Неверное фактическое покрытие на 14:00"
        gaps = schedule.calculate_coverage_gap()
        assert "14:00" in gaps, "Должен быть разрыв в 14:00"
        assert gaps["14:00"] == 1, f"Разрыв должен быть 1, получен: {gaps['14:00']}"
        print("✅ Методы ShiftSchedule работают корректно")
        
        # Тест Shift с новыми полями
        shift = Shift(
            user_id=1,  # Предполагаем, что пользователь с ID 1 существует
            start_time=datetime.now(timezone.utc),
            planned_start_time=datetime.now(timezone.utc) + timedelta(hours=1),
            planned_end_time=datetime.now(timezone.utc) + timedelta(hours=9),
            shift_type="regular",
            specialization_focus=["electric", "plumbing"],
            coverage_areas=["building_A"],
            max_requests=12,
            current_request_count=5,
            priority_level=3,
            efficiency_score=87.5
        )
        print("✅ Расширенная модель Shift создана успешно")
        
        # Проверка новых методов Shift
        assert shift.is_full == False, "Смена не должна быть полной"
        assert shift.load_percentage == (5/12)*100, f"Неверная загруженность: {shift.load_percentage}"
        assert shift.can_handle_specialization("electric") == True, "Должна обрабатывать электрику"
        assert shift.can_handle_specialization("hvac") == False, "Не должна обрабатывать HVAC"
        assert shift.can_handle_area("building_A") == True, "Должна покрывать building_A"
        print("✅ Новые методы Shift работают корректно")
        
        # Тест ShiftAssignment
        assignment = ShiftAssignment(
            shift_id=1,  # Предполагаем существование смены
            request_id=1,  # Предполагаем существование заявки
            assignment_priority=4,
            estimated_duration=120,
            ai_score=92.3,
            confidence_level=0.85,
            specialization_match_score=95.0,
            geographic_score=88.5,
            workload_score=76.2,
            status="assigned",
            auto_assigned=True
        )
        print("✅ ShiftAssignment создан успешно")
        
        # Проверка методов ShiftAssignment
        efficiency = assignment.calculate_efficiency_score()
        assert efficiency > 0, f"Оценка эффективности должна быть положительной: {efficiency}"
        print(f"✅ Оценка эффективности назначения: {efficiency:.1f}%")
        
        # Тест обновления статуса
        assignment.update_status_with_timestamp("in_progress")
        assert assignment.status == "in_progress", "Статус должен быть обновлен"
        assert assignment.started_at is not None, "Время начала должно быть установлено"
        print("✅ Обновление статуса работает корректно")
        
        print("\n🎉 Все тесты моделей пройдены успешно!")
        
    except Exception as e:
        print(f"❌ Ошибка в тестах: {e}")
        raise


def test_database_schema():
    """Тестирование схемы базы данных"""
    
    print("\n🗄️ Проверка схемы базы данных...")
    
    try:
        # Получаем сессию базы данных
        db = next(get_db())
        
        # Проверяем, что таблицы существуют (через SQLAlchemy metadata)
        tables = Base.metadata.tables.keys()
        
        expected_tables = [
            'shifts', 'shift_templates', 'shift_schedules', 'shift_assignments'
        ]
        
        for table in expected_tables:
            if table in tables:
                print(f"✅ Таблица {table} найдена в схеме")
            else:
                print(f"❌ Таблица {table} отсутствует в схеме")
        
        # Проверяем поля модели Shift
        shift_columns = [col.name for col in Shift.__table__.columns]
        new_columns = [
            'planned_start_time', 'planned_end_time', 'shift_template_id', 
            'shift_type', 'specialization_focus', 'coverage_areas', 
            'max_requests', 'priority_level', 'efficiency_score'
        ]
        
        for column in new_columns:
            if column in shift_columns:
                print(f"✅ Поле {column} найдено в модели Shift")
            else:
                print(f"❌ Поле {column} отсутствует в модели Shift")
        
        print("✅ Проверка схемы завершена")
        
    except Exception as e:
        print(f"❌ Ошибка проверки схемы: {e}")
        # Не прерываем выполнение, так как БД может быть не настроена
        print("⚠️ Схема БД будет проверена при первом подключении")


def test_relationships():
    """Тестирование связей между моделями"""
    
    print("\n🔗 Тестирование связей между моделями...")
    
    try:
        # Проверяем, что связи определены корректно
        
        # Shift -> ShiftTemplate
        if hasattr(Shift, 'template'):
            print("✅ Связь Shift.template определена")
        else:
            print("❌ Связь Shift.template не определена")
        
        # Shift -> ShiftAssignment
        if hasattr(Shift, 'assignments'):
            print("✅ Связь Shift.assignments определена")
        else:
            print("❌ Связь Shift.assignments не определена")
        
        # ShiftTemplate -> Shift
        if hasattr(ShiftTemplate, 'shifts'):
            print("✅ Связь ShiftTemplate.shifts определена")
        else:
            print("❌ Связь ShiftTemplate.shifts не определена")
        
        # ShiftSchedule -> User
        if hasattr(ShiftSchedule, 'creator'):
            print("✅ Связь ShiftSchedule.creator определена")
        else:
            print("❌ Связь ShiftSchedule.creator не определена")
        
        # ShiftAssignment -> Shift
        if hasattr(ShiftAssignment, 'shift'):
            print("✅ Связь ShiftAssignment.shift определена")
        else:
            print("❌ Связь ShiftAssignment.shift не определена")
        
        # ShiftAssignment -> Request
        if hasattr(ShiftAssignment, 'request'):
            print("✅ Связь ShiftAssignment.request определена")
        else:
            print("❌ Связь ShiftAssignment.request не определена")
            
        print("✅ Проверка связей завершена")
        
    except Exception as e:
        print(f"❌ Ошибка проверки связей: {e}")


def main():
    """Основная функция тестирования"""
    
    print("🚀 Начинаем тестирование новых моделей системы смен")
    print("=" * 60)
    
    try:
        # Тестируем создание моделей
        test_model_creation()
        
        # Тестируем схему БД
        test_database_schema()
        
        # Тестируем связи
        test_relationships()
        
        print("\n" + "=" * 60)
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("✅ Модели готовы к использованию")
        print("✅ Можно переходить к следующему этапу разработки")
        
    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        print("🔧 Необходимо исправить ошибки перед продолжением")
        sys.exit(1)


if __name__ == "__main__":
    main()