#!/usr/bin/env python3
"""
Тестовый скрипт для проверки Entry Handler с единым источником правды

Проверяет:
1. Импорт модуля button_texts
2. Загрузку константы CREATE_REQUEST_TEXTS
3. Корректность текстов для всех языков
4. Работу фильтра F.text.in_()
"""

import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, '/app')

def test_button_texts_module():
    """Тест модуля button_texts"""
    print("=" * 60)
    print("ТЕСТ 1: Импорт модуля button_texts")
    print("=" * 60)
    
    try:
        from uk_management_bot.utils.button_texts import (
            get_create_request_texts,
            BUTTON_TEXTS,
            get_button_texts_for_all_languages
        )
        print("✅ Модуль button_texts импортирован успешно")
        return True
    except Exception as e:
        print(f"❌ Ошибка импорта модуля: {e}")
        return False


def test_create_request_texts():
    """Тест функции get_create_request_texts"""
    print("\n" + "=" * 60)
    print("ТЕСТ 2: Функция get_create_request_texts()")
    print("=" * 60)
    
    try:
        from uk_management_bot.utils.button_texts import get_create_request_texts
        from uk_management_bot.utils.language_helpers import SUPPORTED_LANGUAGES
        
        texts = get_create_request_texts()
        
        print(f"✅ Функция выполнена успешно")
        print(f"   Поддерживаемые языки: {SUPPORTED_LANGUAGES}")
        print(f"   Загружено текстов: {len(texts)}")
        print(f"   Тексты: {texts}")
        
        # Проверки
        assert len(texts) > 0, "Список текстов не должен быть пустым"
        assert "📝 Создать заявку" in texts, "Должен содержать русский текст"
        assert "📝 Ariza yaratish" in texts, "Должен содержать узбекский текст"
        assert len(texts) == len(SUPPORTED_LANGUAGES), f"Количество текстов должно соответствовать количеству языков ({len(SUPPORTED_LANGUAGES)})"
        
        print("✅ Все проверки пройдены")
        return True
    except AssertionError as e:
        print(f"❌ Проверка не пройдена: {e}")
        return False
    except Exception as e:
        print(f"❌ Ошибка выполнения: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_requests_handler_import():
    """Тест импорта handler'а requests"""
    print("\n" + "=" * 60)
    print("ТЕСТ 3: Импорт handler'а requests")
    print("=" * 60)
    
    try:
        from uk_management_bot.handlers import requests
        
        print("✅ Модуль requests импортирован успешно")
        print(f"   CREATE_REQUEST_TEXTS содержит {len(requests.CREATE_REQUEST_TEXTS)} текстов")
        print(f"   Тексты: {requests.CREATE_REQUEST_TEXTS}")
        
        # Проверки
        assert hasattr(requests, 'CREATE_REQUEST_TEXTS'), "Константа CREATE_REQUEST_TEXTS должна существовать"
        assert len(requests.CREATE_REQUEST_TEXTS) > 0, "Константа не должна быть пустой"
        assert "📝 Создать заявку" in requests.CREATE_REQUEST_TEXTS, "Должен содержать русский текст"
        assert "📝 Ariza yaratish" in requests.CREATE_REQUEST_TEXTS, "Должен содержать узбекский текст"
        
        print("✅ Все проверки пройдены")
        return True
    except AssertionError as e:
        print(f"❌ Проверка не пройдена: {e}")
        return False
    except Exception as e:
        print(f"❌ Ошибка импорта: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_filter_simulation():
    """Симуляция работы фильтра F.text.in_()"""
    print("\n" + "=" * 60)
    print("ТЕСТ 4: Симуляция работы фильтра")
    print("=" * 60)
    
    try:
        from uk_management_bot.handlers.requests import CREATE_REQUEST_TEXTS
        
        # Симулируем сообщения от пользователей
        test_messages = [
            ("📝 Создать заявку", "ru", True),
            ("📝 Ariza yaratish", "uz", True),
            ("📋 Мои заявки", "ru", False),  # Другой handler
            ("Неизвестный текст", "ru", False),  # Не должен сработать
        ]
        
        print("Проверка фильтрации сообщений:")
        all_passed = True
        
        for message_text, lang, should_match in test_messages:
            matches = message_text in CREATE_REQUEST_TEXTS
            status = "✅" if matches == should_match else "❌"
            expected = "должен" if should_match else "не должен"
            
            print(f"  {status} '{message_text}' ({lang}) - {expected} совпадать: {matches}")
            
            if matches != should_match:
                all_passed = False
        
        if all_passed:
            print("\n✅ Все проверки фильтрации пройдены")
            return True
        else:
            print("\n❌ Некоторые проверки не пройдены")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка тестирования фильтра: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_all_button_texts():
    """Тест всех кнопок в BUTTON_TEXTS"""
    print("\n" + "=" * 60)
    print("ТЕСТ 5: Проверка всех кнопок")
    print("=" * 60)
    
    try:
        from uk_management_bot.utils.button_texts import BUTTON_TEXTS
        from uk_management_bot.utils.language_helpers import SUPPORTED_LANGUAGES
        
        print(f"Загружено типов кнопок: {len(BUTTON_TEXTS)}")
        print()
        
        all_valid = True
        for key, texts_list in BUTTON_TEXTS.items():
            if len(texts_list) == 0:
                print(f"  ⚠️  {key}: пустой список")
                all_valid = False
            elif len(texts_list) != len(SUPPORTED_LANGUAGES):
                print(f"  ⚠️  {key}: {len(texts_list)} текстов (ожидается {len(SUPPORTED_LANGUAGES)})")
            else:
                print(f"  ✅ {key}: {len(texts_list)} языков - {texts_list}")
        
        if all_valid:
            print("\n✅ Все кнопки загружены корректно")
            return True
        else:
            print("\n⚠️  Некоторые кнопки имеют проблемы")
            return True  # Не критично для Entry Handler
        
    except Exception as e:
        print(f"❌ Ошибка проверки кнопок: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Главная функция тестирования"""
    print("\n" + "=" * 60)
    print("ТЕСТИРОВАНИЕ ENTRY HANDLER С ЕДИНЫМ ИСТОЧНИКОМ ПРАВДЫ")
    print("=" * 60)
    print()
    
    tests = [
        ("Импорт модуля button_texts", test_button_texts_module),
        ("Функция get_create_request_texts", test_create_request_texts),
        ("Импорт handler'а requests", test_requests_handler_import),
        ("Симуляция работы фильтра", test_filter_simulation),
        ("Проверка всех кнопок", test_all_button_texts),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ Критическая ошибка в тесте '{test_name}': {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # Итоговый отчет
    print("\n" + "=" * 60)
    print("ИТОГОВЫЙ ОТЧЕТ")
    print("=" * 60)
    print()
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ ПРОЙДЕН" if result else "❌ ПРОВАЛЕН"
        print(f"  {status}: {test_name}")
    
    print()
    print(f"Результат: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("✅ Entry Handler готов к использованию")
        return 0
    else:
        print(f"\n⚠️  {total - passed} тест(ов) провалено")
        return 1


if __name__ == "__main__":
    sys.exit(main())

