#!/usr/bin/env python3
"""
Простой тест для проверки исправления ошибки парсинга callback data для редактирования шаблонов.
"""

def test_callback_data_parsing():
    """Тестируем правильность парсинга callback data"""
    
    # Тестовые callback data для редактирования
    edit_test_cases = [
        # (callback_data, should_match_main_handler, expected_template_id_for_main)
        ("template_edit_1", True, 1),
        ("template_edit_123", True, 123),
        ("template_edit_time_1", False, None),
        ("template_edit_duration_1", False, None),
        ("template_edit_name_1", False, None),
        ("template_edit_description_1", False, None),
        ("template_edit_", False, None),
        ("template_edit_abc", False, None),
    ]
    
    # Тестовые callback data для удаления
    delete_test_cases = [
        # (callback_data, should_match_delete_handler, should_match_confirm_handler, expected_id)
        ("template_delete_1", True, False, 1),
        ("template_delete_123", True, False, 123),
        ("template_delete_confirm_1", False, True, 1),
        ("template_delete_confirm_123", False, True, 123),
        ("template_delete_", False, False, None),
        ("template_delete_abc", False, False, None),
        ("template_delete_confirm_", False, False, None),
        ("template_delete_confirm_abc", False, False, None),
    ]
    
    print("🧪 Тестирование парсинга callback data для шаблонов")
    print("=" * 70)
    
    print("📝 Тестирование РЕДАКТИРОВАНИЯ шаблонов")
    print("-" * 40)
    
    for callback_data, should_match, expected_id in edit_test_cases:
        # Тест основного обработчика (должен матчить только template_edit_{digit})
        main_handler_matches = callback_data.startswith("template_edit_") and callback_data.replace("template_edit_", "").isdigit()
        
        # Тест конкретных обработчиков
        time_handler_matches = callback_data.startswith("template_edit_time_")
        duration_handler_matches = callback_data.startswith("template_edit_duration_")
        name_handler_matches = callback_data.startswith("template_edit_name_")
        description_handler_matches = callback_data.startswith("template_edit_description_")
        
        print(f"📝 Callback: '{callback_data}'")
        print(f"   Основной обработчик: {main_handler_matches} (ожидался: {should_match})")
        print(f"   Время: {time_handler_matches}, Длительность: {duration_handler_matches}")
        print(f"   Название: {name_handler_matches}, Описание: {description_handler_matches}")
        
        # Проверяем корректность
        if main_handler_matches == should_match:
            print(f"   ✅ Основной обработчик работает правильно")
        else:
            print(f"   ❌ Основной обработчик работает неправильно!")
        
        # Проверяем извлечение ID для основного обработчика
        if main_handler_matches and expected_id:
            extracted_id = int(callback_data.replace("template_edit_", ""))
            if extracted_id == expected_id:
                print(f"   ✅ ID правильно извлечен: {extracted_id}")
            else:
                print(f"   ❌ Ошибка извлечения ID: получен {extracted_id}, ожидался {expected_id}")
        
        print()
    
    print("\n🗑️ Тестирование УДАЛЕНИЯ шаблонов")
    print("-" * 40)
    
    for callback_data, should_match_delete, should_match_confirm, expected_id in delete_test_cases:
        # Тест основного обработчика удаления
        delete_handler_matches = (callback_data.startswith("template_delete_") and 
                                not callback_data.startswith("template_delete_confirm_") and 
                                callback_data.replace("template_delete_", "").isdigit())
        
        # Тест обработчика подтверждения удаления  
        confirm_handler_matches = (callback_data.startswith("template_delete_confirm_") and 
                                 callback_data.replace("template_delete_confirm_", "").isdigit())
        
        print(f"🗑️ Callback: '{callback_data}'")
        print(f"   Основное удаление: {delete_handler_matches} (ожидался: {should_match_delete})")
        print(f"   Подтверждение: {confirm_handler_matches} (ожидался: {should_match_confirm})")
        
        # Проверяем корректность
        if delete_handler_matches == should_match_delete and confirm_handler_matches == should_match_confirm:
            print(f"   ✅ Обработчики удаления работают правильно")
        else:
            print(f"   ❌ Обработчики удаления работают неправильно!")
        
        # Проверяем извлечение ID
        if delete_handler_matches and expected_id:
            extracted_id = int(callback_data.replace("template_delete_", ""))
            if extracted_id == expected_id:
                print(f"   ✅ ID правильно извлечен для удаления: {extracted_id}")
            else:
                print(f"   ❌ Ошибка извлечения ID удаления: получен {extracted_id}, ожидался {expected_id}")
        
        if confirm_handler_matches and expected_id:
            extracted_id = int(callback_data.replace("template_delete_confirm_", ""))
            if extracted_id == expected_id:
                print(f"   ✅ ID правильно извлечен для подтверждения: {extracted_id}")
            else:
                print(f"   ❌ Ошибка извлечения ID подтверждения: получен {extracted_id}, ожидался {expected_id}")
        
        print()
    
    print("🎯 Резюме:")
    print("- template_edit_{id} должны обрабатываться основным обработчиком редактирования")
    print("- template_edit_{action}_{id} должны обрабатываться специализированными обработчиками редактирования")
    print("- template_delete_{id} должны обрабатываться основным обработчиком удаления")
    print("- template_delete_confirm_{id} должны обрабатываться обработчиком подтверждения удаления")
    print("- Конфликты между всеми обработчиками должны быть исключены")

if __name__ == "__main__":
    test_callback_data_parsing()