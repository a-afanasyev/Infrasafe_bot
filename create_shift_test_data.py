#!/usr/bin/env python3
"""
Скрипт для создания тестовых данных для системы смен
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict
import json

# Добавляем путь к проекту
sys.path.append('/Users/andreyafanasyev/Library/Mobile Documents/com~apple~CloudDocs/Code/UK')

from uk_management_bot.database.session import SessionLocal
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_template import ShiftTemplate
from uk_management_bot.database.models.shift_assignment import ShiftAssignment
from uk_management_bot.database.models.shift_schedule import ShiftSchedule
from uk_management_bot.utils.constants import (
    SHIFT_STATUS_PLANNED, SHIFT_STATUS_ACTIVE, SHIFT_STATUS_COMPLETED,
    SHIFT_TYPE_REGULAR, SHIFT_TYPE_EMERGENCY, SHIFT_TYPE_MAINTENANCE,
    SPECIALIZATIONS, ROLE_EXECUTOR, ROLE_MANAGER
)

def create_test_users(db) -> Dict[str, List[User]]:
    """Создает тестовых пользователей"""
    
    test_users = {
        'executors': [],
        'managers': []
    }
    
    # Исполнители с разными специализациями
    executor_data = [
        {
            'name': 'Иван Петров',
            'telegram_id': 1001,
            'phone': '+7901234567',
            'specialization': 'electric'
        },
        {
            'name': 'Сергей Иванов', 
            'telegram_id': 1002,
            'phone': '+7902234567',
            'specialization': 'plumbing'
        },
        {
            'name': 'Алексей Сидоров',
            'telegram_id': 1003,
            'phone': '+7903234567',
            'specialization': 'security'
        },
        {
            'name': 'Михаил Козлов',
            'telegram_id': 1004,
            'phone': '+7904234567',
            'specialization': 'universal'
        },
        {
            'name': 'Николай Морозов',
            'telegram_id': 1005,
            'phone': '+7905234567',
            'specialization': 'maintenance'
        }
    ]
    
    # Создаем исполнителей
    for data in executor_data:
        # Проверяем, существует ли пользователь
        existing_user = db.query(User).filter(User.telegram_id == data['telegram_id']).first()
        if existing_user:
            user = existing_user
            # Обновляем роли если нужно
            roles = json.loads(user.roles) if user.roles else []
            if ROLE_EXECUTOR not in roles:
                roles.append(ROLE_EXECUTOR)
                user.roles = json.dumps(roles)
                user.active_role = ROLE_EXECUTOR
                user.specialization = data['specialization']
        else:
            user = User(
                telegram_id=data['telegram_id'],
                first_name=data['name'].split()[0],
                last_name=data['name'].split()[1] if len(data['name'].split()) > 1 else '',
                phone=data['phone'],
                status='approved',
                roles=json.dumps([ROLE_EXECUTOR]),
                active_role=ROLE_EXECUTOR,
                specialization=data['specialization']
            )
            db.add(user)
        
        test_users['executors'].append(user)
    
    # Менеджеры
    manager_data = [
        {
            'name': 'Елена Константинова',
            'telegram_id': 2001,
            'phone': '+7911234567'
        },
        {
            'name': 'Дмитрий Волков',
            'telegram_id': 2002,
            'phone': '+7912234567'
        }
    ]
    
    for data in manager_data:
        existing_user = db.query(User).filter(User.telegram_id == data['telegram_id']).first()
        if existing_user:
            user = existing_user
            roles = json.loads(user.roles) if user.roles else []
            if ROLE_MANAGER not in roles:
                roles.append(ROLE_MANAGER)
                user.roles = json.dumps(roles)
                user.active_role = ROLE_MANAGER
        else:
            user = User(
                telegram_id=data['telegram_id'],
                first_name=data['name'].split()[0],
                last_name=data['name'].split()[1] if len(data['name'].split()) > 1 else '',
                phone=data['phone'],
                status='approved',
                roles=json.dumps([ROLE_MANAGER]),
                active_role=ROLE_MANAGER
            )
            db.add(user)
        
        test_users['managers'].append(user)
    
    db.commit()
    print(f"✅ Создано {len(test_users['executors'])} исполнителей и {len(test_users['managers'])} менеджеров")
    return test_users

def create_shift_templates(db) -> List[ShiftTemplate]:
    """Создает шаблоны смен"""
    
    templates_data = [
        {
            'name': 'Дневная смена - Электрика',
            'description': 'Дневная смена для электриков',
            'default_start_time': '08:00',
            'default_duration_hours': 8,
            'specialization_requirements': ['electric'],
            'days_of_week': [1, 2, 3, 4, 5],  # Пн-Пт
            'min_executors': 2,
            'max_executors': 4,
            'is_active': True
        },
        {
            'name': 'Ночная смена - Охрана',
            'description': 'Ночная смена охраны',
            'default_start_time': '22:00',
            'default_duration_hours': 10,
            'specialization_requirements': ['security'],
            'days_of_week': [1, 2, 3, 4, 5, 6, 7],  # Каждый день
            'min_executors': 1,
            'max_executors': 2,
            'is_active': True
        },
        {
            'name': 'Аварийная смена - Сантехника',
            'description': 'Экстренная смена для сантехнических работ',
            'default_start_time': '09:00',
            'default_duration_hours': 6,
            'specialization_requirements': ['plumbing'],
            'days_of_week': [6, 7],  # Выходные
            'min_executors': 1,
            'max_executors': 2,
            'is_active': True
        },
        {
            'name': 'Универсальная смена',
            'description': 'Универсальная смена для различных работ',
            'default_start_time': '10:00',
            'default_duration_hours': 8,
            'specialization_requirements': ['universal', 'maintenance'],
            'days_of_week': [1, 2, 3, 4, 5],
            'min_executors': 2,
            'max_executors': 3,
            'is_active': True
        }
    ]
    
    templates = []
    for data in templates_data:
        # Проверяем существующий шаблон
        existing_template = db.query(ShiftTemplate).filter(ShiftTemplate.name == data['name']).first()
        if existing_template:
            template = existing_template
        else:
            template = ShiftTemplate(
                name=data['name'],
                description=data['description'],
                default_start_time=data['default_start_time'],
                default_duration_hours=data['default_duration_hours'],
                specialization_requirements=json.dumps(data['specialization_requirements']),
                days_of_week=json.dumps(data['days_of_week']),
                min_executors=data['min_executors'],
                max_executors=data['max_executors'],
                is_active=data['is_active']
            )
            db.add(template)
        
        templates.append(template)
    
    db.commit()
    print(f"✅ Создано {len(templates)} шаблонов смен")
    return templates

def create_test_shifts(db, executors: List[User], managers: List[User], templates: List[ShiftTemplate]) -> List[Shift]:
    """Создает тестовые смены"""
    
    shifts = []
    now = datetime.now()
    
    # Смены на последнюю неделю (завершенные)
    for i in range(7):
        shift_date = (now - timedelta(days=i+1)).date()
        
        for template in templates[:2]:  # Используем первые 2 шаблона
            shift_start = datetime.combine(
                shift_date,
                datetime.strptime(template.default_start_time, '%H:%M').time()
            )
            shift_end = shift_start + timedelta(hours=template.default_duration_hours)
            
            shift = Shift(
                planned_start_time=shift_start,
                planned_end_time=shift_end,
                actual_start_time=shift_start + timedelta(minutes=5),
                actual_end_time=shift_end - timedelta(minutes=10),
                status=SHIFT_STATUS_COMPLETED,
                shift_type=SHIFT_TYPE_REGULAR,
                created_by_id=managers[0].id,
                template_id=template.id,
                specialization_focus=json.loads(template.specialization_requirements),
                notes=f"Тестовая завершенная смена за {shift_date.strftime('%d.%m.%Y')}",
                location="Офисное здание, этаж 1-5"
            )
            db.add(shift)
            shifts.append(shift)
    
    # Текущие смены (активные и запланированные)
    for i in range(3):
        shift_date = (now + timedelta(days=i)).date()
        
        for j, template in enumerate(templates):
            shift_start = datetime.combine(
                shift_date,
                datetime.strptime(template.default_start_time, '%H:%M').time()
            )
            shift_end = shift_start + timedelta(hours=template.default_duration_hours)
            
            # Определяем статус смены
            if shift_date == now.date() and j == 0:
                status = SHIFT_STATUS_ACTIVE
                actual_start = shift_start
            elif shift_date == now.date() and shift_start <= now:
                status = SHIFT_STATUS_ACTIVE  
                actual_start = shift_start
            else:
                status = SHIFT_STATUS_PLANNED
                actual_start = None
            
            shift = Shift(
                planned_start_time=shift_start,
                planned_end_time=shift_end,
                actual_start_time=actual_start,
                status=status,
                shift_type=SHIFT_TYPE_REGULAR if j < 3 else SHIFT_TYPE_MAINTENANCE,
                created_by_id=managers[j % len(managers)].id,
                template_id=template.id,
                specialization_focus=json.loads(template.specialization_requirements),
                notes=f"Тестовая смена на {shift_date.strftime('%d.%m.%Y')}",
                location="Офисное здание, этажи 1-10"
            )
            db.add(shift)
            shifts.append(shift)
    
    # Экстренная смена
    emergency_start = now + timedelta(hours=2)
    emergency_shift = Shift(
        planned_start_time=emergency_start,
        planned_end_time=emergency_start + timedelta(hours=4),
        status=SHIFT_STATUS_PLANNED,
        shift_type=SHIFT_TYPE_EMERGENCY,
        created_by_id=managers[0].id,
        specialization_focus=["universal"],
        notes="Экстренная смена - авария в здании",
        location="Аварийный объект, подъезд 3",
        priority_level="high"
    )
    db.add(emergency_shift)
    shifts.append(emergency_shift)
    
    db.commit()
    print(f"✅ Создано {len(shifts)} тестовых смен")
    return shifts

def create_shift_assignments(db, shifts: List[Shift], executors: List[User]):
    """Создает назначения исполнителей на смены"""
    
    assignments = []
    
    for shift in shifts:
        # Определяем исполнителей по специализации
        suitable_executors = []
        shift_specializations = shift.specialization_focus or []
        
        for executor in executors:
            if (executor.specialization in shift_specializations or 
                'universal' in shift_specializations or 
                executor.specialization == 'universal'):
                suitable_executors.append(executor)
        
        if not suitable_executors:
            suitable_executors = executors  # Fallback
        
        # Назначаем 1-2 исполнителей на смену
        assigned_count = min(2, len(suitable_executors))
        for i in range(assigned_count):
            executor = suitable_executors[i % len(suitable_executors)]
            
            # Проверяем, нет ли уже назначения
            existing_assignment = db.query(ShiftAssignment).filter(
                ShiftAssignment.shift_id == shift.id,
                ShiftAssignment.executor_id == executor.id
            ).first()
            
            if not existing_assignment:
                assignment = ShiftAssignment(
                    shift_id=shift.id,
                    executor_id=executor.id,
                    assigned_at=datetime.now(),
                    status='active' if shift.status in ['planned', 'active'] else 'completed'
                )
                db.add(assignment)
                assignments.append(assignment)
    
    db.commit()
    print(f"✅ Создано {len(assignments)} назначений на смены")
    return assignments

def create_shift_schedules(db, shifts: List[Shift], templates: List[ShiftTemplate]):
    """Создает расписания смен на будущее"""
    
    schedules = []
    now = datetime.now()
    
    # Создаем расписание на следующие 2 недели
    for days_ahead in range(1, 15):
        target_date = (now + timedelta(days=days_ahead)).date()
        weekday = target_date.isoweekday()  # 1=Понедельник, 7=Воскресенье
        
        for template in templates:
            template_days = json.loads(template.days_of_week) if template.days_of_week else []
            
            if weekday in template_days:
                # Проверяем, нет ли уже смены на этот день по этому шаблону
                existing_shift = db.query(Shift).filter(
                    Shift.template_id == template.id,
                    Shift.planned_start_time >= datetime.combine(target_date, datetime.min.time()),
                    Shift.planned_start_time < datetime.combine(target_date + timedelta(days=1), datetime.min.time())
                ).first()
                
                if not existing_shift:
                    start_time = datetime.combine(
                        target_date,
                        datetime.strptime(template.default_start_time, '%H:%M').time()
                    )
                    
                    schedule = ShiftSchedule(
                        template_id=template.id,
                        scheduled_date=target_date,
                        planned_start_time=start_time,
                        planned_end_time=start_time + timedelta(hours=template.default_duration_hours),
                        required_executors=template.min_executors,
                        status='scheduled',
                        auto_created=True
                    )
                    db.add(schedule)
                    schedules.append(schedule)
    
    db.commit()
    print(f"✅ Создано {len(schedules)} расписаний смен")
    return schedules

def main():
    """Основная функция создания тестовых данных"""
    
    print("🚀 Начинаю создание тестовых данных для системы смен...")
    
    db = SessionLocal()
    try:
        # 1. Создаем пользователей
        print("\n📱 Создание тестовых пользователей...")
        users = create_test_users(db)
        
        # 2. Создаем шаблоны смен
        print("\n📋 Создание шаблонов смен...")
        templates = create_shift_templates(db)
        
        # 3. Создаем смены
        print("\n⏰ Создание тестовых смен...")
        shifts = create_test_shifts(db, users['executors'], users['managers'], templates)
        
        # 4. Создаем назначения
        print("\n👥 Создание назначений исполнителей...")
        assignments = create_shift_assignments(db, shifts, users['executors'])
        
        # 5. Создаем расписания
        print("\n📅 Создание расписаний смен...")
        schedules = create_shift_schedules(db, shifts, templates)
        
        print("\n✅ Тестовые данные успешно созданы!")
        print(f"   • Пользователи: {len(users['executors']) + len(users['managers'])}")
        print(f"   • Шаблоны смен: {len(templates)}")
        print(f"   • Смены: {len(shifts)}")
        print(f"   • Назначения: {len(assignments)}")
        print(f"   • Расписания: {len(schedules)}")
        
        print("\n🎯 Рекомендации для тестирования:")
        print("   • Используйте telegram_id 1001-1005 для исполнителей")
        print("   • Используйте telegram_id 2001-2002 для менеджеров")
        print("   • Проверьте команды /shifts и /my_shifts")
        print("   • Тестируйте разные роли через переключение")
        
    except Exception as e:
        print(f"❌ Ошибка при создании тестовых данных: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()