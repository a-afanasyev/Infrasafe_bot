"""
Простые тесты для AUTH P3 - Панель управления пользователями

Тестирует основную логику без SQLAlchemy ORM для избежания конфликтов метаданных
"""

import sys
sys.path.append('uk_management_bot')

def test_specialization_service_logic():
    """Тест логики SpecializationService без базы данных"""
    print("1️⃣ Тест логики специализаций...")
    
    from uk_management_bot.services.specialization_service import SpecializationService
    
    # Тестируем доступные специализации
    available = SpecializationService.AVAILABLE_SPECIALIZATIONS
    assert isinstance(available, list)
    assert len(available) > 0
    assert "plumber" in available
    assert "electrician" in available
    
    # Создаем mock service для тестирования логики
    class MockDB:
        pass
    
    service = SpecializationService(MockDB())
    
    # Тест валидации специализаций
    assert service.validate_specialization("plumber") == True
    assert service.validate_specialization("invalid_spec") == False
    
    # Тест валидации списка специализаций
    test_specs = ["plumber", "electrician", "invalid", "hvac", ""]
    valid_specs = service.validate_specializations(test_specs)
    
    assert "plumber" in valid_specs
    assert "electrician" in valid_specs
    assert "hvac" in valid_specs
    assert "invalid" not in valid_specs
    assert "" not in valid_specs
    
    print("✅ Логика специализаций работает корректно")


def test_user_management_service_logic():
    """Тест логики UserManagementService"""
    print("2️⃣ Тест логики управления пользователями...")
    
    from uk_management_bot.services.user_management_service import UserManagementService
    
    # Mock пользователь для тестирования форматирования
    class MockUser:
        def __init__(self):
            self.id = 1
            self.telegram_id = 123456789
            self.first_name = "John"
            self.last_name = "Doe"
            self.username = "johndoe"
            self.status = "approved"
            self.roles = '["executor", "applicant"]'
            self.active_role = "executor"
            self.phone = "+998901234567"
            self.specialization = "plumber,electrician"
    
    class MockDB:
        pass
    
    service = UserManagementService(MockDB())
    user = MockUser()
    
    # Тест определения сотрудника
    assert service.is_user_staff(user) == True
    
    # Тест получения списка ролей
    roles = service.get_user_role_list(user)
    assert "executor" in roles
    assert "applicant" in roles
    assert len(roles) == 2
    
    print("✅ Логика управления пользователями работает корректно")


def test_keyboards():
    """Тест генерации клавиатур"""
    print("3️⃣ Тест генерации клавиатур...")
    
    from uk_management_bot.keyboards.user_management import (
        get_user_management_main_keyboard,
        get_specializations_selection_keyboard,
        get_roles_management_keyboard
    )
    
    # Тест главной клавиатуры
    stats = {
        'pending': 5,
        'approved': 10,
        'blocked': 2,
        'staff': 8,
        'total': 17
    }
    
    main_keyboard = get_user_management_main_keyboard(stats, 'ru')
    assert main_keyboard is not None
    assert hasattr(main_keyboard, 'inline_keyboard')
    assert len(main_keyboard.inline_keyboard) > 0
    
    # Тест клавиатуры специализаций
    user_specs = ["plumber", "electrician"]
    spec_keyboard = get_specializations_selection_keyboard(user_specs, 'ru')
    assert spec_keyboard is not None
    assert hasattr(spec_keyboard, 'inline_keyboard')
    
    # Тест клавиатуры ролей
    user_roles = ["applicant", "executor"]
    roles_keyboard = get_roles_management_keyboard(user_roles, 'ru')
    assert roles_keyboard is not None
    assert hasattr(roles_keyboard, 'inline_keyboard')
    
    print("✅ Генерация клавиатур работает корректно")


def test_localization():
    """Тест локализации"""
    print("4️⃣ Тест локализации...")
    
    from uk_management_bot.utils.helpers import get_text
    
    # Тест русской локализации
    ru_text = get_text('user_management.main_title', language='ru')
    assert isinstance(ru_text, str)
    assert len(ru_text) > 0
    assert "управления пользователями" in ru_text.lower()
    
    # Тест узбекской локализации
    uz_text = get_text('user_management.main_title', language='uz')
    assert isinstance(uz_text, str)
    assert len(uz_text) > 0
    
    # Тест специализаций
    plumber_ru = get_text('specializations.plumber', language='ru')
    plumber_uz = get_text('specializations.plumber', language='uz')
    
    assert plumber_ru == "Сантехник"
    assert plumber_uz == "Santexnik"
    
    # Тест ролей
    manager_ru = get_text('roles.manager', language='ru')
    manager_uz = get_text('roles.manager', language='uz')
    
    assert manager_ru == "Менеджер"
    assert manager_uz == "Menejer"
    
    print("✅ Локализация работает корректно")


def test_fsm_states():
    """Тест FSM состояний"""
    print("5️⃣ Тест FSM состояний...")
    
    from uk_management_bot.states.user_management import UserManagementStates
    
    # Проверяем что все состояния определены
    assert hasattr(UserManagementStates, 'waiting_for_approval_comment')
    assert hasattr(UserManagementStates, 'waiting_for_block_reason')
    assert hasattr(UserManagementStates, 'waiting_for_unblock_comment')
    assert hasattr(UserManagementStates, 'waiting_for_role_comment')
    assert hasattr(UserManagementStates, 'waiting_for_specialization_comment')
    assert hasattr(UserManagementStates, 'waiting_for_search_query')
    assert hasattr(UserManagementStates, 'selecting_specializations')
    assert hasattr(UserManagementStates, 'selecting_roles')
    assert hasattr(UserManagementStates, 'confirming_action')
    
    print("✅ FSM состояния определены корректно")


def test_pagination_helpers():
    """Тест вспомогательных функций пагинации"""
    print("6️⃣ Тест функций пагинации...")
    
    from uk_management_bot.keyboards.user_management import get_pagination_info
    
    # Тест информации о пагинации
    info = get_pagination_info(page=2, total_pages=5, total_items=47, language='ru')
    assert isinstance(info, str)
    assert "2" in info
    assert "5" in info 
    assert "47" in info
    
    # Тест пустого результата
    empty_info = get_pagination_info(page=1, total_pages=1, total_items=0, language='ru')
    assert isinstance(empty_info, str)
    assert len(empty_info) > 0
    
    print("✅ Функции пагинации работают корректно")


def test_file_structure():
    """Тест структуры файлов"""
    print("7️⃣ Тест структуры файлов...")
    
    import os
    
    # Проверяем что все основные файлы созданы
    files_to_check = [
        'uk_management_bot/services/user_management_service.py',
        'uk_management_bot/services/specialization_service.py',
        'uk_management_bot/keyboards/user_management.py',
        'uk_management_bot/handlers/user_management.py',
        'uk_management_bot/states/user_management.py'
    ]
    
    for file_path in files_to_check:
        assert os.path.exists(file_path), f"Файл {file_path} не найден"
    
    # Проверяем что локализация обновлена
    locales_to_check = [
        'uk_management_bot/config/locales/ru.json',
        'uk_management_bot/config/locales/uz.json'
    ]
    
    for locale_path in locales_to_check:
        assert os.path.exists(locale_path), f"Файл {locale_path} не найден"
        
        # Проверяем что в локализации есть новые ключи
        import json
        with open(locale_path, 'r', encoding='utf-8') as f:
            locale_data = json.load(f)
        
        assert 'user_management' in locale_data
        assert 'moderation' in locale_data
        assert 'specializations' in locale_data
        assert 'pagination' in locale_data
    
    print("✅ Структура файлов корректна")


def test_imports():
    """Тест импортов модулей"""
    print("8️⃣ Тест импортов...")
    
    try:
        # Проверяем импорты сервисов
        from uk_management_bot.services.user_management_service import UserManagementService
        from uk_management_bot.services.specialization_service import SpecializationService
        
        # Проверяем импорты клавиатур
        from uk_management_bot.keyboards.user_management import (
            get_user_management_main_keyboard,
            get_user_list_keyboard,
            get_user_actions_keyboard
        )
        
        # Проверяем импорты состояний
        from uk_management_bot.states.user_management import UserManagementStates
        
        # Проверяем импорты обработчиков
        from uk_management_bot.handlers.user_management import router
        
        print("✅ Все импорты работают корректно")
        
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        return False
    
    return True


def main():
    """Основная функция запуска тестов"""
    print("🧪 ПРОСТЫЕ ТЕСТЫ AUTH P3 (Wave 3) - ПАНЕЛЬ УПРАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯМИ")
    print("=" * 80)
    
    tests = [
        test_file_structure,
        test_imports,
        test_specialization_service_logic,
        test_user_management_service_logic,
        test_keyboards,
        test_localization,
        test_fsm_states,
        test_pagination_helpers,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            result = test()
            if result is False:
                failed += 1
            else:
                passed += 1
        except Exception as e:
            print(f"❌ Ошибка в тесте {test.__name__}: {e}")
            failed += 1
    
    print("\n" + "=" * 80)
    print(f"📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:")
    print(f"✅ Пройдено: {passed}")
    print(f"❌ Провалено: {failed}")
    print(f"📈 Успешность: {passed/(passed+failed)*100:.1f}%")
    
    if failed == 0:
        print("\n🎉 ВСЕ ТЕСТЫ УСПЕШНО ПРОЙДЕНЫ!")
        print("✅ Основная логика работает корректно")
        print("✅ Клавиатуры генерируются корректно") 
        print("✅ Локализация настроена правильно")
        print("✅ FSM состояния определены")
        print("✅ Структура файлов корректна")
        print("✅ Импорты работают")
        print("\n🚀 ПАНЕЛЬ УПРАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯМИ ГОТОВА К ИНТЕГРАЦИИ!")
        return True
    else:
        print(f"\n⚠️ ЕСТЬ ПРОБЛЕМЫ: {failed} тестов провалено")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
