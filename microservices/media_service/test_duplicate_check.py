#!/usr/bin/env python3
"""
Тестовый скрипт для проверки системы проверки дубликатов файлов
"""

import requests
import json
import sys
import os
from typing import Dict, Any, List
from io import BytesIO

# Конфигурация
API_BASE_URL = "http://localhost:8004"
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

def create_test_file(filename: str, content: str = "Test file content") -> BytesIO:
    """Создает тестовый файл в памяти"""
    return BytesIO(content.encode('utf-8'))

def create_test_image() -> BytesIO:
    """Создает простое тестовое изображение в формате PNG"""
    # Минимальный PNG файл (1x1 пиксель, прозрачный)
    png_data = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # 1x1 image
        0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,  # bit depth, color type, etc.
        0x89, 0x00, 0x00, 0x00, 0x0A, 0x49, 0x44, 0x41,  # IDAT chunk
        0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,  # compressed data
        0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00,  # CRC
        0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,  # IEND chunk
        0x42, 0x60, 0x82
    ])
    return BytesIO(png_data)

def test_duplicate_check_endpoint() -> bool:
    """Тестирует endpoint проверки дубликатов"""
    try:
        # Создаем тестовое изображение
        test_file = create_test_image()
        
        # Подготавливаем данные для запроса
        files = {"file": ("test.png", test_file, "image/png")}
        data = {
            "request_number": "TEST-DUPLICATE-001",
            "category": "request_photo",
            "policy": "strict"
        }
        
        response = requests.post(
            f"{DUPLICATE_CHECK_ENDPOINT}/check",
            files=files,
            data=data,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Проверка дубликатов работает: {result}")
            return True
        else:
            print(f"❌ Ошибка проверки дубликатов: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка тестирования проверки дубликатов: {e}")
        return False

def test_duplicate_upload_scenarios() -> Dict[str, bool]:
    """Тестирует различные сценарии загрузки с проверкой дубликатов"""
    results = {}
    
    try:
        # Создаем тестовое изображение
        test_image = create_test_image()
        
        # Сценарий 1: Первая загрузка файла (должна пройти)
        print("\n📤 Тест 1: Первая загрузка файла...")
        files = {"file": ("duplicate_test.png", BytesIO(test_image.getvalue()), "image/png")}
        data = {
            "request_number": "TEST-DUPLICATE-002",
            "category": "request_photo",
            "description": "First upload test",
            "duplicate_policy": "strict"
        }
        
        response = requests.post(
            f"{DUPLICATE_CHECK_ENDPOINT}/upload",
            files=files,
            data=data,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Первая загрузка успешна: ID {result['media_file_id']}")
            results["first_upload"] = True
        else:
            print(f"❌ Первая загрузка неуспешна: {response.status_code} - {response.text}")
            results["first_upload"] = False
        
        # Сценарий 2: Попытка загрузки того же файла (должна быть отклонена)
        print("\n📤 Тест 2: Попытка загрузки дубликата...")
        files = {"file": ("duplicate_test.png", BytesIO(test_image.getvalue()), "image/png")}
        data = {
            "request_number": "TEST-DUPLICATE-002",
            "category": "request_photo",
            "description": "Duplicate upload test",
            "duplicate_policy": "strict"
        }
        
        response = requests.post(
            f"{DUPLICATE_CHECK_ENDPOINT}/upload",
            files=files,
            data=data,
            timeout=10
        )
        
        if response.status_code == 400:
            result = response.json()
            print(f"✅ Дубликат корректно отклонен: {result['detail']}")
            results["duplicate_rejection"] = True
        else:
            print(f"❌ Дубликат не был отклонен: {response.status_code} - {response.text}")
            results["duplicate_rejection"] = False
        
        # Сценарий 3: Загрузка другого файла для той же заявки и категории (должна пройти)
        print("\n📤 Тест 3: Загрузка другого файла...")
        different_image = create_test_image()  # Создаем другое изображение
        files = {"file": ("different_test.png", BytesIO(different_image.getvalue()), "image/png")}
        data = {
            "request_number": "TEST-DUPLICATE-002",
            "category": "request_photo",
            "description": "Different file upload test",
            "duplicate_policy": "strict"
        }
        
        response = requests.post(
            f"{DUPLICATE_CHECK_ENDPOINT}/upload",
            files=files,
            data=data,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Загрузка другого файла успешна: ID {result['media_file_id']}")
            results["different_file_upload"] = True
        else:
            print(f"❌ Загрузка другого файла неуспешна: {response.status_code} - {response.text}")
            results["different_file_upload"] = False
        
        # Сценарий 4: Тест политики WARNING
        print("\n📤 Тест 4: Политика WARNING...")
        files = {"file": ("duplicate_test.png", BytesIO(test_image.getvalue()), "image/png")}
        data = {
            "request_number": "TEST-DUPLICATE-002",
            "category": "request_photo",
            "description": "Warning policy test",
            "duplicate_policy": "warning"
        }
        
        response = requests.post(
            f"{DUPLICATE_CHECK_ENDPOINT}/upload",
            files=files,
            data=data,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Политика WARNING работает: {result['message']}")
            results["warning_policy"] = True
        else:
            print(f"❌ Политика WARNING не работает: {response.status_code} - {response.text}")
            results["warning_policy"] = False
            
    except Exception as e:
        print(f"❌ Ошибка тестирования сценариев загрузки: {e}")
        results["error"] = str(e)
    
    return results

def test_duplicate_stats() -> bool:
    """Тестирует получение статистики дубликатов"""
    try:
        response = requests.get(f"{DUPLICATE_CHECK_ENDPOINT}/stats", timeout=10)
        
        if response.status_code == 200:
            stats = response.json()
            print(f"✅ Статистика дубликатов получена:")
            print(f"   Всего файлов: {stats['total_files']}")
            print(f"   Уникальных файлов: {stats['unique_files']}")
            print(f"   Потенциальных дубликатов: {stats['potential_duplicates']}")
            print(f"   Процент дубликатов: {stats['duplicate_percentage']}%")
            return True
        else:
            print(f"❌ Ошибка получения статистики: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка тестирования статистики: {e}")
        return False

def test_duplicate_config() -> bool:
    """Тестирует получение и обновление конфигурации дубликатов"""
    try:
        # Получаем текущую конфигурацию
        response = requests.get(f"{DUPLICATE_CHECK_ENDPOINT}/config", timeout=10)
        
        if response.status_code == 200:
            config = response.json()
            print(f"✅ Конфигурация получена:")
            print(f"   Включена: {config['enabled']}")
            print(f"   Политика по умолчанию: {config['default_policy']}")
            print(f"   Алгоритм хеширования: {config['hash_algorithm']}")
            return True
        else:
            print(f"❌ Ошибка получения конфигурации: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка тестирования конфигурации: {e}")
        return False

def test_duplicate_health() -> bool:
    """Тестирует health check системы дубликатов"""
    try:
        response = requests.get(f"{DUPLICATE_CHECK_ENDPOINT}/health", timeout=10)
        
        if response.status_code == 200:
            health = response.json()
            print(f"✅ Health check системы дубликатов:")
            print(f"   Статус: {health['status']}")
            print(f"   Сервис: {health['service']}")
            print(f"   Версия: {health['version']}")
            print(f"   Функции: {health['features']}")
            return True
        else:
            print(f"❌ Ошибка health check: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка тестирования health check: {e}")
        return False

def main():
    """Основная функция тестирования"""
    print("🔍 Тестирование системы проверки дубликатов файлов")
    print("=" * 60)
    
    # 1. Проверка доступности сервиса
    print("\n1. Проверка доступности сервиса:")
    if not test_health_check():
        print("❌ Сервис недоступен, завершение тестирования")
        sys.exit(1)
    
    # 2. Тест health check системы дубликатов
    print("\n2. Health check системы дубликатов:")
    health_ok = test_duplicate_health()
    
    # 3. Тест endpoint проверки дубликатов
    print("\n3. Тест endpoint проверки дубликатов:")
    check_ok = test_duplicate_check_endpoint()
    
    # 4. Тест конфигурации
    print("\n4. Тест конфигурации:")
    config_ok = test_duplicate_config()
    
    # 5. Тест статистики
    print("\n5. Тест статистики дубликатов:")
    stats_ok = test_duplicate_stats()
    
    # 6. Тест сценариев загрузки
    print("\n6. Тест сценариев загрузки с проверкой дубликатов:")
    upload_results = test_duplicate_upload_scenarios()
    
    # Итоговый отчет
    print("\n" + "=" * 60)
    print("📊 ИТОГОВЫЙ ОТЧЕТ:")
    
    total_tests = 0
    passed_tests = 0
    
    # Подсчитываем результаты
    if health_ok:
        passed_tests += 1
    total_tests += 1
    
    if check_ok:
        passed_tests += 1
    total_tests += 1
    
    if config_ok:
        passed_tests += 1
    total_tests += 1
    
    if stats_ok:
        passed_tests += 1
    total_tests += 1
    
    # Результаты сценариев загрузки
    for test_name, result in upload_results.items():
        if test_name != "error":
            total_tests += 1
            if result:
                passed_tests += 1
                print(f"✅ {test_name}: ПРОШЕЛ")
            else:
                print(f"❌ {test_name}: НЕ ПРОШЕЛ")
    
    print(f"\n🎯 Общий результат: {passed_tests}/{total_tests} тестов прошли успешно")
    
    if passed_tests == total_tests:
        print("🎉 ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
        return True
    else:
        print("⚠️ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОШЛИ")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
