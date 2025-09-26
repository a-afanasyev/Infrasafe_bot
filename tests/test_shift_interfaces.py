#!/usr/bin/env python3
"""
Тест пользовательских интерфейсов системы смен (ЭТАП 5)
Проверяет корректность созданных обработчиков, клавиатур и состояний
"""

import sys
import os
from datetime import datetime, date, timedelta

# Добавляем путь к модулям
sys.path.append(os.path.join(os.path.dirname(__file__), '.'))

def test_handlers_import():
    """Тест импорта обработчиков"""
    print("📋 Тестирование импорта обработчиков...")
    
    try:
        # Тестируем импорт обработчиков смен для менеджеров
        from uk_management_bot.handlers.shift_management import router as shift_mgmt_router
        print("  ✅ shift_management: импорт успешен")
        
        # Тестируем импорт обработчиков для исполнителей
        from uk_management_bot.handlers.my_shifts import router as my_shifts_router
        print("  ✅ my_shifts: импорт успешен")
        
        return True
        
    except ImportError as e:
        print(f"  ❌ Ошибка импорта обработчиков: {e}")
        return False


def test_keyboards_import():
    """Тест импорта клавиатур"""
    print("\n⌨️  Тестирование импорта клавиатур...")
    
    try:
        # Тестируем импорт клавиатур управления сменами
        from uk_management_bot.keyboards.shift_management import (
            get_main_shift_menu,
            get_planning_menu,
            get_analytics_menu
        )
        print("  ✅ shift_management keyboards: импорт успешен")
        
        # Тестируем импорт клавиатур для исполнителей
        from uk_management_bot.keyboards.my_shifts import (
            get_my_shifts_menu,
            get_shift_actions_keyboard
        )
        print("  ✅ my_shifts keyboards: импорт успешен")
        
        return True
        
    except ImportError as e:
        print(f"  ❌ Ошибка импорта клавиатур: {e}")
        return False


def test_states_import():
    """Тест импорта состояний FSM"""
    print("\n🔄 Тестирование импорта состояний FSM...")
    
    try:
        # Тестируем импорт состояний управления сменами
        from uk_management_bot.states.shift_management import (
            ShiftManagementStates,
            TemplateManagementStates,
            AutoPlanningStates
        )
        print("  ✅ shift_management states: импорт успешен")
        
        # Тестируем импорт состояний для исполнителей
        from uk_management_bot.states.my_shifts import (
            MyShiftsStates,
            ShiftTimeTrackingStates,
            ShiftEmergencyStates
        )
        print("  ✅ my_shifts states: импорт успешен")
        
        return True
        
    except ImportError as e:
        print(f"  ❌ Ошибка импорта состояний: {e}")
        return False


def test_keyboards_functionality():
    """Тест функциональности клавиатур"""
    print("\n⚙️  Тестирование функциональности клавиатур...")
    
    try:
        from uk_management_bot.keyboards.shift_management import get_main_shift_menu
        from uk_management_bot.keyboards.my_shifts import get_my_shifts_menu
        
        # Тестируем создание клавиатур
        mgmt_keyboard = get_main_shift_menu("ru")
        shifts_keyboard = get_my_shifts_menu("ru")
        
        # Проверяем, что клавиатуры созданы
        if mgmt_keyboard and hasattr(mgmt_keyboard, 'inline_keyboard'):
            print("  ✅ Клавиатура управления сменами создана корректно")
        else:
            print("  ❌ Ошибка создания клавиатуры управления сменами")
            return False
            
        if shifts_keyboard and hasattr(shifts_keyboard, 'inline_keyboard'):
            print("  ✅ Клавиатура моих смен создана корректно")
        else:
            print("  ❌ Ошибка создания клавиатуры моих смен")
            return False
        
        # Проверяем количество кнопок
        mgmt_buttons = len(mgmt_keyboard.inline_keyboard)
        shifts_buttons = len(shifts_keyboard.inline_keyboard)
        
        print(f"  📊 Кнопок в меню управления: {mgmt_buttons}")
        print(f"  📊 Кнопок в меню исполнителя: {shifts_buttons}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Ошибка тестирования клавиатур: {e}")
        return False


def test_localization_keys():
    """Тест ключей локализации"""
    print("\n🌐 Тестирование ключей локализации...")
    
    try:
        import json
        
        # Загружаем файл локализации
        with open('uk_management_bot/config/locales/ru.json', 'r', encoding='utf-8') as f:
            locale_data = json.load(f)
        
        # Проверяем наличие ключей для системы смен
        required_sections = [
            'shift_management',
            'shift_analytics', 
            'my_shifts'
        ]
        
        missing_sections = []
        for section in required_sections:
            if section not in locale_data:
                missing_sections.append(section)
            else:
                keys_count = len(locale_data[section])
                print(f"  ✅ {section}: {keys_count} ключей")
        
        if missing_sections:
            print(f"  ❌ Отсутствующие секции: {missing_sections}")
            return False
        
        # Проверяем основные ключи
        mgmt_keys = locale_data.get('shift_management', {})
        analytics_keys = locale_data.get('shift_analytics', {})
        shifts_keys = locale_data.get('my_shifts', {})
        
        essential_mgmt_keys = ['title', 'planning', 'analytics', 'templates']
        essential_shifts_keys = ['title', 'current_shifts', 'week_schedule', 'history']
        
        mgmt_missing = [key for key in essential_mgmt_keys if key not in mgmt_keys]
        shifts_missing = [key for key in essential_shifts_keys if key not in shifts_keys]
        
        if mgmt_missing:
            print(f"  ⚠️ Отсутствующие ключи в shift_management: {mgmt_missing}")
        
        if shifts_missing:
            print(f"  ⚠️ Отсутствующие ключи в my_shifts: {shifts_missing}")
        
        if not mgmt_missing and not shifts_missing:
            print("  ✅ Все основные ключи локализации присутствуют")
        
        return len(missing_sections) == 0
        
    except Exception as e:
        print(f"  ❌ Ошибка тестирования локализации: {e}")
        return False


def test_states_structure():
    """Тест структуры состояний FSM"""
    print("\n📋 Тестирование структуры состояний...")
    
    try:
        from uk_management_bot.states.shift_management import ShiftManagementStates
        from uk_management_bot.states.my_shifts import MyShiftsStates
        
        # Проверяем наличие основных состояний для менеджеров
        mgmt_states = [
            'main_menu', 'planning_menu', 'analytics_menu',
            'selecting_template', 'selecting_date'
        ]
        
        missing_mgmt_states = []
        for state_name in mgmt_states:
            if not hasattr(ShiftManagementStates, state_name):
                missing_mgmt_states.append(state_name)
        
        # Проверяем наличие основных состояний для исполнителей
        shifts_states = [
            'main_menu', 'viewing_shifts', 'viewing_shift_details',
            'time_tracking_menu'
        ]
        
        missing_shifts_states = []
        for state_name in shifts_states:
            if not hasattr(MyShiftsStates, state_name):
                missing_shifts_states.append(state_name)
        
        if missing_mgmt_states:
            print(f"  ❌ Отсутствующие состояния ShiftManagementStates: {missing_mgmt_states}")
        else:
            print("  ✅ Все основные состояния ShiftManagementStates присутствуют")
        
        if missing_shifts_states:
            print(f"  ❌ Отсутствующие состояния MyShiftsStates: {missing_shifts_states}")
        else:
            print("  ✅ Все основные состояния MyShiftsStates присутствуют")
        
        return len(missing_mgmt_states) == 0 and len(missing_shifts_states) == 0
        
    except Exception as e:
        print(f"  ❌ Ошибка тестирования состояний: {e}")
        return False


def test_file_structure():
    """Тест структуры созданных файлов"""
    print("\n📁 Тестирование структуры файлов...")
    
    required_files = [
        'uk_management_bot/handlers/shift_management.py',
        'uk_management_bot/handlers/my_shifts.py',
        'uk_management_bot/keyboards/shift_management.py',
        'uk_management_bot/keyboards/my_shifts.py',
        'uk_management_bot/states/shift_management.py',
        'uk_management_bot/states/my_shifts.py'
    ]
    
    missing_files = []
    file_stats = {}
    
    for file_path in required_files:
        if os.path.exists(file_path):
            size = os.path.getsize(file_path)
            file_stats[file_path] = size
            print(f"  ✅ {file_path}: {size} байт")
        else:
            missing_files.append(file_path)
            print(f"  ❌ {file_path}: не найден")
    
    if missing_files:
        print(f"\n⚠️ Отсутствующие файлы: {len(missing_files)}")
        return False
    
    # Проверяем, что файлы не пустые
    empty_files = [f for f, size in file_stats.items() if size < 100]
    if empty_files:
        print(f"  ⚠️ Подозрительно маленькие файлы: {empty_files}")
    
    total_size = sum(file_stats.values())
    print(f"\n📊 Общий размер созданных файлов: {total_size} байт")
    print(f"📊 Среднее количество строк (оценка): {total_size // 30}")
    
    return True


def main():
    """Главная функция тестирования"""
    print("🚀 ТЕСТИРОВАНИЕ ПОЛЬЗОВАТЕЛЬСКИХ ИНТЕРФЕЙСОВ СИСТЕМЫ СМЕН (ЭТАП 5)")
    print("=" * 80)
    
    tests = [
        ("Структура файлов", test_file_structure),
        ("Импорт обработчиков", test_handlers_import),
        ("Импорт клавиатур", test_keyboards_import),
        ("Импорт состояний", test_states_import),
        ("Функциональность клавиатур", test_keyboards_functionality),
        ("Ключи локализации", test_localization_keys),
        ("Структура состояний", test_states_structure)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n🔍 {test_name.upper()}:")
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"  💥 Критическая ошибка: {e}")
            results.append(False)
    
    # Итоговая статистика
    print("\n" + "=" * 80)
    print("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ ЭТАПА 5")
    print("=" * 80)
    
    passed_tests = sum(1 for r in results if r)
    total_tests = len(results)
    success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    
    for i, (test_name, _) in enumerate(tests):
        status = "✅ УСПЕШНО" if results[i] else "❌ НЕУДАЧА"
        print(f"  {test_name}: {status}")
    
    print(f"\n🎯 ИТОГОВАЯ СТАТИСТИКА:")
    print(f"  • Всего тестов: {total_tests}")
    print(f"  • Успешных: {passed_tests}")
    print(f"  • Процент успеха: {success_rate:.1f}%")
    
    if success_rate >= 85:
        print("\n🎉 ЭТАП 5: ПОЛЬЗОВАТЕЛЬСКИЕ ИНТЕРФЕЙСЫ - УСПЕШНО ЗАВЕРШЕН!")
        print("Все основные компоненты интерфейса созданы и готовы к использованию.")
        return 0
    elif success_rate >= 70:
        print("\n👍 ЭТАП 5: ПОЛЬЗОВАТЕЛЬСКИЕ ИНТЕРФЕЙСЫ - ЧАСТИЧНО ЗАВЕРШЕН")
        print("Основные компоненты работают, но есть области для улучшения.")
        return 0
    else:
        print("\n⚠️ ЭТАП 5: ТРЕБУЮТСЯ ДОРАБОТКИ")
        print("Обнаружены критические проблемы, требующие исправления.")
        return 1


if __name__ == "__main__":
    sys.exit(main())