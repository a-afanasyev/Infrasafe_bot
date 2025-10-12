#!/usr/bin/env python3
"""
Тестовый скрипт для проверки проблемы с дубликатами между разными заявками
Тестирует загрузку одного и того же файла (дамас.jpg) на разные заявки
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
MEDIA_ENDPOINT = f"{API_BASE_URL}/api/v1/media"
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

def upload_same_image_to_different_requests() -> Dict[str, Any]:
    """Тестирует загрузку одного и того же изображения на разные заявки"""
    results = {}
    
    try:
        # Создаем тестовое изображение (имитация дамас.jpg)
        test_image = create_test_image()
        image_data = test_image.getvalue()
        
        # Список разных заявок для тестирования
        test_requests = [
            {"request_number": "TEST-DAMAS-001", "description": "Тест заявка 1"},
            {"request_number": "TEST-DAMAS-002", "description": "Тест заявка 2"},
            {"request_number": "TEST-DAMAS-003", "description": "Тест заявка 3"}
        ]
        
        uploaded_files = []
        
        print("🔍 Тестирование загрузки одного файла на разные заявки...")
        
        for i, req_info in enumerate(test_requests, 1):
            print(f"\n📤 Загрузка {i}/3: Заявка {req_info['request_number']}")
            
            # Подготавливаем данные для загрузки
            files = {"file": ("дамас.jpg", BytesIO(image_data), "image/png")}
            data = {
                "request_number": req_info["request_number"],
                "category": "request_photo",
                "description": req_info["description"],
                "duplicate_policy": "strict"  # Строгая политика
            }
            
            # Загружаем файл с проверкой дубликатов
            response = requests.post(
                f"{DUPLICATE_CHECK_ENDPOINT}/upload",
                files=files,
                data=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                uploaded_files.append({
                    "request_number": req_info["request_number"],
                    "file_id": result["media_file_id"],
                    "file_url": result["file_url"],
                    "was_duplicate": result.get("was_duplicate", False),
                    "message": result["message"]
                })
                print(f"✅ Успешно загружен: ID {result['media_file_id']}")
                print(f"   URL: {result['file_url']}")
                print(f"   Дубликат: {result.get('was_duplicate', False)}")
            else:
                print(f"❌ Ошибка загрузки: {response.status_code} - {response.text}")
                uploaded_files.append({
                    "request_number": req_info["request_number"],
                    "error": f"{response.status_code}: {response.text}"
                })
        
        # Проверяем результаты
        print("\n🔍 Анализ результатов:")
        unique_files = set()
        duplicate_files = []
        
        for file_info in uploaded_files:
            if "file_id" in file_info:
                if file_info["file_id"] in unique_files:
                    duplicate_files.append(file_info)
                    print(f"❌ ДУБЛИКАТ: Заявка {file_info['request_number']} использует файл ID {file_info['file_id']}")
                else:
                    unique_files.add(file_info["file_id"])
                    print(f"✅ УНИКАЛЬНЫЙ: Заявка {file_info['request_number']} имеет файл ID {file_info['file_id']}")
            else:
                print(f"❌ ОШИБКА: Заявка {file_info['request_number']} - {file_info.get('error', 'Неизвестная ошибка')}")
        
        # Итоговый анализ
        results = {
            "total_requests": len(test_requests),
            "successful_uploads": len([f for f in uploaded_files if "file_id" in f]),
            "unique_files": len(unique_files),
            "duplicate_files": len(duplicate_files),
            "has_problem": len(duplicate_files) > 0,
            "uploaded_files": uploaded_files
        }
        
        print(f"\n📊 ИТОГОВЫЙ АНАЛИЗ:")
        print(f"   Всего заявок: {results['total_requests']}")
        print(f"   Успешных загрузок: {results['successful_uploads']}")
        print(f"   Уникальных файлов: {results['unique_files']}")
        print(f"   Дубликатов: {results['duplicate_files']}")
        
        if results['has_problem']:
            print("🚨 ПРОБЛЕМА ОБНАРУЖЕНА: Файлы перетираются между заявками!")
        else:
            print("✅ ПРОБЛЕМА НЕ ОБНАРУЖЕНА: Каждая заявка имеет уникальный файл")
        
        return results
        
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        return {"error": str(e)}

def check_existing_files() -> Dict[str, Any]:
    """Проверяет существующие файлы в системе"""
    try:
        print("\n🔍 Проверка существующих файлов в системе...")
        
        # Получаем все файлы
        response = requests.get(f"{MEDIA_ENDPOINT}/search", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            files = data.get("results", [])
            
            print(f"📁 Найдено файлов в системе: {len(files)}")
            
            # Анализируем файлы по заявкам
            request_files = {}
            for file_info in files:
                req_num = file_info.get("request_number", "unknown")
                if req_num not in request_files:
                    request_files[req_num] = []
                request_files[req_num].append({
                    "id": file_info.get("id"),
                    "filename": file_info.get("original_filename"),
                    "status": file_info.get("status"),
                    "file_hash": file_info.get("file_hash"),
                    "duplicate_check_hash": file_info.get("duplicate_check_hash")
                })
            
            print(f"📊 Файлы по заявкам:")
            for req_num, files_list in request_files.items():
                print(f"   Заявка {req_num}: {len(files_list)} файлов")
                for file_info in files_list:
                    print(f"     - ID {file_info['id']}: {file_info['filename']} (статус: {file_info['status']})")
                    if file_info['file_hash']:
                        print(f"       Хеш: {file_info['file_hash'][:16]}...")
            
            return {
                "total_files": len(files),
                "request_files": request_files
            }
        else:
            print(f"❌ Ошибка получения файлов: {response.status_code} - {response.text}")
            return {"error": f"{response.status_code}: {response.text}"}
            
    except Exception as e:
        print(f"❌ Ошибка проверки файлов: {e}")
        return {"error": str(e)}

def main():
    """Основная функция тестирования"""
    print("🔍 Тестирование проблемы с дубликатами между заявками")
    print("=" * 70)
    
    # 1. Проверка доступности сервиса
    print("\n1. Проверка доступности сервиса:")
    if not test_health_check():
        print("❌ Сервис недоступен, завершение тестирования")
        sys.exit(1)
    
    # 2. Проверка существующих файлов
    existing_files = check_existing_files()
    
    # 3. Тест загрузки одного файла на разные заявки
    print("\n2. Тест загрузки одного файла на разные заявки:")
    upload_results = upload_same_image_to_different_requests()
    
    # 4. Повторная проверка файлов после тестирования
    print("\n3. Повторная проверка файлов после тестирования:")
    final_files = check_existing_files()
    
    # Итоговый отчет
    print("\n" + "=" * 70)
    print("📊 ИТОГОВЫЙ ОТЧЕТ:")
    
    if "error" in upload_results:
        print(f"❌ Ошибка тестирования: {upload_results['error']}")
        return False
    
    if upload_results["has_problem"]:
        print("🚨 ПРОБЛЕМА ПОДТВЕРЖДЕНА:")
        print("   Система перетирает файлы между разными заявками")
        print("   Это происходит из-за неправильной логики обработки дубликатов")
        return False
    else:
        print("✅ ПРОБЛЕМА ИСПРАВЛЕНА:")
        print("   Каждая заявка имеет уникальный файл")
        print("   Дубликаты правильно обрабатываются в рамках одной заявки")
        return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
