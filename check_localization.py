#!/usr/bin/env python3
"""
Скрипт для проверки локализации в проекте

Ищет хардкодированные строки в файлах и проверяет наличие ключей локализации
"""
import os
import re
import json
import logging
from typing import List, Dict, Tuple

# Настройки логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Паттерны для поиска хардкодированных строк
HARDCODED_PATTERNS = [
    r'await message\.answer\("([^"]+)"\)',  # await message.answer("текст")
    r'await callback\.answer\("([^"]+)"\)',  # await callback.answer("текст")
    r'text="([^"]+)"',  # text="текст"
    r'InlineKeyboardButton\([^)]*text="([^"]+)"[^)]*\)',  # InlineKeyboardButton(..., text="текст", ...)
    r'KeyboardButton\([^)]*text="([^"]+)"[^)]*\)',  # KeyboardButton(..., text="текст", ...)
]

# Исключения - строки, которые не нужно локализовать
EXCLUSIONS = [
    "❌ Отмена",  # Кнопка отмены, которая должна быть в локализации
    "🔑 Войти",  # Кнопка входа, которая должна быть в локализации
    "/start",  # Команды
    "/help",
    "/cancel",
]

# Файлы для проверки
FILES_TO_CHECK = [
    "uk_management_bot/handlers",
    "uk_management_bot/keyboards",
    "uk_management_bot/utils",
]

# Ключи, которые должны быть в локализации
REQUIRED_KEYS = [
    "errors.search_error",
    "errors.apartment_not_found",
    "errors.building_not_found",
    "errors.request_not_found",
    "errors.user_not_found",
    "errors.unknown_error",
    "errors.name_empty",
    "errors.last_name_empty",
    "errors.cancelled",
    "shifts.no_active_shifts",
    "shifts.registration_pending",
    "shifts.awaiting_admin_approval",
    "admin.assigned_successfully",
    "admin.assignment_failed",
    "buttons.cancel",
]

def find_hardcoded_strings(file_path: str) -> List[Tuple[int, str]]:
    """
    Ищет хардкодированные строки в файле
    
    Args:
        file_path: Путь к файлу
        
    Returns:
        Список кортежей (номер_строки, строка)
    """
    hardcoded_strings = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        for line_num, line in enumerate(lines, 1):
            for pattern in HARDCODED_PATTERNS:
                matches = re.finditer(pattern, line)
                for match in matches:
                    text = match.group(1)
                    # Проверяем, что текст не в исключениях
                    if text not in EXCLUSIONS:
                        hardcoded_strings.append((line_num, line.strip()))
    except Exception as e:
        logger.error(f"Ошибка при проверке файла {file_path}: {e}")
    
    return hardcoded_strings

def check_localization_keys() -> Dict[str, bool]:
    """
    Проверяет наличие необходимых ключей локализации
    
    Returns:
        Словарь с результатами проверки
    """
    results = {}
    
    # Проверяем русский язык
    ru_path = "uk_management_bot/config/locales/ru.json"
    uz_path = "uk_management_bot/config/locales/uz.json"
    
    try:
        with open(ru_path, 'r', encoding='utf-8') as f:
            ru_data = json.load(f)
        
        with open(uz_path, 'r', encoding='utf-8') as f:
            uz_data = json.load(f)
        
        for key in REQUIRED_KEYS:
            parts = key.split('.')
            current_ru = ru_data
            current_uz = uz_data
            
            # Проверяем вложенные ключи
            for part in parts:
                if part in current_ru:
                    current_ru = current_ru[part]
                else:
                    current_ru = None
                    
                if part in current_uz:
                    current_uz = current_uz[part]
                else:
                    current_uz = None
            
            results[f"{key}_ru"] = current_ru is not None
            results[f"{key}_uz"] = current_uz is not None
            
    except Exception as e:
        logger.error(f"Ошибка при проверке ключей локализации: {e}")
    
    return results

def scan_directory(directory: str) -> Dict[str, List[Tuple[int, str]]]:
    """
    Сканирует директорию в поисках хардкодированных строк
    
    Args:
        directory: Путь к директории
        
    Returns:
        Словарь с результатами проверки
    """
    results = {}
    
    if not os.path.exists(directory):
        logger.warning(f"Директория не существует: {directory}")
        return results
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                hardcoded_strings = find_hardcoded_strings(file_path)
                if hardcoded_strings:
                    results[file_path] = hardcoded_strings
    
    return results

def main():
    """Основная функция скрипта"""
    print("🔍 Проверка локализации в проекте UK Management Bot")
    print("=" * 60)
    
    # Проверяем хардкодированные строки
    print("\n📝 Поиск хардкодированных строк...")
    all_hardcoded = {}
    
    for directory in FILES_TO_CHECK:
        print(f"\n📁 Проверка директории: {directory}")
        results = scan_directory(directory)
        all_hardcoded.update(results)
        
        for file_path, strings in results.items():
            print(f"  📄 {file_path}:")
            for line_num, line in strings:
                print(f"    Строка {line_num}: {line}")
    
    # Проверяем ключи локализации
    print("\n🔑 Проверка ключей локализации...")
    key_results = check_localization_keys()
    
    missing_keys = []
    for key, exists in key_results.items():
        if not exists:
            missing_keys.append(key)
    
    if missing_keys:
        print("  ❌ Отсутствующие ключи:")
        for key in missing_keys:
            print(f"    - {key}")
    else:
        print("  ✅ Все необходимые ключи присутствуют")
    
    # Итоги
    print("\n📊 Итоги:")
    total_hardcoded = sum(len(strings) for strings in all_hardcoded.values())
    print(f"  Найдено хардкодированных строк: {total_hardcoded}")
    print(f"  Отсутствует ключей локализации: {len(missing_keys)}")
    
    if total_hardcoded > 0 or len(missing_keys) > 0:
        print("\n⚠️  Рекомендации:")
        if total_hardcoded > 0:
            print("  - Замените хардкодированные строки на вызовы get_text()")
        if len(missing_keys) > 0:
            print("  - Добавьте отсутствующие ключи в файлы локализации")
        return 1
    else:
        print("\n✅ Локализация в проекте в порядке!")
        return 0

if __name__ == "__main__":
    exit(main())
