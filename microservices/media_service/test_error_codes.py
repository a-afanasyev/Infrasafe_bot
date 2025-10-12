#!/usr/bin/env python3
"""
Тестовый скрипт для проверки системы кодов ошибок Media Service
"""

import requests
import json
import sys
from typing import Dict, Any

# Конфигурация
API_BASE_URL = "http://localhost:8004"
MEDIA_ENDPOINT = f"{API_BASE_URL}/api/v1/media"
DUPLICATE_CHECK_ENDPOINT = f"{API_BASE_URL}/api/v1/duplicate-check"
HEALTH_ENDPOINT = f"{API_BASE_URL}/api/v1/health"

def test_health_check() -> bool:
    """Проверяет доступность сервиса"""
    try:
        response = requests.get(HEALTH_ENDPOINT, timeout=5)
        if response.status_code == 200:
            print("✅ Сервис доступен")
            return True
        else:
            print(f"❌ Сервис недоступен: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка подключения к сервису: {e}")
        return False

def test_invalid_file_type_error() -> Dict[str, Any]:
    """Тестирует ошибку неподдерживаемого типа файла"""
    try:
        print("\n🧪 Тест 1: Неподдерживаемый тип файла")
        
        # Создаем файл с неподдерживаемым типом
        files = {"file": ("test.txt", b"test content", "text/plain")}
        data = {
            "request_number": "TEST-ERROR-001",
            "category": "request_photo"
        }
        
        response = requests.post(
            f"{MEDIA_ENDPOINT}/upload",
            files=files,
            data=data,
            timeout=10
        )
        
        print(f"Статус ответа: {response.status_code}")
        
        if response.status_code == 400:
            error_data = response.json()
            print(f"✅ Получена ошибка с кодом: {error_data.get('error_code', 'N/A')}")
            print(f"   Сообщение: {error_data.get('message', 'N/A')}")
            print(f"   Описание: {error_data.get('description', 'N/A')}")
            print(f"   Категория: {error_data.get('category', 'N/A')}")
            
            if error_data.get('details'):
                print(f"   Детали: {error_data['details']}")
            
            return {
                "test": "invalid_file_type",
                "success": True,
                "error_code": error_data.get('error_code'),
                "message": error_data.get('message')
            }
        else:
            print(f"❌ Неожиданный статус: {response.status_code}")
            print(f"   Ответ: {response.text}")
            return {
                "test": "invalid_file_type",
                "success": False,
                "error": f"Unexpected status: {response.status_code}"
            }
            
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        return {
            "test": "invalid_file_type",
            "success": False,
            "error": str(e)
        }

def test_file_too_large_error() -> Dict[str, Any]:
    """Тестирует ошибку слишком большого файла"""
    try:
        print("\n🧪 Тест 2: Файл слишком большой")
        
        # Создаем файл большого размера (имитируем)
        large_content = b"x" * 1000000  # 1MB
        files = {"file": ("large_file.jpg", large_content, "image/jpeg")}
        data = {
            "request_number": "TEST-ERROR-002",
            "category": "request_photo"
        }
        
        response = requests.post(
            f"{MEDIA_ENDPOINT}/upload",
            files=files,
            data=data,
            timeout=10
        )
        
        print(f"Статус ответа: {response.status_code}")
        
        if response.status_code == 413:
            error_data = response.json()
            print(f"✅ Получена ошибка с кодом: {error_data.get('error_code', 'N/A')}")
            print(f"   Сообщение: {error_data.get('message', 'N/A')}")
            print(f"   Описание: {error_data.get('description', 'N/A')}")
            print(f"   Категория: {error_data.get('category', 'N/A')}")
            
            if error_data.get('details'):
                print(f"   Детали: {error_data['details']}")
            
            return {
                "test": "file_too_large",
                "success": True,
                "error_code": error_data.get('error_code'),
                "message": error_data.get('message')
            }
        else:
            print(f"❌ Неожиданный статус: {response.status_code}")
            print(f"   Ответ: {response.text}")
            return {
                "test": "file_too_large",
                "success": False,
                "error": f"Unexpected status: {response.status_code}"
            }
            
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        return {
            "test": "file_too_large",
            "success": False,
            "error": str(e)
        }

def test_missing_filename_error() -> Dict[str, Any]:
    """Тестирует ошибку отсутствующего имени файла"""
    try:
        print("\n🧪 Тест 3: Отсутствующее имя файла")
        
        # Создаем запрос без имени файла
        files = {"file": (None, b"test content", "image/jpeg")}
        data = {
            "request_number": "TEST-ERROR-003",
            "category": "request_photo"
        }
        
        response = requests.post(
            f"{MEDIA_ENDPOINT}/upload",
            files=files,
            data=data,
            timeout=10
        )
        
        print(f"Статус ответа: {response.status_code}")
        
        if response.status_code == 422:
            error_data = response.json()
            print(f"✅ Получена ошибка валидации")
            print(f"   Ответ: {json.dumps(error_data, indent=2, ensure_ascii=False)}")
            
            return {
                "test": "missing_filename",
                "success": True,
                "error_code": "VALIDATION_ERROR",
                "message": "Validation error"
            }
        else:
            print(f"❌ Неожиданный статус: {response.status_code}")
            print(f"   Ответ: {response.text}")
            return {
                "test": "missing_filename",
                "success": False,
                "error": f"Unexpected status: {response.status_code}"
            }
            
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        return {
            "test": "missing_filename",
            "success": False,
            "error": str(e)
        }

def test_resource_not_found_error() -> Dict[str, Any]:
    """Тестирует ошибку ресурс не найден"""
    try:
        print("\n🧪 Тест 4: Ресурс не найден")
        
        # Запрашиваем несуществующий медиа-файл
        response = requests.get(
            f"{MEDIA_ENDPOINT}/999999",
            timeout=10
        )
        
        print(f"Статус ответа: {response.status_code}")
        
        if response.status_code == 404:
            error_data = response.json()
            print(f"✅ Получена ошибка с кодом: {error_data.get('error_code', 'N/A')}")
            print(f"   Сообщение: {error_data.get('message', 'N/A')}")
            print(f"   Описание: {error_data.get('description', 'N/A')}")
            print(f"   Категория: {error_data.get('category', 'N/A')}")
            
            return {
                "test": "resource_not_found",
                "success": True,
                "error_code": error_data.get('error_code'),
                "message": error_data.get('message')
            }
        else:
            print(f"❌ Неожиданный статус: {response.status_code}")
            print(f"   Ответ: {response.text}")
            return {
                "test": "resource_not_found",
                "success": False,
                "error": f"Unexpected status: {response.status_code}"
            }
            
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        return {
            "test": "resource_not_found",
            "success": False,
            "error": str(e)
        }

def test_duplicate_check_error() -> Dict[str, Any]:
    """Тестирует ошибку проверки дубликатов"""
    try:
        print("\n🧪 Тест 5: Ошибка проверки дубликатов")
        
        # Создаем запрос с некорректными данными
        files = {"file": ("test.jpg", b"test content", "text/plain")}  # Неправильный MIME тип
        data = {
            "request_number": "TEST-ERROR-004",
            "category": "request_photo"
        }
        
        response = requests.post(
            f"{DUPLICATE_CHECK_ENDPOINT}/check",
            files=files,
            data=data,
            timeout=10
        )
        
        print(f"Статус ответа: {response.status_code}")
        
        if response.status_code in [400, 500]:
            error_data = response.json()
            print(f"✅ Получена ошибка с кодом: {error_data.get('error_code', 'N/A')}")
            print(f"   Сообщение: {error_data.get('message', 'N/A')}")
            print(f"   Описание: {error_data.get('description', 'N/A')}")
            print(f"   Категория: {error_data.get('category', 'N/A')}")
            
            if error_data.get('details'):
                print(f"   Детали: {error_data['details']}")
            
            return {
                "test": "duplicate_check_error",
                "success": True,
                "error_code": error_data.get('error_code'),
                "message": error_data.get('message')
            }
        else:
            print(f"❌ Неожиданный статус: {response.status_code}")
            print(f"   Ответ: {response.text}")
            return {
                "test": "duplicate_check_error",
                "success": False,
                "error": f"Unexpected status: {response.status_code}"
            }
            
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        return {
            "test": "duplicate_check_error",
            "success": False,
            "error": str(e)
        }

def main():
    """Основная функция тестирования"""
    print("🔍 Тестирование системы кодов ошибок Media Service")
    print("=" * 60)
    
    # 1. Проверка доступности сервиса
    print("\n1. Проверка доступности сервиса:")
    if not test_health_check():
        print("❌ Сервис недоступен, завершение тестирования")
        sys.exit(1)
    
    # 2. Тестирование различных типов ошибок
    test_results = []
    
    test_results.append(test_invalid_file_type_error())
    test_results.append(test_file_too_large_error())
    test_results.append(test_missing_filename_error())
    test_results.append(test_resource_not_found_error())
    test_results.append(test_duplicate_check_error())
    
    # Итоговый отчет
    print("\n" + "=" * 60)
    print("📊 ИТОГОВЫЙ ОТЧЕТ:")
    
    successful_tests = 0
    total_tests = len(test_results)
    
    for result in test_results:
        if result["success"]:
            successful_tests += 1
            print(f"✅ {result['test']}: УСПЕШНО")
            if result.get('error_code'):
                print(f"   Код ошибки: {result['error_code']}")
            if result.get('message'):
                print(f"   Сообщение: {result['message']}")
        else:
            print(f"❌ {result['test']}: НЕ УДАЛОСЬ")
            if result.get('error'):
                print(f"   Ошибка: {result['error']}")
    
    print(f"\n🎯 Общий результат: {successful_tests}/{total_tests} тестов прошли успешно")
    
    if successful_tests == total_tests:
        print("🎉 ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
        print("✅ Система кодов ошибок работает корректно")
        return True
    else:
        print("⚠️ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОШЛИ")
        print("❌ Требуется доработка системы кодов ошибок")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
