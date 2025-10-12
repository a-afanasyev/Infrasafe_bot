#!/usr/bin/env python3
"""
Тестовый скрипт для проверки функциональности поиска в Media Service
Проверяет API поиска и веб-интерфейс
"""

import requests
import json
import sys
from typing import Dict, Any, List

# Конфигурация
API_BASE_URL = "http://localhost:8004"
SEARCH_ENDPOINT = f"{API_BASE_URL}/api/v1/media/search"
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

def test_search_all() -> Dict[str, Any]:
    """Тестирует поиск всех файлов"""
    try:
        response = requests.get(SEARCH_ENDPOINT, timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Поиск всех файлов: найдено {data.get('total_count', 0)} файлов")
            return data
        else:
            print(f"❌ Ошибка поиска всех файлов: {response.status_code}")
            return {}
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка запроса поиска всех файлов: {e}")
        return {}

def test_search_by_request_number(request_number: str) -> List[Dict[str, Any]]:
    """Тестирует поиск по номеру заявки"""
    try:
        params = {"request_number": request_number}
        response = requests.get(SEARCH_ENDPOINT, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            
            # Фильтруем только файлы с нужным номером заявки
            filtered_results = [r for r in results if r.get('request_number') == request_number]
            
            print(f"✅ Поиск по заявке '{request_number}': найдено {len(filtered_results)} файлов")
            
            for file_info in filtered_results:
                print(f"   📁 {file_info.get('original_filename', 'Unknown')} "
                      f"(ID: {file_info.get('id')}, Категория: {file_info.get('category')})")
            
            return filtered_results
        else:
            print(f"❌ Ошибка поиска по заявке '{request_number}': {response.status_code}")
            return []
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка запроса поиска по заявке: {e}")
        return []

def test_search_by_category(category: str) -> List[Dict[str, Any]]:
    """Тестирует поиск по категории"""
    try:
        params = {"categories": category}
        response = requests.get(SEARCH_ENDPOINT, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            
            print(f"✅ Поиск по категории '{category}': найдено {len(results)} файлов")
            return results
        else:
            print(f"❌ Ошибка поиска по категории '{category}': {response.status_code}")
            return []
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка запроса поиска по категории: {e}")
        return []

def test_search_by_tags(tags: str) -> List[Dict[str, Any]]:
    """Тестирует поиск по тегам"""
    try:
        params = {"tags": tags}
        response = requests.get(SEARCH_ENDPOINT, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            
            print(f"✅ Поиск по тегам '{tags}': найдено {len(results)} файлов")
            return results
        else:
            print(f"❌ Ошибка поиска по тегам '{tags}': {response.status_code}")
            return []
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка запроса поиска по тегам: {e}")
        return []

def test_web_interface_accessibility() -> bool:
    """Проверяет доступность веб-интерфейса"""
    try:
        # Проверяем, что статические файлы доступны
        response = requests.get(f"{API_BASE_URL}/test_interface.html", timeout=5)
        if response.status_code == 200:
            print("✅ Веб-интерфейс доступен")
            return True
        else:
            print(f"❌ Веб-интерфейс недоступен: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка доступа к веб-интерфейсу: {e}")
        return False

def analyze_search_results(results: List[Dict[str, Any]]) -> None:
    """Анализирует результаты поиска"""
    if not results:
        print("📊 Анализ: Результаты поиска пусты")
        return
    
    # Статистика по категориям
    categories = {}
    file_types = {}
    request_numbers = {}
    
    for file_info in results:
        # Категории
        category = file_info.get('category', 'Unknown')
        categories[category] = categories.get(category, 0) + 1
        
        # Типы файлов
        file_type = file_info.get('file_type', 'Unknown')
        file_types[file_type] = file_types.get(file_type, 0) + 1
        
        # Номера заявок
        req_num = file_info.get('request_number', 'Unknown')
        request_numbers[req_num] = request_numbers.get(req_num, 0) + 1
    
    print("\n📊 Анализ результатов поиска:")
    print(f"   Категории: {dict(categories)}")
    print(f"   Типы файлов: {dict(file_types)}")
    print(f"   Номера заявок: {dict(request_numbers)}")

def main():
    """Основная функция тестирования"""
    print("🔍 Тестирование функциональности поиска Media Service")
    print("=" * 60)
    
    # 1. Проверка доступности сервиса
    print("\n1. Проверка доступности сервиса:")
    if not test_health_check():
        print("❌ Сервис недоступен, завершение тестирования")
        sys.exit(1)
    
    # 2. Проверка веб-интерфейса
    print("\n2. Проверка веб-интерфейса:")
    test_web_interface_accessibility()
    
    # 3. Поиск всех файлов
    print("\n3. Поиск всех файлов:")
    all_files = test_search_all()
    analyze_search_results(all_files.get('results', []))
    
    # 4. Поиск по конкретным номерам заявок
    print("\n4. Поиск по номерам заявок:")
    test_request_numbers = ["TEST-001", "251006-001", "280925-001", "200925-001"]
    
    for req_num in test_request_numbers:
        results = test_search_by_request_number(req_num)
        if results:
            analyze_search_results(results)
    
    # 5. Поиск по категориям
    print("\n5. Поиск по категориям:")
    test_categories = ["request_photo", "completion_photo"]
    
    for category in test_categories:
        results = test_search_by_category(category)
        if results:
            analyze_search_results(results)
    
    # 6. Поиск по тегам
    print("\n6. Поиск по тегам:")
    test_tags = ["emergency", "string"]
    
    for tag in test_tags:
        results = test_search_by_tags(tag)
        if results:
            analyze_search_results(results)
    
    print("\n" + "=" * 60)
    print("✅ Тестирование завершено!")

if __name__ == "__main__":
    main()
